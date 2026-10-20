"""Deterministic four-factor engine (1A / 1B / 2 / 3 / 4).

Only rules that can be computed from the data pack are evaluated here.
Qualitative checks are emitted as ``unknown`` instead of being guessed; the
LLM layer (milestone M5) fills them with evidence, and the report marks them.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Mapping, Sequence

from ..config import Settings
from ..data.protocol import StatementRow
from ..metrics import cashflow
from ..metrics import dividends as div_metrics
from ..metrics import grids, owner_earnings, returns, statements, valuation
from ..qualitative import Qualitative
from ..types import DividendEvent, Money, StockCode


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str  # pass | veto | unknown | info
    detail: str


@dataclass(frozen=True, slots=True)
class FactorResult:
    key: str
    title: str
    passed: bool | None
    checks: tuple[Check, ...] = ()
    metrics: tuple[tuple[str, str], ...] = ()
    values: tuple[tuple[str, Decimal | None], ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FactorContext:
    code: StockCode
    rows: Sequence[StatementRow]
    dividends: Sequence[DividendEvent]
    market_cap: Money
    shares: Decimal
    price: Decimal | None
    rf_pct: Decimal
    tax_pct: Decimal
    settings: Settings
    snapshot: valuation.ValuationSnapshot
    diluted_shares: Decimal | None = None
    closes: Sequence[Decimal] = ()
    audit: Sequence[dict[str, object]] = field(default_factory=tuple)
    qualitative: Qualitative | None = None
    payout_reliable: bool = True
    pledge_pct: Decimal | None = None
    parent_cash: Decimal | None = None
    buyback: Money | None = None
    sbc: Money | None = None
    pdf_cash_bridge: Mapping[int, Mapping[str, str | None]] | None = None
    decisions: Mapping[str, str] = field(default_factory=dict)


def _pct(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}%"


def _x(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}x"


def _decision_decimal(ctx: FactorContext, key: str) -> Decimal | None:
    raw = ctx.decisions.get(key)
    if raw is None:
        return None
    try:
        return Decimal(str(raw).strip())
    except Exception as exc:  # invalid decision is a hard error
        raise ValueError(f"decision {key}: invalid decimal {raw!r}") from exc


def _m(value: Decimal | None) -> str:
    return "—" if value is None else f"{value / Decimal('1000000'):,.2f}"


def _median(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return Decimal(str(statistics.median(float(v) for v in values)))


def _latest(series: dict[int, Decimal]) -> Decimal | None:
    return series[max(series)] if series else None


def _trend(values: Sequence[Decimal]) -> str:
    if len(values) < 2:
        return "数据不足"
    if all(b < a for a, b in zip(values, values[1:])):
        return "连续下降"
    if all(b > a for a, b in zip(values, values[1:])):
        return "连续上升"
    return "波动"


def run(ctx: FactorContext) -> dict[str, FactorResult]:
    rows = ctx.rows
    income = statements.net_income(rows)
    revenue = statements.revenue(rows)
    fcf = statements.fcf_series(rows)
    da = statements.da_series(rows)
    debt = statements.interest_bearing_debt(rows)
    equity = statements.equity(rows)
    cash = statements.cash_and_equivalents(rows)
    years = sorted(income)[-5:]
    payouts = div_metrics.payout_by_year(ctx.dividends, income, shares=ctx.shares)
    mean_payout, _ = div_metrics.mean_payout(payouts)
    eps = statements.annual_series(rows, "income", "basic_eps")
    cash_dividends = statements.annual_series(rows, "cashflow", "c_pay_dist_dpcp_int_exp")
    payout_check = grids.payout_crosscheck(
        ctx.dividends, income, eps=eps, shares=ctx.shares, cash_dividends=cash_dividends
    )
    if payout_check.recommended is not None:
        mean_payout = payout_check.recommended
    # A no-dividend company is not "unreliable"; a company with events whose
    # three payout methods disagree is.
    payout_reliable = ctx.payout_reliable and (
        payout_check.reliable or not ctx.dividends
    )

    latest = years[-1] if years else None
    c = income.get(latest) if latest else None
    d = da.get(latest) if latest else None
    capex = statements.annual_series(rows, "cashflow", "c_pay_acq_const_fiolta")
    receivable = statements.annual_series(rows, "balance", "accounts_receiv")
    capex_ratio = grids.capex_da_ratio(capex, da)
    g_rows, g_row, g_reason = grids.g_grid(
        c, d, capex_ratio, ctx.settings.returns
    )
    g_decision = _decision_decimal(ctx, "g")
    if g_decision is not None:
        selected_g = next((row for row in g_rows if row.g == g_decision), None)
        if selected_g is None:
            raise ValueError(f"decision g: {g_decision} is not in the G grid")
        g_row = selected_g
        g_reason = f"研究决策 G={_decimal(g_decision)}"

    # ---- Factor 2: crude return --------------------------------------
    ii = returns.threshold_ii(ctx.rf_pct, ctx.code, ctx.settings.returns)
    if "payout" in ctx.decisions:
        payout_decision = _decision_decimal(ctx, "payout")
        payout_candidates = {
            candidate.value
            for candidate in payout_check.candidates
            if candidate.value is not None
        }
        if payout_decision is None or payout_decision not in payout_candidates:
            raise ValueError(
                f"decision payout: {ctx.decisions['payout']} is not a payout candidate"
            )
        mean_payout = payout_decision
    oe = (c + d - d * g_row.g) if c is not None and d is not None else c
    oe_normalized, oe_years = owner_earnings.normalized_owner_earnings_detail(
        rows, g=g_row.g
    )
    oe_used = oe_normalized if oe_normalized is not None else oe

    def crude_at(tax_pct: Decimal) -> Decimal | None:
        return (
            returns.penetration_return(
                Money(oe_used, ctx.market_cap.currency),
                mean_payout or Decimal("0"),
                tax_pct,
                ctx.buyback or Money.zero(ctx.market_cap.currency),
                ctx.market_cap,
                Decimal("1"),
            )
            if oe_used is not None
            else None
        )

    tax_pct = ctx.tax_pct
    if "tax" in ctx.decisions:
        tax_decision = _decision_decimal(ctx, "tax")
        tax_candidates = {scenario.rate for scenario in grids.tax_scenarios(ctx.code)}
        if tax_decision is None or tax_decision not in tax_candidates:
            raise ValueError(
                f"decision tax: {ctx.decisions['tax']} is not a tax scenario"
            )
        tax_pct = tax_decision

    r = crude_at(tax_pct)
    gate = returns.classify_return(r, ii, ctx.rf_pct)

    # ---- Factor 3: refined return ------------------------------------
    bridge = cashflow.build_cash_bridge(rows, pdf_bridge=ctx.pdf_cash_bridge)
    surplus = cashflow.surplus_series(bridge)
    bridge_complete, bridge_total = cashflow.coverage(bridge)
    bridge_derived = sum(1 for item in bridge.values() if item.source == "derived_bridge")
    bridge_fallback = sum(1 for item in bridge.values() if item.source == "ocf_fallback")
    aa_source_base = cashflow.bridge_label(bridge)
    aa_all = grids.aa_variants(surplus) if surplus else grids.aa_variants(fcf)
    aa = aa_all[0].value if aa_all else None
    aa_source = f"{aa_all[0].label}（{aa_source_base}）" if aa_all else "不可用"
    if "aa" in ctx.decisions:
        aa_decision = str(ctx.decisions["aa"]).strip()
        selected_aa = next((row for row in aa_all if row.label == aa_decision), None)
        if selected_aa is None:
            raise ValueError(f"decision aa: {aa_decision} is not an AA variant")
        aa = selected_aa.value
        aa_source = f"{selected_aa.label}（{aa_source_base}）"
    sbc_amount = ctx.sbc.amount if ctx.sbc is not None else Decimal("0")
    aa_net = (aa - sbc_amount) if aa is not None else None

    def refined_at(tax_pct: Decimal) -> Decimal | None:
        return (
            returns.penetration_return(
                Money(aa_net, ctx.market_cap.currency),
                mean_payout or Decimal("0"),
                tax_pct,
                ctx.buyback or Money.zero(ctx.market_cap.currency),
                ctx.market_cap,
                Decimal("1"),
            )
            if aa_net is not None
            else None
        )

    gg = refined_at(tax_pct)
    hh = (r - gg) if r is not None and gg is not None else None
    margin = (gg - ii) if gg is not None else None
    tax_rows = [
        (scenario.label, scenario.rate, crude_at(scenario.rate), refined_at(scenario.rate))
        for scenario in grids.tax_scenarios(ctx.code)
    ]

    lam_series = surplus if surplus else fcf
    lam, lam_note = grids.operating_lambda(revenue, lam_series)
    effective_lam = lam if lam is not None and lam > 0 else None
    sensitivity = grids.revenue_sensitivity(
        aa,
        revenue.get(latest) if latest else None,
        effective_lam,
        payout_pct=mean_payout or Decimal("0"),
        tax_pct=tax_pct,
        market_cap=ctx.market_cap.amount,
        ii_pct=ii,
    )
    k_star = grids.break_even_revenue_multiple(
        aa,
        revenue.get(latest) if latest else None,
        effective_lam,
        payout_pct=mean_payout or Decimal("0"),
        tax_pct=tax_pct,
        market_cap=ctx.market_cap.amount,
        ii_pct=ii,
    )
    scenario_k = Decimal("1.0")
    if "scenario" in ctx.decisions:
        scenario_k = _decision_decimal(ctx, "scenario") or Decimal("1.0")
        if scenario_k not in {Decimal("0.9"), Decimal("0.8"), Decimal("0.7")}:
            raise ValueError(
                f"decision scenario: {scenario_k} is not a supported k"
            )
    scenario_gg = None
    for row_k, _row_aa, row_gg in sensitivity:
        if row_k == scenario_k:
            scenario_gg = row_gg
            break
    if scenario_gg is None and gg is not None:
        scenario_gg = gg * scenario_k

    # ---- Factor 1A ----------------------------------------------------
    checks_1a: list[Check] = []
    if ctx.audit:
        opinion = str(ctx.audit[0].get("audit_result", "")).strip()
        ok = "标准无保留" in opinion
        checks_1a.append(
            Check("审计意见", "pass" if ok else "veto", opinion or "空值")
        )
        agencies = [
            str(a.get("audit_agency"))
            for a in ctx.audit[:5]
            if a.get("audit_agency")
        ]
        transitions = sum(1 for a, b in zip(agencies, agencies[1:]) if a != b)
        chain = list(dict.fromkeys(agencies))
        checks_1a.append(
            Check(
                "频繁更换审计师",
                "veto" if transitions >= 2 else "pass",
                f"{' → '.join(chain) or '无数据'}（更换 {transitions} 次）",
            )
        )
    else:
        checks_1a.append(Check("审计意见", "unknown", "未取到审计数据"))
        checks_1a.append(Check("频繁更换审计师", "unknown", "未取到审计数据"))
    if ctx.pledge_pct is None:
        checks_1a.append(Check("控股股东质押率", "unknown", "未取到质押数据"))
    else:
        checks_1a.append(
            Check(
                "控股股东质押率",
                "veto" if ctx.pledge_pct > Decimal("70") else "pass",
                f"{ctx.pledge_pct:.2f}%（阈值 70%）",
            )
        )
    for name in ("财务造假或重大违规前科", "看不懂", "商业模式未被验证", "控股股东重大负面信号"):
        if name == "商业模式未被验证":
            checks_1a.append(Check(name, "unknown", "需人工/LLM 判断"))
            continue
        module = {
            "财务造假或重大违规前科": "fraud",
            "看不懂": "understandability",
            "控股股东重大负面信号": "controller",
        }[name]
        checks_1a.append(
            _qualitative_check(name, module, ctx.qualitative, ok_status="pass")
        )

    veto_1a = any(c.status == "veto" for c in checks_1a)
    passed_1a = False if veto_1a else None

    # ---- Factor 1B (observations, not judgments) ----------------------
    capex_da = [
        abs(capex[y]) / da[y]
        for y in years
        if y in capex and y in da and da[y] > 0
    ]
    intensity = _median(capex_da)
    if intensity is None:
        label = "无法判断"
    elif intensity < Decimal("0.9"):
        label = "轻资产"
    elif intensity < Decimal("1.3"):
        label = "中等"
    else:
        label = "重资产"

    ar_ratio = (
        receivable[latest] / revenue[latest] * Decimal("100")
        if latest in receivable and latest in revenue and revenue[latest] > 0
        else None
    )
    revenue_values = [revenue[y] for y in years if y in revenue]
    if len(revenue_values) >= 2:
        mean_rev = sum(revenue_values) / Decimal(len(revenue_values))
        cv = (
            Decimal(str(statistics.pstdev(float(v) for v in revenue_values))) / mean_rev
            * Decimal("100")
            if mean_rev > 0
            else None
        )
    else:
        cv = None

    fcf_positive_years = sum(1 for value in fcf.values() if value > 0)
    confidence = grids.confidence_rating(
        revenue_cv=cv,
        payout_years=sum(1 for value in payouts.values() if value is not None),
        fcf_positive_years=fcf_positive_years,
        history_years=len(years),
        hh=hh,
    )

    consolidated_cash = cash.get(latest) if latest else None
    parent_cash_ratio = (
        ctx.parent_cash / consolidated_cash
        if ctx.parent_cash is not None and consolidated_cash not in (None, 0)
        else None
    )
    checks_1b = [
        Check("资本消耗强度", "info", f"Capex/D&A 中位数 {_x(intensity)} → {label}"),
        Check("收款模式", "info", f"应收账款/营收 {_pct(ar_ratio)}"),
        Check("周期性", "info", f"近 5 年营收变异系数 {_pct(cv)}"),
        Check("商誉占比", "info", f"{_pct(ctx.snapshot.goodwill_ratio)}"),
        Check(
            "现金上游障碍",
            "info" if parent_cash_ratio is None else ("pass" if parent_cash_ratio >= Decimal("0.5") else "veto"),
            "未取到母公司现金"
            if parent_cash_ratio is None
            else f"母公司现金/合并现金 {parent_cash_ratio * 100:.1f}%"
            + ("（<50%，现金可能滞留子公司）" if parent_cash_ratio < Decimal("0.5") else ""),
        ),
        _qualitative_check("护城河与竞争格局", "moat", ctx.qualitative, veto_on_negative=False),
        _qualitative_check("管理层与治理", "management", ctx.qualitative),
        _qualitative_check("监管与政策", "policy", ctx.qualitative, veto_on_negative=False),
    ]
    management_bad = any(
        c.name == "管理层与治理" and c.status == "veto" for c in checks_1b
    )
    cash_upstream_bad = any(
        c.name == "现金上游障碍" and c.status == "veto" for c in checks_1b
    )
    passed_1b = (
        False
        if management_bad or cash_upstream_bad
        else (None if any(c.status == "unknown" for c in checks_1b) else True)
    )

    # ---- Factor 4 -----------------------------------------------------
    trap_checks: list[Check] = []
    fcf_values = [fcf[y] for y in sorted(fcf)[-3:]]
    decline_2y = (
        len(fcf_values) >= 3
        and fcf_values[-1] < fcf_values[-2] < fcf_values[-3]
        and fcf_values[-1] < fcf_values[-3] * Decimal("0.85")
    )
    trap_checks.append(
        Check(
            "现金流趋势性恶化",
            "veto" if decline_2y else "pass",
            " → ".join(_m(v) for v in fcf_values) if fcf_values else "数据不足",
        )
    )
    trap_checks.append(
        Check(
            "分配意愿存疑",
            "veto" if mean_payout is not None and mean_payout < Decimal("30") else "pass",
            f"支付率均值 {_pct(mean_payout)}",
        )
    )
    trap_checks.append(
        Check(
            "杠杆过高",
            "veto" if ctx.snapshot.net_debt_ebitda and ctx.snapshot.net_debt_ebitda > 4 else "pass",
            f"净负债/EBITDA {_x(ctx.snapshot.net_debt_ebitda)}",
        )
    )
    trap_checks.append(_qualitative_trap("护城河正在收窄", "moat", ctx.qualitative))
    trap_checks.append(_qualitative_trap("行业结构性衰退", "policy", ctx.qualitative))
    trap_checks.append(_qualitative_trap("管理层损害价值", "management", ctx.qualitative))
    traps = sum(1 for c in trap_checks if c.status == "veto")

    price = ctx.price
    percentile = (
        Decimal(sum(1 for v in ctx.closes if v < price)) / Decimal(len(ctx.closes)) * Decimal("100")
        if price is not None and ctx.closes
        else None
    )
    target = (
        price * gg / ii if price is not None and gg is not None and ii > 0 else None
    )

    # Floor-price constraint: a rich premium or an unstable composite caps the verdict.
    trad = statements.annual_series(rows, "balance", "trad_asset")
    dps_by_year: dict[int, Decimal] = {}
    for event in ctx.dividends:
        if event.dps_reliable:
            dps_by_year[event.fiscal_year] = (
                dps_by_year.get(event.fiscal_year, Decimal("0")) + event.dps
            )
    recent_dps = sorted(dps_by_year)[-3:]
    avg_dps = (
        sum((dps_by_year[y] for y in recent_dps), Decimal("0")) / Decimal(len(recent_dps))
        if recent_dps
        else None
    )
    recent_fcf_all = dict(sorted(fcf.items())[-5:])
    min_fcf = (
        min(recent_fcf_all.values())
        if recent_fcf_all and min(recent_fcf_all.values()) > 0
        else None
    )
    baselines = valuation.five_baselines(
        cash=cash.get(latest) if latest else None,
        trad_assets=trad.get(latest) if latest else None,
        debt=debt.get(latest) if latest else None,
        equity=equity.get(latest) if latest else None,
        shares=ctx.diluted_shares or ctx.shares,
        closes=ctx.closes,
        average_dps=avg_dps,
        min_fcf=min_fcf,
        rf_pct=ctx.rf_pct,
        dividend_floor_pct=ctx.settings.valuation.dividend_discount_floor,
    )
    composite, stats = valuation.choose_composite(
        baselines,
        ctx.settings.valuation.composite_method,
        ctx.settings.valuation.divergence_threshold,
    )
    floor_premium = (
        valuation.premium(price, composite) if price is not None and composite else None
    )

    if gg is None or margin is None:
        position, verdict = "观察仓位", "观察"
    elif margin < Decimal("0"):
        position, verdict = "不建仓", "排除"
    elif traps >= 2 and margin < Decimal("1.5"):
        position, verdict = "不建仓", "排除"
    elif margin >= Decimal("1.5"):
        if confidence.overall == "high" and traps == 0:
            position, verdict = "标准仓位", "买入"
        elif traps <= 1:
            position, verdict = "70%", "买入"
        else:
            position, verdict = "观察仓位", "观察"
    elif margin >= Decimal("0.5"):
        if confidence.overall == "high" and traps == 0:
            position, verdict = "50%", "观察"
        else:
            position, verdict = "观察仓位", "观察"
    else:
        position, verdict = "观察仓位", "观察"

    caps: list[str] = []
    if floor_premium is not None:
        if floor_premium > Decimal("150"):
            caps.append(f"底价溢价 {floor_premium:.2f}% > 150%")
        elif stats.status == "divergent":
            caps.append(f"底价口径分歧（均值/中位数偏离 {stats.divergence:.2f}%）")
    elif stats.status == "unavailable":
        caps.append("底价不可用")
    if not payout_reliable:
        caps.append("支付率三法口径冲突（法2 含利息/少数股东股利，属上界）")
    if caps and verdict == "买入":
        verdict, position = "观察", "观察仓位"

    passed_4 = verdict != "排除"

    return {
        "1A": FactorResult(
            key="1A",
            title="五分钟快筛",
            passed=passed_1a,
            checks=tuple(checks_1a),
            notes=(
                f"含 {sum(1 for c in checks_1a if c.status == 'unknown')} 项检查未自动验证，"
                "报告中标注为 unknown。",
            ),
        ),
        "1B": FactorResult(
            key="1B",
            title="深度定性（可计算部分）",
            passed=passed_1b,
            checks=tuple(checks_1b),
            values=(
                ("capex_da_ratio", intensity),
                ("ar_ratio", ar_ratio),
                ("revenue_cv", cv),
                ("parent_cash_ratio", parent_cash_ratio * 100 if parent_cash_ratio is not None else None),
            ),
            notes=("护城河、管理层、政策来自 evidence-backed 定性输入；缺失即为 unknown。",),
        ),
        "2": FactorResult(
            key="2",
            title="穿透回报率粗算",
            passed=gate in ("pass", "marginal"),
            checks=(
                Check("分配能力", "pass" if sum(1 for v in fcf.values() if v > 0) >= 3 else "veto",
                      f"近 {len(fcf)} 年中 {sum(1 for v in fcf.values() if v > 0)} 年 FCF 为正"),
                Check("回报率门槛", gate, f"R={_pct(r)} vs II={_pct(ii)}"),
                Check(
                    "税档敏感性",
                    "info",
                    "R "
                    + " / ".join(f"{label}={_pct(value)}" for label, _rate, value, _gg in tax_rows),
                ),
            ),
            metrics=(
                ("Owner Earnings", f"{_m(oe_used)} 百万元（{len(oe_years)} 年正常化）")
                if oe_normalized is not None
                else ("Owner Earnings", f"{_m(oe)} 百万元（当期）"),
                ("维持性 Capex 系数 G", f"{g_row.g}（{g_reason}）"),
                ("支付率 M", f"{_pct(mean_payout)}（{payout_check.recommended_label}）"),
                ("股息税率 Q", _pct(tax_pct)),
                ("回购 O", f"{_m(ctx.buyback.amount) if ctx.buyback else 0} 百万元"),
                ("粗算回报率 R", _pct(r)),
                ("门槛 II", _pct(ii)),
            ),
            values=(
                ("r", r),
                ("ii", ii),
                ("owner_earnings", oe_used),
                ("g", g_row.g),
                ("payout", mean_payout),
                ("owner_earnings_m", oe_used / Decimal("1000000") if oe_used is not None else None),
                *(
                    (f"payout.candidate.{index}", candidate.value)
                    for index, candidate in enumerate(payout_check.candidates)
                ),
                ("payout.spread", _payout_spread(payout_check)),
                *((f"g.candidate.{index}", row.g) for index, row in enumerate(g_rows)),
            ),
            notes=(
                f"G 由 Capex/D&A 强度选择：{g_reason}；税档："
                + " / ".join(
                    f"{label} {_pct(value)}" for label, _rate, value, _gg in tax_rows
                )
                + "（结论按当前适用税率）。",
                f"支付率三法：{_payout_note(payout_check)}。",
            ),
        ),
        "3": FactorResult(
            key="3",
            title="穿透回报率精算（现金桥）",
            passed=aa is not None and aa > 0,
            checks=(
                Check("现金结余 AA", "pass" if aa_net and aa_net > 0 else "veto",
                      f"{aa_source} = {_m(aa_net)} 百万元" + ("（已扣 SBC）" if sbc_amount else "")),
                Check("股份支付 SBC", "info" if sbc_amount else "unknown",
                      f"{_m(sbc_amount)} 百万元" if sbc_amount else "未取得 SBC"),
                Check("现金桥完整度", "pass" if bridge_complete >= 3 else "unknown",
                      f"{bridge_complete}/{bridge_total} 年完整现金桥；"
                      f"{bridge_derived} 年推导桥；{bridge_fallback} 年 OCF 回退"),
                Check("FCF 一致性", "pass" if sum(1 for v in fcf.values() if v > 0) >= 3 else "veto",
                      f"{sum(1 for v in fcf.values() if v > 0)}/{len(fcf)} 年为正"),
                Check("收入敏感性", "info" if sensitivity else "unknown",
                      f"λ={_decimal(effective_lam)}；{lam_note or 'λ 可用'}"),
            ),
            metrics=(
                ("精算回报率 GG", _pct(gg)),
                ("粗算偏差 HH", _pct(hh)),
                ("AA 口径", aa_source),
                ("股份支付 SBC", _m(sbc_amount) if sbc_amount else "—"),
                ("稀释后股数（亿股）", f"{ctx.diluted_shares / Decimal('100000000'):,.2f}" if ctx.diluted_shares else "—"),
                (
                    "税档情景 R",
                    " / ".join(f"{label} {_pct(value)}" for label, _rate, value, _gg in tax_rows),
                ),
                (
                    "税档情景 GG",
                    " / ".join(f"{label} {_pct(value)}" for label, _rate, _r, value in tax_rows),
                ),
                ("经营杠杆 λ", _decimal(effective_lam)),
                ("收入 -10% 情景", _scenario(sensitivity, gg, Decimal("0.9"))),
                ("收入 -20% 情景", _scenario(sensitivity, gg, Decimal("0.8"))),
                ("收入 -30% 情景", _scenario(sensitivity, gg, Decimal("0.7"))),
                ("临界收入倍数 k*", _decimal(k_star)),
                *(
                    (
                        ("悲观情景 k", _decimal(scenario_k)),
                        ("悲观情景 GG", _pct(scenario_gg)),
                    )
                    if "scenario" in ctx.decisions
                    else ()
                ),
            ),
            values=(
                ("gg", gg),
                ("scenario.k", scenario_k),
                ("scenario.gg", scenario_gg),
                ("aa", aa),
                ("aa_m", aa / Decimal("1000000") if aa is not None else None),
                ("aa_net", aa_net),
                ("aa_net_m", aa_net / Decimal("1000000") if aa_net is not None else None),
                ("sbc", sbc_amount),
                ("sbc_m", sbc_amount / Decimal("1000000") if sbc_amount else Decimal("0")),
                ("hh", hh),
                *((f"aa.candidate.{index}", row.value) for index, row in enumerate(aa_all)),
                ("lambda", effective_lam),
                ("k_star", k_star),
                ("scenario_gg_10", gg * Decimal("0.9") if gg is not None else None),
                ("scenario_gg_20", gg * Decimal("0.8") if gg is not None else None),
                ("scenario_gg_30", gg * Decimal("0.7") if gg is not None else None),
                *((f"tax_r_{index}", row[2]) for index, row in enumerate(tax_rows)),
                *((f"tax_gg_{index}", row[3]) for index, row in enumerate(tax_rows)),
                *((f"scenario_gg_{index}", row[2]) for index, row in enumerate(sensitivity)),
            ),
            notes=(
                "AA 优先用真实现金收入−经营流出−Capex 的现金桥；组件缺失的年份使用推导现金桥（部分）或回退 OCF−Capex。",
                "敏感性优先使用 λ 外推；λ 不可用/≤0 时按 AA 等比缩放。",
                f"AA 变体：{'、'.join(v.label for v in aa_all) or '不可用'}。",
            ),
        ),
        "4": FactorResult(
            key="4",
            title="估值与安全边际",
            passed=passed_4,
            checks=(
                *trap_checks,
                Check(
                    "外推可信度",
                    "info",
                    f"{confidence.overall}（" + "；".join(
                        f"{name}={level}" for name, level, _ in confidence.dimensions
                    ) + "）",
                ),
                Check(
                    "底价约束",
                    "veto" if caps else "pass",
                    "；".join(caps) if caps else "底价溢价与口径均在阈值内",
                ),
            ),
            metrics=(
                ("EV/EBITDA", _x(ctx.snapshot.ev_ebitda)),
                ("扣除现金 PE", _x(ctx.snapshot.cash_adj_pe)),
                ("FCF 收益率", _pct(ctx.snapshot.fcf_yield)),
                ("净负债/EBITDA", _x(ctx.snapshot.net_debt_ebitda)),
                ("商誉/总资产", _pct(ctx.snapshot.goodwill_ratio)),
                ("安全边际 KK", _pct(margin)),
                ("外推可信度", confidence.overall),
                ("价值陷阱", f"{traps} 项"),
                ("股价历史分位", _pct(percentile)),
                ("门槛对应价", _num_price(target)),
                ("底价中位数", _num_price(stats.median)),
                ("底价（采用）", _num_price(composite)),
                ("底价溢价", _pct(floor_premium)),
                ("底价口径", stats.status),
                ("仓位建议", position),
                ("结论", verdict),
            ),
            values=(
                ("margin", margin),
                ("floor", composite),
                ("floor.mean", stats.mean),
                ("floor.median", stats.median),
                ("floor.divergence", stats.divergence),
                ("premium", floor_premium),
                ("price", ctx.price),
                ("ev_ebitda", ctx.snapshot.ev_ebitda),
                ("net_debt_ebitda", ctx.snapshot.net_debt_ebitda),
                ("cash_adj_pe", ctx.snapshot.cash_adj_pe),
                ("pb", ctx.snapshot.pb),
                ("fcf_yield", ctx.snapshot.fcf_yield),
                ("dividend_yield", ctx.snapshot.dividend_yield),
                ("ebitda_margin", ctx.snapshot.ebitda_margin),
                ("goodwill_ratio", ctx.snapshot.goodwill_ratio),
                ("target", target),
                ("price_percentile", percentile),
                *(
                    (f"floor.baseline.{index}", baseline.value)
                    for index, baseline in enumerate(baselines)
                ),
            ),
            notes=(
                f"价值陷阱触发 {traps} 项（含护城河/行业/管理层三项定性陷阱，unknown 不计数）。",
                "GG ≥ II 时『门槛对应价』是上限参考，不是必须等到的买点。",
            ),
        ),
    }


def _payout_note(check: grids.PayoutCrosscheck) -> str:
    parts = [
        f"{candidate.label}={_pct(candidate.value)}"
        for candidate in check.candidates
        if candidate.value is not None
    ]
    return " / ".join(parts) + (f"；{check.note}" if check.note else "")


def _payout_spread(check: grids.PayoutCrosscheck) -> Decimal | None:
    values = [candidate.value for candidate in check.candidates if candidate.value is not None]
    if len(values) < 2:
        return None
    high = max(abs(value) for value in values)
    low = min(abs(value) for value in values)
    if high == 0:
        return None
    return (high - low) / high * Decimal("100")


def _decimal(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


def _scenario(
    sensitivity: tuple[tuple[Decimal, Decimal | None, Decimal | None], ...],
    gg: Decimal | None,
    k: Decimal,
) -> str:
    for row_k, _aa, row_gg in sensitivity:
        if row_k == k:
            return _pct(row_gg)
    if gg is None:
        return "—"
    return _pct(gg * k)


def _num_price(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}"


LABELS = {"positive": "正面", "neutral": "中性", "negative": "负面"}


def _qualitative_check(
    name: str,
    module: str,
    qualitative: Qualitative | None,
    *,
    veto_on_negative: bool = True,
    ok_status: str = "info",
) -> Check:
    item = qualitative.get(module) if qualitative else None
    if item is None or item.judgment == "unknown":
        return Check(name, "unknown", "未提供证据化判断")
    status = "veto" if (veto_on_negative and item.judgment == "negative") else ok_status
    return Check(
        name,
        status,
        f"{LABELS[item.judgment]}（置信度 {item.confidence}，{len(item.evidence)} 条证据）",
    )


def _qualitative_trap(
    name: str, module: str, qualitative: Qualitative | None
) -> Check:
    """Negative evidence is a value-trap signal; missing evidence is unknown."""
    item = qualitative.get(module) if qualitative else None
    if item is None or item.judgment == "unknown":
        return Check(name, "unknown", "未提供证据化判断（不计入陷阱）")
    if item.judgment == "negative":
        return Check(name, "veto", f"负面（置信度 {item.confidence}，{len(item.evidence)} 条证据）")
    return Check(name, "pass", f"{LABELS[item.judgment]}（置信度 {item.confidence}）")


def final_verdict(results: dict[str, FactorResult]) -> tuple[str, str]:
    if results["1A"].passed is False:
        return "排除", "因子1A 触发否决"
    if results["1B"].passed is False:
        return "排除", "因子1B 管理层触发否决"
    if results["2"].passed is False:
        return "排除", "粗算穿透回报率未过否决门"
    if results["3"].passed is False:
        return "排除", "现金结余为负"
    f4 = results["4"]
    conclusion = dict(f4.metrics).get("结论", "观察")
    if conclusion == "排除":
        return "排除", "估值未通过门槛"
    if conclusion == "买入":
        return "买入", "估值达标且未触发价值陷阱"
    return "观察", "估值或数据仍待确认"
