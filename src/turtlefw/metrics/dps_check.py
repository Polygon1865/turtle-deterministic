"""Cross-check a PDF DPS fact against provider dividend events."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from ..types import DividendEvent


@dataclass(frozen=True)
class DpsCheck:
    status: str
    pdf_dps: Decimal
    provider_dps: Decimal | None
    diff_pct: Decimal | None


def crosscheck_dps(
    pdf_dps: Decimal,
    events: Sequence[DividendEvent],
    *,
    tolerance_pct: Decimal = Decimal("1.0"),
) -> DpsCheck:
    if not events:
        return DpsCheck("unavailable", pdf_dps, None, None)
    candidates = [event.dps for event in events if event.dps_reliable and event.dps > 0]
    if not candidates:
        return DpsCheck("unavailable", pdf_dps, None, None)
    closest = min(candidates, key=lambda value: abs(value - pdf_dps))
    diff = abs(closest - pdf_dps)
    diff_pct = (diff / closest * Decimal("100")) if closest else None
    status = "match" if diff_pct is not None and diff_pct <= tolerance_pct else "mismatch"
    return DpsCheck(status, pdf_dps, closest, diff_pct)
