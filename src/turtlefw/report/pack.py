"""Data-pack rendering: deterministic Markdown assembled from the bundle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from jinja2 import Environment, FileSystemLoader

from ..config import Settings
from ..data.coverage import coverage_markdown
from ..data.protocol import StatementRow
from ..facts import MetricPoint, MetricRegistry
from ..metrics import cashflow, grids, report_returns, returns, statements, valuation
from ..metrics import dividends as div_metrics
from ..metrics.dividends import average_dps
from ..pdf.hk_facts import extract as extract_hk_facts
from ..types import Currency, DividendEvent, FetchIssue, Money, StockCode
from .extras import render_extras
from .format import TEMPLATE_DIR, _m, _num, _pct, _ratio_pct, _table, _x
from .market import render_market
from .pdf_facts import apply_document_facts
from .snapshot_id import source_snapshot_id


def _series(rows: Sequence[StatementRow], statement: str, item: str) -> dict[int, Decimal]:
    return statements.annual_series(rows, statement, item)


def _week52(
    history: Sequence[dict[str, Any]], as_of: str | None = None
) -> tuple[Decimal | None, Decimal | None]:
    anchor_raw = (as_of or "").replace("-", "")
    if len(anchor_raw) < 8:
        dates = [str(r.get("trade_date", "")) for r in history if r.get("trade_date")]
        anchor_raw = max(dates) if dates else ""
    if len(anchor_raw) < 8:
        return None, None
    anchor = date(int(anchor_raw[:4]), int(anchor_raw[4:6]), int(anchor_raw[6:8]))
    cutoff = anchor.replace(year=anchor.year - 1).strftime("%Y%m%d")
    window = [r for r in history if str(r.get("trade_date", "")) >= cutoff]
    highs = [Decimal(str(r["high"])) for r in window if r.get("high") is not None]
    lows = [Decimal(str(r["low"])) for r in window if r.get("low") is not None]
    return (max(highs) if highs else None, min(lows) if lows else None)


def render_data_pack(
    code: StockCode,
    rows: Sequence[StatementRow],
    dividends: Sequence[DividendEvent],
    *,
    quote: dict[str, Any] | None,
    history: Sequence[dict[str, Any]],
    market_cap: Money,
    shares: Decimal,
    diluted_shares: Decimal | None = None,
    rf_pct: Decimal,
    settings: Settings,
    issues: Sequence[FetchIssue] = (),
    tax_pct: Decimal = Decimal("0"),
    rf_source: str = "",
    parent_cash: Decimal | None = None,
    pledge_pct: Decimal | None = None,
    buyback: Money | None = None,
    sbc: Money | None = None,
    pdf_bridge: dict[int, dict[str, str | None]] | None = None,
    holders: Sequence[Mapping[str, object]] | None = None,
    main_business: Sequence[Mapping[str, object]] | None = None,
    as_of: str | None = None,
    footnotes: Mapping[str, Any] | None = None,
    pdf_sections: Mapping[str, Any] | None = None,
    pit_note: str = "",
    decisions: Mapping[str, str] | None = None,
    snapshot_id: str | None = None,
    document_facts: list[dict[str, object]] | None = None,
    fundamental_extras: Mapping[str, Any] | None = None,
    market_extras: Mapping[str, Any] | None = None,
) -> str:
    rows = apply_document_facts(list(rows), document_facts)
    decisions = decisions or {}
    if decisions.get("tax"):
        tax_pct = Decimal(decisions["tax"])
    currency = rows[0].currency if rows else Currency.CNY
    years = sorted({r.period_end.year for r in rows if r.period_type == "annual"})[-5:]

    revenue = _series(rows, "income", "revenue")
    net_income = _series(rows, "income", "n_income_attr_p")
    eps = _series(rows, "income", "basic_eps")
    ocf = _series(rows, "cashflow", "n_cashflow_act")
    capex = _series(rows, "cashflow", "c_pay_acq_const_fiolta")
    fcf = statements.fcf_series(rows)
    da = statements.da_series(rows)
    debt = statements.interest_bearing_debt(rows)
    debt_full = statements.debt_complete(rows)
    equity = statements.equity(rows)
    cash = statements.cash_and_equivalents(rows)
    trad = _series(rows, "balance", "trad_asset")
    inventory = _series(rows, "balance", "inventory")
    accounts_receiv = _series(rows, "balance", "accounts_receiv")
    contract_liab = _series(rows, "balance", "contract_liab")
    adv_receipts = _series(rows, "balance", "adv_receipts")
    prepayments = _series(rows, "balance", "prepayments")
    net_cash = statements.net_cash(rows, currency)
    payouts = div_metrics.payout_by_year(dividends, net_income, shares=shares)
    mean_payout, payout_years = div_metrics.mean_payout(payouts)
    cash_dividends = _series(rows, "cashflow", "c_pay_dist_dpcp_int_exp")
    payout_check = grids.payout_crosscheck(
        dividends, net_income, eps=eps, shares=shares, cash_dividends=cash_dividends
    )
    if payout_check.recommended is not None:
        mean_payout = payout_check.recommended
    if decisions.get("payout"):
        mean_payout = Decimal(decisions["payout"])

    latest_year = max(years) if years else None
    latest_fcf = fcf.get(latest_year) if latest_year else None
    price = Decimal(str(quote["close"])) if quote and quote.get("close") is not None else None
    high_52w, low_52w = _week52(
        history, as_of or (str(quote.get("trade_date", "")) if quote else None)
    )
    closes = [Decimal(str(r["close"])) for r in history if r.get("close") is not None]

    ii = settings.returns.threshold(rf_pct, code)
    latest_ni = net_income.get(latest_year) if latest_year else None
    latest_da = da.get(latest_year) if latest_year else None
    capex_ratio = grids.capex_da_ratio(capex, da)
    _g_rows, g_row, g_reason = grids.g_grid(
        latest_ni, latest_da, capex_ratio, settings.returns
    )
    if decisions.get("g"):
        selected_g = Decimal(decisions["g"])
        g_matches = [row for row in _g_rows if row.g == selected_g]
        if not g_matches:
            raise ValueError(f"research decision g={selected_g} is not in the G grid")
        g_row = g_matches[0]
        g_reason = "research decision"
    sbc_amount = sbc.amount if sbc is not None else Decimal("0")
    owner_returns = report_returns.compute(
        rows,
        g=g_row.g,
        mean_payout=mean_payout,
        market_cap=market_cap,
        currency=currency,
        tax_pct=tax_pct,
        buyback=buyback,
        sbc=sbc,
        pdf_bridge=pdf_bridge,
        aa_label=decisions.get("aa"),
    )
    aa_bridge = owner_returns.bridge
    bridge_complete, bridge_total = cashflow.coverage(aa_bridge)
    aa_label = owner_returns.aa_source
    r_value = owner_returns.r
    gg_value = owner_returns.gg
    cash_bridge_rows = [
        [
            str(year),
            _m(aa_bridge[year].surplus),
            aa_bridge[year].source,
            "是" if aa_bridge[year].complete else "否",
        ]
        for year in sorted(aa_bridge)
    ]

    min_fcf_all = dict(sorted(fcf.items())[-5:])
    min_fcf = (
        min(min_fcf_all.values())
        if min_fcf_all and min(min_fcf_all.values()) > 0
        else None
    )
    avg_dps = average_dps(dividends)
    floor = valuation.compute_floor(
        cash=cash.get(latest_year) if latest_year else None,
        trad_assets=trad.get(latest_year) if latest_year else None,
        debt=debt.get(latest_year) if latest_year else None,
        equity=equity.get(latest_year) if latest_year else None,
        shares=diluted_shares or shares,
        closes=closes,
        average_dps=avg_dps,
        min_fcf=min_fcf,
        rf_pct=rf_pct,
        price=price,
        dividend_floor_pct=settings.valuation.dividend_discount_floor,
        composite_method=settings.valuation.composite_method,
        divergence_threshold=settings.valuation.divergence_threshold,
    )
    baselines = floor.baselines
    composite = floor.composite
    stats = floor.stats
    premium = floor.premium
    status_label = {"stable": "口径一致", "divergent": "口径分歧", "unavailable": "不可用"}[
        stats.status
    ]
    method_label = "中位数" if settings.valuation.composite_method == "median" else "均值"
    floor_note = (
        f"均值 {_num(stats.mean)} ｜ 中位数 {_num(stats.median)} ｜ "
        f"分歧 {_pct(stats.divergence)}（{status_label}）｜ 采用{method_label}"
    )
    if len(baselines) < 5:
        floor_note += f"；有效锚点 {len(baselines)}/5（缺失或非正已剔除）"
    if stats.status == "divergent":
        floor_note += "。均值受极值影响，建议以中位数为准，且仓位不超过「观察」。"
    elif stats.status == "unavailable":
        floor_note += "。底价不可用，不应据此判断安全边际。"

    snapshot = valuation.build_valuation(
        market_cap=market_cap.amount if market_cap.amount > 0 else None,
        cash=cash.get(latest_year) if latest_year else None,
        debt=debt.get(latest_year) if latest_year else None,
        equity=equity.get(latest_year) if latest_year else None,
        net_income=net_income.get(latest_year) if latest_year else None,
        revenue=revenue.get(latest_year) if latest_year else None,
        operate_profit=_series(rows, "income", "operate_profit").get(latest_year)
        if latest_year
        else None,
        finance_exp=_series(rows, "income", "finance_exp").get(latest_year)
        if latest_year
        else None,
        da=da.get(latest_year) if latest_year else None,
        fcf=latest_fcf,
        goodwill=_series(rows, "balance", "goodwill").get(latest_year) if latest_year else None,
        total_assets=_series(rows, "balance", "total_assets").get(latest_year)
        if latest_year
        else None,
        dps=average_dps(dividends),
        price=price,
    )

    # -- data-pack metric ledger -----------------------------------------
    pack_ledger = MetricRegistry()

    def add_metric(
        metric_id: str,
        name: str,
        value: Decimal | None,
        display: str,
        *,
        unit: str = "",
        formula: str = "",
        period: str | None = None,
    ) -> None:
        pack_ledger.add(
            MetricPoint(
                id=metric_id,
                name=name,
                value=value,
                unit=unit,
                period=period or (str(latest_year) if latest_year else ""),
                formula_id=formula,
                coverage="ok" if value is not None else "missing",
                display=display,
            )
        )

    add_metric("r", "穿透回报率 R", r_value, _pct(r_value), unit="%", formula="returns.penetration_return")
    add_metric("gg", "精算回报率 GG", gg_value, _pct(gg_value), unit="%", formula="returns.refined_return")
    add_metric("ii", "门槛 II", ii, _pct(ii), unit="%", formula="returns.threshold_ii")
    add_metric("floor", "底价（采用）", composite, _num(composite), unit=currency.value, formula="valuation.composite")
    add_metric("price", "当前价", price, _num(price), unit=currency.value, formula="market.price")
    add_metric("premium", "底价溢价", premium, _pct(premium), unit="%", formula="valuation.premium")
    add_metric("revenue.cagr", "营业收入 CAGR", statements.revenue_cagr(rows), _ratio_pct(statements.revenue_cagr(rows)), unit="%", formula="statement.revenue_cagr")
    add_metric("net_income.cagr", "归母净利润 CAGR", statements.net_income_cagr(rows), _ratio_pct(statements.net_income_cagr(rows)), unit="%", formula="statement.net_income_cagr")
    add_metric("payout.mean", "支付率均值", mean_payout, f"{_pct(mean_payout)}（{payout_years} 年）", unit="%", formula="dividends.mean_payout")
    add_metric("fcf.latest", "最新 FCF", latest_fcf, _m(latest_fcf), unit=currency.value, formula="cashflow.fcf")
    add_metric("debt.latest", "有息负债", debt.get(latest_year) if latest_year else None, _m(debt.get(latest_year) if latest_year else None), unit=currency.value, formula="balance.debt")
    latest_ocf = ocf.get(latest_year) if latest_year else None
    latest_ni = net_income.get(latest_year) if latest_year else None
    add_metric(
        "ocf_ni_ratio",
        "OCF/净利润",
        (
            latest_ocf / latest_ni * Decimal("100")
            if latest_ocf is not None and latest_ni not in (None, 0)
            else None
        ),
        _pct(
            latest_ocf / latest_ni * Decimal("100")
            if latest_ocf is not None and latest_ni not in (None, 0)
            else None
        ),
        unit="%",
        formula="cashflow.ocf_ni",
    )
    add_metric("net_cash.latest", "净现金", net_cash[latest_year].amount if latest_year in net_cash else None, _m(net_cash[latest_year].amount) if latest_year in net_cash else "—", unit=currency.value, formula="balance.net_cash")
    add_metric("floor.mean", "底价均值", stats.mean, _num(stats.mean), unit=currency.value, formula="valuation.mean")
    add_metric("floor.median", "底价中位数", stats.median, _num(stats.median), unit=currency.value, formula="valuation.median")
    add_metric("floor.divergence", "口径分歧", stats.divergence, _pct(stats.divergence), unit="%", formula="valuation.divergence")
    ten_year_low = valuation.ten_year_low(closes)
    add_metric("high_52w", "52 周最高", high_52w, _num(high_52w), unit=currency.value, formula="market.high_52w")
    add_metric("low_52w", "52 周最低", low_52w, _num(low_52w), unit=currency.value, formula="market.low_52w")
    add_metric("ten_year_low", "10 年最低", ten_year_low, _num(ten_year_low), unit=currency.value, formula="market.ten_year_low")
    add_metric("market_cap", "总市值", market_cap.amount, _m(market_cap.amount), unit=currency.value, formula="market.market_cap")
    add_metric("shares", "总股本（亿股）", shares / Decimal("100000000") if shares else None, f"{shares / Decimal('100000000'):,.2f}" if shares else "—", unit="亿股", formula="market.shares")
    add_metric("diluted_shares", "稀释后股数（亿股）", diluted_shares / Decimal("100000000") if diluted_shares else None, f"{diluted_shares / Decimal('100000000'):,.2f}" if diluted_shares else "—", unit="亿股", formula="market.diluted_shares")
    add_metric("rf", "无风险利率", rf_pct, _pct(rf_pct), unit="%", formula="market.rf")

    for year in years:
        for prefix, series, display_fn, unit in (
            ("revenue", revenue, _m, currency.value),
            ("net_income", net_income, _m, currency.value),
            ("eps", eps, lambda value: _num(value, 2), "元"),
            ("ocf", ocf, _m, currency.value),
            ("capex", capex, _m, currency.value),
            ("fcf", fcf, _m, currency.value),
            ("da", da, _m, currency.value),
            ("debt", debt, _m, currency.value),
            ("equity", equity, _m, currency.value),
            ("cash", cash, _m, currency.value),
            ("inventory", inventory, _m, currency.value),
            ("accounts_receiv", accounts_receiv, _m, currency.value),
            ("contract_liab", contract_liab, _m, currency.value),
            ("adv_receipts", adv_receipts, _m, currency.value),
            ("prepayments", prepayments, _m, currency.value),
        ):
            value = series.get(year)
            add_metric(
                f"{prefix}.{year}",
                f"{prefix} {year}",
                value,
                display_fn(value),
                unit=unit,
                formula=f"statement.{prefix}",
                period=f"{year}A",
            )
        add_metric(
            f"net_cash.{year}",
            f"净现金 {year}",
            net_cash[year].amount if year in net_cash else None,
            _m(net_cash[year].amount) if year in net_cash else "—",
            unit=currency.value,
            formula="balance.net_cash",
            period=f"{year}A",
        )
        add_metric(
            f"payout.{year}",
            f"支付率 {year}",
            payouts.get(year),
            _pct(payouts.get(year)),
            unit="%",
            formula="dividends.payout",
            period=f"{year}A",
        )

    # -- tables -----------------------------------------------------------
    def money_row(label: str, prefix: str) -> list[str]:
        return [label] + [pack_ledger.display(f"{prefix}.{year}") for year in years]

    trend_rows = [
        money_row("营业收入", "revenue"),
        money_row("归母净利润", "net_income"),
        ["基本 EPS（元）"] + [pack_ledger.display(f"eps.{y}") for y in years],
        money_row("经营现金流", "ocf"),
        money_row("资本开支", "capex"),
        money_row("自由现金流", "fcf"),
        money_row("折旧摊销", "da"),
        money_row("有息负债", "debt"),
        money_row("股东权益", "equity"),
        money_row("货币资金", "cash"),
        money_row("应收账款", "accounts_receiv"),
        money_row("存货", "inventory"),
        money_row("合同负债", "contract_liab"),
        money_row("预收款项", "adv_receipts"),
        money_row("预付款项", "prepayments"),
        ["OCF/净利润（%）"]
        + [
            f"{ocf[y] / net_income[y] * 100:.2f}%"
            if y in ocf and y in net_income and net_income[y] not in (None, 0)
            else "—"
            for y in years
        ],
        ["净现金"] + [pack_ledger.display(f"net_cash.{y}") for y in years],
        ["支付率（%）"] + [pack_ledger.display(f"payout.{y}") for y in years],
    ]

    interim = statements.latest_interim(rows)
    interim_rows: list[list[str]] = []
    interim_note = ""
    if interim is not None:
        period_end, period_type, values = interim
        factor = statements.annualise_factor(period_type)
        for label, statement, item in (
            ("营业收入", "income", "revenue"),
            ("归母净利润", "income", "n_income_attr_p"),
            ("经营现金流", "cashflow", "n_cashflow_act"),
            ("资本开支", "cashflow", "c_pay_acq_const_fiolta"),
        ):
            raw = values.get((statement, item))
            interim_rows.append(
                [
                    label,
                    _m(raw),
                    _m(raw * factor) if raw is not None else "—",
                ]
            )
        interim_note = (
            f"最新非年报表 {period_end.isoformat()}（{period_type}），"
            f"年化系数 ×{factor:.2f}；仅作参考，不替代年报。"
        )
    ttm = statements.ttm(rows)
    ttm_rows: list[list[str]] = []
    if ttm is not None:
        for label, statement, item in (
            ("营业收入", "income", "revenue"),
            ("归母净利润", "income", "n_income_attr_p"),
            ("经营现金流", "cashflow", "n_cashflow_act"),
            ("资本开支", "cashflow", "c_pay_acq_const_fiolta"),
        ):
            value = ttm.values.get((statement, item))
            ttm_rows.append([label, _m(value)])

    div_by_year: dict[int, dict[str, Any]] = {}
    for event in dividends:
        bucket = div_by_year.setdefault(
            event.fiscal_year,
            {"dps": Decimal("0"), "total": None, "count": 0, "dps_reliable": True},
        )
        bucket["count"] += 1
        if event.dps_reliable:
            bucket["dps"] += event.dps
        else:
            bucket["dps_reliable"] = False
        if event.total is not None:
            bucket["total"] = (bucket["total"] or Decimal("0")) + event.total
    for year, bucket in div_by_year.items():
        add_metric(
            f"payout.{year}",
            f"支付率 {year}",
            payouts.get(year),
            _pct(payouts.get(year)),
            unit="%",
            formula="dividends.payout",
            period=f"{year}A",
        )
        dps_display = _num(bucket["dps"], 4) if bucket["dps_reliable"] else "—"
        add_metric(
            f"dps.{year}",
            f"DPS {year}",
            bucket["dps"] if bucket["dps_reliable"] else None,
            dps_display,
            unit=currency.value,
            formula="dividends.dps",
            period=f"{year}A",
        )
        add_metric(
            f"dividend_total.{year}",
            f"分红总额 {year}",
            bucket["total"],
            _m(bucket["total"]),
            unit=currency.value,
            formula="dividends.total",
            period=f"{year}A",
        )
    dividend_rows = [
        [
            str(year),
            str(div_by_year[year]["count"]),
            pack_ledger.display(f"dps.{year}"),
            pack_ledger.display(f"dividend_total.{year}"),
            pack_ledger.display(f"payout.{year}"),
        ]
        for year in sorted(div_by_year, reverse=True)
    ]
    unreliable_dps = any(not bucket["dps_reliable"] for bucket in div_by_year.values())
    dividend_note = (
        "DPS 为「—」表示供应商在多个财年重复同一 TTM 值，已从均值/股息隐含价中剔除；"
        "支付率仍以 divi_ratio 或现金流口径计算。"
        if unreliable_dps
        else "分红总额为「—」表示该市场未提供股本基数；支付率可能仍可用。"
        if any(bucket["total"] is None for bucket in div_by_year.values())
        else ""
    )

    kpi_rows = [
        ["营业收入 CAGR（5 年）", pack_ledger.display("revenue.cagr")],
        ["归母净利润 CAGR（5 年）", pack_ledger.display("net_income.cagr")],
        ["支付率均值", pack_ledger.display("payout.mean")],
        ["维持性 Capex 系数 G", f"{g_row.g}（{g_reason}）"],
        ["最新 FCF（百万元）", pack_ledger.display("fcf.latest")],
        ["有息负债（百万元）", pack_ledger.display("debt.latest")],
        ["有息负债完整度", "完整" if latest_year is not None and debt_full.get(latest_year) else "部分"],
        ["净现金（百万元）", pack_ledger.display("net_cash.latest")],
        ["穿透回报率 R", pack_ledger.display("r")],
        ["精算回报率 GG", pack_ledger.display("gg")],
        ["AA 口径", aa_label],
        ["股份支付 SBC（百万元）", _m(sbc_amount) if sbc_amount else "—"],
        ["现金桥完整度", f"{bridge_complete}/{bridge_total} 年"],
        ["回购 O（百万元）", _m(buyback.amount) if buyback else "0.00"],
        ["门槛 II", pack_ledger.display("ii")],
        ["R 判定", returns.classify_return(r_value, ii, rf_pct)],
        ["底价均值", pack_ledger.display("floor.mean")],
        ["底价中位数", pack_ledger.display("floor.median")],
        ["口径分歧", f"{pack_ledger.display('floor.divergence')}（{status_label}）"],
        [f"底价（采用{method_label}）", pack_ledger.display("floor")],
        ["当前价", pack_ledger.display("price")],
        ["底价溢价", pack_ledger.display("premium")],
    ]

    quote_rows = [
        ["当前价", f"{pack_ledger.display('price')} {currency.value}"],
        ["52 周最高", f"{pack_ledger.display('high_52w')} {currency.value}"],
        ["52 周最低", f"{pack_ledger.display('low_52w')} {currency.value}"],
        ["10 年最低", f"{pack_ledger.display('ten_year_low')} {currency.value}"],
        ["总市值（百万元）", pack_ledger.display("market_cap")],
        ["总股本（亿股）", pack_ledger.display("shares")],
        [
            "稀释后股数（亿股）",
            pack_ledger.display("diluted_shares"),
        ],
        ["无风险利率 Rf", pack_ledger.display("rf")],
    ]

    floor_rows = [[b.name, _num(b.value), b.formula] for b in baselines]

    valuation_rows = [
        ["企业价值 EV（百万元）", _m(snapshot.ev)],
        ["EBITDA（百万元）", _m(snapshot.ebitda)],
        ["EV/EBITDA", _x(snapshot.ev_ebitda)],
        ["净负债/EBITDA", _x(snapshot.net_debt_ebitda)],
        ["扣除现金 PE", _x(snapshot.cash_adj_pe)],
        ["P/B", _x(snapshot.pb)],
        ["FCF 收益率", _pct(snapshot.fcf_yield)],
        ["股息率（3 年均 DPS）", _pct(snapshot.dividend_yield)],
        ["EBITDA 利润率", _pct(snapshot.ebitda_margin)],
        ["商誉/总资产", _pct(snapshot.goodwill_ratio)],
        ["底价均值", pack_ledger.display("floor.mean")],
        ["底价中位数", pack_ledger.display("floor.median")],
        ["口径分歧", f"{pack_ledger.display('floor.divergence')}（{status_label}）"],
    ]

    consolidated_cash = cash.get(latest_year) if latest_year else None
    parent_ratio = (
        parent_cash / consolidated_cash * Decimal("100")
        if parent_cash is not None and consolidated_cash
        else None
    )
    pdf_bridge_rows: list[list[str]] = []
    if pdf_bridge:
        _year, bridge = sorted(pdf_bridge.items())[-1]
        for label, key in (
            ("净利润", "net_profit"),
            ("折旧摊销", "depreciation_amortisation"),
            ("营运资本变动", "working_capital_change"),
            ("经营产生现金", "cash_generated_from_operations"),
            ("已付所得税", "income_tax_paid"),
            ("经营现金流 OCF", "ocf"),
            ("资本开支 Capex", "capex"),
        ):
            raw_value = bridge.get(key)
            display = _m(Decimal(str(raw_value))) if raw_value else "—"
            add_metric(
                f"pdf_bridge.{key}",
                label,
                Decimal(str(raw_value)) if raw_value else None,
                display,
                unit=currency.value,
                formula="pdf.indirect_cash_bridge",
                period=f"{_year}A",
            )
            pdf_bridge_rows.append([label, pack_ledger.display(f"pdf_bridge.{key}")])
    hk_facts = extract_hk_facts(pdf_sections) if pdf_sections else None
    if hk_facts is not None:
        if hk_facts.holders:
            holders = hk_facts.holders
        if hk_facts.segments:
            main_business = hk_facts.segments
    hk_notes: list[str] = []
    if hk_facts is not None:
        if hk_facts.holders:
            hk_notes.append(f"股东来自年报 PDF：{len(hk_facts.holders)} 名")
        if hk_facts.segments:
            hk_notes.append(f"分部收入来自年报 PDF：{len(hk_facts.segments)} 项")
        if hk_facts.segment_balanced:
            hk_notes.append("分部合计=The Group")
        hk_notes.extend(hk_facts.notes)
    for index, row in enumerate((holders or [])[:10]):
        amount = row.get("hold_amount")
        ratio = row.get("hold_ratio")
        add_metric(
            f"holder.{index}.amount",
            f"股东持股 {index}",
            Decimal(str(amount)) / Decimal("100000000") if amount is not None else None,
            f"{Decimal(str(amount))/Decimal('100000000'):,.2f}" if amount is not None else "—",
            unit="亿股",
            formula="holders.amount",
        )
        add_metric(
            f"holder.{index}.ratio",
            f"股东比例 {index}",
            Decimal(str(ratio)) if ratio is not None else None,
            _pct(Decimal(str(ratio)) if ratio is not None else None),
            unit="%",
            formula="holders.ratio",
        )
    for index, row in enumerate((main_business or [])[:12]):
        for key, unit in (("bz_sales", currency.value), ("bz_profit", currency.value)):
            cell = row.get(key)
            numeric = (
                Decimal(str(cell))
                if cell is not None and str(cell) != "nan"
                else None
            )
            add_metric(
                f"segment.{index}.{key}",
                f"分部 {index} {key}",
                numeric,
                _m(numeric),
                unit=unit,
                formula=f"segment.{key}",
            )
    holders_rows = [
        [
            str(row.get("holder_name", "")),
            pack_ledger.display(f"holder.{index}.amount"),
            pack_ledger.display(f"holder.{index}.ratio"),
        ]
        for index, row in enumerate((holders or [])[:10])
    ]
    mainbz_rows = [
        [
            str(row.get("bz_item", "")),
            pack_ledger.display(f"segment.{index}.bz_sales"),
            pack_ledger.display(f"segment.{index}.bz_profit"),
        ]
        for index, row in enumerate((main_business or [])[:12])
    ]
    footnote_rows: list[list[str]] = []
    if footnotes:
        for section_id in ("P2", "P3", "P4", "P6", "P13", "SUB"):
            section = footnotes.get(section_id)
            if not isinstance(section, Mapping):
                continue
            tables = section.get("tables", [])
            if not isinstance(tables, list):
                continue
            for table in tables[:2]:
                if not isinstance(table, Mapping):
                    continue
                table_rows = table.get("rows", [])
                if not isinstance(table_rows, list) or len(table_rows) < 2:
                    continue
                header = [str(x) for x in table_rows[0]][:4]
                first_row = [str(x) for x in table_rows[1]][:4]
                footnote_rows.append(
                    [
                        f"{section_id} p.{table.get('page', '—')}",
                        " / ".join(header),
                        " / ".join(first_row),
                    ]
                )
    context = {
        "code": str(code),
        "market": code.market.value,
        "currency": currency.value,
        "generated_at": str(as_of or (quote.get("trade_date", "") if quote else "")),
        "snapshot_id": snapshot_id or source_snapshot_id(rows),
        "as_of": str(as_of or (quote.get("trade_date", "") if quote else "")),
        "pit_note": pit_note,
        "data_basis": "annual" if not ttm_rows else "annual+TTM",
        "audit_note": "数字来自确定性管线；PDF 事实/来源冲突见 analysis_report.md 与 cleanroom.json。",
        "coverage_table": coverage_markdown(code),
        "rf_source": rf_source,
        "kpi_table": _table(["指标", "数值"], kpi_rows),
        "trend_table": _table(
            ["项目"] + [str(year) for year in years],
            trend_rows,
            ["l"] + ["r"] * len(years),
        ),
        "dividend_table": _table(
            ["财年", "分红次数", "每股合计（元）", "分红总额（百万元）", "支付率"],
            dividend_rows,
            ["l", "r", "r", "r", "r"],
        ),
        "dividend_note": dividend_note,
        "interim_table": _table(["项目", "原始值（百万元）", "年化值（百万元）"], interim_rows, ["l", "r", "r"])
        if interim_rows
        else "",
        "interim_note": interim_note,
        "ttm_table": _table(["项目", "TTM（百万元）"], ttm_rows, ["l", "r"]),
        "ttm_rows": ttm_rows,
        "ttm_note": ttm.note if ttm is not None else "",
        "pdf_bridge_table": _table(["项目", "金额（百万元）"], pdf_bridge_rows),
        "cash_bridge_table": _table(
            ["年份", "结余 AA（百万元）", "来源", "完整"],
            cash_bridge_rows,
            ["l", "r", "l", "l"],
        ),
        "aa_label": aa_label,
        "bridge_coverage": f"{bridge_complete}/{bridge_total}",
        "pdf_section_count": len(pdf_sections or {}),
        "pdf_section_ids": ", ".join(sorted(str(key) for key in (pdf_sections or {}))),
        "pdf_bridge_note": (
            "港股现金流量表为间接法：净利润 + 非现金调整 + 营运资本变动 → 经营产生现金 → "
            "已付税 → OCF；Capex 来自投资活动。无毛利收现/付现明细。"
            if pdf_bridge_rows
            else ""
        ),
        "holders_table": _table(
            ["股东", "持股（亿股）", "比例"], holders_rows, ["l", "r", "r"]
        ),
        "holders_available": bool(holders_rows),
        "hk_facts_note": "；".join(hk_notes),
        "mainbz_table": _table(
            ["主营/分部", "收入（百万元）", "利润（百万元）"],
            mainbz_rows,
            ["l", "r", "r"],
        ),
        "mainbz_available": bool(mainbz_rows),
        "footnote_table": _table(
            ["章节/页", "表头", "首行"], footnote_rows, ["l", "l", "l"]
        ),
        "footnote_available": bool(footnote_rows),
        "quote_table": _table(["项目", "数值"], quote_rows),
        "valuation_table": _table(["指标", "数值"], valuation_rows),
        "floor_table": _table(["方法", "价格", "公式"], floor_rows, ["l", "r", "l"]),
        "methods": len(baselines),
        "composite": _num(composite),
        "premium": _pct(premium),
        "floor_note": floor_note,
        "warnings": [str(issue) for issue in issues],
        "issues_md": "\n".join(f"- {issue}" for issue in issues)
        or "未检测到数据问题。",
        "governance_table": _table(
            ["项目", "数值"],
            [
                ["母公司现金（百万元）", _m(parent_cash)],
                ["母公司现金/合并现金", _pct(parent_ratio)],
                ["控股股东质押率", _pct(pledge_pct)],
                ["近 3 年年均回购（百万元）", _m(buyback.amount) if buyback else "—"],
            ],
        ),
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    text = env.get_template("data_pack.md.j2").render(**context)
    if document_facts:
        fact_rows = [
            [
                str(fact.get("label", "")),
                str(fact.get("value", "")),
                str(fact.get("unit", "")),
                str(fact.get("page", "")),
            ]
            for fact in document_facts
        ]
        text += "\n\n## PDF 证据\n\n" + _table(
            ["项目", "数值", "单位", "页码"], fact_rows
        )
    extras_md = render_extras(fundamental_extras)
    next_section = 17
    if extras_md:
        text += f"\n\n## {next_section}. 补充基本面（Tushare）\n\n" + extras_md
        next_section += 1
    market_md = render_market(market_extras)
    if market_md:
        text += f"\n\n## {next_section}. 市场与宏观（Tushare）\n\n" + market_md
    return text
