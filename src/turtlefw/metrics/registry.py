"""Core metric ledger for the deterministic report.

This is deliberately a small first slice: the factor headline numbers and a
handful of statement facts get stable metric IDs, formula IDs and source fact
IDs. The registry is consumed by the report composer; unmigrated report values
remain code-rendered and are visible as remaining drift.
"""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal, InvalidOperation

from ..facts import MetricPoint, MetricRegistry
from ..factors.engine import FactorContext, FactorResult
from . import dividends as div_metrics
from . import statements

_NUMBER = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def parse_number(text: str) -> Decimal | None:
    cleaned = text.replace(",", "").replace("%", "").replace("x", "").strip()
    if cleaned in {"", "—", "-", "None"}:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _display(percent: bool, value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}%" if percent else f"{value:,.2f}"


def _format(unit: str, value: Decimal | None) -> str:
    if value is None:
        return "—"
    if unit == "%":
        return f"{value:.2f}%"
    if unit == "x":
        return f"{value:,.2f}x"
    return f"{value:,.2f}"


def _from_result(
    registry: MetricRegistry,
    metric_id: str,
    name: str,
    text: str,
    *,
    unit: str,
    formula_id: str,
    period: str,
    source: tuple[str, ...] = (),
) -> None:
    value = parse_number(text)
    registry.add(
        MetricPoint(
            id=metric_id,
            name=name,
            value=value,
            unit=unit,
            period=period,
            formula_id=formula_id,
            source_fact_ids=source,
            coverage="ok" if value is not None else "missing",
            display=text,
            source_rank=3 if source else 0,
        )
    )


def _add(
    registry: MetricRegistry,
    metric_id: str,
    name: str,
    value: Decimal | None,
    *,
    unit: str,
    formula_id: str,
    period: str,
    source: tuple[str, ...] = (),
    display: str | None = None,
) -> None:
    registry.add(
        MetricPoint(
            id=metric_id,
            name=name,
            value=value,
            unit=unit,
            period=period,
            formula_id=formula_id,
            source_fact_ids=source,
            coverage="ok" if value is not None else "missing",
            display=display if display is not None else _format(unit, value),
        )
    )


def build(
    ctx: FactorContext,
    results: dict[str, FactorResult],
    *,
    composite: Decimal | None,
    premium: Decimal | None,
    stats: object | None = None,
) -> MetricRegistry:
    registry = MetricRegistry()
    years = sorted({r.period_end.year for r in ctx.rows if r.period_type == "annual"})
    latest = max(years) if years else None
    period = f"{latest}A" if latest is not None else ""
    f2 = dict(results["2"].metrics)
    f3 = dict(results["3"].metrics)
    f4 = dict(results["4"].metrics)
    typed_values: dict[str, Decimal | None] = {}
    for result in results.values():
        typed_values.update(dict(result.values))

    _from_result(
        registry,
        "r",
        "穿透回报率 R",
        f2.get("粗算回报率 R", "—"),
        unit="%",
        formula_id="returns.penetration_return",
        period=period,
        source=("cashflow.aa", "dividends.payout", "market.market_cap"),
    )
    _from_result(
        registry,
        "gg",
        "精算回报率 GG",
        f3.get("精算回报率 GG", "—"),
        unit="%",
        formula_id="returns.refined_return",
        period=period,
        source=("cashflow.aa", "cashflow.bridge"),
    )
    _from_result(
        registry,
        "ii",
        "门槛 II",
        f2.get("门槛 II", "—"),
        unit="%",
        formula_id="returns.threshold_ii",
        period=period,
    )
    _from_result(
        registry,
        "margin",
        "安全边际 KK",
        f4.get("安全边际 KK", "—"),
        unit="%",
        formula_id="returns.safety_margin",
        period=period,
        source=("gg", "ii"),
    )
    _from_result(
        registry,
        "floor",
        "底价（综合）",
        _display(False, composite),
        unit=ctx.market_cap.currency.value,
        formula_id="valuation.composite",
        period=period,
    )
    _from_result(
        registry,
        "price",
        "当前价",
        _display(False, ctx.price),
        unit=ctx.market_cap.currency.value,
        formula_id="market.price",
        period=period,
        source=("market.quote",),
    )
    _from_result(
        registry,
        "premium",
        "当前价溢价",
        _display(True, premium),
        unit="%",
        formula_id="valuation.premium",
        period=period,
        source=("price", "floor"),
    )
    _add(
        registry,
        "rf",
        "无风险利率",
        ctx.rf_pct,
        unit="%",
        formula_id="market.risk_free",
        period=period,
        source=("market.risk_free",),
    )
    for metric_id, name, value, unit in (
        ("policy.pledge_threshold", "质押率阈值", ctx.settings.screening.max_pledge_pct, "%"),
        ("policy.floor_premium_veto", "底价溢价否决阈值", Decimal("150"), "%"),
        ("policy.payout_spread", "支付率口径差阈值", Decimal("15"), "%"),
    ):
        _add(
            registry,
            metric_id,
            name,
            value,
            unit=unit,
            formula_id=f"policy.{metric_id}",
            period=period,
        )

    for metric_id in ("r", "gg", "ii", "margin"):
        if metric_id in typed_values:
            point = registry.get(metric_id)
            if point is not None:
                typed_override = typed_values[metric_id]
                registry.add(
                    replace(
                        point,
                        value=typed_override,
                        coverage="ok" if typed_override is not None else "missing",
                    )
                )

    if ctx.pledge_pct is not None:
        typed_values["pledge_pct"] = ctx.pledge_pct
    if ctx.buyback is not None and ctx.market_cap.amount:
        typed_values["buyback_ratio"] = (
            ctx.buyback.amount / ctx.market_cap.amount * Decimal("100")
        )
    if ctx.buyback is None:
        buyback_series = statements.annual_series(ctx.rows, "cashflow", "buyback")
        buyback_latest = (
            buyback_series.get(max(buyback_series)) if buyback_series else None
        )
        if buyback_latest is not None:
            _add(
                registry,
                "buyback.latest",
                "回购现金流出（报表）",
                buyback_latest,
                unit=ctx.market_cap.currency.value,
                formula_id="cashflow.buyback",
                period=period,
            )

    percent_ids = {
        "parent_cash_ratio",
        "pledge_pct",
        "buyback_ratio",
        "ar_ratio",
        "revenue_cv",
        "hh",
        "payout",
        "price_percentile",
    }
    for metric_id, typed_value in typed_values.items():
        if registry.get(metric_id) is not None:
            continue
        unit = (
            "%"
            if metric_id in percent_ids
            or metric_id.startswith(("tax_", "scenario_", "payout."))
            else ""
        )
        _add(
            registry,
            metric_id,
            metric_id,
            typed_value,
            unit=unit,
            formula_id=f"factor.{metric_id}",
            period=period,
            display=(
                f"{typed_value:.2f}%"
                if metric_id in {"pledge_pct", "buyback_ratio", "payout.spread"}
                and typed_value is not None
                else f"{typed_value:.1f}%"
                if metric_id == "parent_cash_ratio" and typed_value is not None
                else None
            ),
        )

    snapshot = ctx.snapshot
    for metric_id, name, metric_value, unit, formula in (
        ("ev_ebitda", "EV/EBITDA", snapshot.ev_ebitda, "x", "valuation.ev_ebitda"),
        ("net_debt_ebitda", "净负债/EBITDA", snapshot.net_debt_ebitda, "x", "valuation.net_debt_ebitda"),
        ("cash_adj_pe", "扣除现金 PE", snapshot.cash_adj_pe, "x", "valuation.cash_adj_pe"),
        ("pb", "P/B", snapshot.pb, "x", "valuation.pb"),
        ("fcf_yield", "FCF 收益率", snapshot.fcf_yield, "%", "valuation.fcf_yield"),
        ("dividend_yield", "股息率", snapshot.dividend_yield, "%", "valuation.dividend_yield"),
        ("ebitda_margin", "EBITDA 利润率", snapshot.ebitda_margin, "%", "valuation.ebitda_margin"),
        ("goodwill_ratio", "商誉/总资产", snapshot.goodwill_ratio, "%", "balance.goodwill_ratio"),
    ):
        _add(
            registry,
            metric_id,
            name,
            metric_value,
            unit=unit,
            formula_id=formula,
            period=period,
            source=("valuation.snapshot",),
        )

    if stats is not None:
        for metric_id, name, attr, unit, formula in (
            ("floor.mean", "底价均值", "mean", ctx.market_cap.currency.value, "valuation.mean"),
            ("floor.median", "底价中位数", "median", ctx.market_cap.currency.value, "valuation.median"),
            ("floor.divergence", "口径分歧", "divergence", "%", "valuation.divergence"),
        ):
            stat_value = getattr(stats, attr, None)
            _add(
                registry,
                metric_id,
                name,
                stat_value,
                unit=unit,
                formula_id=formula,
                period=period,
                source=("valuation.baselines",),
            )

    if latest is not None:
        income = statements.net_income(ctx.rows)
        payouts = div_metrics.payout_by_year(ctx.dividends, income, shares=ctx.shares)
        mean_payout, _ = div_metrics.mean_payout(payouts)
        _add(
            registry,
            "payout.mean",
            "三年均值支付率",
            mean_payout,
            unit="%",
            formula_id="dividends.mean_payout",
            period=period,
            source=("dividends", "net_income"),
            display=dict(results["2"].metrics).get("支付率 M"),
        )
        revenue = statements.revenue(ctx.rows)
        revenue_yoy = None
        if latest - 1 in revenue and revenue[latest - 1] > 0:
            revenue_yoy = (revenue[latest] / revenue[latest - 1] - 1) * Decimal("100")
        _add(
            registry,
            "revenue.yoy",
            "营收同比",
            revenue_yoy,
            unit="%",
            formula_id="statement.revenue_yoy",
            period=period,
            source=("revenue.latest",),
        )

    if latest is not None:
        values = {
            "revenue.latest": ("营业收入", "income", "revenue"),
            "net_income.latest": ("归母净利润", "income", "n_income_attr_p"),
            "ocf.latest": ("经营现金流", "cashflow", "n_cashflow_act"),
            "capex.latest": ("资本开支", "cashflow", "c_pay_acq_const_fiolta"),
            "equity.latest": ("归母权益", "balance", "total_hldr_eqy_exc_min_int"),
        }
        for metric_id, (name, statement, item) in values.items():
            period_value = statements.annual_series(ctx.rows, statement, item).get(latest)
            registry.add(
                MetricPoint(
                    id=metric_id,
                    name=name,
                    value=period_value,
                    unit=ctx.market_cap.currency.value,
                    period=period,
                    formula_id=f"statement.{statement}.{item}",
                    source_fact_ids=(f"statement:{period}:{statement}:{item}",),
                    coverage="ok" if period_value is not None else "missing",
                    display=_display(False, period_value),
                )
            )
        fcf = statements.fcf_series(ctx.rows).get(latest)
        registry.add(
            MetricPoint(
                id="fcf.latest",
                name="最新 FCF",
                value=fcf,
                unit=ctx.market_cap.currency.value,
                period=period,
                formula_id="cashflow.fcf",
                source_fact_ids=(f"statement:{period}:cashflow:ocf",),
                coverage="ok" if fcf is not None else "missing",
                display=_display(False, fcf),
            )
        )
        net_cash = statements.net_cash(ctx.rows, ctx.market_cap.currency).get(latest)
        registry.add(
            MetricPoint(
                id="net_cash.latest",
                name="净现金",
                value=net_cash.amount if net_cash is not None else None,
                unit=ctx.market_cap.currency.value,
                period=period,
                formula_id="balance.net_cash",
                source_fact_ids=(f"statement:{period}:balance:cash",),
                coverage="ok" if net_cash is not None else "missing",
                display=(
                    f"{net_cash.amount / Decimal('1000000'):,.2f}"
                    if net_cash is not None
                    else "—"
                ),
            )
        )
    if latest is not None:
        for item, label in (
            ("accounts_receiv", "应收账款"),
            ("inventory", "存货"),
            ("contract_liab", "合同负债"),
        ):
            series = statements.annual_series(ctx.rows, "balance", item)
            balance_value = series.get(latest)
            source = ctx.pdf_source_ids.get(item) or f"statement:{period}:balance:{item}"
            registry.add(
                MetricPoint(
                    id=item,
                    name=label,
                    value=balance_value,
                    unit=ctx.market_cap.currency.value,
                    period=period,
                    formula_id=f"balance.{item}",
                    source_fact_ids=(source,),
                    coverage="ok" if balance_value is not None else "missing",
                    display=(
                        f"{balance_value / Decimal('1000000'):,.2f}"
                        if balance_value is not None
                        else "—"
                    ),
                )
            )
        pdf_dps = ctx.pdf_values.get("dps")
        if pdf_dps:
            try:
                dps_value = Decimal(pdf_dps)
            except InvalidOperation:
                dps_value = None
            if dps_value is not None:
                registry.add(
                    MetricPoint(
                        id="dps.pdf",
                        name="PDF 每股派息",
                        value=dps_value,
                        unit="CNY/股",
                        period=period,
                        formula_id="dividends.pdf",
                        source_fact_ids=(ctx.pdf_source_ids.get("dps", "pdf:dps"),),
                        coverage="ok",
                        display=f"{dps_value:.4f}",
                    )
                )
        for row in ctx.pdf_fact_rows:
            row_item = str(row.get("item", ""))
            if row_item not in {"main_business", "capex_detail"} or not row.get("fact_id"):
                continue
            try:
                segment_value = Decimal(str(row.get("value")))
            except InvalidOperation:
                continue
            label = str(row.get("label", ""))
            registry.add(
                MetricPoint(
                    id=f"{row_item}.{label}",
                    name=f"{row_item} {label}",
                    value=segment_value,
                    unit=ctx.market_cap.currency.value,
                    period=str(row.get("period", period)),
                    formula_id=f"{row_item}.pdf",
                    source_fact_ids=(str(row["fact_id"]),),
                    coverage="ok",
                    display=f"{segment_value / Decimal('1000000'):,.2f}",
                )
            )
    return registry


REQUIRED_FOR_REPORT = ("r", "gg", "ii", "margin", "floor", "price", "premium")
