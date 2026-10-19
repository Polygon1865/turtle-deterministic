"""Deterministic factor grids.

The upstream v2 project pre-computes payout/return/G/lambda tables so the
LLM only selects a row. This module keeps the same idea, but every value is
computed in ``Decimal`` and the *selection* is also deterministic: the report
may explain the choice, it cannot change the arithmetic.

Nothing here talks to a provider. Inputs are the canonical statement rows or
plain series already normalised by :mod:`turtlefw.metrics`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Iterable, Mapping, Sequence

from ..config import ReturnsConfig
from ..types import DividendEvent, Market, StockCode
from . import dividends as div_metrics


# ---------------------------------------------------------------------------
# Tax scenarios
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaxScenario:
    label: str
    rate: Decimal


def tax_scenarios(code: StockCode) -> tuple[TaxScenario, ...]:
    if code.market is Market.HK:
        return (
            TaxScenario("H股直接", Decimal("28")),
            TaxScenario("港股通", Decimal("20")),
            TaxScenario("红筹/开曼", Decimal("20")),
        )
    if code.market is Market.US:
        return (
            TaxScenario("直接持有", Decimal("30")),
            TaxScenario("W-8BEN", Decimal("10")),
        )
    return (
        TaxScenario("持有>1年", Decimal("0")),
        TaxScenario("持有1月-1年", Decimal("10")),
        TaxScenario("持有<1月", Decimal("20")),
    )


def default_tax_rate(code: StockCode) -> Decimal:
    if code.market is Market.HK:
        return Decimal("20")
    if code.market is Market.US:
        return Decimal("10")
    return Decimal("0")


# ---------------------------------------------------------------------------
# Payout cross-check (v2 §17.10)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PayoutCandidate:
    label: str
    value: Decimal | None
    source: str


@dataclass(frozen=True, slots=True)
class PayoutCrosscheck:
    candidates: tuple[PayoutCandidate, ...]
    recommended: Decimal | None
    recommended_label: str
    reliable: bool
    note: str


def _mean(values: Iterable[Decimal | None]) -> Decimal | None:
    items = [value for value in values if value is not None]
    if not items:
        return None
    return sum(items, Decimal("0")) / Decimal(len(items))


def _relative_spread(values: Sequence[Decimal]) -> Decimal | None:
    clean = [abs(value) for value in values if value is not None]
    if len(clean) < 2:
        return None
    high, low = max(clean), min(clean)
    if high <= 0:
        return None
    return (high - low) / high


def payout_crosscheck(
    dividends: Sequence[DividendEvent],
    net_income: Mapping[int, Decimal],
    *,
    eps: Mapping[int, Decimal] | None = None,
    shares: Decimal | None = None,
    cash_dividends: Mapping[int, Decimal] | None = None,
    years: int = 3,
) -> PayoutCrosscheck:
    """Three ways to estimate M; disagreements are surfaced, not hidden.

    * 法1: DPS / EPS (per-share, both in the report currency)
    * 法2: cash paid dividends (cash-flow statement) / net income
    * 法3: per-year payout from event totals (the canonical path)
    """
    empty = PayoutCrosscheck((), None, "无", False, "无分红事件")
    if not dividends:
        return empty

    fiscal_years = sorted({event.fiscal_year for event in dividends})[-years:]
    reliable_events = [event for event in dividends if event.dps_reliable]

    # 法1: DPS / EPS
    m1_values: list[Decimal] = []
    if eps:
        for year in fiscal_years:
            dps = sum(
                (e.dps for e in reliable_events if e.fiscal_year == year),
                Decimal("0"),
            )
            eps_value = eps.get(year)
            if eps_value and eps_value > 0 and dps > 0:
                m1_values.append(dps / eps_value * Decimal("100"))

    # 法2: cash dividends paid / net income; fall back to event totals when
    # the cash-flow line is unavailable (HK often lacks it).
    m2_values: list[Decimal] = []
    for year in fiscal_years:
        income = net_income.get(year)
        if income is None or income <= 0:
            continue
        total: Decimal | None = None
        if cash_dividends and cash_dividends.get(year):
            total = abs(cash_dividends[year])
        year_events = [e for e in dividends if e.fiscal_year == year]
        if total is None and any(e.total is not None for e in year_events):
            total = sum((e.total for e in year_events if e.total is not None), Decimal("0"))
        if total is None and shares and shares > 0 and reliable_events:
            total = sum(
                (e.dps for e in reliable_events if e.fiscal_year == year),
                Decimal("0"),
            ) * shares
        if total is not None and total > 0:
            m2_values.append(total / income * Decimal("100"))

    # 法3: canonical payout_by_year over the last three available years
    payouts = div_metrics.payout_by_year(dividends, net_income, shares=shares)
    m3_values = [
        payouts[year]
        for year in sorted(payouts)[-years:]
        if payouts.get(year) is not None
    ]
    m3 = _mean(m3_values)

    candidates = (
        PayoutCandidate("法1 DPS/EPS", _mean(m1_values), "每股股息/每股收益"),
        PayoutCandidate("法2 现金流", _mean(m2_values), "现金分红/归母净利润"),
        PayoutCandidate("法3 事件合计", m3, "分红事件/归母净利润"),
    )
    present = [candidate for candidate in candidates if candidate.value is not None]
    if not present:
        return PayoutCrosscheck(candidates, None, "无", False, "三种口径均不可用")

    values = [candidate.value for candidate in present if candidate.value is not None]
    spread = _relative_spread(values)
    dps_values = [e.dps for e in reliable_events if e.dps > 0]
    repeated_dps = len(dps_values) >= 3 and len(set(dps_values)) == 1

    m1_candidate = candidates[0]
    m2_candidate = candidates[1]
    m3_candidate = candidates[2]

    # 法2 is an upper bound (it includes interest/minority distributions), so
    # judge reliability on the two shareholder-level methods (法1/法3) first.
    if m1_candidate.value is not None and m3_candidate.value is not None:
        core_spread: Decimal | None = abs(m1_candidate.value - m3_candidate.value) / max(
            abs(m1_candidate.value), abs(m3_candidate.value), Decimal("1e-9")
        )
    else:
        core_spread = spread

    note = ""
    if core_spread is not None and core_spread > Decimal("0.15"):
        label = (
            "法1/法3"
            if m1_candidate.value is not None and m3_candidate.value is not None
            else "可用口径"
        )
        note = f"{label} 相对差 {core_spread * 100:.1f}% > 15%"
    elif spread is not None and spread > Decimal("0.15"):
        note = "法2 含利息/少数股东股利，属上界；法1/法3 一致"
    if repeated_dps:
        note = (note + "；" if note else "") + "DPS 在多个年度重复，疑似供应商填充错误"
    reliable = core_spread is None or core_spread <= Decimal("0.15")

    # Event totals are the canonical dividend record: they are the actual cash
    # paid to common shareholders. The cash-flow line is an upper bound (it
    # also contains interest/minority distributions), so it is a cross-check,
    # not the default.
    if m3_candidate.value is not None:
        return PayoutCrosscheck(candidates, m3_candidate.value, m3_candidate.label, reliable, note)
    if m2_candidate.value is not None:
        return PayoutCrosscheck(candidates, m2_candidate.value, m2_candidate.label, reliable, note)
    return PayoutCrosscheck(
        candidates, m1_candidate.value, m1_candidate.label, reliable, note or "仅 DPS/EPS 可用"
    )


# ---------------------------------------------------------------------------
# G grid (v2 §17.12)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GRow:
    g: Decimal
    maintenance_capex: Decimal | None
    owner_earnings: Decimal | None
    band: str


def capex_da_ratio(
    capex: Mapping[int, Decimal], da: Mapping[int, Decimal], years: int = 5
) -> Decimal | None:
    ratios = [
        abs(capex[year]) / da[year]
        for year in sorted(set(capex) & set(da))[-years:]
        if da[year] and da[year] > 0 and capex.get(year) is not None
    ]
    if not ratios:
        return None
    return Decimal(str(median(float(value) for value in ratios)))


def g_grid(
    net_income: Decimal | None,
    da: Decimal | None,
    ratio: Decimal | None,
    cfg: ReturnsConfig,
) -> tuple[tuple[GRow, ...], GRow, str]:
    """Return all 12 G rows, the selected row, and the selection reason."""
    if net_income is None:
        fallback = GRow(cfg.g_default, None, None, "不可用")
        return (), fallback, "归母净利润缺失"
    if da is None or da <= 0:
        fallback = GRow(cfg.g_default, Decimal("0"), net_income, "无D&A")
        return (fallback,), fallback, "折旧摊销缺失，G 不影响 OE"

    rows: list[GRow] = []
    g = Decimal("0.7")
    while g <= Decimal("1.8001"):
        maintenance = da * g
        rows.append(GRow(g, maintenance, net_income + da - maintenance, "网格"))
        g = (g + Decimal("0.1")).quantize(Decimal("0.1"))

    if ratio is None:
        selected_g = cfg.g_default
        reason = "Capex/D&A 不可用，使用默认 G"
    elif ratio < Decimal("0.9"):
        selected_g = cfg.g_light
        reason = f"Capex/D&A 中位数 {ratio:.2f} < 0.9，按轻资产 G"
    elif ratio < Decimal("1.3"):
        selected_g = cfg.g_mid
        reason = f"Capex/D&A 中位数 {ratio:.2f} 在 0.9–1.3，按中等资产 G"
    else:
        selected_g = cfg.g_heavy
        reason = f"Capex/D&A 中位数 {ratio:.2f} ≥ 1.3，按重资产 G"

    selected = next((row for row in rows if row.g == selected_g), None)
    if selected is None:
        maintenance = da * selected_g
        selected = GRow(
            selected_g, maintenance, net_income + da - maintenance, "自定义"
        )
    return tuple(rows), selected, reason


# ---------------------------------------------------------------------------
# AA variants and lambda
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AAVariant:
    label: str
    value: Decimal


def aa_variants(fcf: Mapping[int, Decimal]) -> tuple[AAVariant, ...]:
    values = [value for _, value in sorted(fcf.items())]
    if not values:
        return ()
    aa_2y = _mean(values[-2:])
    aa_all = _mean(values)
    if len(values) >= 4:
        trimmed = sorted(values)[1:-1]
        aa_excl = _mean(trimmed) if trimmed else aa_all
    else:
        aa_excl = aa_all
    variants: list[AAVariant] = []
    for label, value in (("AA_2y", aa_2y), ("AA_all", aa_all), ("AA_excl", aa_excl)):
        if value is not None:
            variants.append(AAVariant(label, value))
    return tuple(variants)


def operating_lambda(
    revenue: Mapping[int, Decimal],
    surplus: Mapping[int, Decimal],
    *,
    years: int = 3,
) -> tuple[Decimal | None, str]:
    """Median Δsurplus / Δrevenue over the most recent overlapping years."""
    years_sorted = sorted(set(revenue) & set(surplus))
    if len(years_sorted) < 2:
        return None, "收入/结余年份不足"
    pairs: list[Decimal] = []
    for previous, current in zip(years_sorted, years_sorted[1:]):
        delta_revenue = revenue[current] - revenue[previous]
        delta_surplus = surplus[current] - surplus[previous]
        if delta_revenue == 0:
            continue
        pairs.append(delta_surplus / delta_revenue)
    if not pairs:
        return None, "收入无变化，λ 不可估"
    recent = pairs[-years:]
    lam = Decimal(str(median(float(value) for value in recent)))
    if lam <= 0:
        return lam, "λ ≤ 0，外推方向不稳定"
    if lam > 3:
        return lam, "λ > 3，外推可靠性低"
    if len(recent) < 2:
        return lam, "样本不足，λ 仅供参考"
    return lam, ""


def revenue_sensitivity(
    base_aa: Decimal | None,
    base_revenue: Decimal | None,
    lam: Decimal | None,
    *,
    payout_pct: Decimal,
    tax_pct: Decimal,
    market_cap: Decimal,
    ii_pct: Decimal,
    ks: Sequence[Decimal] = (Decimal("1.0"), Decimal("0.9"), Decimal("0.8"), Decimal("0.7")),
) -> tuple[tuple[Decimal, Decimal | None, Decimal | None], ...]:
    """λ-based GG scenarios and the break-even revenue multiple."""
    if (
        base_aa is None
        or base_revenue is None
        or lam is None
        or lam <= 0
        or market_cap <= 0
        or payout_pct <= 0
    ):
        return ()
    factor = payout_pct / Decimal("100") * (Decimal("1") - tax_pct / Decimal("100"))
    rows: list[tuple[Decimal, Decimal | None, Decimal | None]] = []
    for k in ks:
        aa_k = base_aa + lam * (k - Decimal("1")) * base_revenue
        gg = aa_k * factor / market_cap * Decimal("100")
        rows.append((k, aa_k, gg))
    return tuple(rows)


def break_even_revenue_multiple(
    base_aa: Decimal | None,
    base_revenue: Decimal | None,
    lam: Decimal | None,
    *,
    payout_pct: Decimal,
    tax_pct: Decimal,
    market_cap: Decimal,
    ii_pct: Decimal,
) -> Decimal | None:
    if (
        base_aa is None
        or base_revenue is None
        or lam is None
        or lam <= 0
        or base_revenue <= 0
        or payout_pct <= 0
        or market_cap <= 0
    ):
        return None
    factor = payout_pct / Decimal("100") * (Decimal("1") - tax_pct / Decimal("100"))
    required_aa = ii_pct / Decimal("100") * market_cap / factor
    return Decimal("1") + (required_aa - base_aa) / (lam * base_revenue)


# ---------------------------------------------------------------------------
# Confidence (v2 5-dimension extrapolation rating)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Confidence:
    overall: str
    dimensions: tuple[tuple[str, str, str], ...]


def _level(value: Decimal | None, high: Decimal, medium: Decimal, *, lower_is_better: bool = True) -> str:
    if value is None:
        return "low"
    if lower_is_better:
        return "high" if value < high else ("medium" if value < medium else "low")
    return "high" if value >= high else ("medium" if value >= medium else "low")


def confidence_rating(
    *,
    revenue_cv: Decimal | None,
    payout_years: int,
    fcf_positive_years: int,
    history_years: int,
    hh: Decimal | None,
) -> Confidence:
    dimensions = (
        ("收入波动率", _level(revenue_cv, Decimal("10"), Decimal("25")), "CV，越低越稳"),
        (
            "支付率覆盖",
            "high" if payout_years >= 3 else ("medium" if payout_years == 2 else "low"),
            f"{payout_years} 年",
        ),
        (
            "FCF 为正年数",
            "high" if fcf_positive_years >= 4 else ("medium" if fcf_positive_years >= 2 else "low"),
            f"{fcf_positive_years} 年",
        ),
        ("粗算偏差 |HH|", _level(abs(hh) if hh is not None else None, Decimal("1"), Decimal("3")), "pct"),
        (
            "历史长度",
            "high" if history_years >= 5 else ("medium" if history_years >= 3 else "low"),
            f"{history_years} 年",
        ),
    )
    levels = [level for _, level, _ in dimensions]
    if levels.count("low") >= 2:
        overall = "low"
    elif levels.count("high") >= 4 and "low" not in levels:
        overall = "high"
    else:
        overall = "medium"
    return Confidence(overall, dimensions)
