"""Penetration return (穿透回报率) and threshold logic."""

from __future__ import annotations

from decimal import Decimal

from ..config import ReturnsConfig
from ..types import Money, StockCode


def threshold_ii(rf_pct: Decimal, code: StockCode, cfg: ReturnsConfig) -> Decimal:
    """II = max(floor, Rf + spread).

    A-share: max(3.5%, Rf+2%). HK: max(5%, Rf+3%).
    """
    return cfg.threshold(rf_pct, code)


def penetration_return(
    aa: Money,
    payout_pct: Decimal,
    tax_pct: Decimal,
    buyback: Money,
    market_cap: Money,
    fx: Decimal,
) -> Decimal | None:
    """R = (AA x M x (1 - Q) + O) / market cap x 100.

    ``fx`` converts the reporting currency into the market-cap currency.
    Returns ``None`` when the market cap is not positive.
    """
    if market_cap.amount <= 0:
        return None
    aa_market = aa.to(market_cap.currency, fx)
    buyback_market = buyback.to(market_cap.currency, fx)
    distributed = aa_market.amount * payout_pct / Decimal("100") * (
        Decimal("1") - tax_pct / Decimal("100")
    ) + buyback_market.amount
    return distributed / market_cap.amount * Decimal("100")


def classify_return(r: Decimal | None, ii: Decimal, rf: Decimal | None) -> str:
    """Classify R against the threshold, mirroring the framework gates."""
    if r is None:
        return "unknown"
    if rf is not None and r < rf:
        return "below_rf"
    if r < ii * Decimal("0.5"):
        return "fail"
    if r < ii:
        return "marginal"
    return "pass"


def safety_margin(gg: Decimal | None, ii: Decimal) -> Decimal | None:
    if gg is None:
        return None
    return gg - ii
