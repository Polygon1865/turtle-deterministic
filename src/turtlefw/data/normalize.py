"""Normalisation from provider payloads into the canonical long format."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Mapping

import pandas as pd

from ..types import Currency, DividendEvent, TurtleError
from .protocol import StatementRow


def parse_date(raw: Any) -> date | None:
    if raw is None or (isinstance(raw, float) and pd.isna(raw)):
        return None
    if isinstance(raw, date):
        return raw
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    text = text.replace("-", "")[:8]
    if len(text) != 8 or not text.isdigit():
        raise TurtleError(f"unrecognised date: {raw!r}")
    return date(int(text[:4]), int(text[4:6]), int(text[6:]))


def to_decimal(raw: Any) -> Decimal | None:
    """Convert a payload value to Decimal without introducing float noise."""
    if raw is None:
        return None
    if isinstance(raw, float):
        if pd.isna(raw):
            return None
        return Decimal(repr(raw))
    if isinstance(raw, Decimal):
        return raw
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none", "--"}:
        return None
    try:
        return Decimal(text)
    except Exception:  # noqa: BLE001 - payload may contain placeholders
        return None


def period_type(end_date: date, fy_end_month: int = 12) -> str:
    if end_date.month == fy_end_month:
        return "annual"
    return {3: "q1", 6: "interim", 9: "q3"}.get(end_date.month, "other")


def rows_from_wide(
    df: pd.DataFrame,
    *,
    statement: str,
    item_map: Mapping[str, str],
    currency: Currency,
    source: str = "tushare",
    fy_end_month: int = 12,
) -> list[StatementRow]:
    """A-share style: one row per period, one column per canonical item."""
    rows: list[StatementRow] = []
    if df is None or df.empty:
        return rows

    for record in df.to_dict("records"):
        period_end = parse_date(record.get("end_date"))
        if period_end is None:
            continue
        ann_date = parse_date(record.get("ann_date"))
        ptype = period_type(period_end, fy_end_month)
        for item, column in item_map.items():
            if column not in record:
                continue
            value = to_decimal(record.get(column))
            if value is None:
                continue
            rows.append(
                StatementRow(
                    code=str(record.get("ts_code", "")),
                    period_end=period_end,
                    period_type=ptype,
                    statement=statement,
                    item=item,
                    value=value,
                    currency=currency,
                    source=source,
                    ann_date=ann_date,
                )
            )
    return rows


def rows_from_hk_line_items(
    df: pd.DataFrame,
    *,
    statement: str,
    item_map: Mapping[str, str | tuple[str, ...]],
    currency: Currency,
    source: str = "tushare",
) -> list[StatementRow]:
    """HK style: ``ind_name`` / ``ind_value`` rows pivoted onto canonical items.

    A canonical item may map to several line items (e.g. HK capex is split
    between property/equipment and intangible assets); those lines are summed.
    """
    rows: list[StatementRow] = []
    if df is None or df.empty:
        return rows

    reverse: dict[str, str] = {}
    for canonical, names in item_map.items():
        for name in (names,) if isinstance(names, str) else names:
            reverse[name] = canonical
    seen: set[tuple[date, str, str]] = set()
    totals: dict[tuple[date, str], Decimal] = defaultdict(Decimal)
    ann_dates: dict[tuple[date, str], date | None] = {}

    for record in df.to_dict("records"):
        raw_name = str(record.get("ind_name", "")).strip()
        item = reverse.get(raw_name)
        if item is None:
            continue
        period_end = parse_date(record.get("end_date"))
        if period_end is None:
            continue
        value = to_decimal(record.get("ind_value"))
        if value is None:
            continue
        key = (period_end, item)
        line_key = (period_end, item, raw_name)
        if line_key in seen:  # exact duplicate line item
            continue
        seen.add(line_key)
        totals[key] += value
        ann_dates[key] = parse_date(record.get("ann_date"))

    for (period_end, item), value in totals.items():
        rows.append(
            StatementRow(
                code=str(df.iloc[0].get("ts_code", "")) if len(df) else "",
                period_end=period_end,
                period_type=period_type(period_end),
                statement=statement,
                item=item,
                value=value,
                currency=currency,
                source=source,
                ann_date=ann_dates.get((period_end, item)),
            )
        )
    return rows


def dividend_events(
    df: pd.DataFrame,
    *,
    currency: Currency,
    source: str = "tushare",
) -> list[DividendEvent]:
    """Convert Tushare ``dividend`` rows into events with a total amount.

    Tushare emits the *same* dividend several times, once per process stage
    (预案 / 股东大会通过 / 实施), sometimes with different ``ann_date`` values.
    Only implemented (实施) rows are kept, then de-duplicated on
    ``(period_end, dps)`` so a fiscal year with an interim and a final
    dividend still yields two events that get summed later.
    """
    events: list[DividendEvent] = []
    if df is None or df.empty:
        return events

    records = df.to_dict("records")
    implemented = [
        r for r in records if str(r.get("div_proc", "")).strip() == "实施"
    ]
    candidates = implemented or records  # some vendors omit div_proc

    seen: set[tuple[str, str]] = set()
    for record in candidates:
        fiscal_end = parse_date(record.get("end_date"))
        if fiscal_end is None:
            continue
        dps = to_decimal(record.get("cash_div_tax"))
        base_share_wan = to_decimal(record.get("base_share"))
        if dps is None or dps <= 0 or base_share_wan is None or base_share_wan <= 0:
            continue
        key = (fiscal_end.isoformat(), str(dps))
        if key in seen:
            continue
        seen.add(key)
        total = dps * base_share_wan * Decimal("10000")
        ann = parse_date(record.get("ann_date"))
        events.append(
            DividendEvent(
                fiscal_year=fiscal_end.year,
                event_id=f"{fiscal_end.isoformat()}:{dps}",
                dps=dps,
                currency=currency,
                total=total,
                ann_date=ann,
            )
        )
    return sorted(events, key=lambda e: (e.fiscal_year, e.event_id))


def hk_dividend_events(
    df: pd.DataFrame, *, currency: Currency, dps_fx: Decimal = Decimal("1")
) -> list[DividendEvent]:
    """HK dividends from ``hk_fina_indicator``.

    That endpoint repeats the same DPS on every quarter and its ``dps_hkd``
    is a TTM-style field, so we keep annual rows only and use ``divi_ratio``
    (a payout ratio) as the authoritative payout figure.
    """
    events: list[DividendEvent] = []
    if df is None or df.empty:
        return events

    by_year: dict[int, DividendEvent] = {}
    for record in df.to_dict("records"):
        fiscal_end = parse_date(record.get("end_date"))
        if fiscal_end is None or fiscal_end.month != 12:
            continue
        ratio = to_decimal(record.get("divi_ratio"))
        dps = to_decimal(record.get("dps_hkd"))
        payout_pct = None
        if ratio is not None:
            payout_pct = ratio * Decimal("100") if ratio <= 1 else ratio
        if payout_pct is None and (dps is None or dps <= 0):
            continue
        by_year[fiscal_end.year] = DividendEvent(
            fiscal_year=fiscal_end.year,
            event_id=f"{fiscal_end.year}",
            dps=(dps or Decimal("0")) * dps_fx,
            currency=currency,
            total=None,
            payout_pct=payout_pct,
        )
    events = [by_year[year] for year in sorted(by_year)]
    positive = [event.dps for event in events if event.dps > 0]
    # hk_fina_indicator repeats one TTM DPS on every annual row for some names.
    # Three identical positive years is a vendor placeholder, not a dividend
    # history: keep the payout ratio but stop using DPS for averages.
    if len(positive) >= 3 and len(set(positive)) == 1:
        events = [replace(event, dps_reliable=False) for event in events]
    return events


def rows_to_frame(rows: Iterable[StatementRow]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "code": r.code,
                "period_end": r.period_end.isoformat(),
                "period_type": r.period_type,
                "statement": r.statement,
                "item": r.item,
                "value": str(r.value),
                "currency": r.currency.value,
                "source": r.source,
                "ann_date": r.ann_date.isoformat() if r.ann_date else None,
            }
            for r in rows
        ]
    )
