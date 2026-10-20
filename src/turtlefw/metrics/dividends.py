"""Dividend aggregation.

The original framework overwrote same-year dividend rows, keeping only the
last one written. This module sums every distinct event of a fiscal year, so
interim + final (the HK norm) are both counted.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Mapping, Sequence

from ..types import DividendEvent


def total_for(event: DividendEvent, shares: Decimal | None = None) -> Decimal | None:
    """Total cash paid by one event, or ``None`` when it cannot be derived."""
    if event.total is not None:
        return event.total
    if not event.dps_reliable:
        return None
    if shares is None or shares <= 0:
        return None
    return event.dps * shares


def payout_by_year(
    events: Sequence[DividendEvent],
    net_income: Mapping[int, Decimal],
    *,
    shares: Decimal | None = None,
) -> dict[int, Decimal | None]:
    """Return payout ratio (%) per fiscal year.

    ``None`` means "cannot be determined", which callers must treat as missing
    rather than as zero.
    """
    if not events:
        return {year: None for year in net_income}

    totals: dict[int, Decimal] = defaultdict(Decimal)
    explicit: dict[int, list[Decimal]] = defaultdict(list)
    seen: set[tuple[int, str]] = set()
    years_with_events: set[int] = set()

    for event in events:
        key = (event.fiscal_year, event.event_id)
        if key in seen:  # repeated announcements are idempotent
            continue
        seen.add(key)
        years_with_events.add(event.fiscal_year)
        if event.payout_pct is not None:
            explicit[event.fiscal_year].append(event.payout_pct)
            continue
        amount = total_for(event, shares)
        if amount is None:
            continue
        totals[event.fiscal_year] += amount

    result: dict[int, Decimal | None] = {}
    for year, income in net_income.items():
        if year in explicit:
            values = explicit[year]
            result[year] = sum(values, Decimal("0")) / Decimal(len(values))
        elif income is None or income <= 0:
            result[year] = None
        elif year not in totals:
            # An event exists but carries no derivable amount: unknown, not 0.
            result[year] = None if year in years_with_events else Decimal("0")
        else:
            result[year] = totals[year] / income * Decimal("100")
    return result


def mean_payout(
    payouts: Mapping[int, Decimal | None], *, years: int = 3
) -> tuple[Decimal | None, int]:
    """Mean payout over the most recent ``years`` available observations."""
    recent = sorted(payouts, reverse=True)[:years]
    values: list[Decimal] = []
    for year in recent:
        value = payouts[year]
        if value is not None:
            values.append(value)
    if not values:
        return None, 0
    return sum(values, Decimal("0")) / Decimal(len(values)), len(values)


def _completed_fiscal_year(events: Sequence[DividendEvent]) -> bool:
    """Whether the dividend rows for one fiscal year include a year-end event."""
    dated = []
    for event in events:
        raw = event.event_id.split(":", 1)[0]
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            dated.append(raw)
    if not dated:
        # Vendors that emit one annual DPS row use the fiscal year as the id.
        return True
    return any(event_id[5:] == "12-31" for event_id in dated)


def average_dps(dividends: Sequence[DividendEvent], years: int = 3) -> Decimal | None:
    """Mean annual DPS over the most recent completed fiscal years.

    Events are summed per year first. A year with only an interim event is
    excluded until its year-end dividend exists; otherwise the current partial
    fiscal year would dilute the three-year average.
    """
    reliable = [event for event in dividends if event.dps_reliable]
    if not reliable:
        return None
    per_year: dict[int, list[DividendEvent]] = defaultdict(list)
    for event in reliable:
        per_year[event.fiscal_year].append(event)
    completed = [
        year for year, events in per_year.items() if _completed_fiscal_year(events)
    ]
    recent = sorted(completed)[-years:]
    if not recent:
        return None
    return sum(
        (
            sum(
                (event.dps for event in per_year[year] if event.dps is not None),
                Decimal("0"),
            )
            for year in recent
        ),
        Decimal("0"),
    ) / Decimal(len(recent))
