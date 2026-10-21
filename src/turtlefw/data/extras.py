"""Normalise non-statement Tushare data used by the report.

The canonical statement rows stay in :mod:`turtlefw.data.normalize`.  This
module only shapes supplemental fundamentals (indicators, forecasts, company
profile, governance, ownership and industry classification) into a stable,
JSON-serialisable payload.

Rules:
* vendor ratios stay in percentage points (``20.5`` means ``20.5%``);
* missing values stay ``None`` and are never zero-filled;
* every payload carries its source endpoint so the report can label it;
* forecasts/express figures are explicitly *not* merged into statement rows.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from decimal import Decimal
from typing import Any

from .normalize import parse_date, to_decimal


def _iso(raw: Any) -> str:
    parsed = parse_date(raw)
    return parsed.isoformat() if parsed is not None else ""


def _text(raw: Any) -> str:
    if raw is None:
        return ""
    text = str(raw).strip()
    return "" if text.lower() in {"nan", "none", "--"} else text


def _dec(raw: Any) -> Decimal | None:
    return to_decimal(raw)


def _first(row: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and _text(value):
            return value
    return None


def _sorted(
    rows: Iterable[Mapping[str, Any]], key: str, *, limit: int | None = None
) -> list[Mapping[str, Any]]:
    items = sorted(rows, key=lambda row: _text(row.get(key)), reverse=True)
    return items[:limit] if limit is not None else items


def normalize_fina_indicator(
    rows: Iterable[Mapping[str, Any]], market: str
) -> list[dict[str, Any]]:
    """A/HK/US indicator rows mapped to one common schema.

    ``market`` selects the vendor-specific column names; the output keys are
    identical so the report does not branch on the listing venue.
    """
    market = market.upper()
    columns = {
        "A": {
            "roe": "roe_waa",
            "gross_margin": "grossprofit_margin",
            "net_margin": "netprofit_margin",
            "debt_ratio": "debt_to_assets",
        },
        "HK": {
            "roe": "roe_avg",
            "gross_margin": "gross_profit_ratio",
            "net_margin": "net_profit_ratio",
            "debt_ratio": "debt_asset_ratio",
        },
        "US": {
            "roe": "roe_avg",
            "gross_margin": "gross_profit_ratio",
            "net_margin": "net_profit_ratio",
            "debt_ratio": "debt_asset_ratio",
        },
    }.get(market, {})
    endpoint = {
        "A": "fina_indicator",
        "HK": "hk_fina_indicator",
        "US": "us_fina_indicator",
    }.get(market, "fina_indicator")
    ocf_key = "ocf_to_or" if market == "A" else ("ocf_sales" if market == "HK" else "")
    by_period: dict[str, dict[str, Any]] = {}
    for row in rows:
        period_end = _iso(row.get("end_date"))
        if not period_end:
            continue
        item: dict[str, Any] = {
            "period_end": period_end,
            "ann_date": _iso(row.get("ann_date")),
            "eps": _dec(_first(row, "eps", "basic_eps")),
            "bps": _dec(row.get("bps")),
            "ocf_to_revenue": _dec(row.get(ocf_key)) if ocf_key else None,
            "source": f"tushare:{endpoint}",
        }
        # A-share ``ocf_to_or`` is a ratio (0.1517); HK ``ocf_sales`` is
        # already in percentage points. Align both to percentage points.
        if market == "A" and item["ocf_to_revenue"] is not None:
            item["ocf_to_revenue"] *= Decimal(100)
        for output_key, vendor_key in columns.items():
            item[output_key] = _dec(row.get(vendor_key))
        previous = by_period.get(period_end)
        if previous is None or item["ann_date"] > previous["ann_date"]:
            by_period[period_end] = item
    result = sorted(by_period.values(), key=lambda item: item["period_end"], reverse=True)
    return result[:8]


def normalize_forecast(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in _sorted(rows, "ann_date", limit=6):
        profit_min = _dec(row.get("net_profit_min"))
        profit_max = _dec(row.get("net_profit_max"))
        item = {
            "period_end": _iso(row.get("end_date")),
            "ann_date": _iso(row.get("ann_date")),
            "type": _text(row.get("type")),
            "p_change_min": _dec(row.get("p_change_min")),
            "p_change_max": _dec(row.get("p_change_max")),
            # Tushare reports forecast profit in 万元; normalise to yuan.
            "net_profit_min": profit_min * Decimal(10000) if profit_min is not None else None,
            "net_profit_max": profit_max * Decimal(10000) if profit_max is not None else None,
            "summary": _text(row.get("summary")),
            "reason": _text(row.get("change_reason")),
            "source": "tushare:forecast",
        }
        if item["period_end"]:
            result.append(item)
    return result


def normalize_express(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in _sorted(rows, "ann_date", limit=4):
        item = {
            "period_end": _iso(row.get("end_date")),
            "ann_date": _iso(row.get("ann_date")),
            "revenue": _dec(row.get("revenue")),
            "net_income": _dec(row.get("n_income")),
            "total_assets": _dec(row.get("total_assets")),
            "equity": _dec(row.get("total_hldr_eqy_exc_min_int")),
            "eps": _dec(_first(row, "eps", "diluted_eps")),
            "roe": _dec(_first(row, "roe", "diluted_roe")),
            "source": "tushare:express",
        }
        if item["period_end"]:
            result.append(item)
    return result


def normalize_disclosures(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in _sorted(rows, "end_date", limit=8):
        item = {
            "period_end": _iso(row.get("end_date")),
            "ann_date": _iso(row.get("ann_date")),
            "pre_date": _iso(row.get("pre_date")),
            "actual_date": _iso(row.get("actual_date")),
            "modify_date": _iso(row.get("modify_date")),
            "source": "tushare:disclosure_date",
        }
        if item["period_end"]:
            result.append(item)
    return result


def normalize_company(row: Mapping[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {}
    return {
        "name": _text(_first(row, "com_name", "name")),
        "chairman": _text(row.get("chairman")),
        "manager": _text(row.get("manager")),
        "secretary": _text(row.get("secretary")),
        "reg_capital": _dec(row.get("reg_capital")),
        "setup_date": _iso(row.get("setup_date")),
        "province": _text(row.get("province")),
        "city": _text(row.get("city")),
        "employees": _dec(row.get("employees")),
        "main_business": _text(row.get("main_business")),
        "website": _text(row.get("website")),
        "source": "tushare:stock_company",
    }


def normalize_managers(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in _sorted(rows, "begin_date", limit=20):
        item = {
            "name": _text(row.get("name")),
            "gender": _text(row.get("gender")),
            "title": _text(row.get("title")),
            "beg_date": _iso(_first(row, "begin_date", "beg_date")),
            "end_date": _iso(row.get("end_date")),
            "source": "tushare:stk_managers",
        }
        if item["name"]:
            result.append(item)
    return result


def normalize_rewards(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in _sorted(rows, "ann_date", limit=20):
        item = {
            "ann_date": _iso(row.get("ann_date")),
            "name": _text(row.get("name")),
            "title": _text(row.get("title")),
            "reward": _dec(row.get("reward")),
            "hold_vol": _dec(row.get("hold_vol")),
            "source": "tushare:stk_rewards",
        }
        if item["name"]:
            result.append(item)
    return result


def normalize_industry(
    membership: Iterable[Mapping[str, Any]], classification: Iterable[Mapping[str, Any]]
) -> dict[str, Any]:
    current = [row for row in membership if _text(row.get("is_new")).upper() in {"Y", "1"}]
    if not current:
        current = list(membership)
    if not current:
        return {}
    row = max(current, key=lambda item: _text(item.get("in_date")))
    names = {
        _text(item.get("index_code")): _text(item.get("industry_name"))
        for item in classification
        if _text(item.get("index_code"))
    }
    level1 = _text(row.get("l1_name")) or names.get(_text(row.get("l1_code")), "")
    level2 = _text(row.get("l2_name"))
    level3 = _text(row.get("l3_name"))
    if not (level1 or level2 or level3):
        return {}
    return {
        "level1_code": _text(row.get("l1_code")),
        "level1": level1,
        "level2": level2,
        "level3": level3,
        "in_date": _iso(row.get("in_date")),
        "source": "tushare:index_member_all",
    }


def _latest_period(rows: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    if not rows:
        return []
    latest = max(_text(row.get("end_date")) for row in rows)
    return [row for row in rows if _text(row.get("end_date")) == latest]


def normalize_float_holders(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    records = _latest_period(list(rows))
    result = []
    for row in sorted(records, key=lambda item: -(_dec(item.get("hold_ratio")) or Decimal(0))):
        item = {
            "end_date": _iso(row.get("end_date")),
            "name": _text(row.get("holder_name")),
            "hold_amount": _dec(row.get("hold_amount")),
            "hold_ratio": _dec(row.get("hold_ratio")),
            "hold_float_ratio": _dec(row.get("hold_float_ratio")),
            "hold_change": _dec(row.get("hold_change")),
            "holder_type": _text(row.get("holder_type")),
            "source": "tushare:top10_floatholders",
        }
        if item["name"]:
            result.append(item)
    return result[:10]


def normalize_holder_count(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in _sorted(rows, "end_date", limit=8):
        item = {
            "end_date": _iso(row.get("end_date")),
            "holder_count": _dec(_first(row, "holder_num", "holder_nums")),
            "source": "tushare:stk_holdernumber",
        }
        if item["end_date"]:
            result.append(item)
    return result


def normalize_holder_trades(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in _sorted(rows, "ann_date", limit=12):
        item = {
            "ann_date": _iso(row.get("ann_date")),
            "name": _text(row.get("holder_name")),
            "holder_type": _text(row.get("holder_type")),
            "direction": _text(row.get("in_de")),
            "change_vol": _dec(row.get("change_vol")),
            "change_ratio": _dec(row.get("change_ratio")),
            "after_share": _dec(row.get("after_share")),
            "after_ratio": _dec(row.get("after_ratio")),
            "avg_price": _dec(row.get("avg_price")),
            "source": "tushare:stk_holdertrade",
        }
        if item["name"]:
            result.append(item)
    return result


def normalize_share_float(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for row in _sorted(rows, "float_date", limit=10):
        item = {
            "float_date": _iso(row.get("float_date")),
            "holder_name": _text(row.get("holder_name")),
            "float_share": _dec(row.get("float_share")),
            "float_ratio": _dec(row.get("float_ratio")),
            "share_type": _text(row.get("share_type")),
            "source": "tushare:share_float",
        }
        if item["float_date"]:
            result.append(item)
    return result


def source_date(value: Any) -> date | None:
    """Public helper for callers that need to validate a vendor date."""
    return parse_date(value)
