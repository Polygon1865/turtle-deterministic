"""Single source of truth for payout-ratio arithmetic (roadmap T2).

Payout ratios arrive in three shapes:

* vendor ratio (Tushare ``divi_ratio``): a fraction (``0.928`` = 92.8%) that can
  legitimately exceed 1.0 when a special dividend is paid (``1.4084`` = 140.84%);
* ``dps / eps`` for HK rows where the ratio is missing;
* ``total dividends / net income`` for A-share event tables.

Historically the HK screener and the HK dividend normaliser disagreed on the
fraction/percent boundary (screener: ``<= 10``, normaliser: ``<= 1``), which made
the same stock show 100.00% in the ranking CSV and 1.41% in its report.  Every
caller must now go through this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

MAX_PCT = Decimal("100")
# Values at or below this are fractions (300% cap); above it the vendor already
# emitted a percentage.  HK ``divi_ratio`` never exceeds ~2 in practice.
FRACTION_MAX = Decimal("3")
TOLERANCE = Decimal("0.01")


def _dec(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


@dataclass(frozen=True, slots=True)
class Payout:
    """One payout answer plus where it came from."""

    pct: Decimal | None
    source: str
    reliable: bool
    note: str = ""

    def rounded(self, places: str = "0.01") -> Decimal | None:
        if self.pct is None:
            return None
        return self.pct.quantize(Decimal(places))


NONE = Payout(None, "none", False, "no data")


def vendor_ratio(value: object) -> Payout:
    """Tushare ``divi_ratio``: fraction (0.928) or percent (92.8)."""

    number = _dec(value)
    if number is None:
        return Payout(None, "divi_ratio", False, "missing")
    if number <= 0:
        return Payout(None, "divi_ratio", False, "non-positive")
    pct = number * 100 if number <= FRACTION_MAX else number
    if pct > MAX_PCT:
        return Payout(MAX_PCT, "divi_ratio", False, f"clipped from {pct:.2f}%")
    return Payout(pct, "divi_ratio", True)


def dps_ratio(dps: object, eps: object, *, eps_fx: Decimal = Decimal("1")) -> Payout:
    """``dps / eps`` in percent; ``eps_fx`` converts EPS into the DPS currency."""

    dps_value = _dec(dps)
    eps_value = _dec(eps)
    if dps_value is None or dps_value <= 0:
        return Payout(None, "dps", False, "missing dps")
    if eps_value is None or eps_value <= 0:
        return Payout(None, "dps", False, "missing eps")
    eps_adj = eps_value / eps_fx if eps_fx and eps_fx > 0 else eps_value
    pct = dps_value / eps_adj * MAX_PCT
    if pct <= 0:
        return Payout(None, "dps", False, "non-positive")
    if pct > MAX_PCT:
        return Payout(MAX_PCT, "dps", False, f"clipped from {pct:.2f}%")
    return Payout(pct, "dps", True)


def events_ratio(total: object, net_income: object) -> Payout:
    """``total dividends / net income`` in percent (A-share event tables)."""

    paid = _dec(total)
    income = _dec(net_income)
    if paid is None or income is None or income <= 0:
        return Payout(None, "events", False, "missing inputs")
    pct = paid / income * MAX_PCT
    if pct <= 0:
        return Payout(None, "events", False, "non-positive")
    if pct > MAX_PCT:
        return Payout(MAX_PCT, "events", False, f"clipped from {pct:.2f}%")
    return Payout(pct, "events", True)


def resolve(*candidates: Payout, prefer: tuple[str, ...] = ("divi_ratio", "dps", "events")) -> Payout:
    """Pick the first usable candidate in ``prefer`` order.

    A clipped candidate (``reliable=False``) still beats "no data": the value is
    kept, but the unreliable flag travels with it so callers can warn.
    """

    usable = [item for item in candidates if item.pct is not None]
    if not usable:
        return NONE
    for source in prefer:
        for item in usable:
            if item.source == source:
                return item
    return usable[0]


def agree(left: Payout | None, right: Payout | None, *, tol: Decimal = TOLERANCE) -> bool:
    """True when two payout answers describe the same number (or both are absent)."""

    if left is None or right is None:
        return left is None and right is None
    if left.pct is None or right.pct is None:
        return left.pct is None and right.pct is None
    return abs(left.pct - right.pct) <= tol
