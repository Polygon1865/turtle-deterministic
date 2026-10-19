"""Price-history normalisation helpers.

A-share ``weekly`` rows are raw prices. Splits/bonus issues make the 10-year
low and 52-week range incomparable over time, so OHLC is multiplied by
``adj_factor / latest_adj_factor`` before it reaches the floor calculation.
HK history from yfinance is already adjusted.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Iterable, Mapping, Sequence


def adjust_ohlc(
    history: Sequence[Mapping[str, object]],
    factors: Mapping[str, Decimal],
) -> list[dict[str, object]]:
    """Apply a backward-adjustment factor to OHLC rows (latest factor = 1)."""
    if not history or not factors:
        return [dict(item) for item in history]
    latest = max(factors.values())
    if latest <= 0:
        return [dict(item) for item in history]
    result: list[dict[str, object]] = []
    for item in history:
        record = dict(item)
        raw_date = str(record.get("trade_date", "")).replace("-", "")
        factor = factors.get(raw_date)
        if factor is None or factor <= 0:
            result.append(record)
            continue
        ratio = factor / latest
        for key in ("open", "high", "low", "close"):
            value = record.get(key)
            if value is None:
                continue
            try:
                record[key] = str(Decimal(str(value)) * ratio)
            except Exception:  # noqa: BLE001 - vendor payload
                continue
        result.append(record)
    return result


def factor_map(rows: Iterable[Mapping[str, object]]) -> dict[str, Decimal]:
    """Tushare adj_factor rows → ``{YYYYMMDD: Decimal}``."""
    result: dict[str, Decimal] = {}
    for row in rows:
        raw_date = str(row.get("trade_date", "")).replace("-", "")
        raw_factor = row.get("adj_factor")
        if not raw_date or raw_factor is None:
            continue
        try:
            result[raw_date] = Decimal(str(raw_factor))
        except Exception:  # noqa: BLE001 - vendor payload
            continue
    return result
