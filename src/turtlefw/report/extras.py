"""Render supplemental Tushare fundamentals for report and data pack.

The same string is inserted into both documents.  That is deliberate: the
numeric audit requires every report number to be traceable to a source file,
and the data pack is one of those sources.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from .format import _m, _num, _pct, _table


def _d(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return value if isinstance(value, Decimal) else Decimal(str(value))
    except Exception:  # noqa: BLE001 - display fallback
        return None


def _date(value: Any) -> str:
    text = str(value or "").strip()
    return text or "—"


def _text(value: Any, limit: int = 0) -> str:
    text = str(value or "").strip()
    if not text:
        return "—"
    return text[:limit] + "…" if limit and len(text) > limit else text


def _money(value: Any) -> str:
    amount = _d(value)
    return _m(amount) if amount is not None else "—"


def _count(value: Any) -> str:
    amount = _d(value)
    return _num(amount, 0) if amount is not None else "—"


def _indicator_section(rows: Sequence[Mapping[str, Any]]) -> str:
    if not rows:
        return "### 财务指标（Tushare）\n\n未取得 `fina_indicator` 数据。"
    body = _table(
        ["报告期", "ROE", "毛利率", "净利率", "资产负债率", "OCF/营收", "EPS", "BPS"],
        [
            [
                _date(row.get("period_end")),
                _pct(_d(row.get("roe"))),
                _pct(_d(row.get("gross_margin"))),
                _pct(_d(row.get("net_margin"))),
                _pct(_d(row.get("debt_ratio"))),
                _pct(_d(row.get("ocf_to_revenue"))),
                _num(_d(row.get("eps"))),
                _num(_d(row.get("bps"))),
            ]
            for row in rows
        ],
        ["l", "r", "r", "r", "r", "r", "r", "r"],
    )
    return (
        "### 财务指标（Tushare）\n\n"
        + body
        + "\n\n> 供应商口径，未并入审计报表；季度/中报指标未年化。"
    )


def _forecast_section(
    forecasts: Sequence[Mapping[str, Any]],
    express: Sequence[Mapping[str, Any]],
    disclosures: Sequence[Mapping[str, Any]],
) -> str:
    parts = ["### 业绩预告 / 快报 / 披露日期"]
    if forecasts:
        parts.append(
            _table(
                ["报告期", "类型", "归母净利下限", "归母净利上限", "变动下限", "变动上限"],
                [
                    [
                        _date(row.get("period_end")),
                        _text(row.get("type")),
                        _money(row.get("net_profit_min")),
                        _money(row.get("net_profit_max")),
                        _pct(_d(row.get("p_change_min"))),
                        _pct(_d(row.get("p_change_max"))),
                    ]
                    for row in forecasts
                ],
                ["l", "l", "r", "r", "r", "r"],
            )
        )
        reasons = [
            f"- {_date(row.get('period_end'))}：{_text(row.get('reason'), 160)}"
            for row in forecasts
            if str(row.get("reason") or "").strip()
        ]
        if reasons:
            parts.append("**变动原因（原文摘录）**\n\n" + "\n".join(reasons[:3]))
    else:
        parts.append("业绩预告：未取得。")

    if express:
        parts.append(
            "**业绩快报**\n\n"
            + _table(
                ["报告期", "营业收入", "归母净利", "总资产", "ROE"],
                [
                    [
                        _date(row.get("period_end")),
                        _money(row.get("revenue")),
                        _money(row.get("net_income")),
                        _money(row.get("total_assets")),
                        _pct(_d(row.get("roe"))),
                    ]
                    for row in express
                ],
                ["l", "r", "r", "r", "r"],
            )
        )
    else:
        parts.append("业绩快报：未取得（可能尚未披露）。")

    if disclosures:
        parts.append(
            "**预约披露**\n\n"
            + _table(
                ["报告期", "预约日期", "实际日期", "修改日期"],
                [
                    [
                        _date(row.get("period_end")),
                        _date(row.get("pre_date")),
                        _date(row.get("actual_date")),
                        _date(row.get("modify_date")),
                    ]
                    for row in disclosures
                ],
                ["l", "l", "l", "l"],
            )
        )
    else:
        parts.append("预约披露：未取得。")
    parts.append(
        "> 预告与快报是未经审计的供应商数据，不覆盖正式报表；"
        "金额单位为百万报告币种。"
    )
    return "\n\n".join(parts)


def _company_section(
    company: Mapping[str, Any],
    managers: Sequence[Mapping[str, Any]],
    rewards: Sequence[Mapping[str, Any]],
) -> str:
    if not company and not managers and not rewards:
        return "### 公司与管理层\n\n未取得 `stock_company` / `stk_managers` 数据。"
    lines = ["### 公司与管理层"]
    if company:
        lines.append(
            "\n".join(
                [
                    f"- 公司名称：{_text(company.get('name'))}",
                    (
                        f"- 董事长 / 总经理：{_text(company.get('chairman'))} / "
                        f"{_text(company.get('manager'))}"
                    ),
                    (
                        f"- 注册地：{_text(company.get('province'))} "
                        f"{_text(company.get('city'))}"
                    ),
                    f"- 员工人数：{_count(company.get('employees'))}",
                    f"- 主营：{_text(company.get('main_business'), 240)}",
                ]
            )
        )
    if managers:
        lines.append(
            "**管理层（按起始日期倒序，最多 10 人）**\n\n"
            + _table(
                ["姓名", "职务", "任职起始", "任职结束"],
                [
                    [
                        _text(row.get("name")),
                        _text(row.get("title")),
                        _date(row.get("beg_date")),
                        _date(row.get("end_date")),
                    ]
                    for row in managers[:10]
                ],
                ["l", "l", "l", "l"],
            )
        )
    if rewards:
        lines.append(
            "**高管薪酬（最近披露，最多 10 条）**\n\n"
            + _table(
                ["公告日", "姓名", "职务", "薪酬（百万元）", "持股"],
                [
                    [
                        _date(row.get("ann_date")),
                        _text(row.get("name")),
                        _text(row.get("title")),
                        _money(row.get("reward")),
                        _count(row.get("hold_vol")),
                    ]
                    for row in rewards[:10]
                ],
                ["l", "l", "l", "r", "r"],
            )
        )
    return "\n\n".join(lines)


def _ownership_section(
    counts: Sequence[Mapping[str, Any]],
    float_holders: Sequence[Mapping[str, Any]],
    trades: Sequence[Mapping[str, Any]],
    share_float: Sequence[Mapping[str, Any]],
) -> str:
    parts = ["### 股东结构"]
    if counts:
        parts.append(
            "**股东户数**\n\n"
            + _table(
                ["报告期", "股东户数"],
                [
                    [_date(row.get("end_date")), _count(row.get("holder_count"))]
                    for row in counts
                ],
                ["l", "r"],
            )
        )
    else:
        parts.append("股东户数：未取得。")

    if float_holders:
        parts.append(
            "**十大流通股东（最新一期）**\n\n"
            + _table(
                ["股东", "持股数量", "持股比例", "占流通比", "本期变动"],
                [
                    [
                        _text(row.get("name"), 28),
                        _count(row.get("hold_amount")),
                        _pct(_d(row.get("hold_ratio"))),
                        _pct(_d(row.get("hold_float_ratio"))),
                        _count(row.get("hold_change")),
                    ]
                    for row in float_holders
                ],
                ["l", "r", "r", "r", "r"],
            )
        )
    else:
        parts.append("十大流通股东：未取得。")

    if trades:
        parts.append(
            "**重要股东增减持（最近 8 条）**\n\n"
            + _table(
                ["公告日", "股东", "方向", "变动数量", "变动比例", "均价"],
                [
                    [
                        _date(row.get("ann_date")),
                        _text(row.get("name"), 24),
                        _text(row.get("direction")),
                        _count(row.get("change_vol")),
                        _pct(_d(row.get("change_ratio"))),
                        _num(_d(row.get("avg_price"))),
                    ]
                    for row in trades[:8]
                ],
                ["l", "l", "l", "r", "r", "r"],
            )
        )
    if share_float:
        parts.append(
            "**限售解禁（最近 6 条）**\n\n"
            + _table(
                ["解禁日", "股东", "解禁数量", "解禁比例", "股份类型"],
                [
                    [
                        _date(row.get("float_date")),
                        _text(row.get("holder_name"), 24),
                        _count(row.get("float_share")),
                        _pct(_d(row.get("float_ratio"))),
                        _text(row.get("share_type")),
                    ]
                    for row in share_float[:6]
                ],
                ["l", "l", "r", "r", "l"],
            )
        )
    if not (counts or float_holders or trades or share_float):
        parts.append("股东结构数据未取得。")
    parts.append("> 股东数据来自 Tushare，按最新披露期展示；不替代正式年报。")
    return "\n\n".join(parts)


def _industry_section(industry: Mapping[str, Any]) -> str:
    if not industry:
        return ""
    detail = " / ".join(
        part
        for part in (
            _text(industry.get("level1")),
            _text(industry.get("level2")),
            _text(industry.get("level3")),
        )
        if part and part != "—"
    )
    return (
        "### 行业分类（申万）\n\n"
        f"- 一级：{_text(industry.get('level1'))}\n"
        f"- 二级 / 三级：{_text(industry.get('level2'))} / "
        f"{_text(industry.get('level3'))}\n"
        f"- 分类路径：{detail or '—'}\n"
        "- 来源：`tushare:index_member_all` + `tushare:index_classify`；"
        "分类用于选择行业模板，不改变财务口径。"
    )


def render_extras(extras: Mapping[str, Any] | None) -> str:
    """Return a Markdown section, or ``""`` when no supplemental data exists."""
    if not extras:
        return ""
    indicators = list(extras.get("financial_indicators") or [])
    forecasts = list(extras.get("forecasts") or [])
    express = list(extras.get("express") or [])
    disclosures = list(extras.get("disclosures") or [])
    company = extras.get("company") or {}
    managers = list(extras.get("managers") or [])
    rewards = list(extras.get("rewards") or [])
    industry = extras.get("industry") or {}
    counts = list(extras.get("holder_count") or [])
    float_holders = list(extras.get("float_holders") or [])
    trades = list(extras.get("holder_trades") or [])
    share_float = list(extras.get("share_float") or [])
    if not any(
        (
            indicators,
            forecasts,
            express,
            disclosures,
            company,
            managers,
            rewards,
            industry,
            counts,
            float_holders,
            trades,
            share_float,
        )
    ):
        return ""

    sections = []
    if indicators:
        sections.append(_indicator_section(indicators))
    if forecasts or express or disclosures:
        sections.append(_forecast_section(forecasts, express, disclosures))
    if company or managers or rewards:
        sections.append(_company_section(company, managers, rewards))
    if counts or float_holders or trades or share_float:
        sections.append(_ownership_section(counts, float_holders, trades, share_float))
    if industry:
        sections.append(_industry_section(industry))
    sections = [section for section in sections if section]
    if not sections:
        return ""

    sources = [str(item) for item in extras.get("sources") or [] if str(item)]
    missing = [str(item) for item in extras.get("missing") or [] if str(item)]
    footer = []
    if sources:
        footer.append("数据来源：" + "、".join(f"`{item}`" for item in sources))
    if missing:
        footer.append("未取得：" + "、".join(f"`{item}`" for item in missing))
    footer.append(
        "> 以上为 Tushare 补充基本面，仅用于交叉核对与前瞻提示；"
        "不进入 StatementRow，不改变确定性指标。"
    )
    return "\n\n".join(sections + ["\n\n".join(footer)])
