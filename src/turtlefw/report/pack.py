"""Data-pack rendering: deterministic Markdown assembled from the bundle."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, FileSystemLoader

from ..config import Settings
from ..data.protocol import StatementRow
from ..metrics import dividends as div_metrics
from ..metrics import returns, statements, valuation
from ..types import Currency, DividendEvent, FetchIssue, Money, StockCode

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _m(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value / Decimal('1000000'):,.2f}"


def _pct(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}%"


def _ratio_pct(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return _pct(value * Decimal("100"))


def _num(value: Decimal | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    aligns: Sequence[str] | None = None,
) -> str:
    aligns = aligns or ["l"] * len(headers)
    sep = "|" + "|".join("---:" if a == "r" else ":---" for a in aligns) + "|"
    lines = ["| " + " | ".join(headers) + " |", sep]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _snapshot_id(rows: Sequence[StatementRow]) -> str:
    payload = "\n".join(
        f"{r.code}|{r.period_end}|{r.period_type}|{r.statement}|{r.item}|{r.value}|{r.source}"
        for r in sorted(rows, key=lambda r: (r.period_end, r.statement, r.item))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _series(rows: Sequence[StatementRow], statement: str, item: str) -> dict[int, Decimal]:
    return statements.annual_series(rows, statement, item)


def _week52(history: Sequence[dict]) -> tuple[Decimal | None, Decimal | None]:
    cutoff = date.today().replace(year=date.today().year - 1).strftime("%Y%m%d")
    window = [r for r in history if str(r.get("trade_date", "")) >= cutoff]
    highs = [Decimal(str(r["high"])) for r in window if r.get("high") is not None]
    lows = [Decimal(str(r["low"])) for r in window if r.get("low") is not None]
    return (max(highs) if highs else None, min(lows) if lows else None)


def average_dps(dividends: Sequence[DividendEvent], years: int = 3) -> Decimal | None:
    """Mean annual DPS over the most recent ``years`` fiscal years.

    Events are summed per year first: a year with an interim and a final
    dividend is one year, not two.
    """
    if not dividends:
        return None
    per_year: dict[int, Decimal] = defaultdict(Decimal)
    for event in dividends:
        per_year[event.fiscal_year] += event.dps
    recent = sorted(per_year)[-years:]
    if not recent:
        return None
    return sum((per_year[y] for y in recent), Decimal("0")) / Decimal(len(recent))


def render_data_pack(
    code: StockCode,
    rows: Sequence[StatementRow],
    dividends: Sequence[DividendEvent],
    *,
    quote: dict | None,
    history: Sequence[dict],
    market_cap: Money,
    shares: Decimal,
    rf_pct: Decimal,
    settings: Settings,
    issues: Sequence[FetchIssue] = (),
    tax_pct: Decimal = Decimal("0"),
) -> str:
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
    equity = statements.equity(rows)
    cash = statements.cash_and_equivalents(rows)
    trad = _series(rows, "balance", "trad_asset")
    net_cash = statements.net_cash(rows, currency)
    payouts = div_metrics.payout_by_year(dividends, net_income, shares=shares)
    mean_payout, payout_years = div_metrics.mean_payout(payouts)

    latest_year = max(years) if years else None
    latest_fcf = fcf.get(latest_year) if latest_year else None
    price = Decimal(str(quote["close"])) if quote and quote.get("close") is not None else None
    high_52w, low_52w = _week52(history)
    closes = [Decimal(str(r["close"])) for r in history if r.get("close") is not None]

    ii = settings.returns.threshold(rf_pct, code)
    aa = Money(latest_fcf, currency) if latest_fcf is not None else Money.zero(currency)
    r_value = returns.penetration_return(
        aa,
        mean_payout or Decimal("0"),
        tax_pct,
        Money.zero(currency),
        market_cap,
        Decimal("1"),
    )

    min_fcf_all = dict(sorted(fcf.items())[-5:])
    min_fcf = (
        min(min_fcf_all.values())
        if min_fcf_all and min(min_fcf_all.values()) > 0
        else None
    )
    baselines = valuation.five_baselines(
        cash=cash.get(latest_year) if latest_year else None,
        trad_assets=trad.get(latest_year) if latest_year else None,
        debt=debt.get(latest_year) if latest_year else None,
        equity=equity.get(latest_year) if latest_year else None,
        shares=shares,
        closes=closes,
        average_dps=average_dps(dividends),
        min_fcf=min_fcf,
        rf_pct=rf_pct,
        dividend_floor_pct=settings.valuation.dividend_discount_floor,
    )
    composite = valuation.composite(baselines, settings.valuation.composite_method)
    premium = valuation.premium(price, composite) if price and composite else None

    # -- tables -----------------------------------------------------------
    def money_row(label: str, series: dict[int, Decimal]) -> list[str]:
        return [label] + [_m(series.get(year)) for year in years]

    trend_rows = [
        money_row("营业收入", revenue),
        money_row("归母净利润", net_income),
        ["基本 EPS（元）"] + [_num(eps.get(y), 2) for y in years],
        money_row("经营现金流", ocf),
        money_row("资本开支", capex),
        money_row("自由现金流", fcf),
        money_row("折旧摊销", da),
        money_row("有息负债", debt),
        money_row("股东权益", equity),
        money_row("货币资金", cash),
        ["净现金"] + [_m(net_cash[y].amount) if y in net_cash else "—" for y in years],
        ["支付率（%）"] + [_pct(payouts.get(y)) for y in years],
    ]

    div_by_year: dict[int, dict] = {}
    for event in dividends:
        bucket = div_by_year.setdefault(
            event.fiscal_year, {"dps": Decimal("0"), "total": Decimal("0"), "count": 0}
        )
        bucket["dps"] += event.dps
        if event.total is not None:
            bucket["total"] += event.total
        bucket["count"] += 1
    dividend_rows = [
        [
            str(year),
            str(div_by_year[year]["count"]),
            _num(div_by_year[year]["dps"], 4),
            _m(div_by_year[year]["total"]),
            _pct(payouts.get(year)),
        ]
        for year in sorted(div_by_year, reverse=True)
    ]

    kpi_rows = [
        ["营业收入 CAGR（5 年）", _ratio_pct(statements.revenue_cagr(rows))],
        ["归母净利润 CAGR（5 年）", _ratio_pct(statements.net_income_cagr(rows))],
        ["支付率均值", f"{_pct(mean_payout)}（{payout_years} 年）"],
        ["最新 FCF（百万元）", _m(latest_fcf)],
        ["有息负债（百万元）", _m(debt.get(latest_year) if latest_year else None)],
        ["净现金（百万元）", _m(net_cash[latest_year].amount) if latest_year in net_cash else "—"],
        ["穿透回报率 R", _pct(r_value)],
        ["门槛 II", _pct(ii)],
        ["R 判定", returns.classify_return(r_value, ii, rf_pct)],
        ["底价（综合）", _num(composite)],
        ["当前价", _num(price)],
        ["底价溢价", _pct(premium)],
    ]

    quote_rows = [
        ["当前价", f"{_num(price)} {currency.value}"],
        ["52 周最高", _num(high_52w)],
        ["52 周最低", _num(low_52w)],
        ["10 年最低", _num(valuation.ten_year_low(closes))],
        ["总市值（百万元）", _m(market_cap.amount)],
        ["总股本（亿股）", f"{shares / Decimal('100000000'):,.2f}" if shares else "—"],
        ["无风险利率 Rf", _pct(rf_pct)],
    ]

    floor_rows = [[b.name, _num(b.value), b.formula] for b in baselines]

    context = {
        "code": str(code),
        "market": code.market.value,
        "currency": currency.value,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "snapshot_id": _snapshot_id(rows),
        "as_of": str(quote.get("trade_date", "")) if quote else "",
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
        "quote_table": _table(["项目", "数值"], quote_rows),
        "floor_table": _table(["方法", "价格", "公式"], floor_rows, ["l", "r", "l"]),
        "methods": len(baselines),
        "composite": _num(composite),
        "premium": _pct(premium),
        "warnings": [str(issue) for issue in issues],
        "issues_md": "\n".join(f"- {issue}" for issue in issues)
        or "未检测到数据问题。",
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    return env.get_template("data_pack.md.j2").render(**context)
