"""Deterministic peer-multiple reference values.

Peer comps are deliberately a *reference*, not a fair-value model: the peer set
is a market-cap screen, multiples can be distorted by one-off earnings, and the
sample is small.  We therefore use the median and require three valid peers.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PeerComps:
    peer_count: int
    pe_median: Decimal | None
    pb_median: Decimal | None
    pe_value: Decimal | None
    pb_value: Decimal | None
    source: str = "tushare:daily_basic"


def _median(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / Decimal(2)


def _positive(row: Mapping[str, object], key: str) -> Decimal | None:
    raw = row.get(key)
    if raw is None:
        return None
    try:
        value = Decimal(str(raw))
    except (ArithmeticError, ValueError):
        return None
    return value if value > 0 else None


def compute(
    *,
    eps: Decimal | None,
    bvps: Decimal | None,
    peers: Iterable[Mapping[str, object]],
    min_peers: int = 3,
) -> PeerComps:
    """Median peer PE/PB and the values they imply for the target."""
    rows = list(peers)
    pe_values = [value for row in rows if (value := _positive(row, "pe_ttm"))]
    pb_values = [value for row in rows if (value := _positive(row, "pb"))]
    pe_median = _median(pe_values) if len(pe_values) >= min_peers else None
    pb_median = _median(pb_values) if len(pb_values) >= min_peers else None
    return PeerComps(
        peer_count=len(rows),
        pe_median=pe_median,
        pb_median=pb_median,
        pe_value=(
            pe_median * eps
            if pe_median is not None and eps is not None and eps > 0
            else None
        ),
        pb_value=(
            pb_median * bvps
            if pb_median is not None and bvps is not None and bvps > 0
            else None
        ),
    )
