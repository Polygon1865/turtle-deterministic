"""Valuation helpers: five floor-price anchors and their composite."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Sequence


@dataclass(frozen=True, slots=True)
class Baseline:
    name: str
    value: Decimal
    formula: str


def net_liquid_assets_per_share(
    cash: Decimal, trad_assets: Decimal, debt: Decimal, shares: Decimal
) -> Decimal | None:
    if shares <= 0:
        return None
    return (cash + trad_assets - debt) / shares


def book_value_per_share(equity: Decimal, shares: Decimal) -> Decimal | None:
    if shares <= 0:
        return None
    return equity / shares


def ten_year_low(closes: Iterable[Decimal]) -> Decimal | None:
    values = [value for value in closes if value is not None and value > 0]
    return min(values) if values else None


def dividend_implied_price(
    average_dps: Decimal | None, rf_pct: Decimal, floor_pct: Decimal = Decimal("3")
) -> Decimal | None:
    """Price at which the dividend yield equals the discount rate."""
    if average_dps is None or average_dps <= 0 or rf_pct <= 0:
        return None
    discount = max(rf_pct, floor_pct) / Decimal("100")
    return average_dps / discount


def pessimistic_fcf_price(
    min_fcf: Decimal | None, rf_pct: Decimal, shares: Decimal
) -> Decimal | None:
    """Capitalise the worst positive FCF year at the risk-free rate."""
    if min_fcf is None or min_fcf <= 0 or rf_pct <= 0 or shares <= 0:
        return None
    return min_fcf / (rf_pct / Decimal("100")) / shares


def five_baselines(
    *,
    cash: Decimal | None = None,
    trad_assets: Decimal | None = None,
    debt: Decimal | None = None,
    equity: Decimal | None = None,
    shares: Decimal | None = None,
    closes: Sequence[Decimal] | None = None,
    average_dps: Decimal | None = None,
    min_fcf: Decimal | None = None,
    rf_pct: Decimal | None = None,
    dividend_floor_pct: Decimal = Decimal("3"),
) -> list[Baseline]:
    """Build the valid anchors only; invalid inputs are skipped, not zeroed."""
    baselines: list[Baseline] = []
    if shares and shares > 0 and cash is not None and debt is not None:
        value = net_liquid_assets_per_share(
            cash, trad_assets or Decimal("0"), debt, shares
        )
        if value is not None:
            baselines.append(
                Baseline("净流动资产/股", value, "(现金+交易性资产-有息负债)/总股本")
            )
    if shares and shares > 0 and equity is not None:
        value = book_value_per_share(equity, shares)
        if value is not None:
            baselines.append(Baseline("每股净资产", value, "归母权益/总股本"))
    if closes:
        value = ten_year_low(closes)
        if value is not None:
            baselines.append(Baseline("10年最低价", value, "周线最低收盘价"))
    if rf_pct is not None:
        value = dividend_implied_price(average_dps, rf_pct, dividend_floor_pct)
        if value is not None:
            baselines.append(
                Baseline("股息隐含价", value, f"3年均DPS/max(Rf,{dividend_floor_pct}%)")
            )
        if shares and shares > 0 and min_fcf is not None:
            value = pessimistic_fcf_price(min_fcf, rf_pct, shares)
            if value is not None:
                baselines.append(
                    Baseline("悲观FCF资本化", value, "min(5年FCF)/Rf/总股本")
                )
    return baselines


def composite(baselines: Iterable[Baseline], method: str = "mean") -> Decimal | None:
    values = sorted(b.value for b in baselines)
    if not values:
        return None
    if method == "median":
        middle = len(values) // 2
        if len(values) % 2:
            return values[middle]
        return (values[middle - 1] + values[middle]) / Decimal("2")
    return sum(values, Decimal("0")) / Decimal(len(values))


def premium(price: Decimal, baseline: Decimal | None) -> Decimal | None:
    """Premium of the current price over the baseline, in percent."""
    if baseline is None or baseline <= 0:
        return None
    return (price / baseline - Decimal("1")) * Decimal("100")
