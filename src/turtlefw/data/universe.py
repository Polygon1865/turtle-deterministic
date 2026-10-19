"""Universe helpers for reproducible screening dates.

Tushare's ``stock_basic`` is a *current* universe, so this filter can remove
future listings but cannot recover delisted names. The limitation is explicit
in the screening output; true point-in-time universes need a stored daily
snapshot.
"""

from __future__ import annotations

from typing import Iterable, Mapping


def _date(value: object) -> str:
    text = str(value or "").replace("-", "")[:8]
    return "" if text.lower() in {"nan", "none", "nat"} else text


def listed_as_of(
    universe: Iterable[Mapping[str, object]], as_of: str
) -> list[dict[str, object]]:
    cutoff = _date(as_of)
    if not cutoff:
        return [dict(row) for row in universe]
    result: list[dict[str, object]] = []
    for row in universe:
        listed = _date(row.get("list_date"))
        delisted = _date(row.get("delist_date"))
        if listed and listed > cutoff:
            continue
        if delisted and delisted <= cutoff:
            continue
        result.append(dict(row))
    return result
