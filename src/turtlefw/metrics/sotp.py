"""Deterministic sum-of-the-parts (SOTP) from an explicit analyst input file.

The input contract is deliberately narrow: every segment supplies a metric base
in the reporting currency's *base unit* and an EV multiple.  The module never
guesses segment data, and skipped segments are reported instead of zero-filled.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Segment:
    name: str
    metric: str
    base: Decimal | None
    multiple: Decimal | None


@dataclass(frozen=True, slots=True)
class SOTPResult:
    segments: tuple[Segment, ...]
    ev: Decimal | None
    net_debt: Decimal | None
    equity: Decimal | None
    per_share: Decimal | None
    skipped: tuple[str, ...]


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ArithmeticError, ValueError):
        return None


def parse_segments(payload: Iterable[Mapping[str, object]]) -> list[Segment]:
    segments: list[Segment] = []
    for index, raw in enumerate(payload):
        name = str(raw.get("name", "")).strip() or f"segment-{index + 1}"
        metric = str(raw.get("metric", "metric")).strip() or "metric"
        segments.append(
            Segment(
                name=name,
                metric=metric,
                base=_decimal(raw.get("base")),
                multiple=_decimal(raw.get("multiple")),
            )
        )
    return segments


def compute(
    segments: Iterable[Segment],
    *,
    cash: Decimal | None,
    debt: Decimal | None,
    shares: Decimal | None,
) -> SOTPResult:
    items = tuple(segments)
    ev = Decimal(0)
    skipped: list[str] = []
    used = 0
    for segment in items:
        if (
            segment.base is None
            or segment.multiple is None
            or segment.base < 0
            or segment.multiple <= 0
        ):
            skipped.append(segment.name)
            continue
        ev += segment.base * segment.multiple
        used += 1
    if used == 0:
        return SOTPResult(items, None, None, None, None, tuple(skipped))
    net_debt = (debt or Decimal(0)) - (cash or Decimal(0))
    equity = ev - net_debt
    per_share = equity / shares if shares is not None and shares > 0 else None
    return SOTPResult(items, ev, net_debt, equity, per_share, tuple(skipped))
