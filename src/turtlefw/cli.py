"""Command line interface (stdlib argparse; no shell assumptions)."""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from . import __version__
from .config import Settings, get_token, load_settings
from .data.protocol import StatementRow
from .data.store import StatementStore
from .metrics import dividends as div_metrics
from .metrics import returns, statements, valuation
from .types import Currency, DividendEvent, Market, Money, StockCode, TurtleError


def _pct(value: Decimal | None, digits: int = 2) -> str:
    """Format a ratio (0.1) as a percentage string (10.00%)."""
    if value is None:
        return "—"
    return f"{value * Decimal('100'):,.{digits}f}%"


def _fmt(value: Decimal | None, suffix: str = "", digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}{suffix}"


def _money(value: Decimal | None) -> str:
    return "—" if value is None else f"{value / Decimal('1000000'):,.2f} 百万元"


def kpi_summary(
    code: StockCode,
    rows: list[StatementRow],
    dividends: list[DividendEvent],
    *,
    market_cap: Money,
    shares: Decimal,
    rf_pct: Decimal,
    settings: Settings,
    tax_pct: Decimal = Decimal("0"),
    buyback: Money | None = None,
    closes: list[Decimal] | None = None,
    price: Decimal | None = None,
) -> list[tuple[str, str]]:
    """Compute the deterministic KPI block shared by demo and live modes."""
    currency = rows[0].currency if rows else Currency.CNY
    income = statements.net_income(rows)
    fcf = statements.fcf_series(rows)
    debt = statements.interest_bearing_debt(rows)
    equity = statements.equity(rows)
    cash = statements.cash_and_equivalents(rows)

    payouts = div_metrics.payout_by_year(dividends, income, shares=shares)
    mean_payout, used_years = div_metrics.mean_payout(payouts)

    latest_fcf = statements.latest_value(fcf)
    aa = Money(latest_fcf, currency) if latest_fcf is not None else Money.zero(currency)
    ii = settings.returns.threshold(rf_pct, code)
    r = returns.penetration_return(
        aa,
        mean_payout or Decimal("0"),
        tax_pct,
        buyback or Money.zero(currency),
        market_cap,
        Decimal("1"),
    )
    latest_year = max(income) if income else None
    debt_latest = debt.get(latest_year) if latest_year else None
    cash_latest = cash.get(latest_year) if latest_year else None
    net_cash = (
        Money(cash_latest - debt_latest, currency)
        if cash_latest is not None and debt_latest is not None
        else None
    )

    per_year: dict[int, Decimal] = defaultdict(Decimal)
    for event in dividends:
        per_year[event.fiscal_year] += event.dps
    recent_years = sorted(per_year)[-3:]
    avg_dps = (
        sum((per_year[year] for year in recent_years), Decimal("0"))
        / Decimal(len(recent_years))
        if recent_years
        else None
    )
    min_fcf_all = dict(sorted(fcf.items())[-5:])
    min_fcf = (
        min(min_fcf_all.values())
        if min_fcf_all and min(min_fcf_all.values()) > 0
        else None
    )
    trad = statements.annual_series(rows, "balance", "trad_asset")

    baselines = valuation.five_baselines(
        cash=cash_latest,
        trad_assets=trad.get(latest_year) if latest_year else None,
        debt=debt_latest,
        equity=equity.get(latest_year) if latest_year else None,
        shares=shares,
        closes=closes,
        average_dps=avg_dps,
        min_fcf=min_fcf,
        rf_pct=rf_pct,
    )
    composite = valuation.composite(baselines, settings.valuation.composite_method)
    if price is None and shares:
        price = market_cap.amount / shares
    premium = valuation.premium(price, composite) if price and composite else None

    return [
        ("股票代码", str(code)),
        ("报表币种", currency.value),
        ("营业收入 CAGR", _pct(statements.revenue_cagr(rows))),
        ("归母净利润 CAGR", _pct(statements.net_income_cagr(rows))),
        ("三年均值支付率", _fmt(mean_payout, f"% ({used_years} 年)")),
        ("最新 FCF", _money(latest_fcf)),
        ("有息负债", _money(debt_latest)),
        ("净现金", _money(net_cash.amount) if net_cash else "—"),
        ("穿透回报率 R", _fmt(r, "%")),
        ("门槛 II", _fmt(ii, "%")),
        ("R 判定", returns.classify_return(r, ii, rf_pct)),
        ("底价", f"{_fmt(composite, f' {currency.value}/股')}（{len(baselines)} 法）"),
        ("当前价", _fmt(price, f" {currency.value}/股")),
        ("底价溢价", _fmt(premium, "%")),
    ]


def _print_kpis(title: str, items: list[tuple[str, str]]) -> None:
    print(f"\n=== {title} ===")
    width = max(len(k) for k, _ in items) + 2
    for key, value in items:
        print(f"{key:<{width}}{value}")


def _demo_analyze() -> int:
    from . import demo

    settings = load_settings()
    rows = demo.demo_rows()
    items = kpi_summary(
        demo.DEMO_CODE,
        rows,
        demo.demo_dividends(),
        market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
        shares=demo.DEMO_SHARES,
        rf_pct=demo.DEMO_RF,
        settings=settings,
        closes=demo.demo_closes(),
    )
    _print_kpis(f"{demo.DEMO_NAME} {demo.DEMO_CODE}（合成数据）", items)
    print("\n提示：--demo 使用内置合成数据，仅用于验证管线，不构成任何分析结论。")
    return 0


def _num(value: object) -> Decimal | None:
    """Parse a provider value, rejecting None / NaN / inf."""
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except Exception:  # noqa: BLE001 - vendor payload may be a placeholder
        return None
    return number if number.is_finite() else None


def _unit_for(code: StockCode, currency: str | None) -> Currency:
    if currency:
        return Currency(currency)
    if code.market is Market.HK:
        print(
            "提示：港股默认按人民币报表处理（多数内地企业）；"
            "若为港元报表请加 --currency HKD",
            file=sys.stderr,
        )
    return Currency.CNY


def _live_analyze(raw_code: str, save: bool, currency: str | None = None) -> int:
    from .data.tushare_provider import TushareProvider

    settings = load_settings()
    code = StockCode.parse(raw_code)
    unit = _unit_for(code, currency)

    provider = TushareProvider(get_token())
    rows = provider.statements(code, currency=unit)
    if not rows:
        print("未取到报表数据，请检查 Token 权限与代码。", file=sys.stderr)
        for issue in provider.issues:
            print(f"  {issue}", file=sys.stderr)
        return 2

    divs = provider.dividends(code, currency=unit)
    basic = provider.daily_basic(code)
    # daily_basic with only ts_code returns many dates; the newest row wins.
    basic = sorted(basic, key=lambda r: str(r.get("trade_date", "")), reverse=True)
    weekly = provider.weekly(code)

    rf = provider.risk_free_rate(code)
    if rf is None:
        rf = settings.returns.default_rf
        print(
            f"提示：无风险利率接口不可用，使用默认 Rf={rf}%（见 configs/screening.toml）",
            file=sys.stderr,
        )

    market_cap = Money(Decimal("0"), Currency.CNY)
    shares = Decimal("0")
    price: Decimal | None = None
    if basic:
        record = basic[0]
        price = _num(record.get("close"))
        total_mv_wan = _num(record.get("total_mv"))
        total_share_wan = _num(record.get("total_share"))
        if total_mv_wan is not None and total_share_wan is not None:
            market_cap = Money(total_mv_wan * Decimal("10000"), Currency.CNY)
            shares = total_share_wan * Decimal("10000")

    closes = [
        value
        for item in weekly
        if (value := _num(item.get("close"))) is not None
    ]

    tax = Decimal("20") if code.market is Market.HK else Decimal("0")
    items = kpi_summary(
        code,
        rows,
        divs,
        market_cap=market_cap,
        shares=shares,
        rf_pct=rf,
        settings=settings,
        tax_pct=tax,
        closes=closes,
        price=price,
    )
    _print_kpis(f"{code}", items)

    if provider.issues:
        print("\n数据问题：", file=sys.stderr)
        for issue in provider.issues:
            print(f"  {issue}", file=sys.stderr)

    if save:
        store = StatementStore(Path("output") / "store")
        store.append(rows)
        print(f"\n已写入 output/store，snapshot_id={store.snapshot_id(str(code))}")
    return 0


def _pack(raw_code: str, out: str | None, currency: str | None = None) -> int:
    from .data.tushare_provider import TushareProvider
    from .report.pack import render_data_pack

    settings = load_settings()
    code = StockCode.parse(raw_code)
    unit = _unit_for(code, currency)
    provider = TushareProvider(get_token())

    rows = provider.statements(code, currency=unit)
    if not rows:
        print("未取到报表数据。", file=sys.stderr)
        for issue in provider.issues:
            print(f"  {issue}", file=sys.stderr)
        return 2

    dividends = provider.dividends(code, currency=unit)
    basic = sorted(
        provider.daily_basic(code), key=lambda r: str(r.get("trade_date", "")), reverse=True
    )
    history = provider.weekly(code)
    rf = provider.risk_free_rate(code) or settings.returns.default_rf

    quote = basic[0] if basic else None
    market_cap = Money(Decimal("0"), Currency.CNY)
    shares = Decimal("0")
    if quote:
        total_mv_wan = _num(quote.get("total_mv"))
        total_share_wan = _num(quote.get("total_share"))
        if total_mv_wan is not None and total_share_wan is not None:
            market_cap = Money(total_mv_wan * Decimal("10000"), unit)
            shares = total_share_wan * Decimal("10000")

    markdown = render_data_pack(
        code,
        rows,
        dividends,
        quote=quote,
        history=history,
        market_cap=market_cap,
        shares=shares,
        rf_pct=rf,
        settings=settings,
        issues=provider.issues,
        tax_pct=Decimal("20") if code.market is Market.HK else Decimal("0"),
    )

    path = Path(out) if out else Path("output") / str(code) / "data_pack.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    print(f"数据包已写入 {path.resolve()}")
    print(f"字节数：{len(markdown.encode('utf-8')):,} ｜ 行数：{markdown.count(chr(10)) + 1}")
    return 0


def _screen(tier1_only: bool) -> int:
    from .data.tushare_provider import TushareProvider
    from .screener import tier1 as tier1_mod

    settings = load_settings()
    provider = TushareProvider(get_token())
    universe = provider.stock_basic()
    if not universe:
        print("未取到股票列表。", file=sys.stderr)
        for issue in provider.issues:
            print(f"  {issue}", file=sys.stderr)
        return 2

    # Today's snapshot is unavailable before the evening, and trade_cal may be
    # restricted; walk back over recent days until a non-empty snapshot appears.
    trade_date = provider.latest_trade_date()
    daily = provider.daily_basic(trade_date=trade_date)
    if not daily:
        for delta in range(1, 10):
            candidate = (date.today() - timedelta(days=delta)).strftime("%Y%m%d")
            daily = provider.daily_basic(trade_date=candidate)
            if daily:
                trade_date = candidate
                break

    import pandas as pd

    if not daily:
        print("未取到当日行情快照。", file=sys.stderr)
        for issue in provider.issues:
            print(f"  {issue}", file=sys.stderr)
        return 2

    print(f"交易日: {trade_date}")
    frame = pd.DataFrame(universe).merge(pd.DataFrame(daily), on="ts_code", how="inner")
    filtered = tier1_mod.apply_filters(frame, settings.screening)
    channels = tier1_mod.split_channels(filtered, settings.screening)

    if tier1_only:
        ranked = tier1_mod.rank_main(channels, settings.screening)
        print(ranked[["ts_code", "name", "channel", "tier1_score"]].head(30).to_string(index=False))
        return 0

    print("Tier 2 尚未实现（里程碑 M3）。使用 --tier1-only 查看 Tier 1 结果。")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="turtle", description="Turtle Investment Framework")
    parser.add_argument("--version", action="version", version=f"turtle-framework {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="分析单只股票")
    analyze.add_argument("code", help="股票代码，如 600887 / 00700.HK")
    analyze.add_argument("--demo", action="store_true", help="使用内置合成数据，不需要 Token")
    analyze.add_argument("--save", action="store_true", help="把报表写入 output/store")
    analyze.add_argument(
        "--currency",
        choices=[c.value for c in Currency],
        default=None,
        help="报表币种；港股默认 CNY，港元报表请显式指定 HKD",
    )

    screen = sub.add_parser("screen", help="全市场筛选")
    screen.add_argument("--tier1-only", action="store_true", help="只跑 Tier 1")

    pack = sub.add_parser("pack", help="生成 Markdown 数据包")
    pack.add_argument("code", help="股票代码，如 600887")
    pack.add_argument("--out", default=None, help="输出路径，默认 output/<code>/data_pack.md")
    pack.add_argument(
        "--currency",
        choices=[c.value for c in Currency],
        default=None,
        help="报表币种；港股默认 CNY",
    )

    sub.add_parser("version", help="版本信息")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "version":
            print(f"turtle-framework {__version__}")
            return 0
        if args.command == "analyze":
            return _demo_analyze() if args.demo else _live_analyze(
                args.code, args.save, args.currency
            )
        if args.command == "screen":
            return _screen(args.tier1_only)
        if args.command == "pack":
            return _pack(args.code, args.out, args.currency)
    except TurtleError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
