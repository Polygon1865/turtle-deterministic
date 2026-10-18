"""Normalisation from provider payloads into the canonical long format."""

from __future__ import annotations

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
    item_map: Mapping[str, str],
    currency: Currency,
    source: str = "tushare",
) -> list[StatementRow]:
    """HK style: ``ind_name`` / ``ind_value`` rows pivoted onto canonical items."""
    rows: list[StatementRow] = []
    if df is None or df.empty:
        return rows

    reverse = {v: k for k, v in item_map.items()}
    seen: set[tuple[date, str]] = set()

    for record in df.to_dict("records"):
        item = reverse.get(str(record.get("ind_name", "")).strip())
        if item is None:
            continue
        period_end = parse_date(record.get("end_date"))
        if period_end is None:
            continue
        value = to_decimal(record.get("ind_value"))
        if value is None:
            continue
        key = (period_end, item)
        if key in seen:  # first non-null wins for duplicated line items
            continue
        seen.add(key)
        rows.append(
            StatementRow(
                code=str(record.get("ts_code", "")),
                period_end=period_end,
                period_type=period_type(period_end),
                statement=statement,
                item=item,
                value=value,
                currency=currency,
                source=source,
                ann_date=parse_date(record.get("ann_date")),
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

    ``cash_div_tax`` is per-share pre-tax, ``base_share`` is in 10k shares.
    Multiple events within one fiscal year are kept separate; aggregation
    happens later in ``metrics.dividends``.
    """
    events: list[DividendEvent] = []
    if df is None or df.empty:
        return events

    for record in df.to_dict("records"):
        fiscal_end = parse_date(record.get("end_date"))
        if fiscal_end is None:
            continue
        dps = to_decimal(record.get("cash_div_tax"))
        base_share_wan = to_decimal(record.get("base_share"))
        if dps is None or dps <= 0 or base_share_wan is None or base_share_wan <= 0:
            continue
        total = dps * base_share_wan * Decimal("10000")
        ann = parse_date(record.get("ann_date"))
        event_id = f"{ann.isoformat() if ann else fiscal_end.isoformat()}:{record.get('div_proc') or 'unknown'}"
        events.append(
            DividendEvent(
                fiscal_year=fiscal_end.year,
                event_id=event_id,
                dps=dps,
                total=total,
                currency=currency,
                ann_date=ann,
            )
        )
    return sorted(events, key=lambda e: (e.fiscal_year, e.event_id))


def hk_dividend_events(df: pd.DataFrame, *, currency: Currency) -> list[DividendEvent]:
    """HK dividends come from ``hk_fina_indicator`` as DPS only.

    ``total`` stays ``None``; ``payout_by_year`` derives it when a share count
    is supplied.
    """
    events: list[DividendEvent] = []
    if df is None or df.empty:
        return events

    for record in df.to_dict("records"):
        fiscal_end = parse_date(record.get("end_date"))
        dps = to_decimal(record.get("dps_hkd"))
        if fiscal_end is None or dps is None or dps <= 0:
            continue
        events.append(
            DividendEvent(
                fiscal_year=fiscal_end.year,
                event_id=fiscal_end.isoformat(),
                dps=dps,
                currency=currency,
                total=None,
            )
        )
    return sorted(events, key=lambda e: (e.fiscal_year, e.event_id))


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
