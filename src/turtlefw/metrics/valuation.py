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
    """Build the valid anchors only; invalid or non-positive inputs are skipped."""
    baselines: list[Baseline] = []
    if shares and shares > 0 and cash is not None and debt is not None:
        value = net_liquid_assets_per_share(
            cash, trad_assets or Decimal("0"), debt, shares
        )
        if value is not None and value > 0:
            baselines.append(
                Baseline("净流动资产/股", value, "(现金+交易性资产-有息负债)/总股本")
            )
    if shares and shares > 0 and equity is not None:
        value = book_value_per_share(equity, shares)
        if value is not None and value > 0:
            baselines.append(Baseline("每股净资产", value, "归母权益/总股本"))
    if closes:
        value = ten_year_low(closes)
        if value is not None and value > 0:
            baselines.append(Baseline("10年最低价", value, "周线最低收盘价"))
    if rf_pct is not None:
        value = dividend_implied_price(average_dps, rf_pct, dividend_floor_pct)
        if value is not None and value > 0:
            baselines.append(
                Baseline("股息隐含价", value, f"3年均DPS/max(Rf,{dividend_floor_pct}%)")
            )
        if shares and shares > 0 and min_fcf is not None:
            value = pessimistic_fcf_price(min_fcf, rf_pct, shares)
            if value is not None and value > 0:
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


def choose_composite(
    baselines: Iterable[Baseline],
    method: str = "median",
    divergence_threshold: Decimal = Decimal("20"),
) -> tuple[Decimal | None, "FloorStats"]:
    """Pick the composite consistently for CLI, data pack and report.

    ``median`` is the default because the five anchors include one or two
    liquidation-style values that can be extreme. When the configured method
    is unavailable (e.g. no valid anchor), fall back to the other one.
    """
    items = list(baselines)
    stats = floor_stats(items, divergence_threshold)
    if stats.mean is None and stats.median is None:
        return None, stats
    if method == "mean":
        value = stats.mean if stats.mean is not None else stats.median
    else:
        value = stats.median if stats.median is not None else stats.mean
    if value is not None and value <= 0:
        return None, stats
    return value, stats


@dataclass(frozen=True, slots=True)
class FloorStats:
    mean: Decimal | None
    median: Decimal | None
    divergence: Decimal | None  # |mean - median| / |median| * 100
    status: str  # stable | divergent | unavailable


def floor_stats(
    baselines: Iterable[Baseline], threshold: Decimal = Decimal("20")
) -> FloorStats:
    """Mean and median of the anchors plus their relative divergence.

    With five anchors the median tolerates up to two extreme values, so a large
    gap between the two is a signal that the composite is not decision-grade.
    """
    values = sorted(b.value for b in baselines)
    if not values:
        return FloorStats(None, None, None, "unavailable")
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    middle = len(values) // 2
    median = (
        values[middle]
        if len(values) % 2
        else (values[middle - 1] + values[middle]) / Decimal("2")
    )
    if median <= 0:
        return FloorStats(mean, median, None, "unavailable")
    divergence = abs(mean - median) / abs(median) * Decimal("100")
    status = "divergent" if divergence > threshold else "stable"
    return FloorStats(mean, median, divergence, status)


@dataclass(frozen=True, slots=True)
class FloorResult:
    baselines: tuple[Baseline, ...]
    composite: Decimal | None
    stats: "FloorStats"
    premium: Decimal | None


def compute_floor(
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
    price: Decimal | None = None,
    dividend_floor_pct: Decimal = Decimal("3"),
    composite_method: str = "median",
    divergence_threshold: Decimal = Decimal("20"),
) -> FloorResult:
    """Single deterministic floor calculation for report, pack and CLI."""
    baselines = tuple(
        five_baselines(
            cash=cash,
            trad_assets=trad_assets,
            debt=debt,
            equity=equity,
            shares=shares,
            closes=closes,
            average_dps=average_dps,
            min_fcf=min_fcf,
            rf_pct=rf_pct,
            dividend_floor_pct=dividend_floor_pct,
        )
    )
    composite, stats = choose_composite(
        baselines,
        composite_method,
        divergence_threshold,
    )
    return FloorResult(
        baselines=baselines,
        composite=composite,
        stats=stats,
        premium=premium(price, composite) if price is not None else None,
    )


@dataclass(frozen=True, slots=True)
class ValuationSnapshot:
    ev: Decimal | None
    ebitda: Decimal | None
    net_debt: Decimal | None
    ev_ebitda: Decimal | None
    net_debt_ebitda: Decimal | None
    cash_adj_pe: Decimal | None
    fcf_yield: Decimal | None
    pb: Decimal | None
    goodwill_ratio: Decimal | None
    dividend_yield: Decimal | None
    ebitda_margin: Decimal | None


def build_valuation(
    *,
    market_cap: Decimal | None,
    cash: Decimal | None,
    debt: Decimal | None,
    equity: Decimal | None,
    net_income: Decimal | None,
    revenue: Decimal | None,
    operate_profit: Decimal | None,
    finance_exp: Decimal | None,
    da: Decimal | None,
    fcf: Decimal | None,
    goodwill: Decimal | None,
    total_assets: Decimal | None,
    dps: Decimal | None,
    price: Decimal | None,
) -> ValuationSnapshot:
    """Absolute-valuation dashboard. Missing inputs yield ``None``, never zero."""
    net_debt = debt - cash if debt is not None and cash is not None else None
    ev = market_cap + net_debt if market_cap is not None and net_debt is not None else None

    ebitda = None
    if operate_profit is not None and da is not None:
        ebitda = operate_profit + (finance_exp or Decimal("0")) + da

    ev_ebitda = ev / ebitda if ev is not None and ebitda and ebitda > 0 else None
    net_debt_ebitda = (
        net_debt / ebitda if net_debt is not None and ebitda and ebitda > 0 else None
    )
    cash_adj_pe = (
        (market_cap + net_debt) / net_income
        if market_cap is not None and net_debt is not None and net_income and net_income > 0
        else None
    )
    fcf_yield = (
        fcf / market_cap * Decimal("100")
        if fcf is not None and market_cap and market_cap > 0
        else None
    )
    pb = market_cap / equity if market_cap is not None and equity and equity > 0 else None
    goodwill_ratio = (
        goodwill / total_assets * Decimal("100")
        if goodwill is not None and total_assets and total_assets > 0
        else None
    )
    dividend_yield = (
        dps / price * Decimal("100")
        if dps is not None and price and price > 0
        else None
    )
    ebitda_margin = (
        ebitda / revenue * Decimal("100")
        if ebitda is not None and revenue and revenue > 0
        else None
    )

    return ValuationSnapshot(
        ev=ev,
        ebitda=ebitda,
        net_debt=net_debt,
        ev_ebitda=ev_ebitda,
        net_debt_ebitda=net_debt_ebitda,
        cash_adj_pe=cash_adj_pe,
        fcf_yield=fcf_yield,
        pb=pb,
        goodwill_ratio=goodwill_ratio,
        dividend_yield=dividend_yield,
        ebitda_margin=ebitda_margin,
    )
