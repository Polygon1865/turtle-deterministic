"""Deterministic four-factor engine (1A / 1B / 2 / 3 / 4).

Only rules that can be computed from the data pack are evaluated here.
Qualitative checks are emitted as ``unknown`` instead of being guessed; the
LLM layer (milestone M5) fills them with evidence, and the report marks them.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Sequence

from ..config import Settings
from ..data.protocol import StatementRow
from ..metrics import dividends as div_metrics
from ..metrics import returns, statements, valuation
from ..qualitative import Qualitative
from ..types import DividendEvent, Money, StockCode

G = Decimal("1.0")  # maintenance-capex factor; framework default when no industry view


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
    closes: Sequence[Decimal] = ()
    audit: Sequence[dict] = field(default_factory=tuple)
    qualitative: Qualitative | None = None


def _pct(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}%"


def _x(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:,.2f}x"


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
    mean_payout, payout_years = div_metrics.mean_payout(payouts)

    latest = years[-1] if years else None
    c = income.get(latest) if latest else None
    d = da.get(latest) if latest else None
    capex = statements.annual_series(rows, "cashflow", "c_pay_acq_const_fiolta")
    receivable = statements.annual_series(rows, "balance", "accounts_receiv")
    goodwill = _latest(statements.annual_series(rows, "balance", "goodwill")) or Decimal("0")
    total_assets = _latest(statements.annual_series(rows, "balance", "total_assets")) or Decimal("0")

    # ---- Factor 2: crude return --------------------------------------
    ii = returns.threshold_ii(ctx.rf_pct, ctx.code, ctx.settings.returns)
    oe = (c + d - d * G) if c is not None and d is not None else c
    r = (
        returns.penetration_return(
            Money(oe, ctx.market_cap.currency),
            mean_payout or Decimal("0"),
            ctx.tax_pct,
            Money.zero(ctx.market_cap.currency),
            ctx.market_cap,
            Decimal("1"),
        )
        if oe is not None
        else None
    )
    gate = returns.classify_return(r, ii, ctx.rf_pct)

    # ---- Factor 3: refined return ------------------------------------
    recent_fcf = list(sorted(fcf.items()))[-2:]
    aa = (
        sum((v for _, v in recent_fcf), Decimal("0")) / Decimal(len(recent_fcf))
        if recent_fcf
        else None
    )
    gg = (
        returns.penetration_return(
            Money(aa, ctx.market_cap.currency),
            mean_payout or Decimal("0"),
            ctx.tax_pct,
            Money.zero(ctx.market_cap.currency),
            ctx.market_cap,
            Decimal("1"),
        )
        if aa is not None
        else None
    )
    hh = (r - gg) if r is not None and gg is not None else None
    margin = (gg - ii) if gg is not None else None

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

    checks_1b = [
        Check("资本消耗强度", "info", f"Capex/D&A 中位数 {_x(intensity)} → {label}"),
        Check("收款模式", "info", f"应收账款/营收 {_pct(ar_ratio)}"),
        Check("周期性", "info", f"近 5 年营收变异系数 {_pct(cv)}"),
        Check("商誉占比", "info", f"{_pct(ctx.snapshot.goodwill_ratio)}"),
        _qualitative_check("护城河与竞争格局", "moat", ctx.qualitative, veto_on_negative=False),
        _qualitative_check("管理层与治理", "management", ctx.qualitative),
        _qualitative_check("监管与政策", "policy", ctx.qualitative, veto_on_negative=False),
    ]
    management_bad = any(
        c.name == "管理层与治理" and c.status == "veto" for c in checks_1b
    )
    passed_1b = (
        False
        if management_bad
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

    if gg is None or margin is None:
        position, verdict = "观察", "观察"
    elif margin < 0:
        position, verdict = "不建仓", "排除"
    elif margin >= Decimal("1.5") and traps == 0:
        position, verdict = "标准仓位", "买入"
    elif margin >= Decimal("1.5"):
        position, verdict = "70%", "买入"
    elif margin >= Decimal("0.5") and traps == 0:
        position, verdict = "50%", "观察"
    else:
        position, verdict = "观察仓位", "观察"

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
            ),
            metrics=(
                ("Owner Earnings", f"{_m(oe)} 百万元"),
                ("支付率均值 M", f"{_pct(mean_payout)}（{payout_years} 年）"),
                ("粗算回报率 R", _pct(r)),
                ("门槛 II", _pct(ii)),
            ),
            notes=(f"维持性资本开支系数 G={G}；回购 O=0（未接入回购数据）。",),
        ),
        "3": FactorResult(
            key="3",
            title="穿透回报率精算",
            passed=aa is not None and aa > 0,
            checks=(
                Check("现金结余 AA", "pass" if aa and aa > 0 else "veto",
                      f"近 2 年 FCF 均值 {_m(aa)} 百万元"),
                Check("FCF 一致性", "pass" if sum(1 for v in fcf.values() if v > 0) >= 3 else "veto",
                      f"{sum(1 for v in fcf.values() if v > 0)}/{len(fcf)} 年为正"),
            ),
            metrics=(
                ("精算回报率 GG", _pct(gg)),
                ("粗算偏差 HH", _pct(hh)),
                ("收入 -10% 情景", _pct(gg * Decimal("0.9")) if gg is not None else "—"),
                ("收入 -20% 情景", _pct(gg * Decimal("0.8")) if gg is not None else "—"),
                ("收入 -30% 情景", _pct(gg * Decimal("0.7")) if gg is not None else "—"),
            ),
            notes=("敏感性按 AA 等比例缩放，未使用经营杠杆 λ。",),
        ),
        "4": FactorResult(
            key="4",
            title="估值与安全边际",
            passed=passed_4,
            checks=tuple(trap_checks),
            metrics=(
                ("EV/EBITDA", _x(ctx.snapshot.ev_ebitda)),
                ("扣除现金 PE", _x(ctx.snapshot.cash_adj_pe)),
                ("FCF 收益率", _pct(ctx.snapshot.fcf_yield)),
                ("净负债/EBITDA", _x(ctx.snapshot.net_debt_ebitda)),
                ("商誉/总资产", _pct(ctx.snapshot.goodwill_ratio)),
                ("安全边际 KK", _pct(margin)),
                ("股价历史分位", _pct(percentile)),
                ("门槛对应价", _num_price(target)),
                ("仓位建议", position),
                ("结论", verdict),
            ),
            notes=(
                f"价值陷阱触发 {traps} 项",
                "GG ≥ II 时『门槛对应价』是上限参考，不是必须等到的买点。",
            ),
        ),
    }


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
