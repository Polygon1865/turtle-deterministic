"""Normalise market, macro and governance data used by the report.

These figures are background context, not inputs to the deterministic
valuation.  They are kept in a separate payload from statement rows and
supplemental fundamentals so that a stale broker forecast or a daily flow can
never silently change the valuation.

Units are normalised to the project convention:

* money values are stored in the reporting currency's base unit (yuan/HKD/USD);
* vendor amounts quoted in 万元 are multiplied by 10,000;
* ratios quoted in percentage points stay in percentage points.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from decimal import Decimal
from typing import Any

from .normalize import to_decimal


def _text(raw: Any) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    return "" if text.lower() in {"nan", "none", "--"} else text


def _dec(raw: Any) -> Decimal | None:
    return to_decimal(raw)


def _scaled(row: Mapping[str, Any], key: str, factor: str) -> Decimal | None:
    value = _dec(row.get(key))
    return value * Decimal(factor) if value is not None else None


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and _text(value):
            return value
    return None


def _date_text(raw: Any) -> str:
    text = _text(raw)
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text


def _period_text(raw: Any) -> str:
    text = _text(raw)
    if len(text) == 6 and text.isdigit():
        return f"{text[:4]}-{text[4:]}"
    return text


def _sorted(rows: Iterable[Mapping[str, Any]], key: str) -> list[Mapping[str, Any]]:
    items = [row for row in rows if _text(row.get(key))]
    return sorted(items, key=lambda row: _text(row.get(key)), reverse=True)


def _pct_rank(values: Iterable[Decimal | None], latest: Decimal | None) -> Decimal | None:
    valid = [value for value in values if value is not None]
    if not valid or latest is None:
        return None
    below = sum(1 for value in valid if value <= latest)
    return Decimal(below) / Decimal(len(valid)) * Decimal(100)


def normalize_research(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Broker forecasts (``report_rc``); amounts are 万元 in the vendor API."""
    result: list[dict[str, Any]] = []
    for row in _sorted(rows, "report_date")[:8]:
        result.append(
            {
                "report_date": _date_text(row.get("report_date")),
                "org": _text(row.get("org_name")),
                "quarter": _text(row.get("quarter")),
                "revenue": _scaled(row, "op_rt", "10000"),
                "net_profit": _scaled(row, "np", "10000"),
                "eps": _dec(row.get("eps")),
                "pe": _dec(row.get("pe")),
                "dividend_yield": _dec(row.get("rd")),
                "roe": _dec(row.get("roe")),
                "rating": _text(row.get("rating")),
                "source": "tushare:report_rc",
            }
        )
    return result


def normalize_moneyflow(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Daily stock money flow; vendor amounts are 万元."""
    result: list[dict[str, Any]] = []
    for row in _sorted(rows, "trade_date")[:5]:
        buy_large = _scaled(row, "buy_lg_amount", "10000")
        buy_elg = _scaled(row, "buy_elg_amount", "10000")
        sell_large = _scaled(row, "sell_lg_amount", "10000")
        sell_elg = _scaled(row, "sell_elg_amount", "10000")
        main_net = None
        if (
            buy_large is not None
            and buy_elg is not None
            and sell_large is not None
            and sell_elg is not None
        ):
            main_net = buy_large + buy_elg - sell_large - sell_elg
        result.append(
            {
                "trade_date": _date_text(row.get("trade_date")),
                "main_net": main_net,
                "net_amount": _scaled(row, "net_mf_amount", "10000"),
                "source": "tushare:moneyflow",
            }
        )
    return result


def normalize_margin(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Margin financing balances; vendor amounts are already yuan."""
    result: list[dict[str, Any]] = []
    for row in _sorted(rows, "trade_date")[:5]:
        result.append(
            {
                "trade_date": _date_text(row.get("trade_date")),
                "financing_balance": _dec(row.get("rzye")),
                "securities_balance": _dec(row.get("rqye")),
                "total_balance": _dec(row.get("rzrqye")),
                "source": "tushare:margin_detail",
            }
        )
    return result


def normalize_limits(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in _sorted(rows, "trade_date")[:3]:
        result.append(
            {
                "trade_date": _date_text(row.get("trade_date")),
                "up_limit": _dec(row.get("up_limit")),
                "down_limit": _dec(row.get("down_limit")),
                "source": "tushare:stk_limit",
            }
        )
    return result


def normalize_index_valuation(
    rows: Iterable[Mapping[str, Any]], *, index_code: str = "000300.SH"
) -> dict[str, Any] | None:
    """Latest index valuation plus a three-year percentile of PE/PB."""
    ordered = _sorted(rows, "trade_date")
    if not ordered:
        return None
    latest = ordered[0]
    history = ordered[:750]
    pe = _dec(latest.get("pe_ttm"))
    pb = _dec(latest.get("pb"))
    return {
        "index_code": index_code,
        "trade_date": _date_text(latest.get("trade_date")),
        "pe_ttm": pe,
        "pb": pb,
        "pe_percentile": _pct_rank((_dec(row.get("pe_ttm")) for row in history), pe),
        "pb_percentile": _pct_rank((_dec(row.get("pb")) for row in history), pb),
        "samples": len(history),
        "source": "tushare:index_dailybasic",
    }


def normalize_index_weights(
    rows: Iterable[Mapping[str, Any]],
    *,
    names: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Top index constituents by weight; ``weight`` is in percentage points."""
    ordered = sorted(
        (row for row in rows if _dec(row.get("weight")) is not None),
        key=lambda row: _dec(row.get("weight")) or Decimal(0),
        reverse=True,
    )
    return [
        {
            "code": _text(row.get("con_code")),
            "name": _text(row.get("con_name"))
            or str((names or {}).get(_text(row.get("con_code")), "")).strip(),
            "weight": _dec(row.get("weight")),
            "source": "tushare:index_weight",
        }
        for row in ordered[:10]
    ]


def normalize_macro(
    *,
    cpi: Iterable[Mapping[str, Any]] = (),
    ppi: Iterable[Mapping[str, Any]] = (),
    gdp: Iterable[Mapping[str, Any]] = (),
    pmi: Iterable[Mapping[str, Any]] = (),
    shibor: Iterable[Mapping[str, Any]] = (),
    lpr: Iterable[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """One compact macro table with explicit units.

    The latest two observations per indicator are enough for the report; the
    payload is background context and is not used to forecast.
    """
    result: list[dict[str, Any]] = []

    for row in _sorted(cpi, "month")[:2]:
        result.append(
            {
                "indicator": "CPI",
                "period": _period_text(row.get("month")),
                "value": _dec(row.get("nt_val")),
                "yoy": _dec(row.get("nt_yoy")),
                "unit": "指数",
                "source": "tushare:cn_cpi",
            }
        )
    for row in _sorted(ppi, "month")[:2]:
        result.append(
            {
                "indicator": "PPI 同比",
                "period": _period_text(row.get("month")),
                "value": _dec(row.get("ppi_yoy")),
                "yoy": None,
                "unit": "%",
                "source": "tushare:cn_ppi",
            }
        )
    for row in _sorted(gdp, "quarter")[:2]:
        result.append(
            {
                "indicator": "GDP（累计）",
                "period": _text(row.get("quarter")),
                "value": _dec(row.get("gdp")),
                "yoy": _dec(row.get("gdp_yoy")),
                "unit": "亿元",
                "source": "tushare:cn_gdp",
            }
        )
    pmi_key = "pmi010000"
    for row in _sorted(pmi, "month")[:2]:
        value = _dec(row.get(pmi_key))
        if value is None:
            value = _dec(row.get("pmi020100"))
        result.append(
            {
                "indicator": "制造业 PMI" if _dec(row.get(pmi_key)) is not None else "非制造业 PMI",
                "period": _period_text(row.get("month")),
                "value": value,
                "yoy": None,
                "unit": "指数",
                "source": "tushare:cn_pmi",
            }
        )
    for row in _sorted(shibor, "date")[:2]:
        result.append(
            {
                "indicator": "Shibor 3M",
                "period": _date_text(row.get("date")),
                "value": _dec(row.get("3m")),
                "yoy": None,
                "unit": "%",
                "source": "tushare:shibor",
            }
        )
    for row in _sorted(lpr, "date")[:2]:
        result.append(
            {
                "indicator": "LPR 1Y",
                "period": _date_text(row.get("date")),
                "value": _dec(row.get("1y")),
                "yoy": None,
                "unit": "%",
                "source": "tushare:shibor_lpr",
            }
        )
    return result


def normalize_announcements(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in _sorted(rows, "ann_date")[:8]:
        result.append(
            {
                "date": _date_text(row.get("ann_date")),
                "title": _text(row.get("title")),
                "url": _text(row.get("url")),
                "source": "tushare:anns_d",
            }
        )
    return result


def normalize_news(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for row in _sorted(rows, "datetime")[:8]:
        result.append(
            {
                "datetime": _text(row.get("datetime")),
                "title": _text(row.get("title")),
                "source": "tushare:news",
            }
        )
    return result


def normalize_governance(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Institutional holders from Yahoo Finance (HK/US fallback)."""
    result: list[dict[str, Any]] = []
    for row in list(rows)[:10]:
        pct = _dec(_first(row, "pctHeld", "pct", "pct_out", "% Out"))
        if pct is not None and pct <= 1:
            pct *= 100
        as_of = _text(_first(row, "as_of", "date_reported", "Date Reported"))
        result.append(
            {
                "holder": _text(_first(row, "holder", "Holder")),
                "shares": _dec(_first(row, "shares", "Shares")),
                "value": _dec(_first(row, "value", "Value")),
                "pct": pct,
                "as_of": as_of[:10] if as_of else "",
                "source": "yfinance:institutional_holders",
            }
        )
    return [row for row in result if row["holder"]]
