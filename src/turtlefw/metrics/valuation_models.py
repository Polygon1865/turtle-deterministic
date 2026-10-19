"""Deterministic valuation models.

These functions are deliberately small and pure so the CLI, reports and tests
share the same arithmetic. They do not read providers or config; callers pass
explicit assumptions and get ``Decimal`` results or ``None`` when an input is
missing/meaningless.

The model set mirrors the upstream v2 valuation engine (DCF, DDM, PE band,
PEG, PS) without its LLM adjustment layer.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence


def wacc(
    *,
    rf_pct: Decimal,
    beta: Decimal,
    erp_pct: Decimal,
    cost_of_debt_pct: Decimal,
    tax_pct: Decimal,
    equity_value: Decimal,
    debt_value: Decimal,
) -> Decimal | None:
    """Weighted average cost of capital in percent."""
    total = equity_value + debt_value
    if total <= 0 or equity_value < 0 or debt_value < 0:
        return None
    cost_of_equity = rf_pct + beta * erp_pct
    after_tax_debt = cost_of_debt_pct * (Decimal("1") - tax_pct / Decimal("100"))
    return (cost_of_equity * equity_value + after_tax_debt * debt_value) / total


def dcf(
    *,
    fcf_base: Decimal | None,
    growth_rates_pct: Sequence[Decimal],
    terminal_growth_pct: Decimal,
    wacc_pct: Decimal,
    cash: Decimal | None,
    debt: Decimal | None,
    shares: Decimal | None,
) -> dict[str, Decimal | None]:
    """Five-year fading-growth DCF; returns per-share and components."""
    empty: dict[str, Decimal | None] = {
        "ev": None,
        "equity": None,
        "per_share": None,
        "terminal_share_pct": None,
    }
    if (
        fcf_base is None
        or fcf_base <= 0
        or shares is None
        or shares <= 0
        or wacc_pct <= terminal_growth_pct
        or not growth_rates_pct
    ):
        return empty
    projected: list[Decimal] = []
    previous = fcf_base
    for growth in growth_rates_pct:
        previous = previous * (Decimal("1") + growth / Decimal("100"))
        projected.append(previous)
    terminal = (
        projected[-1]
        * (Decimal("1") + terminal_growth_pct / Decimal("100"))
        / (wacc_pct / Decimal("100") - terminal_growth_pct / Decimal("100"))
    )
    pv_fcf = sum(
        value / (Decimal("1") + wacc_pct / Decimal("100")) ** (index + 1)
        for index, value in enumerate(projected)
    )
    pv_terminal = terminal / (Decimal("1") + wacc_pct / Decimal("100")) ** len(projected)
    ev = pv_fcf + pv_terminal
    equity = ev + (cash or Decimal("0")) - (debt or Decimal("0"))
    return {
        "ev": ev,
        "equity": equity,
        "per_share": equity / shares,
        "terminal_share_pct": pv_terminal / ev * Decimal("100") if ev > 0 else None,
    }


def ddm(*, dps: Decimal | None, ke_pct: Decimal, growth_pct: Decimal) -> Decimal | None:
    """Gordon growth model; returns per-share value."""
    if dps is None or dps <= 0 or ke_pct <= growth_pct:
        return None
    return dps * (Decimal("1") + growth_pct / Decimal("100")) / (
        ke_pct / Decimal("100") - growth_pct / Decimal("100")
    )


def pe_band(
    *, eps: Decimal | None, pe_low: Decimal, pe_mid: Decimal, pe_high: Decimal
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    if eps is None or eps <= 0:
        return None, None, None
    return eps * pe_low, eps * pe_mid, eps * pe_high


def peg(
    *, eps: Decimal | None, growth_pct: Decimal | None, target_peg: Decimal = Decimal("1")
) -> Decimal | None:
    """Fair value from PEG: PE = growth (%) × target PEG."""
    if eps is None or eps <= 0 or growth_pct is None or growth_pct <= 0:
        return None
    return eps * growth_pct * target_peg


def ps(*, revenue_per_share: Decimal | None, ps_multiple: Decimal) -> Decimal | None:
    if revenue_per_share is None or revenue_per_share <= 0 or ps_multiple <= 0:
        return None
    return revenue_per_share * ps_multiple


def cross_validate(
    values: Mapping[str, Decimal | None],
    weights: Mapping[str, Decimal] | None = None,
) -> Decimal | None:
    """Weighted average of the available model values, normalised by weights."""
    usable = {name: value for name, value in values.items() if value is not None and value > 0}
    if not usable:
        return None
    if not weights:
        return sum(usable.values(), Decimal("0")) / Decimal(len(usable))
    total_weight = Decimal("0")
    total_value = Decimal("0")
    for name, value in usable.items():
        weight = weights.get(name, Decimal("0"))
        if weight <= 0:
            continue
        total_weight += weight
        total_value += value * weight
    if total_weight <= 0:
        return sum(usable.values(), Decimal("0")) / Decimal(len(usable))
    return total_value / total_weight


def blended_upside(current_price: Decimal | None, fair_value: Decimal | None) -> Decimal | None:
    if current_price is None or current_price <= 0 or fair_value is None:
        return None
    return (fair_value / current_price - Decimal("1")) * Decimal("100")


def classify_company(
    *,
    roe_5y: Decimal | None,
    payout_3y: Decimal | None,
    revenue_cagr: Decimal | None,
    profit_cagr: Decimal | None,
) -> tuple[str, dict[str, Decimal]]:
    """Classify into blue-chip / growth / mixed and return method weights."""
    blue = 0
    growth = 0
    if roe_5y is not None and roe_5y > 15:
        blue += 1
    if payout_3y is not None and payout_3y > 30:
        blue += 1
    if revenue_cagr is not None and revenue_cagr < 20:
        blue += 1
    if revenue_cagr is not None and revenue_cagr > 20:
        growth += 1
    if profit_cagr is not None and profit_cagr > 25:
        growth += 1
    if blue >= 2 and growth == 0:
        return "蓝筹价值型", {
            "DCF": Decimal("40"),
            "DDM": Decimal("30"),
            "PE Band": Decimal("30"),
        }
    if growth >= 2 and blue <= 1:
        return "成长型", {
            "DCF": Decimal("40"),
            "PEG": Decimal("35"),
            "PS": Decimal("25"),
        }
    return "混合型", {
        "DCF": Decimal("35"),
        "DDM": Decimal("15"),
        "PE Band": Decimal("25"),
        "PEG": Decimal("25"),
    }


def dcf_sensitivity(
    *,
    fcf_base: Decimal | None,
    growth_rates_pct: Sequence[Decimal],
    terminal_growth_pct: Decimal,
    wacc_pct: Decimal,
    cash: Decimal | None,
    debt: Decimal | None,
    shares: Decimal | None,
    wacc_offsets: Sequence[Decimal] = (Decimal("-2"), Decimal("-1"), Decimal("0"), Decimal("1"), Decimal("2")),
    growth_offsets: Sequence[Decimal] = (Decimal("-1"), Decimal("-0.5"), Decimal("0"), Decimal("0.5"), Decimal("1")),
) -> tuple[tuple[Decimal, ...], list[list[Decimal | None]]]:
    """5×5 per-share DCF sensitivity around the base WACC/terminal growth."""
    matrix: list[list[Decimal | None]] = []
    for wacc_offset in wacc_offsets:
        row: list[Decimal | None] = []
        for growth_offset in growth_offsets:
            result = dcf(
                fcf_base=fcf_base,
                growth_rates_pct=growth_rates_pct,
                terminal_growth_pct=terminal_growth_pct + growth_offset,
                wacc_pct=wacc_pct + wacc_offset,
                cash=cash,
                debt=debt,
                shares=shares,
            )
            row.append(result["per_share"])
        matrix.append(row)
    return tuple(wacc_offsets), matrix


def implied_growth_pct(
    *,
    fcf_base: Decimal | None,
    wacc_pct: Decimal,
    terminal_growth_pct: Decimal,
    cash: Decimal | None,
    debt: Decimal | None,
    shares: Decimal | None,
    current_price: Decimal | None,
    low: Decimal = Decimal("-5"),
    high: Decimal = Decimal("25"),
) -> Decimal | None:
    """Reverse DCF: constant 5-year growth that makes per-share value = price."""
    if fcf_base is None or fcf_base <= 0 or shares is None or shares <= 0 or current_price is None:
        return None

    def value(growth: Decimal) -> Decimal | None:
        result = dcf(
            fcf_base=fcf_base,
            growth_rates_pct=(growth,) * 5,
            terminal_growth_pct=terminal_growth_pct,
            wacc_pct=wacc_pct,
            cash=cash,
            debt=debt,
            shares=shares,
        )
        return result["per_share"]

    low_value = value(low)
    high_value = value(high)
    if low_value is None or high_value is None:
        return None
    if current_price < low_value or current_price > high_value:
        return None
    for _ in range(60):
        mid = (low + high) / Decimal("2")
        mid_value = value(mid)
        if mid_value is None:
            return None
        if mid_value < current_price:
            low = mid
        else:
            high = mid
    return (low + high) / Decimal("2")
