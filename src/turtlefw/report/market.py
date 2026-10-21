"""Render market, macro and governance context for reports.

The section is deliberately descriptive.  None of these values are used by the
factor engine, and the footer says so explicitly.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from .format import _m as _fmt_m
from .format import _num as _fmt_num
from .format import _pct as _fmt_pct
from .format import _table


def _d(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _m(value: Any) -> str:
    return _fmt_m(_d(value))


def _num(value: Any, digits: int = 2) -> str:
    return _fmt_num(_d(value), digits)


def _pct(value: Any) -> str:
    return _fmt_pct(_d(value))


def _major_value(row: Mapping[str, Any]) -> str:
    text = _num(row.get("value"))
    return f"{text}%" if row.get("percent") else text


def _rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    return [dict(row) for row in value if isinstance(row, Mapping)]


def _has(extras: Mapping[str, Any]) -> bool:
    keys = (
        "research",
        "macro",
        "moneyflow",
        "margin",
        "limits",
        "index_valuation",
        "index_weights",
        "announcements",
        "news",
        "governance",
        "major_holders",
    )
    return any(bool(extras.get(key)) for key in keys)


def _research_section(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    table = _table(
        ["报告日", "机构", "预测期", "营收(百万元)", "净利润(百万元)", "EPS", "PE", "评级"],
        [
            [
                str(row.get("report_date", "")),
                str(row.get("org", "")),
                str(row.get("quarter", "")),
                _m(row.get("revenue")),
                _m(row.get("net_profit")),
                _num(row.get("eps")),
                _num(row.get("pe")),
                str(row.get("rating", "")) or "—",
            ]
            for row in rows
        ],
        ["l", "l", "l", "r", "r", "r", "r", "l"],
    )
    return (
        "### 卖方盈利预测（Tushare report_rc）\n\n"
        + table
        + "\n\n> 供应商预测值仅作交叉参考，不进入确定性估值；试用权限每日限 10 次。"
    )


def _macro_value(row: Mapping[str, Any]) -> str:
    value = row.get("value")
    unit = str(row.get("unit", ""))
    if value is None:
        return "—"
    if unit == "%":
        return _pct(value)
    if unit == "亿元":
        return f"{_num(value, 0)} 亿元"
    return _num(value)


def _macro_section(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return ""
    table = _table(
        ["指标", "期间", "数值", "同比"],
        [
            [
                str(row.get("indicator", "")),
                str(row.get("period", "")),
                _macro_value(row),
                _pct(row.get("yoy")) if row.get("yoy") is not None else "—",
            ]
            for row in rows
        ],
        ["l", "l", "r", "r"],
    )
    return "### 宏观（Tushare）\n\n" + table


def _flow_section(
    moneyflow: list[dict[str, Any]],
    margin: list[dict[str, Any]],
    limits: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    if moneyflow:
        parts.append(
            "**个股资金流向（最近 5 日，百万元）**\n\n"
            + _table(
                ["日期", "主力净流入", "净流入"],
                [
                    [
                        str(row.get("trade_date", "")),
                        _m(row.get("main_net")),
                        _m(row.get("net_amount")),
                    ]
                    for row in moneyflow
                ],
                ["l", "r", "r"],
            )
        )
    if margin:
        parts.append(
            "**融资融券（最近 5 日，百万元）**\n\n"
            + _table(
                ["日期", "融资余额", "融券余额", "两融余额"],
                [
                    [
                        str(row.get("trade_date", "")),
                        _m(row.get("financing_balance")),
                        _m(row.get("securities_balance")),
                        _m(row.get("total_balance")),
                    ]
                    for row in margin
                ],
                ["l", "r", "r", "r"],
            )
        )
    if limits:
        parts.append(
            "**涨跌停价格（最近 3 日）**\n\n"
            + _table(
                ["日期", "涨停价", "跌停价"],
                [
                    [
                        str(row.get("trade_date", "")),
                        _num(row.get("up_limit")),
                        _num(row.get("down_limit")),
                    ]
                    for row in limits
                ],
                ["l", "r", "r"],
            )
        )
    return "### 资金面（Tushare）\n\n" + "\n\n".join(parts) if parts else ""


def _index_section(
    valuation: Mapping[str, Any] | None, weights: list[dict[str, Any]]
) -> str:
    parts: list[str] = []
    if valuation:
        parts.append(
            "**沪深300 估值**\n\n"
            + _table(
                ["日期", "PE TTM", "PB", "PE 三年分位", "PB 三年分位", "样本"],
                [
                    [
                        str(valuation.get("trade_date", "")),
                        _num(valuation.get("pe_ttm")),
                        _num(valuation.get("pb")),
                        _pct(valuation.get("pe_percentile")),
                        _pct(valuation.get("pb_percentile")),
                        str(valuation.get("samples", "")),
                    ]
                ],
                ["l", "r", "r", "r", "r", "r"],
            )
        )
    if weights:
        parts.append(
            "**沪深300 前十大权重**\n\n"
            + _table(
                ["代码", "名称", "权重"],
                [
                    [
                        str(row.get("code", "")),
                        str(row.get("name", "")) or "—",
                        _pct(row.get("weight")),
                    ]
                    for row in weights
                ],
                ["l", "l", "r"],
            )
        )
    return "### 指数估值与成分（Tushare）\n\n" + "\n\n".join(parts) if parts else ""


def _news_section(
    announcements: list[dict[str, Any]],
    news: list[dict[str, Any]],
    governance: list[dict[str, Any]],
    major_holders: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    if announcements:
        parts.append(
            "**公司公告**\n\n"
            + _table(
                ["日期", "标题"],
                [
                    [str(row.get("date", "")), str(row.get("title", ""))]
                    for row in announcements
                ],
                ["l", "l"],
            )
        )
    if news:
        parts.append(
            "**新闻快讯**\n\n"
            + _table(
                ["时间", "标题"],
                [
                    [str(row.get("datetime", "")), str(row.get("title", ""))]
                    for row in news
                ],
                ["l", "l"],
            )
        )
    if governance:
        parts.append(
            "**机构股东（Yahoo Finance）**\n\n"
            + _table(
                ["股东", "持股", "占比", "披露日"],
                [
                    [
                        str(row.get("holder", "")),
                        _num(row.get("shares"), 0),
                        _pct(row.get("pct")) if row.get("pct") is not None else "—",
                        str(row.get("as_of", "")),
                    ]
                    for row in governance
                ],
                ["l", "r", "r", "l"],
            )
        )
    if major_holders:
        parts.append(
            "**股东结构（Yahoo Finance）**\n\n"
            + _table(
                ["项目", "数值"],
                [
                    [str(row.get("label", "")), _major_value(row)]
                    for row in major_holders
                ],
                ["l", "r"],
            )
        )
    return "### 公告、新闻与治理\n\n" + "\n\n".join(parts) if parts else ""


def render_market(extras: Mapping[str, Any] | None) -> str:
    """Render a compact market section; empty payload means no section."""
    if not extras or not _has(extras):
        return ""
    research = _rows(extras.get("research"))
    macro = _rows(extras.get("macro"))
    moneyflow = _rows(extras.get("moneyflow"))
    margin = _rows(extras.get("margin"))
    limits = _rows(extras.get("limits"))
    valuation = extras.get("index_valuation")
    if not isinstance(valuation, Mapping):
        valuation = None
    weights = _rows(extras.get("index_weights"))
    announcements = _rows(extras.get("announcements"))
    news = _rows(extras.get("news"))
    governance = _rows(extras.get("governance"))
    major_holders = _rows(extras.get("major_holders"))

    sections = [
        _research_section(research),
        _macro_section(macro),
        _flow_section(moneyflow, margin, limits),
        _index_section(valuation, weights),
        _news_section(announcements, news, governance, major_holders),
    ]
    body = "\n\n".join(section for section in sections if section)
    if not body:
        return ""
    sources = [str(item) for item in extras.get("sources", []) if str(item)]
    missing = [str(item) for item in extras.get("missing", []) if str(item)]
    footer: list[str] = []
    if sources:
        footer.append("来源：" + "、".join(f"`{source}`" for source in sources))
    if missing:
        footer.append("未取得：" + "、".join(missing))
    footer.append("市场数据仅作 vendor context 背景，不进入 StatementRow 或确定性估值。")
    return body + "\n\n" + "\n".join(f"> {line}" for line in footer)


__all__ = ["render_market"]
