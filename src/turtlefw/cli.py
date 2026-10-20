"""Command line interface (stdlib argparse; no shell assumptions)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from . import __version__
from .config import Settings, get_token, load_settings
from .data.protocol import StatementRow
from .data.store import StatementStore
from .metrics import dividends as div_metrics
from .metrics import cashflow, grids, owner_earnings, returns, statements, valuation
from .paths import output_root
from .qualitative import load as load_qualitative
from .qualitative import summary as qualitative_summary
from .qualitative import write_template
from .types import Currency, DividendEvent, FetchIssue, Market, Money, StockCode, TurtleError


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
    diluted_shares: Decimal | None = None,
    rf_pct: Decimal,
    settings: Settings,
    tax_pct: Decimal = Decimal("0"),
    buyback: Money | None = None,
    closes: list[Decimal] | None = None,
    price: Decimal | None = None,
    pledge_pct: Decimal | None = None,
    parent_cash: Decimal | None = None,
    pdf_bridge: dict[int, dict[str, str | None]] | None = None,
    sbc: Money | None = None,
) -> list[tuple[str, str]]:
    """Compute the deterministic KPI block shared by demo and live modes."""
    currency = rows[0].currency if rows else Currency.CNY
    income = statements.net_income(rows)
    eps = statements.annual_series(rows, "income", "basic_eps")
    fcf = statements.fcf_series(rows)
    da = statements.da_series(rows)
    debt = statements.interest_bearing_debt(rows)
    equity = statements.equity(rows)
    cash = statements.cash_and_equivalents(rows)
    capex = statements.annual_series(rows, "cashflow", "c_pay_acq_const_fiolta")

    payouts = div_metrics.payout_by_year(dividends, income, shares=shares)
    mean_payout, _ = div_metrics.mean_payout(payouts)
    cash_dividends = statements.annual_series(rows, "cashflow", "c_pay_dist_dpcp_int_exp")
    payout_check = grids.payout_crosscheck(
        dividends, income, eps=eps, shares=shares, cash_dividends=cash_dividends
    )
    if payout_check.recommended is not None:
        mean_payout = payout_check.recommended
    payout_years = sum(
        1
        for year in sorted(payouts)[-3:]
        if payouts.get(year) is not None
    )

    latest_fcf = statements.latest_value(fcf)
    latest_year = max(income) if income else None
    c = income.get(latest_year) if latest_year else None
    d = da.get(latest_year) if latest_year else None
    capex_ratio = grids.capex_da_ratio(capex, da)
    _g_rows, g_row, _g_reason = grids.g_grid(c, d, capex_ratio, settings.returns)
    oe = (c + d - d * g_row.g) if c is not None and d is not None else c
    oe_normalized = owner_earnings.normalized_owner_earnings(rows, g=g_row.g)
    oe = oe_normalized if oe_normalized is not None else oe
    aa_bridge = cashflow.build_cash_bridge(rows, pdf_bridge=pdf_bridge)
    aa_surplus = cashflow.surplus_series(aa_bridge)
    aa_all = grids.aa_variants(aa_surplus) if aa_surplus else grids.aa_variants(fcf)
    aa_value = aa_all[0].value if aa_all else None
    bridge_complete, bridge_total = cashflow.coverage(aa_bridge)
    ii = settings.returns.threshold(rf_pct, code)
    r = (
        returns.penetration_return(
            Money(oe, currency),
            mean_payout or Decimal("0"),
            tax_pct,
            buyback or Money.zero(currency),
            market_cap,
            Decimal("1"),
        )
        if oe is not None
        else None
    )
    sbc_amount = sbc.amount if sbc is not None else Decimal("0")
    aa_net = (aa_value - sbc_amount) if aa_value is not None else None
    gg = (
        returns.penetration_return(
            Money(aa_net, currency) if aa_net is not None else Money.zero(currency),
            mean_payout or Decimal("0"),
            tax_pct,
            buyback or Money.zero(currency),
            market_cap,
            Decimal("1"),
        )
        if aa_net is not None
        else None
    )
    debt_latest = debt.get(latest_year) if latest_year else None
    cash_latest = cash.get(latest_year) if latest_year else None
    net_cash = (
        Money(cash_latest - debt_latest, currency)
        if cash_latest is not None and debt_latest is not None
        else None
    )

    avg_dps = div_metrics.average_dps(dividends)
    min_fcf_all = dict(sorted(fcf.items())[-5:])
    min_fcf = (
        min(min_fcf_all.values())
        if min_fcf_all and min(min_fcf_all.values()) > 0
        else None
    )
    trad = statements.annual_series(rows, "balance", "trad_asset")
    if price is None and shares:
        price = market_cap.amount / shares
    floor = valuation.compute_floor(
        cash=cash_latest,
        trad_assets=trad.get(latest_year) if latest_year else None,
        debt=debt_latest,
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
    premium = floor.premium

    return [
        ("股票代码", str(code)),
        ("报表币种", currency.value),
        ("营业收入 CAGR", _pct(statements.revenue_cagr(rows))),
        ("归母净利润 CAGR", _pct(statements.net_income_cagr(rows))),
        ("三年均值支付率", _fmt(mean_payout, f"% ({payout_years} 年)")),
        ("最新 FCF", _money(latest_fcf)),
        ("有息负债", _money(debt_latest)),
        ("净现金", _money(net_cash.amount) if net_cash else "—"),
        ("维持性 Capex 系数 G", f"{g_row.g}"),
        ("现金桥完整度", f"{bridge_complete}/{bridge_total} 年"),
        ("控股股东质押率", _fmt(pledge_pct, "%")),
        ("母公司现金", _money(parent_cash)),
        ("穿透回报率 R", _fmt(r, "%")),
        ("精算回报率 GG", _fmt(gg, "%")),
        ("股份支付 SBC", _fmt(sbc_amount / Decimal("1000000"), " 百万元") if sbc_amount else "—"),
        ("门槛 II", _fmt(ii, "%")),
        ("R 判定", returns.classify_return(r, ii, rf_pct)),
        ("GG 判定", returns.classify_return(gg, ii, rf_pct)),
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


def _unit_for(
    code: StockCode, currency: str | None, provider: object | None = None
) -> Currency:
    if currency:
        return Currency(currency)
    if code.market is Market.HK:
        detected: Currency | None = None
        if provider is not None:
            method = getattr(provider, "reporting_currency", None)
            if callable(method):
                try:
                    detected = method(code)
                except Exception:  # noqa: BLE001 - metadata is best effort
                    detected = None
        if isinstance(detected, Currency):
            return detected
        print(
            "提示：无法从行情元数据读取港股报表币种，默认按人民币报表处理；"
            "若为港元报表请加 --currency HKD",
            file=sys.stderr,
        )
        return Currency.CNY
    if code.market is Market.US:
        return Currency.USD
    return Currency.CNY


def _fx_history(
    history: list[dict[str, object]], fx: Decimal
) -> list[dict[str, object]]:
    """Convert OHLC history into the report currency (no-op when fx == 1)."""
    if fx == Decimal("1"):
        return history
    converted: list[dict[str, object]] = []
    for item in history:
        record = dict(item)
        for key in ("close", "high", "low"):
            raw = record.get(key)
            if raw is not None:
                record[key] = str(Decimal(str(raw)) * fx)
        converted.append(record)
    return converted


def _pdf_bridge(path: str | None) -> dict[int, dict[str, str | None]] | None:
    """Load ``cash_bridge`` from a ``reported_numbers.json`` file."""
    if not path:
        return None
    import json

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        bridge = payload.get("cash_bridge")
        year = payload.get("year")
        if isinstance(bridge, dict) and year is not None:
            return {int(year): {str(k): v for k, v in bridge.items()}}
    except (OSError, ValueError, TypeError):
        return None
    return None


def _pdf_facts(path: str | None) -> dict[str, str]:
    """Map document fact ids to display values for research placeholders."""
    if not path:
        return {}
    import json

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    facts: dict[str, str] = {}
    for item in payload.get("document_facts", []):
        fact_id = str(item.get("id", ""))
        if fact_id:
            facts[fact_id] = (
                f"{item.get('value', '')} {item.get('unit', '')}".strip()
            )
    return facts


def _evidence_facts(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    import json

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, list):
        return {}
    return {
        str(item.get("id", "")): str(item.get("quote", ""))
        for item in payload
        if isinstance(item, dict) and item.get("id")
    }


def _sbc_from_rows(rows: list[StatementRow], unit: Currency) -> Money | None:
    series = statements.annual_series(rows, "cashflow", "sbc")
    if not series:
        return None
    latest = series[max(series)]
    return Money(latest, unit) if latest is not None else None


def _pdf_sbc(path: str | None) -> Decimal | None:
    if not path:
        return None
    import json

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        value = payload.get("sbc", {}).get("sbc")
        return Decimal(str(value)) if value not in (None, "") else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def _governance(
    provider, code: StockCode, unit: Currency
) -> tuple[Decimal | None, Decimal | None, Money | None]:
    """Parent-company cash, pledge ratio and annualised buyback amount."""
    parent_cash: Decimal | None = None
    pledge_pct: Decimal | None = None
    buyback: Money | None = None
    if code.is_a_share:
        try:
            parent_rows = provider.statements(code, report_type="6")
            parent_cash_series = statements.cash_and_equivalents(parent_rows)
            if parent_cash_series:
                parent_cash = parent_cash_series[max(parent_cash_series)]
            else:
                # Never fall back to consolidated cash: report_type 6 is the
                # only parent-company statement. Missing data must stay unknown.
                parent_cash = None
        except Exception:  # noqa: BLE001 - parent statements are optional
            parent_cash = None
        try:
            pledge_pct = provider.pledge_ratio(code)
        except Exception:  # noqa: BLE001
            pledge_pct = None
        try:
            amount = provider.buyback_amount(code)
            if amount is not None:
                buyback = Money(amount, unit)
        except Exception:  # noqa: BLE001
            buyback = None
    return parent_cash, pledge_pct, buyback


def _rf_for(provider, settings, code: StockCode, rf: float | None, rf_source: str | None):
    """Resolve the risk-free rate: explicit override > live endpoint > config."""
    if rf is not None:
        return Decimal(str(rf)), (rf_source or "命令行 --rf")
    live = provider.risk_free_rate(code)
    if live is not None:
        return live, "Tushare yc_cb"
    print(
        f"提示：无风险利率接口不可用，使用默认 Rf={settings.returns.default_rf}%"
        "（见 configs/screening.toml）",
        file=sys.stderr,
    )
    return settings.returns.default_rf, "configs/screening.toml default_rf"


def _fx_for(code: StockCode, unit: Currency, settings: Settings) -> Decimal:
    """HKD quote -> report currency; 1 for everything else."""
    if code.market is Market.HK and unit is Currency.CNY:
        return settings.fx.cny_per_hkd
    if code.market is Market.HK and unit is Currency.USD:
        raise TurtleError("港股美元报表暂不支持：请用 --currency CNY/HKD 或补汇率配置")
    return Decimal("1")


def _live_analyze(
    raw_code: str,
    save: bool,
    currency: str | None = None,
    rf: float | None = None,
    rf_source: str | None = None,
    ttm: bool = False,
) -> int:
    from .data.tushare_provider import TushareProvider

    settings = load_settings()
    code = StockCode.parse(raw_code)
    provider = TushareProvider(get_token())
    unit = _unit_for(code, currency, provider)

    rows = provider.statements(code, currency=unit)
    if not rows:
        print("未取到报表数据，请检查 Token 权限与代码。", file=sys.stderr)
        for issue in provider.issues:
            print(f"  {issue}", file=sys.stderr)
        return 2
    if ttm:
        transformed = statements.apply_ttm(rows)
        rows = transformed.rows
        print(f"TTM：{transformed.note}")

    fx = _fx_for(code, unit, settings)
    divs = provider.dividends(code, currency=unit, dps_fx=fx)
    basic = provider.daily_basic(code)
    # daily_basic with only ts_code returns many dates; the newest row wins.
    basic = sorted(basic, key=lambda r: str(r.get("trade_date", "")), reverse=True)
    weekly = _fx_history(provider.weekly(code), fx)

    rf_value, _ = _rf_for(provider, settings, code, rf, rf_source)
    rf = rf_value

    market_cap = Money(Decimal("0"), Currency.CNY)
    shares = Decimal("0")
    price: Decimal | None = None
    if basic:
        record = basic[0]
        price = _num(record.get("close"))
        if price is not None:
            price = price * fx
        total_mv_wan = _num(record.get("total_mv"))
        total_share_wan = _num(record.get("total_share"))
        if total_mv_wan is not None and total_share_wan is not None:
            market_cap = Money(total_mv_wan * Decimal("10000") * fx, unit)
            shares = total_share_wan * Decimal("10000")

    closes = [
        value
        for item in weekly
        if (value := _num(item.get("close"))) is not None
    ]
    diluted_shares = statements.diluted_shares(rows)

    tax = grids.default_tax_rate(code)
    parent_cash, pledge_pct, buyback = _governance(provider, code, unit)
    sbc = _sbc_from_rows(rows, unit)
    items = kpi_summary(
        code,
        rows,
        divs,
        market_cap=market_cap,
        shares=shares,
        diluted_shares=diluted_shares,
        rf_pct=rf,
        settings=settings,
        tax_pct=tax,
        buyback=buyback,
        closes=closes,
        price=price,
        pledge_pct=pledge_pct,
        parent_cash=parent_cash,
        sbc=sbc,
    )
    _print_kpis(f"{code}", items)

    if provider.issues:
        print("\n数据问题：", file=sys.stderr)
        for issue in provider.issues:
            print(f"  {issue}", file=sys.stderr)

    if save:
        store = StatementStore(output_root() / "store")
        store.append(rows)
        print(f"\n已写入 output/store，snapshot_id={store.snapshot_id(str(code))}")
    return 0


def _pack(
    raw_code: str,
    out: str | None,
    currency: str | None = None,
    rf: float | None = None,
    rf_source: str | None = None,
    pdf_numbers: str | None = None,
    footnotes_path: str | None = None,
    pdf_sections_path: str | None = None,
    as_of: str | None = None,
    pit: bool = False,
) -> int:
    from .data.tushare_provider import TushareProvider
    from .report.pack import render_data_pack

    settings = load_settings()
    code = StockCode.parse(raw_code)
    provider = TushareProvider(get_token())
    unit = _unit_for(code, currency, provider)
    if pit and not as_of:
        print("--pit 必须与 --as-of 一起使用", file=sys.stderr)
        return 2

    rows = provider.statements(code, currency=unit)
    if not rows:
        print("未取到报表数据。", file=sys.stderr)
        for issue in provider.issues:
            print(f"  {issue}", file=sys.stderr)
        return 2
    pit_note = ""
    if as_of:
        try:
            cutoff = date.fromisoformat(as_of)
        except ValueError:
            print(f"无效 --as-of：{as_of}", file=sys.stderr)
            return 2
        if pit:
            from .pit import PitError, PitStore

            try:
                selection = PitStore().load(str(code), cutoff)
                rows = list(selection.rows)
                pit_note = (
                    f"PIT snapshot {selection.snapshot.snapshot_id[:12]} "
                    f"known={selection.snapshot.knowledge_date}；行情/市值仍为最新"
                )
            except PitError as exc:
                print(f"{exc}；回退公告日过滤", file=sys.stderr)
                rows = statements.as_of_rows(rows, cutoff)
                pit_note = "无 PIT snapshot，回退公告日过滤；行情/市值仍为最新"
        else:
            rows = statements.as_of_rows(rows, cutoff)
            pit_note = "财务按公告日过滤；行情/市值仍为最新，非完整 PIT"
        if not rows:
            print(f"截至 {as_of} 没有可用报表。", file=sys.stderr)
            return 2

    fx = _fx_for(code, unit, settings)
    dividends = provider.dividends(code, currency=unit, dps_fx=fx)
    basic = sorted(
        provider.daily_basic(code), key=lambda r: str(r.get("trade_date", "")), reverse=True
    )
    history = _fx_history(provider.weekly(code), fx)
    rf_value, rf_src = _rf_for(provider, settings, code, rf, rf_source)

    quote = basic[0] if basic else None
    market_cap = Money(Decimal("0"), unit)
    shares = Decimal("0")
    price: Decimal | None = None
    if quote:
        price = _num(quote.get("close"))
        if price is not None:
            price = price * fx
            quote = {**quote, "close": float(price)}
        total_mv_wan = _num(quote.get("total_mv"))
        total_share_wan = _num(quote.get("total_share"))
        if total_mv_wan is not None and total_share_wan is not None:
            market_cap = Money(total_mv_wan * Decimal("10000") * fx, unit)
            shares = total_share_wan * Decimal("10000")

    parent_cash, pledge_pct, buyback = _governance(provider, code, unit)
    pdf_bridge = _pdf_bridge(pdf_numbers)
    sbc_value = _pdf_sbc(pdf_numbers)
    sbc = Money(sbc_value, unit) if sbc_value is not None else _sbc_from_rows(rows, unit)
    diluted_shares = statements.diluted_shares(rows)
    holders = provider.holders(code) if hasattr(provider, "holders") else []
    main_business = (
        provider.main_business(code) if hasattr(provider, "main_business") else []
    )
    footnotes = None
    if footnotes_path:
        import json

        footnotes = json.loads(Path(footnotes_path).read_text(encoding="utf-8-sig"))
    pdf_sections = None
    if pdf_sections_path:
        import json

        pdf_sections = json.loads(Path(pdf_sections_path).read_text(encoding="utf-8-sig"))
    markdown = render_data_pack(
        code,
        rows,
        dividends,
        quote=quote,
        history=history,
        market_cap=market_cap,
        shares=shares,
        diluted_shares=diluted_shares,
        rf_pct=rf_value,
        settings=settings,
        issues=provider.issues,
        tax_pct=grids.default_tax_rate(code),
        rf_source=rf_src,
        parent_cash=parent_cash,
        pledge_pct=pledge_pct,
        buyback=buyback,
        sbc=sbc,
        pdf_bridge=pdf_bridge,
        holders=holders,
        main_business=main_business,
        as_of=as_of or (str(quote.get("trade_date", "")) if quote else ""),
        footnotes=footnotes,
        pdf_sections=pdf_sections,
        pit_note=pit_note,
    )

    path = Path(out) if out else output_root() / str(code) / "data_pack.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(markdown.encode("utf-8"))
    print(f"数据包已写入 {path.resolve()}")
    print(f"字节数：{len(markdown.encode('utf-8')):,} ｜ 行数：{markdown.count(chr(10)) + 1}")
    return 0





def _qualitative_cmd(code_raw: str, init: bool, check: bool, out: str | None) -> int:
    code = StockCode.parse(code_raw)
    path = Path(out) if out else output_root() / str(code) / "qualitative.json"
    if init:
        write_template(path)
        print(f"模板已写入 {path.resolve()}")
        print("填写 judgment/confidence/evidence 后，用 --check 校验，再运行 report。")
        return 0
    if check:
        if not path.is_file():
            print(f"文件不存在：{path}", file=sys.stderr)
            return 2
        qualitative = load_qualitative(path)
        print(f"{path} 校验通过")
        for label, judgment, confidence, count in qualitative_summary(qualitative):
            print(f"  {label:<12} {judgment:<9} 置信度 {confidence:<6} 证据 {count}")
        return 0
    print(f"{path.resolve()} ｜ {'存在' if path.is_file() else '不存在（用 --init 生成模板）'}")
    return 0


def _golden_cmd(
    init: str | None, codes: str, score_path: str | None, threshold: float
) -> int:
    from . import golden

    if init:
        code_list = [item.strip() for item in codes.split(",") if item.strip()]
        if not code_list:
            print("--init 需要配合 --codes（逗号分隔）", file=sys.stderr)
            return 2
        path = golden.write_template(init, code_list)
        print(f"模板已写入 {path}（{len(code_list) * 6} 行待标注）")
        return 0
    if score_path:
        labels = golden.read_labels(score_path)
        if not labels:
            print("没有有效标注行（human_judgment 需为 positive/neutral/negative/unknown）", file=sys.stderr)
            return 2
        result = golden.score(labels, output_root())
        print(golden.format_report(result))
        return 0 if result["agreement"] >= threshold else 1
    print("用法：turtle golden --init <csv> --codes 600887.SH,... 或 --score <csv>", file=sys.stderr)
    return 2


def _qa_cmd(
    code_raw: str,
    write: bool,
    json_out: str | None = None,
    allow_missing_qualitative: bool = False,
) -> int:
    from . import qa
    from . import state as st

    code = StockCode.parse(code_raw)
    rows = qa.run_qa(
        str(code),
        output_root(),
        allow_missing_qualitative=allow_missing_qualitative,
    )
    print(f"QA：{code}")
    for name, status, detail in rows:
        print(f"  {name:<20} | {status:<6} | {detail}")
    bad = qa.failed(rows)
    if json_out or write:
        target = qa.write_json(
            str(code),
            rows,
            path=json_out,
            root=output_root(),
        )
        print(f"QA JSON：{target.resolve()}")
    if bad:
        print(f"未通过：{', '.join(bad)}", file=sys.stderr)
        return 1
    if write:
        path = st.path_for(str(code), output_root())
        run = st.load(path) if path.is_file() else st.new(str(code))
        st.advance(run, "done")
        st.save(run, path)
        print("已推进到 done")
    return 0


def _narrative_cmd(code_raw: str, file_path: str) -> int:
    from . import narrative

    code = StockCode.parse(code_raw)
    bad = narrative.check(str(code), file_path, root=output_root())
    if bad:
        print("叙述中出现无法追溯的数字：" + ", ".join(bad), file=sys.stderr)
        print("只能引用 analysis_report.md / data_pack.md / qualitative.json 中的数字。", file=sys.stderr)
        return 1
    print("叙述数字全部可追溯。")
    return 0


def _verify_cmd(
    code_raw: str,
    qualitative_path: str | None,
    threshold: float,
    timeout: int,
    write: bool,
) -> int:
    import json as _json

    from . import verify as vf
    from .qualitative import load as load_q

    code = StockCode.parse(code_raw)
    path = (
        Path(qualitative_path)
        if qualitative_path
        else output_root() / str(code) / "qualitative.json"
    )
    qualitative = load_q(path)
    checks = vf.check_qualitative(
        qualitative,
        fetch=lambda url: vf.fetch_url(url, timeout),
        threshold=threshold,
    )
    ok = sum(1 for check in checks if check.status == "ok")
    print(f"证据校验：{ok}/{len(checks)} 通过（阈值 {threshold:.2f}）")
    for check in checks:
        print(
            f"  {check.module:<16}{check.status:<14}{check.score:>6.3f}  {check.url[:80]}"
        )

    failed = vf.failing_modules(checks)
    if write and failed:
        payload = _json.loads(path.read_text(encoding="utf-8"))
        updated = vf.downgrade(payload, failed)
        path.write_text(
            _json.dumps(updated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"已降级 {len(failed)} 个模块：{', '.join(sorted(failed))}")
    elif failed:
        print(f"未通过模块：{', '.join(sorted(failed))}（加 --write 可自动降级）")
    return 0 if not failed else 1


def _state_cmd(
    code_raw: str,
    init: bool,
    phase: str | None,
    artifact: str | None,
    warnings: list[str] | None,
) -> int:
    import json as _json

    from . import state as st

    code = StockCode.parse(code_raw)
    path = st.path_for(str(code), output_root())
    if init or not path.is_file():
        run = st.new(str(code))
    else:
        run = st.load(path)

    if phase:
        st.advance(run, phase)
    if artifact:
        key, _, value = artifact.partition("=")
        if not key or not value:
            print("--artifact 需要 key=path 格式", file=sys.stderr)
            return 2
        st.add_artifact(run, key, value)
    for message in warnings or []:
        st.add_warning(run, message)

    st.save(run, path)
    print(_json.dumps(run.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _audit(raw_code: str, doc_path: str, write_path: str | None, threshold: float) -> int:
    import json

    from .data.tushare_provider import TushareProvider
    from .metrics import statements
    from .metrics.audit import compare, parse_doc_items

    code = StockCode.parse(raw_code)
    provider = TushareProvider(get_token())
    unit = _unit_for(code, None, provider)
    rows = provider.statements(code, currency=unit)
    if not rows:
        print("未取到报表数据。", file=sys.stderr)
        return 2

    years = sorted({r.period_end.year for r in rows if r.period_type == "annual"})
    latest = max(years)
    series = statements.annual_series
    cli = {
        "revenue": series(rows, "income", "revenue").get(latest),
        "net_income": series(rows, "income", "n_income_attr_p").get(latest),
        "ocf": series(rows, "cashflow", "n_cashflow_act").get(latest),
        "capex": series(rows, "cashflow", "c_pay_acq_const_fiolta").get(latest),
        "equity": series(rows, "balance", "total_hldr_eqy_exc_min_int").get(latest),
        "total_assets": series(rows, "balance", "total_assets").get(latest),
        "accounts_receiv": series(rows, "balance", "accounts_receiv").get(latest),
        "inventory": series(rows, "balance", "inventory").get(latest),
        "contract_liab": series(rows, "balance", "contract_liab").get(latest),
        "adv_receipts": series(rows, "balance", "adv_receipts").get(latest),
        "prepayments": series(rows, "balance", "prepayments").get(latest),
    }
    cli = {key: value for key, value in cli.items() if value is not None}

    payload = json.loads(Path(doc_path).read_text(encoding="utf-8"))
    documents = parse_doc_items(payload.get("items", []))
    rows_out = compare(cli, documents, threshold_pct=Decimal(str(threshold)))

    print(f"审计口径：{code} FY{latest} ｜ 阈值 {threshold}% ｜ 文档条目 {len(documents)}")
    if payload.get("document_hash"):
        print(
            f"文档 hash：{str(payload['document_hash'])[:16]} ｜ "
            f"DocumentFact：{len(payload.get('document_facts', []))}"
        )
    if not rows_out:
        print("未发现数字口径冲突。")
    else:
        print(f"{'项目':<10}{'CLI(百万)':>14}{'文档(百万)':>14}  来源 / 备注")
        for row in rows_out:
            print(
                f"{row['item']:<10}{row['cli_value']:>14}{row['doc_value']:>14}  "
                f"rank={row.get('source_rank', '?')} {row['source']} {row['note']}"
            )

    if write_path:
        path = Path(write_path)
        if not path.is_file():
            print(f"目标 qualitative.json 不存在：{path}", file=sys.stderr)
            return 2
        target = json.loads(path.read_text(encoding="utf-8"))
        existing = target.get("discrepancies", []) or []
        target["discrepancies"] = existing + rows_out
        path.write_text(
            json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"已写入 {path.resolve()}（新增 {len(rows_out)} 条）")
    return 0


def _run_passthrough(module_main, argv: list[str], *, patch_argv: bool = False) -> int:
    """Run a ported CLI whose argparse lives in its own module."""
    import sys

    old_argv = sys.argv
    try:
        if patch_argv:
            sys.argv = ["turtle", *argv]
            module_main()
        else:
            module_main(argv)
    except SystemExit as exc:
        return int(exc.code or 0)
    finally:
        sys.argv = old_argv
    return 0


def _valuation(
    raw_code: str,
    currency: str | None = None,
    rf: float | None = None,
    rf_source: str | None = None,
    ttm: bool = False,
) -> int:
    """Deterministic DCF/DDM/PE-band/PEG/PS valuation snapshot."""
    from .data.tushare_provider import TushareProvider
    from .metrics import dividends as div_metrics
    from .metrics import statements, valuation_models
    from .metrics.dividends import average_dps

    settings = load_settings()
    code = StockCode.parse(raw_code)
    provider = TushareProvider(get_token())
    unit = _unit_for(code, currency, provider)
    rows = provider.statements(code, currency=unit)
    if not rows:
        print("未取到报表数据。", file=sys.stderr)
        return 2
    if ttm:
        transformed = statements.apply_ttm(rows)
        rows = transformed.rows
        print(f"TTM：{transformed.note}")
    fx = _fx_for(code, unit, settings)
    dividends = provider.dividends(code, currency=unit, dps_fx=fx)
    basic = sorted(
        provider.daily_basic(code), key=lambda r: str(r.get("trade_date", "")), reverse=True
    )
    quote = basic[0] if basic else None
    price = _num(quote.get("close")) if quote else None
    if price is not None:
        price = price * fx
    market_cap = Decimal("0")
    shares = Decimal("0")
    if quote:
        total_mv_wan = _num(quote.get("total_mv"))
        total_share_wan = _num(quote.get("total_share"))
        if total_mv_wan is not None and total_share_wan is not None:
            market_cap = total_mv_wan * Decimal("10000") * fx
            shares = total_share_wan * Decimal("10000")
    if market_cap <= 0 or shares <= 0 or price is None:
        print("行情/股本不足，无法估值。", file=sys.stderr)
        return 2

    rf_value, rf_src = _rf_for(provider, settings, code, rf, rf_source)
    years = sorted({r.period_end.year for r in rows if r.period_type == "annual"})
    latest = max(years) if years else None
    income = lambda item: statements.annual_series(rows, "income", item)  # noqa: E731
    fcf = statements.fcf_series(rows)
    debt = statements.interest_bearing_debt(rows)
    cash = statements.cash_and_equivalents(rows)
    revenue = statements.revenue(rows)
    net_income = statements.net_income(rows)
    eps_series = income("basic_eps")
    eps = eps_series.get(latest) if latest else None
    value_shares = statements.diluted_shares(rows) or shares

    tax_pct = (
        Decimal("16.5") if code.market is Market.HK
        else Decimal("21") if code.market is Market.US
        else Decimal("25")
    )
    erp_pct = (
        Decimal("5.5") if code.market is Market.HK
        else Decimal("5.0") if code.market is Market.US
        else Decimal("6.0")
    )
    terminal_pct = (
        Decimal("2.5") if code.market in (Market.HK, Market.US) else Decimal("3.0")
    )
    beta = (
        Decimal("0.8") if market_cap > Decimal("100000000000")
        else Decimal("1.0") if market_cap > Decimal("10000000000")
        else Decimal("1.2")
    )
    finance_exp = income("finance_exp").get(latest) if latest else None
    debt_latest = debt.get(latest) if latest else None
    cost_of_debt = (
        (finance_exp / debt_latest * Decimal("100"))
        if finance_exp is not None and debt_latest and debt_latest > 0
        else Decimal("5")
    )
    cost_of_debt = min(max(cost_of_debt, Decimal("2")), Decimal("8"))
    wacc_pct = valuation_models.wacc(
        rf_pct=rf_value,
        beta=beta,
        erp_pct=erp_pct,
        cost_of_debt_pct=cost_of_debt,
        tax_pct=tax_pct,
        equity_value=market_cap,
        debt_value=debt_latest or Decimal("0"),
    )
    if wacc_pct is None:
        print("WACC 无法计算（市值/债务异常）。", file=sys.stderr)
        return 2

    recent_fcf = [value for _, value in sorted(fcf.items())[-3:]]
    fcf_base = (
        sum(recent_fcf, Decimal("0")) / Decimal(len(recent_fcf))
        if recent_fcf
        else None
    )
    fcf_growth = statements.cagr(fcf, years=5)
    growth_pct = min(max((fcf_growth or Decimal("0.05")) * Decimal("100"), Decimal("0")), Decimal("15"))
    growth_rates = (
        growth_pct,
        growth_pct,
        (growth_pct * Decimal("2") + terminal_pct) / Decimal("3"),
        (growth_pct + terminal_pct * Decimal("2")) / Decimal("3"),
        terminal_pct,
    )
    dcf = valuation_models.dcf(
        fcf_base=fcf_base,
        growth_rates_pct=growth_rates,
        terminal_growth_pct=terminal_pct,
        wacc_pct=wacc_pct,
        cash=cash.get(latest) if latest else None,
        debt=debt_latest,
        shares=value_shares,
    )
    ke_pct = rf_value + beta * erp_pct
    ddm = valuation_models.ddm(
        dps=average_dps(dividends),
        ke_pct=ke_pct,
        growth_pct=terminal_pct,
    )
    eps_value = eps if eps and eps > 0 else None
    _pe_low, pe_mid, _pe_high = valuation_models.pe_band(
        eps=eps_value,
        pe_low=Decimal("10"),
        pe_mid=Decimal("15"),
        pe_high=Decimal("25"),
    )
    ni_growth = statements.net_income_cagr(rows)
    peg = valuation_models.peg(
        eps=eps_value,
        growth_pct=ni_growth * Decimal("100") if ni_growth is not None else None,
    )
    revenue_latest = revenue.get(latest) if latest else None
    revenue_per_share = revenue_latest / value_shares if revenue_latest is not None else None
    ps = valuation_models.ps(revenue_per_share=revenue_per_share, ps_multiple=Decimal("2"))
    values = {
        "DCF": dcf["per_share"],
        "DDM": ddm,
        "PE Band": pe_mid,
        "PEG": peg,
        "PS": ps,
    }
    equity_series = statements.equity(rows)
    roe_values = [
        net_income[year] / equity_series[year] * Decimal("100")
        for year in sorted(set(net_income) & set(equity_series))[-5:]
        if equity_series[year] and equity_series[year] > 0
    ]
    roe_5y = sum(roe_values, Decimal("0")) / Decimal(len(roe_values)) if roe_values else None
    payout_map = div_metrics.payout_by_year(dividends, net_income, shares=shares)
    payout_values = [
        value for year, value in sorted(payout_map.items())[-3:] if value is not None
    ]
    payout_3y = (
        sum(payout_values, Decimal("0")) / Decimal(len(payout_values))
        if payout_values
        else None
    )
    rev_growth = statements.revenue_cagr(rows)
    profile, weights = valuation_models.classify_company(
        roe_5y=roe_5y,
        payout_3y=payout_3y,
        revenue_cagr=rev_growth * Decimal("100") if rev_growth is not None else None,
        profit_cagr=ni_growth * Decimal("100") if ni_growth is not None else None,
    )
    fair = valuation_models.cross_validate(values, weights)
    upside = valuation_models.blended_upside(price, fair)
    wacc_offsets, sensitivity = valuation_models.dcf_sensitivity(
        fcf_base=fcf_base,
        growth_rates_pct=growth_rates,
        terminal_growth_pct=terminal_pct,
        wacc_pct=wacc_pct,
        cash=cash.get(latest) if latest else None,
        debt=debt_latest,
        shares=value_shares,
    )
    implied = valuation_models.implied_growth_pct(
        fcf_base=fcf_base,
        wacc_pct=wacc_pct,
        terminal_growth_pct=terminal_pct,
        cash=cash.get(latest) if latest else None,
        debt=debt_latest,
        shares=value_shares,
        current_price=price,
    )

    def show(value: Decimal | None) -> str:
        return "—" if value is None else f"{value:,.2f}"

    print(f"=== 估值快照：{code} ===")
    print(f"报表币种 {unit.value} ｜ 当前价 {price:,.2f} ｜ 总市值 {market_cap / Decimal('1000000'):,.2f} 百万元")
    print(f"Rf {rf_value:.2f}%（{rf_src}）｜ WACC {wacc_pct:.2f}% ｜ β {beta} ｜ ERP {erp_pct}% ｜ 税率 {tax_pct}%")
    print(f"公司类型 {profile} ｜ ROE5y {show(roe_5y)}% ｜ 支付率3y {show(payout_3y)}% ｜ 营收CAGR {show(rev_growth * 100 if rev_growth is not None else None)}%")
    print(f"FCF 基数 {show(fcf_base / Decimal('1000000') if fcf_base is not None else None)} 百万元 ｜ 5 年 FCF CAGR {show(fcf_growth * 100 if fcf_growth is not None else None)}% ｜ 采用增长 {growth_pct:.2f}%")
    print(f"方法权重：{' / '.join(f'{name} {weight:g}%' for name, weight in weights.items())}")
    print("")
    print(f"{'方法':<10}{'每股价值':>14}  说明")
    for name, value in values.items():
        note = {
            "DCF": f"WACC {wacc_pct:.2f}% / 终值增长 {terminal_pct}%",
            "DDM": f"Ke {ke_pct:.2f}% / g {terminal_pct}%",
            "PE Band": "PE 10/15/25x，取中值",
            "PEG": "目标 PEG=1.0",
            "PS": "PS=2.0x",
        }[name]
        print(f"{name:<10}{show(value):>14}  {note}")
    print(f"{'综合':<10}{show(fair):>14}  （可用方法加权）")
    print(f"当前价 {price:,.2f} ｜ 综合公平价 {show(fair)} ｜ 空间 {show(upside)}%")
    print("")
    print("DCF 敏感性（行：WACC 偏移；列：终值增长偏移）")
    growth_offsets = (Decimal("-1"), Decimal("-0.5"), Decimal("0"), Decimal("0.5"), Decimal("1"))
    header = "WACC\\g" + "".join(f"{offset:>10}" for offset in growth_offsets)
    print(header)
    for wacc_offset, row in zip(wacc_offsets, sensitivity):
        print(f"{wacc_offset:>6}" + "".join(f"{show(value):>10}" for value in row))
    print(f"反推 5 年增长（股价隐含）：{show(implied)}%")
    return 0


def _cleanroom_cmd(
    snapshot: str,
    pdf_numbers: str,
    threshold: float,
    out: str | None,
    strict: bool,
    pdf_file: str | None = None,
) -> int:
    import json

    from .cleanroom import run

    try:
        result = run(
            snapshot,
            pdf_numbers,
            threshold_pct=Decimal(str(threshold)),
            pdf_file=pdf_file,
        )
    except (OSError, ValueError) as exc:
        print(f"clean-room 失败：{exc}", file=sys.stderr)
        return 2
    if out:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"clean-room 结果：{target.resolve()}")
    for check in result["checks"]:
        print(f"{check['label']}: {check['status']} {check.get('diff_pct', '')}%")
    if strict and result["status"] != "pass":
        return 1
    return 0


def _numeric_audit_cmd(
    report: str,
    sources: list[str],
    out: str | None,
    strict: bool = False,
) -> int:
    import json

    from .numeric_audit import audit

    try:
        result = audit(report, sources, strict=strict)
    except OSError as exc:
        print(f"numeric audit 失败：{exc}", file=sys.stderr)
        return 2
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if out:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((text + "\n").encode("utf-8"))
        print(f"numeric audit：{target.resolve()}")
    else:
        print(text)
    return 0 if result["status"] == "pass" else 1


def _smoke_cmd(
    codes: str,
    rf: float | None,
    rf_source: str | None,
    snapshot: bool,
) -> int:
    root = output_root() / "smoke"
    failures: list[str] = []
    targets = [item.strip() for item in codes.split(",") if item.strip()]
    for raw in targets:
        code = StockCode.parse(raw)
        target = root / str(code) / "analysis_report.md"
        snapshot_dir = root / str(code) / "snapshot" if snapshot else None
        rc = _report(
            raw,
            str(target),
            rf=rf,
            rf_source=rf_source,
            save_snapshot=str(snapshot_dir) if snapshot_dir else None,
        )
        if rc != 0 or not target.is_file() or target.stat().st_size < 1000:
            failures.append(str(code))
            continue
        if snapshot_dir is not None and not (snapshot_dir / "manifest.json").is_file():
            failures.append(f"{code}: manifest missing")
            continue
        print(f"smoke {code}: PASS ({target.stat().st_size:,} bytes)")
    print(f"smoke: {len(targets) - len(failures)}/{len(targets)} pass")
    if failures:
        print("smoke failures: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


def _pit_cmd(
    action: str,
    code_raw: str,
    known_at: str | None,
    as_of: str | None,
    out: str | None,
    backfill: bool,
    keep: int = 5,
) -> int:
    import json

    from .data.tushare_provider import TushareProvider
    from .metrics import statements
    from .pit import PitError, PitStore, rows_payload

    code = StockCode.parse(code_raw)
    store = PitStore()
    if action == "freeze":
        provider = TushareProvider(get_token())
        rows = provider.statements(code, currency=_unit_for(code, None, provider))
        if not rows:
            print("未取到报表数据。", file=sys.stderr)
            return 2
        known = known_at or date.today().isoformat()
        if backfill:
            snapshots = store.freeze_backfill(str(code), rows)
            print(f"PIT backfill：{len(snapshots)} 个公告日 snapshot")
            for snap in snapshots[-3:]:
                print(f"  {snap.knowledge_date} {snap.snapshot_id[:12]} rows={len(snap.rows)}")
        else:
            snap = store.write(str(code), rows, known, source="tushare")
            print(f"PIT snapshot：{snap.snapshot_id[:12]} knowledge={snap.knowledge_date} rows={len(snap.rows)}")
        return 0
    if action == "prune":
        try:
            removed = store.prune(str(code), keep=keep)
        except PitError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(f"PIT prune：删除 {removed} 个旧 snapshot，保留最新 {keep} 个")
        return 0
    if action == "list":
        entries = store.list(str(code))
        if not entries:
            print("没有 PIT snapshot。", file=sys.stderr)
            return 2
        for entry in entries:
            print(
                f"{entry.get('knowledge_date')} {str(entry.get('snapshot_id'))[:12]} "
                f"rows={entry.get('row_count')} backfill={entry.get('backfill')}"
            )
        return 0
    if as_of is None:
        print("show/export 需要 --as-of", file=sys.stderr)
        return 2
    try:
        selection = store.load(str(code), as_of)
    except PitError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if action == "show":
        print(
            f"as_of={selection.as_of} knowledge={selection.snapshot.knowledge_date} "
            f"snapshot={selection.snapshot.snapshot_id[:12]} rows={len(selection.rows)}"
        )
        for row in statements.annual_series(selection.rows, "income", "revenue").items():
            print(f"  revenue {row[0]}: {row[1]}")
        return 0
    if action == "export":
        target = Path(out) if out else output_root() / "pit" / str(code) / f"export_{as_of}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(
            (
                json.dumps(
                    {
                        "code": str(code),
                        "as_of": selection.as_of,
                        "knowledge_date": selection.snapshot.knowledge_date,
                        "snapshot_id": selection.snapshot.snapshot_id,
                        "rows": rows_payload(selection.rows),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
        )
        print(f"PIT 导出：{target.resolve()} rows={len(selection.rows)}")
        return 0
    print(f"未知 pit action：{action}", file=sys.stderr)
    return 2


def _agent_cmd(
    directory: str,
    phase: str | None,
    commands: list[str] | None = None,
    timeout: int = 300,
    retries: int = 0,
    resume: bool = False,
) -> int:
    from .agent import PHASES, run, run_commands, validate

    root = Path(directory)
    if not root.is_dir():
        print(f"找不到目录：{root}", file=sys.stderr)
        return 2
    command_map: dict[str, str] = {}
    for item in commands or []:
        key, separator, command = item.partition("=")
        if not separator or not command.strip():
            print(f"--command 需要 phase=command：{item}", file=sys.stderr)
            return 2
        if key not in PHASES:
            print(f"未知 agent phase：{key}", file=sys.stderr)
            return 2
        command_map[key] = command
    if command_map:
        selected = [phase] if phase else list(PHASES)
        if phase and phase not in command_map:
            print(f"phase {phase} 没有对应 --command", file=sys.stderr)
            return 2
        results = run_commands(
            root,
            command_map,
            phases=selected,
            timeout=timeout,
            retries=retries,
            resume=resume,
        )
    elif phase:
        result = validate(root, phase)
        print(f"{result.phase}: {result.status}" + (f" missing={result.missing}" if result.missing else ""))
        return 0 if result.status == "pass" else 1
    else:
        results = run(root, phases=PHASES)
    for result in results:
        print(f"{result.phase}: {result.status}" + (f" missing={result.missing}" if result.missing else ""))
    return 0 if results and all(r.status == "pass" for r in results) else 1


def _snapshot_cmd(
    code_text: str,
    as_of: str,
    out: str | None,
    report_path: str | None,
    research_path: str | None,
) -> int:
    import json

    from .data.store import StatementStore
    from .facts import (
        ReportManifest,
        config_payload,
        content_hash,
        file_hash,
        template_hash,
    )

    code = StockCode.parse(code_text)
    rows = StatementStore(output_root() / "store").read(str(code))
    if not rows:
        print("output/store 中没有该股票的报表行；先运行 pack/report 并 --save。", file=sys.stderr)
        return 2
    facts_payload = [
        {
            "code": row.code,
            "period_end": row.period_end.isoformat(),
            "period_type": row.period_type,
            "statement": row.statement,
            "item": row.item,
            "value": str(row.value),
            "currency": row.currency.value,
            "source": row.source,
        }
        for row in sorted(rows, key=lambda r: (r.period_end, r.statement, r.item, r.source))
    ]
    settings = load_settings()
    manifest = ReportManifest(
        code=str(code),
        as_of=as_of,
        currency=str(rows[0].currency.value),
        facts_hash=content_hash(facts_payload),
        config_hash=content_hash(config_payload(settings)),
        research_hash=file_hash(research_path) if research_path else "",
        template_hash=template_hash(Path(__file__).resolve().parent / "report" / "templates"),
        engine_version=__version__,
        report_hash=file_hash(report_path) if report_path else "",
    )
    target = Path(out) if out else output_root() / str(code) / "manifest.json"
    manifest.write(target)
    print(f"snapshot_id: {manifest.snapshot_id}")
    print(f"manifest: {target.resolve()}")
    print(json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _research_context(
    snapshot: str,
    data_pack: str | None = None,
) -> dict[str, object]:
    import json

    root = Path(snapshot)
    inputs_path = root / "inputs.json"
    if not inputs_path.is_file():
        raise FileNotFoundError(f"找不到 snapshot inputs：{inputs_path}")
    payload = json.loads(inputs_path.read_text(encoding="utf-8-sig"))
    context: dict[str, object] = {
        "code": payload.get("code", ""),
        "as_of": payload.get("as_of", ""),
        "currency": payload.get("currency", ""),
        "metrics": {},
        "facts": [],
        "governance": {
            "parent_cash": payload.get("parent_cash"),
            "pledge_pct": payload.get("pledge_pct"),
            "buyback": payload.get("buyback"),
            "audit": payload.get("audit", []),
        },
    }
    manifest = root / "manifest.json"
    if manifest.is_file():
        manifest_payload = json.loads(manifest.read_text(encoding="utf-8-sig"))
        context["snapshot_id"] = manifest_payload.get("snapshot_id", "")
    try:
        from .data.coverage import capabilities
        from .types import StockCode

        context["coverage"] = [
            {"key": row.key, "label": row.label, "status": row.status, "detail": row.detail}
            for row in capabilities(StockCode.parse(str(context["code"])))
        ]
    except (KeyError, ValueError):
        context["coverage"] = []
    metrics_path = root / "metrics.json"
    if metrics_path.is_file():
        context["metrics"] = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    reported = root / "reported_numbers.json"
    if reported.is_file():
        report_payload = json.loads(reported.read_text(encoding="utf-8-sig"))
        context["facts"] = report_payload.get("document_facts", [])
    evidence = root / "evidence.json"
    if evidence.is_file():
        evidence_payload = json.loads(evidence.read_text(encoding="utf-8-sig"))
        if isinstance(evidence_payload, list):
            context["facts"] = list(context["facts"]) + evidence_payload
    governance = context["governance"]
    if isinstance(governance, dict) and any(governance.values()):
        facts = context["facts"]
        if isinstance(facts, list):
            facts.append(
                {
                    "id": "data:governance",
                    "url": "",
                    "page": "",
                    "source_type": "data",
                    "quote": (
                        f"parent_cash={governance.get('parent_cash')}; "
                        f"pledge_pct={governance.get('pledge_pct')}; "
                        f"buyback={governance.get('buyback')}; "
                        f"audit={governance.get('audit')}"
                    ),
                }
            )
    if data_pack and Path(data_pack).is_file():
        context["data_pack"] = Path(data_pack).read_text(encoding="utf-8-sig")[:40000]
    elif (root / "data_pack.md").is_file():
        context["data_pack"] = (root / "data_pack.md").read_text(
            encoding="utf-8-sig"
        )[:40000]
    pdf_sections = root / "pdf_sections.json"
    if pdf_sections.is_file():
        sections = json.loads(pdf_sections.read_text(encoding="utf-8-sig"))
        context["pdf_sections"] = {
            str(key): str(value)[:12000]
            for key, value in sections.items()
            if key != "metadata" and isinstance(value, str)
        }
    return context


def _research_context_cmd(
    snapshot: str,
    out: str,
    data_pack: str | None,
) -> int:
    import json

    try:
        context = _research_context(snapshot, data_pack)
    except (OSError, ValueError, KeyError) as exc:
        print(f"research context 失败：{exc}", file=sys.stderr)
        return 2
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (json.dumps(context, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    print(f"research context 已写入 {target.resolve()}")
    return 0


def _research_provenance_cmd(
    research_path: str,
    snapshot: str,
    provider: str,
    model: str,
    out: str,
    generated_at: str | None,
) -> int:
    import hashlib
    import json
    from datetime import datetime, timezone

    source = Path(research_path)
    if not source.is_file():
        print(f"找不到 research.json：{source}", file=sys.stderr)
        return 2
    context_path = Path(snapshot) / "research_context.json"
    context_hash = ""
    if context_path.is_file():
        context_hash = hashlib.sha256(context_path.read_bytes()).hexdigest()
    payload = {
        "provider": provider,
        "model": model,
        "generated_at": generated_at
        or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "research_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "context_sha256": context_hash,
    }
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
            "utf-8"
        )
    )
    print(f"research provenance 已写入 {target.resolve()}")
    return 0


def _research_agent_cmd(
    snapshot: str,
    out: str,
    base_url: str | None,
    model: str | None,
    api_key: str | None,
    data_pack: str | None = None,
    retries: int = 0,
    min_claims: int = 0,
    min_dimensions: int = 0,
    response: str | None = None,
) -> int:
    import json
    import os

    from .agent import AgentError, FakeLLM, LLM, OpenAICompatibleLLM, ResearchAgent
    from .research import to_payload

    try:
        context = _research_context(snapshot, data_pack)
    except (OSError, ValueError, KeyError) as exc:
        print(f"找不到 snapshot context：{exc}", file=sys.stderr)
        return 2

    key = api_key or os.environ.get("TURTLE_LLM_API_KEY", "")
    url = base_url or os.environ.get(
        "TURTLE_LLM_BASE_URL", "https://api.openai.com/v1"
    )
    model_name = model or os.environ.get("TURTLE_LLM_MODEL", "")
    if response and Path(response).is_file():
        llm: LLM = FakeLLM(
            json.loads(Path(response).read_text(encoding="utf-8-sig"))
        )
    elif not key or not model_name:
        print(
            "缺少 LLM 配置：设置 TURTLE_LLM_API_KEY / TURTLE_LLM_MODEL（或 --api-key/--model）",
            file=sys.stderr,
        )
        return 2
    else:
        llm = OpenAICompatibleLLM(base_url=url, model=model_name, api_key=key)
    try:
        document = ResearchAgent(llm).run(
            context,
            retries=retries,
            min_claims=min_claims,
            min_dimensions=min_dimensions,
        )
    except AgentError as exc:
        print(f"research agent 失败：{exc}", file=sys.stderr)
        return 2
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (
            json.dumps(to_payload(document), ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
    )
    print(
        f"research.json 已写入 {target.resolve()}："
        f"{len(document.claims)} claims，{len(document.params)} params，"
        f"{len(document.decisions)} decisions"
    )
    return 0


def _coverage_cmd(code_raw: str, as_json: bool) -> int:
    import json

    from .data.coverage import capabilities

    code = StockCode.parse(code_raw)
    rows = capabilities(code)
    if as_json:
        print(
            json.dumps(
                [
                    {
                        "key": row.key,
                        "label": row.label,
                        "status": row.status,
                        "detail": row.detail,
                    }
                    for row in rows
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"数据覆盖：{code}")
        for row in rows:
            print(f"  {row.label:<18} | {row.status:<14} | {row.detail}")
    return 0


def _hkex_news_cmd(
    code_raw: str,
    from_date: str,
    to_date: str,
    keyword: str,
    out: str,
) -> int:
    import json

    from .data.hkexnews import (
        UrllibTransport,
        buyback_evidence,
        search_announcements,
        stock_id_map,
    )

    code = code_raw.split(".")[0].zfill(5)
    transport = UrllibTransport()
    try:
        mapping = stock_id_map(
            transport.get(
                "https://www.hkexnews.hk/ncms/script/eds/activestock_sehk_e.json"
            )
        )
    except Exception as exc:  # noqa: BLE001
        print(f"HKEXnews 股票映射失败：{exc}", file=sys.stderr)
        return 2
    stock_id = mapping.get(code)
    if not stock_id:
        print(f"HKEXnews 找不到股票：{code}", file=sys.stderr)
        return 2
    try:
        rows = search_announcements(
            stock_id,
            from_date=from_date,
            to_date=to_date,
            title_keyword=keyword,
            transport=transport,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"HKEXnews 查询失败：{exc}", file=sys.stderr)
        return 2
    evidence = buyback_evidence(rows)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (json.dumps(evidence, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    print(f"HKEXnews evidence 已写入 {target.resolve()}（{len(evidence)} 条）")
    return 0


def _sec_evidence_cmd(
    ticker: str | None,
    cik: int | None,
    out: str,
) -> int:
    import json

    from .data.sec import (
        cik_for_ticker,
        evidence_facts,
        fetch_companyfacts,
        fetch_submissions,
        filing_evidence,
    )

    if cik is None:
        if not ticker:
            print("需要 --ticker 或 --cik", file=sys.stderr)
            return 2
        try:
            cik = cik_for_ticker(ticker)
        except Exception as exc:  # noqa: BLE001
            print(f"SEC CIK 查询失败：{exc}", file=sys.stderr)
            return 2
    try:
        payload = fetch_companyfacts(cik)
    except Exception as exc:  # noqa: BLE001
        print(f"SEC companyfacts 查询失败：{exc}", file=sys.stderr)
        return 2
    facts = evidence_facts(payload, cik=cik)
    try:
        facts.extend(filing_evidence(fetch_submissions(cik), cik=cik))
    except Exception:  # noqa: BLE001 - filing metadata is optional
        pass
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (json.dumps(facts, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    print(f"SEC evidence 已写入 {target.resolve()}（{len(facts)} facts）")
    return 0


def _sec_audit_cmd(
    snapshot: str,
    ticker: str | None,
    cik: int | None,
    out: str | None,
    tolerance: float,
) -> int:
    import json

    from .data.sec import annual_facts, cik_for_ticker, compare_rows, UrllibTransport

    inputs_path = Path(snapshot) / "inputs.json"
    if not inputs_path.is_file():
        print(f"找不到 snapshot inputs：{inputs_path}", file=sys.stderr)
        return 2
    payload = json.loads(inputs_path.read_text(encoding="utf-8-sig"))
    if cik is None:
        if not ticker:
            print("需要 --ticker 或 --cik", file=sys.stderr)
            return 2
        try:
            cik = cik_for_ticker(ticker)
        except Exception as exc:  # noqa: BLE001
            print(f"SEC CIK 查询失败：{exc}", file=sys.stderr)
            return 2
    try:
        facts_payload = UrllibTransport().get(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json",
            {"User-Agent": "turtle-deterministic/0.1 research@example.com"},
        )
    except Exception as exc:  # noqa: BLE001
        print(f"SEC companyfacts 查询失败：{exc}", file=sys.stderr)
        return 2
    result = {
        "cik": cik,
        "rows": compare_rows(
            payload.get("rows", []),
            annual_facts(facts_payload),
            tolerance_pct=Decimal(str(tolerance)),
        ),
    }
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if out:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((text + "\n").encode("utf-8"))
        print(f"SEC audit：{target.resolve()}")
    else:
        print(text)
    return 0


def _research_audit_cmd(
    path: str,
    metrics_path: str | None,
    facts_path: str | None,
    out: str | None,
    min_claims: int = 0,
    min_dimensions: int = 0,
) -> int:
    import json

    from .research import audit, load

    try:
        document = load(path)
    except (OSError, ValueError) as exc:
        print(f"research 加载失败：{exc}", file=sys.stderr)
        return 2
    metrics: dict[str, str] = {}
    if metrics_path and Path(metrics_path).is_file():
        payload = json.loads(Path(metrics_path).read_text(encoding="utf-8-sig"))
        for key, point in payload.items():
            if isinstance(point, dict):
                metrics[str(key)] = str(point.get("display", point.get("value", "")))
            else:
                metrics[str(key)] = str(point)
    facts: dict[str, str] = {}
    if facts_path and Path(facts_path).is_file():
        payload = json.loads(Path(facts_path).read_text(encoding="utf-8-sig"))
        items = payload if isinstance(payload, list) else payload.get("document_facts", [])
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                facts[str(item["id"])] = str(
                    item.get("quote", item.get("value", ""))
                )
    result = audit(document, metrics, facts)
    quality = result["quality"]
    errors = list(result["errors"])
    if len(document.claims) < min_claims:
        errors.append(
            f"claims {len(document.claims)} < min_claims {min_claims}"
        )
    if len(quality["covered_dimensions"]) < min_dimensions:
        errors.append(
            f"covered dimensions {len(quality['covered_dimensions'])} "
            f"< min_dimensions {min_dimensions}"
        )
    if errors:
        result["status"] = "review"
        result["errors"] = errors
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if out:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((text + "\n").encode("utf-8"))
        print(f"research audit：{target.resolve()}")
    else:
        print(text)
    return 0 if result["status"] == "pass" else 1


def _research_cmd(path: str) -> int:
    from .research import load

    source = Path(path)
    if not source.is_file():
        print(f"找不到 research JSON：{source}", file=sys.stderr)
        return 2
    try:
        document = load(source)
    except (ValueError, OSError) as exc:
        print(f"research 校验失败：{exc}", file=sys.stderr)
        return 2
    print(f"research 校验通过：{len(document.claims)} claims，{len(document.evidence)} evidence")
    return 0


def _html_cmd(input_path: str, output: str | None, title: str | None) -> int:
    from .report.html import convert_file

    source = Path(input_path)
    if not source.is_file():
        print(f"找不到输入文件：{source}", file=sys.stderr)
        return 2
    target = Path(output) if output else source.with_suffix(".html")
    convert_file(source, target, title=title or source.stem)
    print(f"HTML 已写入 {target.resolve()}")
    return 0


def _pdf_numbers(
    pdf_path: str,
    year: int,
    report_type: str,
    output: str | None,
    max_pages: int | None,
) -> int:
    from .pdf.extract import (
        extract_dps_pdf,
        extract_main_business_facts,
        extract_pdf_bundle,
        write_reported_numbers,
    )

    source = Path(pdf_path)
    if not source.is_file():
        print(f"找不到 PDF：{source}", file=sys.stderr)
        return 2
    try:
        items, cash_bridge, sbc = extract_pdf_bundle(
            source, year=year, report_type=report_type, max_pages=max_pages
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    target = Path(output) if output else source.with_name("reported_numbers.json")
    dps = extract_dps_pdf(source, max_pages=max_pages)
    fact_rows = extract_main_business_facts(source, year=year, max_pages=max_pages)
    write_reported_numbers(
        items,
        target,
        pdf_path=str(source),
        cash_bridge=cash_bridge,
        sbc=sbc,
        dps=dps,
        fact_rows=fact_rows,
        year=year,
    )
    print(f"已抽取 {len(items)}/6 项数字 → {target.resolve()}")
    if dps:
        print(f"  DPS           {dps.get('dps', ''):>18}  p.{dps.get('page', '')} ({dps.get('currency', '')})")
    for item in items:
        print(f"  {item['item']:<12} {item['value']:>18}  p.{item['page']} ({item['confidence']})")
    if cash_bridge.get("ocf"):
        print(
            "  现金桥："
            f"净利润 {cash_bridge.get('net_profit')} / D&A {cash_bridge.get('depreciation_amortisation')} / "
            f"营运资本 {cash_bridge.get('working_capital_change')} / OCF {cash_bridge.get('ocf')} / "
            f"Capex {cash_bridge.get('capex')}"
        )
    if sbc.get("sbc"):
        print(f"  股份支付 SBC：{sbc.get('sbc')} 元（p.{sbc.get('page')}）")
    return 0 if items else 1


def _pdf_footnotes(sections: str, output: str | None) -> int:
    from .pdf.footnotes import structure_file

    source = Path(sections)
    if not source.is_file():
        print(f"找不到 sections JSON：{source}", file=sys.stderr)
        return 2
    target = Path(output) if output else source.with_name("footnotes.json")
    structure_file(source, target)
    print(f"附注结构已写入 {target.resolve()}")
    return 0


def _pdf_evidence(sections: str, output: str | None) -> int:
    from .pdf.research_facts import write

    source = Path(sections)
    if not source.is_file():
        print(f"找不到 sections JSON：{source}", file=sys.stderr)
        return 2
    target = Path(output) if output else source.with_name("evidence.json")
    facts = write(source, target)
    print(f"研究证据已写入 {target.resolve()}（{len(facts)} sections）")
    return 0


def _run_cmd(
    code_raw: str,
    rf: float | None,
    rf_source: str | None,
    currency: str | None,
    pdf_numbers: str | None,
    evidence: str | None,
    footnotes: str | None,
    pdf_sections: str | None,
    research: str | None,
    as_of: str | None,
    ttm: bool,
    pit: bool,
    html: bool,
    strict: bool,
    qa: bool,
    min_claims: int = 0,
    min_dimensions: int = 0,
    allow_research_decisions: bool = False,
) -> int:
    """One-command deterministic workflow: fetch once -> pack/report/snapshot -> QA."""
    from .paths import ensure_output_root

    code = StockCode.parse(code_raw)
    ensure_output_root()
    base = output_root() / str(code)
    snapshot = base / "snapshot"

    print(f"[1/3] state：{code}")
    if _state_cmd(str(code), True, None, None, []) != 0:
        return 2

    print(f"[2/3] data pack + report + snapshot：{code}")
    if (min_claims or min_dimensions) and not (
        research and Path(research).is_file()
    ):
        print("设置了 research 质量阈值，但未提供有效 --research", file=sys.stderr)
        return 2
    if research and Path(research).is_file():
        from .research import load as load_research
        from .research import quality as research_quality

        try:
            _document = load_research(research)
        except (ValueError, OSError) as exc:
            print(f"research 校验失败：{exc}", file=sys.stderr)
            return 2
        _quality = research_quality(_document)
        if len(_document.claims) < min_claims:
            print(
                f"research claims {len(_document.claims)} < min_claims {min_claims}",
                file=sys.stderr,
            )
            return 2
        if len(_quality["covered_dimensions"]) < min_dimensions:
            print(
                "research dimensions "
                f"{len(_quality['covered_dimensions'])} < min_dimensions {min_dimensions}",
                file=sys.stderr,
            )
            return 2
    rc = _report(
        str(code),
        None,
        currency,
        rf,
        rf_source,
        None,
        pdf_numbers,
        str(snapshot),
        None,
        research,
        as_of,
        ttm,
        pit,
        "record-only",
        strict,
        evidence,
        html,
        str(base / "data_pack.md"),
        footnotes,
        pdf_sections,
        allow_research_decisions,
    )
    if rc != 0:
        print(f"run 在 report 阶段失败：{rc}", file=sys.stderr)
        return rc

    if research and Path(research).is_file():
        import shutil

        base.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(research, base / "research.json")
        provenance = Path(research).with_name("research_provenance.json")
        if provenance.is_file():
            shutil.copyfile(provenance, base / "research_provenance.json")

    from . import state as st
    from .facts import ReportManifest

    state_path = base / "run_state.json"
    run = st.load(state_path) if state_path.is_file() else st.new(str(code))
    manifest_path = snapshot / "manifest.json"
    if manifest_path.is_file():
        frozen = ReportManifest.read(manifest_path)
        run.snapshot_id = frozen.snapshot_id
    st.add_artifact(run, "snapshot", str(snapshot.resolve()))
    st.add_artifact(run, "data_pack", str((base / "data_pack.md").resolve()))
    st.add_artifact(
        run, "analysis_report", str((base / "analysis_report.md").resolve())
    )
    if (base / "research.json").is_file():
        st.add_artifact(run, "research", str((base / "research.json").resolve()))
    if (base / "research_audit.json").is_file():
        st.add_artifact(
            run, "research_audit", str((base / "research_audit.json").resolve())
        )
    if run.phase in ("intake", "data"):
        st.advance(run, "report")
    st.save(run, state_path)

    if qa:
        print(f"[3/3] QA：{code}")
        rc = _qa_cmd(str(code), True, None, True)
        if rc != 0:
            print(f"run 在 QA 阶段失败：{rc}", file=sys.stderr)
            return rc
    print(f"run 完成：{snapshot.resolve()}")
    return 0


def _finalize_cmd(
    snapshot: str,
    research: str,
    out: str,
    report: str | None,
    strict: bool,
    min_claims: int,
    min_dimensions: int,
    html: bool,
    allow_research_decisions: bool = False,
) -> int:
    from .report.finalize import FinalizeError, finalize_research

    try:
        target = finalize_research(
            snapshot,
            research,
            out,
            report_path=report,
            strict=strict,
            min_claims=min_claims,
            min_dimensions=min_dimensions,
            html=html,
            allow_research_decisions=allow_research_decisions,
        )
    except (FinalizeError, ValueError, OSError) as exc:
        print(f"finalize 失败：{exc}", file=sys.stderr)
        return 2
    print(f"finalize 完成：{target.resolve()}")
    return 0


def _report(
    raw_code: str,
    out: str | None,
    currency: str | None = None,
    rf: float | None = None,
    rf_source: str | None = None,
    qualitative_path: str | None = None,
    pdf_numbers: str | None = None,
    save_snapshot: str | None = None,
    snapshot_dir: str | None = None,
    research_path: str | None = None,
    as_of: str | None = None,
    ttm: bool = False,
    pit: bool = False,
    source_policy: str = "record-only",
    strict_numeric: bool = False,
    evidence_path: str | None = None,
    html_out: bool = False,
    data_pack_out: str | None = None,
    footnotes_path: str | None = None,
    pdf_sections_path: str | None = None,
    allow_research_decisions: bool = False,
) -> int:
    from .data.tushare_provider import TushareProvider
    from .metrics import statements
    from .report import snapshot as snap
    from .report.manifest import build_manifest
    from .report.pack import _snapshot_id

    if pit and not as_of:
        print("--pit 必须与 --as-of 一起使用", file=sys.stderr)
        return 2
    if pit and snapshot_dir:
        print("--snapshot 与 --pit 不能同时使用", file=sys.stderr)
        return 2
    if snapshot_dir and source_policy != "record-only":
        print("--snapshot 使用冻结的 source policy，不能再传 --source-policy", file=sys.stderr)
        return 2
    if source_policy not in ("record-only", "display-primary", "engine-primary"):
        print(f"未知 --source-policy：{source_policy}", file=sys.stderr)
        return 2
    if strict_numeric and not save_snapshot:
        print("--strict-numeric 必须与 --save-snapshot 一起使用", file=sys.stderr)
        return 2

    if snapshot_dir:
        from .facts import ReportManifest

        if as_of:
            print("--snapshot 已包含 as_of，不能再传 --as-of", file=sys.stderr)
            return 2
        inputs, settings = snap.load(snapshot_dir)
        manifest_path = Path(snapshot_dir) / "manifest.json"
        manifest = ReportManifest.read(manifest_path) if manifest_path.is_file() else None
        markdown, verdict = snap.render(
            inputs,
            settings,
            snapshot_id=manifest.snapshot_id if manifest else _snapshot_id(inputs.rows),
            snapshot_dir=snapshot_dir,
            allow_research_decisions=allow_research_decisions,
        )
        if manifest is not None:
            errors = snap.verify_manifest(inputs, settings, markdown, manifest, snapshot_dir)
            if errors:
                print("snapshot 校验失败：" + "; ".join(errors), file=sys.stderr)
                return 2
    else:
        settings = load_settings()
        code = StockCode.parse(raw_code)
        provider = TushareProvider(get_token())
        unit = _unit_for(code, currency, provider)
        rows = provider.statements(code, currency=unit)
        if not rows:
            print("未取到报表数据。", file=sys.stderr)
            return 2
        source_id = ""
        if as_of:
            try:
                cutoff = date.fromisoformat(as_of)
            except ValueError:
                print(f"无效 --as-of：{as_of}", file=sys.stderr)
                return 2
            if pit:
                from .pit import PitError, PitStore

                try:
                    selection = PitStore().load(str(code), cutoff)
                    rows = list(selection.rows)
                    source_id = selection.snapshot.snapshot_id
                    pit_note = (
                        f"PIT snapshot {selection.snapshot.snapshot_id[:12]} "
                        f"known={selection.snapshot.knowledge_date}；市值近似"
                    )
                except PitError as exc:
                    print(f"{exc}；回退公告日过滤", file=sys.stderr)
                    rows = statements.as_of_rows(rows, cutoff)
                    pit_note = "无 PIT snapshot，回退公告日过滤；市值近似"
            else:
                rows = statements.as_of_rows(rows, cutoff)
                pit_note = "财务按公告日过滤；市值近似"
            if not rows:
                print(f"截至 {as_of} 没有已公告报表。", file=sys.stderr)
                return 2
        else:
            pit_note = ""
        ttm_note = ""
        if ttm:
            transformed = statements.apply_ttm(rows)
            rows = transformed.rows
            ttm_note = transformed.note
        fx = _fx_for(code, unit, settings)
        dividends = provider.dividends(code, currency=unit, dps_fx=fx)
        basic_current = sorted(
            provider.daily_basic(code),
            key=lambda r: str(r.get("trade_date", "")),
            reverse=True,
        )
        history_all = _fx_history(provider.weekly(code), fx)
        history = history_all
        basic_asof: list[dict] = []
        if as_of:
            history = [
                item
                for item in history_all
                if str(item.get("trade_date", "")) <= as_of
            ]
            if code.is_a_share:
                basic_asof = sorted(
                    provider.daily_basic(code, trade_date=as_of),
                    key=lambda r: str(r.get("trade_date", "")),
                    reverse=True,
                )
        quote = basic_asof[0] if basic_asof else (
            basic_current[0] if basic_current and not as_of else None
        )
        price_from_history = False
        if as_of and quote is None and history:
            reference = basic_current[0] if basic_current else {}
            quote = {
                **reference,
                "trade_date": history[-1].get("trade_date", ""),
                "close": history[-1].get("close"),
            }
            price_from_history = True
        if as_of and quote is None:
            print(f"截至 {as_of} 没有可用行情。", file=sys.stderr)
            return 2
        price = _num(quote.get("close")) if quote else None
        if price is not None and not price_from_history:
            price = price * fx
            quote = {**quote, "close": float(price)}
        market_cap = Money(Decimal("0"), unit)
        shares = Decimal("0")
        if quote:
            total_share_wan = _num(quote.get("total_share"))
            if total_share_wan is not None:
                shares = total_share_wan * Decimal("10000")
            if price_from_history:
                if shares > 0 and price is not None:
                    market_cap = Money(shares * price, unit)
            else:
                total_mv_wan = _num(quote.get("total_mv"))
                if total_mv_wan is not None and total_share_wan is not None:
                    market_cap = Money(total_mv_wan * Decimal("10000") * fx, unit)
                    shares = total_share_wan * Decimal("10000")
        rf_value, rf_src = _rf_for(provider, settings, code, rf, rf_source)
        qual_path = (
            Path(qualitative_path)
            if qualitative_path
            else output_root() / str(code) / "qualitative.json"
        )
        research_file = (
            Path(research_path)
            if research_path
            else output_root() / str(code) / "research.json"
        )
        if research_file.is_file():
            from .research import engine_decisions, load as load_research

            engine_decisions(
                load_research(research_file),
                allow=allow_research_decisions,
            )
        evidence_facts = _pdf_facts(pdf_numbers) | _evidence_facts(evidence_path)
        parent_cash, pledge_pct, buyback = _governance(provider, code, unit)
        pdf_bridge = _pdf_bridge(pdf_numbers)
        sbc_value = _pdf_sbc(pdf_numbers)
        sbc = Money(sbc_value, unit) if sbc_value is not None else _sbc_from_rows(rows, unit)
        issues = list(provider.issues)
        if pit_note:
            issues.append(FetchIssue(endpoint="pit", code=str(code), message=pit_note))
        elif as_of:
            issues.append(
                FetchIssue(
                    endpoint="pit",
                    code=str(code),
                    message="as-of 财务按公告日过滤；市值用当日价×最新股本近似",
                )
            )
        if ttm:
            issues.append(FetchIssue(endpoint="ttm", code=str(code), message=ttm_note))
        resolved_facts: list[dict[str, object]] = []
        if pdf_numbers and Path(pdf_numbers).is_file():
            import json

            from .metrics import source_resolver

            reported_payload = json.loads(Path(pdf_numbers).read_text(encoding="utf-8-sig"))
            reported_items = reported_payload.get("items", [])
            candidates = source_resolver.collect(
                rows,
                reported_items,
                year=int(reported_payload["year"]) if reported_payload.get("year") else None,
            )
            resolved = source_resolver.solve(
                candidates,
                policy=source_policy,
                as_of=as_of,
            )
            if source_policy == "engine-primary":
                rows = source_resolver.apply_engine(rows, resolved)
            resolved_facts = source_resolver.to_payload(resolved)
            conflicts = sum(1 for fact in resolved if fact.status == "conflict")
            issues.append(
                FetchIssue(
                    endpoint="source-rank",
                    code=str(code),
                    message=f"policy={source_policy}; conflicts={conflicts}",
                )
            )
        if not source_id:
            from .facts import content_hash, file_hash, statement_payload

            source_payload = {
                "code": str(code),
                "as_of": as_of or "",
                "rows": statement_payload(rows),
            }
            if pdf_numbers and Path(pdf_numbers).is_file():
                source_payload["pdf_numbers"] = file_hash(pdf_numbers)
            source_id = content_hash(source_payload)
        inputs = snap.ReportInputs(
            code=str(code),
            currency=unit.value,
            as_of=(
                as_of
                or (
                    str(quote.get("trade_date", ""))
                    if quote
                    else str(history[-1].get("trade_date", "")) if history else ""
                )
            ),
            rows=list(rows),
            dividends=list(dividends),
            quote=quote,
            history=list(history),
            market_cap=str(market_cap.amount),
            shares=str(shares),
            price=str(price) if price is not None else None,
            rf_pct=str(rf_value),
            rf_source=rf_src,
            parent_cash=str(parent_cash) if parent_cash is not None else None,
            pledge_pct=str(pledge_pct) if pledge_pct is not None else None,
            buyback=str(buyback.amount) if buyback is not None else None,
            sbc=str(sbc.amount) if sbc is not None else None,
            audit=list(provider.audit(code)),
            pdf_bridge=pdf_bridge,
            issues=issues,
            has_qualitative=qual_path.is_file(),
            source_id=source_id,
            source_policy=source_policy,
            resolved_facts=resolved_facts,
        )
        if save_snapshot:
            snap.freeze(
                inputs,
                settings,
                save_snapshot,
                qualitative_source=qual_path if qual_path.is_file() else None,
                research_source=research_file if research_file.is_file() else None,
            )
        from .facts import file_hash as _file_hash

        frozen_manifest = (
            build_manifest(
                inputs,
                settings,
                Path(save_snapshot),
                pdf_fact_hash=(
                    _file_hash(Path(pdf_numbers))
                    if pdf_numbers and Path(pdf_numbers).is_file()
                    else ""
                ),
            )
            if save_snapshot
            else None
        )
        if data_pack_out:
            from json import loads as json_loads

            from .research import engine_decisions, load as load_research
            from .report.pack import render_data_pack

            pack_decisions: dict[str, str] = {}
            if allow_research_decisions and research_file.is_file():
                pack_decisions = engine_decisions(
                    load_research(research_file), allow=True
                )

            try:
                holders = provider.holders(code) if hasattr(provider, "holders") else []
            except Exception:  # noqa: BLE001 - optional pack section
                holders = []
            try:
                main_business = (
                    provider.main_business(code)
                    if hasattr(provider, "main_business")
                    else []
                )
            except Exception:  # noqa: BLE001 - optional pack section
                main_business = []
            footnotes = (
                json_loads(Path(footnotes_path).read_text(encoding="utf-8-sig"))
                if footnotes_path and Path(footnotes_path).is_file()
                else None
            )
            pdf_sections = (
                json_loads(Path(pdf_sections_path).read_text(encoding="utf-8-sig"))
                if pdf_sections_path and Path(pdf_sections_path).is_file()
                else None
            )
            inputs.holders = list(holders)
            inputs.main_business = list(main_business)
            inputs.footnotes = footnotes
            inputs.pdf_sections = pdf_sections
            inputs.pit_note = pit_note
            pack_markdown = render_data_pack(
                code,
                inputs.rows,
                inputs.dividends,
                quote=inputs.quote,
                history=inputs.history,
                market_cap=Money(Decimal(inputs.market_cap), unit),
                shares=Decimal(inputs.shares),
                diluted_shares=statements.diluted_shares(inputs.rows),
                rf_pct=Decimal(inputs.rf_pct),
                settings=settings,
                issues=inputs.issues,
                tax_pct=grids.default_tax_rate(code),
                rf_source=inputs.rf_source,
                parent_cash=Decimal(inputs.parent_cash) if inputs.parent_cash else None,
                pledge_pct=Decimal(inputs.pledge_pct) if inputs.pledge_pct else None,
                buyback=(
                    Money(Decimal(inputs.buyback), unit)
                    if inputs.buyback
                    else None
                ),
                sbc=Money(Decimal(inputs.sbc), unit) if inputs.sbc else None,
                pdf_bridge=inputs.pdf_bridge,
                holders=holders,
                main_business=main_business,
                as_of=inputs.as_of,
                footnotes=footnotes,
                pdf_sections=pdf_sections,
                pit_note=pit_note,
                decisions=pack_decisions,
                snapshot_id=(
                    frozen_manifest.snapshot_id if frozen_manifest else None
                ),
            )
            pack_path = Path(data_pack_out)
            pack_path.parent.mkdir(parents=True, exist_ok=True)
            pack_path.write_bytes(pack_markdown.encode("utf-8"))
        metrics_out: dict[str, object] = {}
        markdown, verdict = snap.render(
            inputs,
            settings,
            snapshot_id=(
                frozen_manifest.snapshot_id if frozen_manifest else _snapshot_id(rows)
            ),
            snapshot_dir=save_snapshot or None,
            qualitative_path=qual_path,
            research_path=research_file,
            metrics_out=metrics_out,
            facts=evidence_facts,
            refresh_metrics=True,
            allow_research_decisions=allow_research_decisions,
        )

    code_text = inputs.code
    gate_failed = False
    path = Path(out) if out else output_root() / code_text / "analysis_report.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(markdown.encode("utf-8"))

    if save_snapshot:
        import hashlib
        import json
        import shutil

        snapshot_root = Path(save_snapshot)
        base_dir = output_root() / code_text
        metrics_path = snapshot_root / "metrics.json"
        if metrics_out:
            metrics_path.write_bytes(
                (
                    json.dumps(metrics_out, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n"
                ).encode("utf-8")
            )
        from .facts import file_hash

        resolved_path = snapshot_root / "resolved_facts.json"
        if inputs.resolved_facts:
            resolved_path.write_bytes(
                (
                    json.dumps(
                        inputs.resolved_facts,
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
            )
        if qual_path.is_file() and not (snapshot_root / "qualitative.json").is_file():
            shutil.copyfile(qual_path, snapshot_root / "qualitative.json")
        if research_file.is_file() and not (snapshot_root / "research.json").is_file():
            shutil.copyfile(research_file, snapshot_root / "research.json")
        pack_candidates = [base_dir / "data_pack.md", *sorted(base_dir.glob("data_pack_*.md"))]
        pack_source = next((item for item in pack_candidates if item.is_file()), None)
        if pack_source is not None:
            shutil.copyfile(pack_source, snapshot_root / "data_pack.md")
        if pdf_numbers and Path(pdf_numbers).is_file():
            shutil.copyfile(pdf_numbers, snapshot_root / "reported_numbers.json")
        if evidence_path and Path(evidence_path).is_file():
            shutil.copyfile(evidence_path, snapshot_root / "evidence.json")

        from .numeric_audit import audit as numeric_audit

        source_paths = [
            metrics_path,
            resolved_path,
            snapshot_root / "inputs.json",
            snapshot_root / "qualitative.json",
            snapshot_root / "research.json",
            snapshot_root / "data_pack.md",
            snapshot_root / "reported_numbers.json",
            snapshot_root / "evidence.json",
        ]
        if strict_numeric:
            source_paths = [
                source for source in source_paths if source.name != "inputs.json"
            ]
        numeric_sources = tuple(
            source.name for source in source_paths if source.is_file()
        )
        numeric = numeric_audit(
            path,
            [source for source in source_paths if source.is_file()],
            strict=strict_numeric,
        )
        numeric["sources"] = list(numeric_sources)
        numeric_path = snapshot_root / "numeric_audit.json"
        numeric_path.write_bytes(
            (json.dumps(numeric, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        )
        research_audit_path = snapshot_root / "research_audit.json"
        research_audit_hash = ""
        if (snapshot_root / "research.json").is_file():
            from .research import snapshot_audit

            research_audit = snapshot_audit(snapshot_root)
            research_audit_path.write_bytes(
                (json.dumps(research_audit, ensure_ascii=False, indent=2) + "\n").encode(
                    "utf-8"
                )
            )
            research_audit_hash = file_hash(research_audit_path)
            base_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(research_audit_path, base_dir / "research_audit.json")
            if research_audit["status"] != "pass":
                gate_failed = True
                print(
                    "research audit 未通过："
                    + "; ".join(str(item) for item in research_audit["errors"]),
                    file=sys.stderr,
                )
        manifest = build_manifest(
            inputs,
            settings,
            snapshot_root,
            report_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            metrics_hash=file_hash(metrics_path) if metrics_path.is_file() else "",
            resolved_hash=file_hash(resolved_path) if resolved_path.is_file() else "",
            research_audit_hash=research_audit_hash,
            numeric_coverage=str(numeric["coverage"]),
            numeric_status=str(numeric["status"]),
            numeric_unknown=tuple(str(item) for item in numeric["unknown"]),
            numeric_hash=file_hash(numeric_path) if numeric_path.is_file() else "",
            numeric_sources=numeric_sources,
        )
        manifest.write(snapshot_root / "manifest.json")
        print(f"snapshot_id: {manifest.snapshot_id}")
        print(
            f"numeric coverage: {numeric['coverage']:.4f} ｜ "
            f"{numeric['status']} ｜ unknown={len(numeric['unknown'])}"
        )
        if strict_numeric and numeric["status"] != "pass":
            gate_failed = True
            print("strict numeric gate 未通过", file=sys.stderr)

    print(f"分析报告已写入 {path.resolve()}")
    if html_out:
        from .report.html import convert_file

        html_path = convert_file(path, path.with_suffix(".html"), title=code_text)
        print(f"HTML 已写入 {html_path.resolve()}")
    print(f"结论：{verdict} ｜ 字节数：{len(markdown.encode('utf-8')):,}")
    return 1 if gate_failed else 0


def _screen(
    tier1_only: bool,
    tier2_limit: int | None = None,
    csv_path: str | None = None,
    rf: float | None = None,
    rf_source: str | None = None,
    workers: int = 6,
    fast: bool = False,
    fast_limit: int = 50,
    deep: int = 0,
    api_interval: float = 0.35,
    as_of: str | None = None,
) -> int:
    from .data.tushare_provider import TushareProvider
    from .data.universe import listed_as_of
    from .screener import tier1 as tier1_mod
    from .screener.tier2 import run_tier2

    settings = load_settings()
    provider = TushareProvider(get_token(), min_interval=api_interval)
    universe = provider.stock_basic()
    if as_of:
        seen: set[str] = set()
        combined: list[dict] = []
        for status in ("L", "D", "P"):
            for row in provider.stock_basic(list_status=status):
                code_key = str(row.get("ts_code", ""))
                if code_key and code_key not in seen:
                    seen.add(code_key)
                    combined.append(row)
        universe = listed_as_of(combined, as_of)
        print(
            f"筛选日期 {as_of}：上市状态/日行情使用该日快照；tier1 日频指标为 PIT。",
            file=sys.stderr,
        )
        if fast or deep:
            print(
                "--as-of 不能与 --fast/--deep 一起使用：二者使用最新批量财务报表，"
                "会产生前视偏差；请只用 tier1，或改用 PIT snapshot 逐票分析。",
                file=sys.stderr,
            )
            return 2
    if not universe:
        print("未取到股票列表。", file=sys.stderr)
        for issue in provider.issues:
            print(f"  {issue}", file=sys.stderr)
        return 2

    if as_of:
        trade_date = as_of.replace("-", "")
        daily = provider.daily_basic(trade_date=trade_date)
        if not daily:
            anchor = date(int(trade_date[:4]), int(trade_date[4:6]), int(trade_date[6:8]))
            for delta in range(1, 11):
                candidate = (anchor - timedelta(days=delta)).strftime("%Y%m%d")
                daily = provider.daily_basic(trade_date=candidate)
                if daily:
                    trade_date = candidate
                    break
    else:
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

    ranked = tier1_mod.rank_main(channels, settings.screening)

    if fast:
        from .screener.fast import fast_screen

        rf_value, _ = _rf_for(provider, settings, StockCode.parse("600887"), rf, rf_source)
        print("\n=== Fast screen：全市场批量（阶段 1） ===")
        started = time.perf_counter()
        result = fast_screen(channels, provider, settings, rf_value, limit=fast_limit)
        elapsed = time.perf_counter() - started
        print(result.to_string(index=False))
        print(f"\n耗时 {elapsed:.1f}s ｜ 候选 {len(result)} 只")
        if csv_path:
            Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
            result.to_csv(csv_path, index=False, encoding="utf-8-sig")
            print(f"已导出 {Path(csv_path).resolve()}")

        if deep and not result.empty:
            from .screener.tier2 import run_tier2

            codes = list(result["ts_code"])
            order = {code: index for index, code in enumerate(codes)}
            deep_frame = channels[channels["ts_code"].isin(codes)].copy()
            deep_frame["_order"] = deep_frame["ts_code"].map(order)
            deep_frame = deep_frame.sort_values("_order").drop(columns="_order")
            print(f"\n=== Deep：前 {min(deep, len(deep_frame))} 只 ===")
            deep_result = run_tier2(
                deep_frame, provider, settings, rf_value, limit=deep, workers=workers
            )
            print(deep_result.to_string(index=False))
            if csv_path:
                path = Path(csv_path)
                deep_path = path.with_name(f"{path.stem}_deep{path.suffix}")
                deep_result.to_csv(deep_path, index=False, encoding="utf-8-sig")
                print(f"已导出 {deep_path.resolve()}")
        return 0

    if tier1_only:
        print(ranked[["ts_code", "name", "channel", "tier1_score"]].head(30).to_string(index=False))
        return 0

    rf_value, _ = _rf_for(provider, settings, StockCode.parse("600887"), rf, rf_source)
    limit = tier2_limit or 10
    print(f"\n=== Tier 2：前 {limit} 只（并发 {workers}） ===")
    started = time.perf_counter()
    result = run_tier2(ranked, provider, settings, rf_value, limit=limit, workers=workers)
    elapsed = time.perf_counter() - started
    print(result.to_string(index=False))
    print(f"\n耗时 {elapsed:.1f}s（{len(result)} 只，平均 {elapsed / max(len(result), 1):.1f}s/只）")

    if csv_path:
        Path(csv_path).parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(csv_path, index=False, encoding="utf-8-sig")
        print(f"\n已导出 {Path(csv_path).resolve()}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="turtle", description="Turtle Investment Framework")
    parser.add_argument("--version", action="version", version=f"turtle-framework {__version__}")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="运行产物根目录（默认 .runs；也可设 TURTLE_OUTPUT_DIR）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="分析单只股票")
    analyze.add_argument("code", help="股票代码，如 600887 / 00700.HK")
    analyze.add_argument("--demo", action="store_true", help="使用内置合成数据，不需要 Token")
    analyze.add_argument("--save", action="store_true", help="把报表写入 output/store")
    analyze.add_argument(
        "--currency",
        choices=[c.value for c in Currency],
        default=None,
        help="报表币种；港股自动探测 financialCurrency，失败时默认 CNY",
    )
    analyze.add_argument("--rf", type=float, default=None, help="覆盖无风险利率（%%）")
    analyze.add_argument("--rf-source", default=None, help="Rf 来源说明或 URL")
    analyze.add_argument("--ttm", action="store_true", help="用最新 interim 构造 TTM 年度行")

    screen = sub.add_parser("screen", help="全市场筛选")
    screen.add_argument("--tier1-only", action="store_true", help="只跑 Tier 1")
    screen.add_argument("--tier2-limit", type=int, default=None, help="Tier 2 分析只数（默认 10）")
    screen.add_argument("--csv", dest="csv_path", default=None, help="导出 CSV 路径")
    screen.add_argument("--rf", type=float, default=None, help="覆盖无风险利率（%%）")
    screen.add_argument("--rf-source", default=None, help="Rf 来源说明或 URL")
    screen.add_argument("--workers", type=int, default=6, help="Tier 2 并发线程数（默认 6）")
    screen.add_argument("--fast", action="store_true", help="阶段 1：全市场批量粗筛")
    screen.add_argument("--fast-limit", type=int, default=50, help="Fast screen 输出只数")
    screen.add_argument("--deep", type=int, default=0, help="对 Fast 前 N 只接深度四因子")
    screen.add_argument(
        "--api-interval", type=float, default=0.35, help="API 最小间隔秒数（默认 0.35）"
    )
    screen.add_argument("--as-of", default=None, help="筛选日期 YYYY-MM-DD（仅上市日期过滤）")

    pack = sub.add_parser("pack", help="生成 Markdown 数据包")
    pack.add_argument("code", help="股票代码，如 600887")
    pack.add_argument("--out", default=None, help="输出路径，默认 .runs/<code>/data_pack.md")
    pack.add_argument(
        "--currency",
        choices=[c.value for c in Currency],
        default=None,
        help="报表币种；港股自动探测，失败时默认 CNY",
    )
    pack.add_argument("--rf", type=float, default=None, help="覆盖无风险利率（%%）")
    pack.add_argument("--rf-source", default=None, help="Rf 来源说明或 URL")
    pack.add_argument("--pdf-numbers", default=None, help="reported_numbers.json（含 cash_bridge）")
    pack.add_argument("--footnotes", default=None, help="pdf-footnotes 生成的 footnotes.json")
    pack.add_argument("--pdf-sections", default=None, help="pdf 生成的 pdf_sections.json")
    pack.add_argument("--as-of", default=None, help="按公告日做近似 PIT 过滤（YYYY-MM-DD）")
    pack.add_argument("--pit", action="store_true", help="从本地 PIT 库读取 as-of 财务")

    report = sub.add_parser("report", help="生成四因子分析报告")
    report.add_argument("code", help="股票代码，如 600887")
    report.add_argument("--out", default=None, help="输出路径，默认 .runs/<code>/analysis_report.md")
    report.add_argument(
        "--currency",
        choices=[c.value for c in Currency],
        default=None,
        help="报表币种；港股自动探测，失败时默认 CNY",
    )
    report.add_argument("--rf", type=float, default=None, help="覆盖无风险利率（%%）")
    report.add_argument("--rf-source", default=None, help="Rf 来源说明或 URL")
    report.add_argument(
        "--qualitative",
        default=None,
        help="定性 JSON 路径，默认 .runs/<code>/qualitative.json",
    )
    report.add_argument("--pdf-numbers", default=None, help="reported_numbers.json（含 cash_bridge）")
    report.add_argument("--evidence", default=None, help="pdf-evidence 生成的 evidence.json")
    report.add_argument("--html", action="store_true", help="同时生成 HTML 报告")
    report.add_argument("--save-snapshot", default=None, help="把报告输入冻结到目录")
    report.add_argument("--snapshot", default=None, help="从冻结的 snapshot 目录离线渲染")
    report.add_argument("--research", default=None, help="D1-D6 research.json 路径")
    report.add_argument("--as-of", default=None, help="近似 PIT 日期（YYYY-MM-DD）")
    report.add_argument("--ttm", action="store_true", help="用最新 interim 构造 TTM 年度行")
    report.add_argument("--pit", action="store_true", help="从本地 PIT 库读取 as-of 财务")
    report.add_argument(
        "--allow-research-decisions",
        action="store_true",
        help="允许 research.json 的决策改变 G/M/Q/AA/scenario（必须带 evidence）",
    )

    run = sub.add_parser(
        "run",
        help="一键跑完 pack -> report/snapshot -> QA（确定性流程）",
    )
    run.add_argument("code", help="股票代码，如 600887 / 00700.HK")
    run.add_argument("--rf", type=float, default=None, help="覆盖无风险利率（%%）")
    run.add_argument("--rf-source", default=None, help="Rf 来源说明或 URL")
    run.add_argument(
        "--currency",
        choices=[c.value for c in Currency],
        default=None,
        help="报表币种；港股自动探测 financialCurrency",
    )
    run.add_argument("--pdf-numbers", default=None, help="reported_numbers.json")
    run.add_argument("--evidence", default=None, help="pdf-evidence / sec-evidence 生成的 evidence.json")
    run.add_argument("--footnotes", default=None, help="footnotes.json")
    run.add_argument("--pdf-sections", default=None, help="pdf_sections.json")
    run.add_argument("--research", default=None, help="research.json（可选）")
    run.add_argument("--as-of", default=None, help="近似 PIT 日期（YYYY-MM-DD）")
    run.add_argument("--ttm", action="store_true", help="用最新 interim 构造 TTM 年度行")
    run.add_argument("--pit", action="store_true", help="从本地 PIT 库读取 as-of 财务")
    run.add_argument("--no-html", action="store_false", dest="html", help="不生成 HTML")
    run.set_defaults(html=True)
    run.add_argument(
        "--strict",
        action="store_true",
        help="numeric gate 不通过时返回非零",
    )
    run.add_argument(
        "--no-qa",
        action="store_false",
        dest="qa",
        help="跳过最终 QA",
    )
    run.set_defaults(qa=True)
    run.add_argument("--min-claims", type=int, default=0)
    run.add_argument("--min-dimensions", type=int, default=0)
    run.add_argument(
        "--allow-research-decisions",
        action="store_true",
        help="允许 research 决策改变数字（必须带 evidence）",
    )
    report.add_argument(
        "--source-policy",
        choices=["record-only", "display-primary", "engine-primary"],
        default="record-only",
        help="SourceRank 冲突策略",
    )
    report.add_argument(
        "--strict-numeric",
        action="store_true",
        help="numeric audit 不允许 inputs.json 原始值兜底；失败返回 1",
    )

    val = sub.add_parser("valuation", help="DCF/DDM/PE Band/PEG/PS 绝对估值")
    val.add_argument("code", help="股票代码，如 600887 / 00700.HK")
    val.add_argument(
        "--currency",
        choices=[c.value for c in Currency],
        default=None,
        help="报表币种；港股自动探测，失败时默认 CNY",
    )
    val.add_argument("--rf", type=float, default=None, help="覆盖无风险利率（%%）")
    val.add_argument("--rf-source", default=None, help="Rf 来源说明或 URL")
    val.add_argument("--ttm", action="store_true", help="用最新 interim 构造 TTM 年度行")

    qual = sub.add_parser("qualitative", help="生成/校验定性输入模板")
    qual.add_argument("code", help="股票代码")
    qual.add_argument("--init", action="store_true", help="生成模板 JSON")
    qual.add_argument("--check", action="store_true", help="校验现有 JSON")
    qual.add_argument("--out", default=None, help="自定义路径")

    research = sub.add_parser("research", help="校验 D1-D6 research.json（证据/占位符）")
    research.add_argument("--file", required=True, help="research.json 路径")

    research_audit = sub.add_parser("research-audit", help="校验 research 占位符/决策")
    research_audit.add_argument("--file", required=True, help="research.json")
    research_audit.add_argument("--metrics", default=None, help="metrics.json")
    research_audit.add_argument("--facts", default=None, help="evidence.json / reported_numbers.json")
    research_audit.add_argument("--out", default=None, help="审计 JSON 输出")
    research_audit.add_argument("--min-claims", type=int, default=0)
    research_audit.add_argument("--min-dimensions", type=int, default=0)

    research_context = sub.add_parser(
        "research-context", help="导出 DSH/LLM 研究上下文 JSON"
    )
    research_context.add_argument("--snapshot", required=True, help="snapshot 目录")
    research_context.add_argument("--out", required=True, help="context.json 输出")
    research_context.add_argument("--data-pack", default=None, help="可选 data_pack.md")

    research_provenance = sub.add_parser(
        "research-provenance", help="记录 DSH/LLM research provenance"
    )
    research_provenance.add_argument("--research", required=True, help="research.json")
    research_provenance.add_argument("--snapshot", required=True, help="snapshot 目录")
    research_provenance.add_argument("--provider", default="dsh")
    research_provenance.add_argument("--model", default="")
    research_provenance.add_argument("--generated-at", default=None)
    research_provenance.add_argument("--out", required=True, help="provenance JSON")

    sec_audit = sub.add_parser("sec-audit", help="用 SEC companyfacts 复核美股 snapshot")
    sec_audit.add_argument("--snapshot", required=True, help="snapshot 目录")
    sec_audit.add_argument("--ticker", default=None, help="美股 ticker，如 AAPL")
    sec_audit.add_argument("--cik", type=int, default=None, help="SEC CIK")
    sec_audit.add_argument("--out", default=None, help="JSON 输出")
    sec_audit.add_argument("--tolerance", type=float, default=1.0, help="差异阈值 %%")

    sec_evidence = sub.add_parser(
        "sec-evidence", help="从 SEC companyfacts 生成 research evidence"
    )
    sec_evidence.add_argument("--ticker", default=None, help="美股 ticker")
    sec_evidence.add_argument("--cik", type=int, default=None, help="SEC CIK")
    sec_evidence.add_argument("--out", required=True, help="evidence.json 输出")

    coverage = sub.add_parser("coverage", help="显示数据覆盖能力矩阵")
    coverage.add_argument("code", help="股票代码")
    coverage.add_argument("--json", action="store_true", help="JSON 输出")

    hkex_news = sub.add_parser(
        "hkex-news", help="搜索 HKEXnews 回购公告并生成 evidence"
    )
    hkex_news.add_argument("--code", required=True, help="港股代码，如 00700")
    hkex_news.add_argument("--from", dest="from_date", default="20240101")
    hkex_news.add_argument("--to", dest="to_date", default="20261231")
    hkex_news.add_argument("--keyword", default="Next Day Disclosure")
    hkex_news.add_argument("--out", required=True, help="evidence.json 输出")

    research_agent = sub.add_parser(
        "research-agent", help="用 OpenAI-compatible LLM 生成 research.json"
    )
    research_agent.add_argument("--snapshot", required=True, help="snapshot 目录")
    research_agent.add_argument("--out", required=True, help="research.json 输出")
    research_agent.add_argument("--base-url", default=None, help="LLM base URL")
    research_agent.add_argument("--model", default=None, help="模型名")
    research_agent.add_argument("--api-key", default=None, help="API key（建议用环境变量）")
    research_agent.add_argument("--data-pack", default=None, help="可选 data_pack.md")
    research_agent.add_argument("--retries", type=int, default=0, help="schema/质量失败重试次数")
    research_agent.add_argument("--min-claims", type=int, default=0, help="最少 claim 数")
    research_agent.add_argument("--min-dimensions", type=int, default=0, help="最少覆盖维度")
    research_agent.add_argument(
        "--response", default=None, help="离线回放 LLM JSON（不发网络请求）"
    )

    snapshot = sub.add_parser("snapshot", help="生成不可变 ReportSnapshot manifest")
    snapshot.add_argument("code", help="股票代码")
    snapshot.add_argument("--as-of", required=True, help="数据截止日 YYYY-MM-DD")
    snapshot.add_argument("--out", default=None, help="manifest 输出路径")
    snapshot.add_argument("--report", default=None, help="已有报告路径（计算 report_hash）")
    snapshot.add_argument("--research", default=None, help="research.json 路径（计算 research_hash）")

    finalize = sub.add_parser(
        "finalize",
        help="把 research 附加到冻结 snapshot，不重新取数",
    )
    finalize.add_argument("--snapshot", required=True, help="旧 snapshot 目录")
    finalize.add_argument("--research", required=True, help="research.json")
    finalize.add_argument("--out", required=True, help="新 snapshot 目录（不能已存在）")
    finalize.add_argument("--report", default=None, help="报告输出路径")
    finalize.add_argument("--strict", action="store_true", help="numeric gate 不通过时失败")
    finalize.add_argument("--min-claims", type=int, default=0)
    finalize.add_argument("--min-dimensions", type=int, default=0)
    finalize.add_argument("--html", action="store_true", help="同时生成 HTML")
    finalize.add_argument(
        "--allow-research-decisions",
        action="store_true",
        help="允许 research 决策改变数字（必须带 evidence）",
    )

    agent = sub.add_parser("agent", help="检查/推进 Agent 阶段 artifact 契约")
    agent.add_argument("--dir", required=True, help="artifact 目录")
    agent.add_argument("--phase", default=None, help="只检查/执行单个 phase")
    agent.add_argument(
        "--command",
        dest="phase_commands",
        action="append",
        default=[],
        help="phase=命令；可重复。命令在 --dir 内执行",
    )
    agent.add_argument("--timeout", type=int, default=300, help="单阶段命令超时秒数")
    agent.add_argument("--retries", type=int, default=0, help="命令失败重试次数")
    agent.add_argument("--resume", action="store_true", help="跳过 agent_state 中已通过阶段")

    pit = sub.add_parser("pit", help="本地 PIT 快照库")
    pit.add_argument("action", choices=["freeze", "list", "show", "export", "prune"])
    pit.add_argument("--code", required=True, help="股票代码")
    pit.add_argument("--known-at", default=None, help="快照知识日期（默认今天）")
    pit.add_argument("--as-of", default=None, help="查询日期")
    pit.add_argument("--out", default=None, help="export 输出")
    pit.add_argument("--backfill", action="store_true", help="按公告日生成累计快照")
    pit.add_argument("--keep", type=int, default=5, help="prune 保留数量")

    numeric = sub.add_parser("numeric-audit", help="报告数字可追溯性审计")
    numeric.add_argument("--report", required=True, help="analysis_report.md")
    numeric.add_argument(
        "--source",
        action="append",
        default=[],
        help="允许数字来源文件，可重复",
    )
    numeric.add_argument("--out", default=None, help="JSON 输出")
    numeric.add_argument("--strict", action="store_true", help="排除 inputs.json 原始值")

    smoke = sub.add_parser("smoke", help="本地真实数据 smoke（A/HK/US）")
    smoke.add_argument(
        "--codes",
        default="600887,00700.HK,AAPL",
        help="逗号分隔，默认 600887,00700.HK,AAPL",
    )
    smoke.add_argument("--rf", type=float, default=None, help="无风险利率（%%）")
    smoke.add_argument("--rf-source", default=None, help="无风险利率出处")
    smoke.add_argument(
        "--no-snapshot", dest="snapshot", action="store_false", help="不冻结 snapshot"
    )
    smoke.set_defaults(snapshot=True)

    cleanroom = sub.add_parser("cleanroom", help="PDF 与 snapshot 的独立数值复核（建议型）")
    cleanroom.add_argument("--snapshot", required=True, help="冻结 snapshot 目录")
    cleanroom.add_argument("--pdf-numbers", required=True, help="reported_numbers.json")
    cleanroom.add_argument("--pdf-file", default=None, help="原始 PDF，用于复核 document_hash")
    cleanroom.add_argument("--threshold", type=float, default=1.0, help="相对差异阈值（%%）")
    cleanroom.add_argument("--out", default=None, help="cleanroom.json 输出")
    cleanroom.add_argument("--strict", action="store_true", help="review 时返回非零")

    audit = sub.add_parser("audit", help="年报数字与 CLI 数字交叉审计")
    audit.add_argument("code", help="股票代码")
    audit.add_argument("--doc", required=True, help="文档数字 JSON（item/value/source/page）")
    audit.add_argument("--write", default=None, help="把冲突写入 qualitative.json")
    audit.add_argument("--threshold", type=float, default=1.0, help="相对差异阈值（%%）")

    state = sub.add_parser("state", help="初始化/更新多阶段运行状态")
    state.add_argument("code", help="股票代码")
    state.add_argument("--init", action="store_true", help="新建 run_state.json")
    state.add_argument("--phase", default=None, help="推进到指定阶段")
    state.add_argument("--artifact", default=None, help="记录产物 key=path")
    state.add_argument("--warning", action="append", default=None, help="追加警告（可重复）")

    verify = sub.add_parser("verify", help="证据事实校验（URL + 引文）")
    verify.add_argument("code", help="股票代码")
    verify.add_argument("--qualitative", default=None, help="定性 JSON 路径")
    verify.add_argument("--threshold", type=float, default=0.9, help="引文匹配阈值")
    verify.add_argument("--timeout", type=int, default=20, help="单 URL 超时秒数")
    verify.add_argument("--write", action="store_true", help="未通过模块降级为 unknown")

    narrative = sub.add_parser("narrative", help="校验叙述中的数字是否可追溯")
    narrative.add_argument("code", help="股票代码")
    narrative.add_argument("--file", required=True, help="叙述 Markdown 路径")

    qa = sub.add_parser("qa", help="交付前门控检查")
    qa.add_argument("code", help="股票代码")
    qa.add_argument("--write", action="store_true", help="全部通过后写 qa.json 并推进到 done")
    qa.add_argument("--json", dest="json_out", default=None, help="qa.json 输出路径")
    qa.add_argument(
        "--allow-missing-qualitative",
        action="store_true",
        help="确定性/研究流程允许无 qualitative.json",
    )

    golden = sub.add_parser("golden", help="黄金集标注模板与评分")
    golden.add_argument("--init", default=None, help="写出模板 CSV 路径")
    golden.add_argument("--codes", default="", help="逗号分隔的股票代码")
    golden.add_argument("--score", default=None, help="对已标注 CSV 评分")
    golden.add_argument("--threshold", type=float, default=0.75, help="一致率阈值")

    fetch = sub.add_parser("fetch-report", help="下载年报 PDF")
    fetch.add_argument("--url", required=True, help="PDF URL（雪球/同花顺）")
    fetch.add_argument("--stock-code", required=True, help="股票代码，如 SH600887")
    fetch.add_argument("--report-type", required=True, help="年报/中报/一季报/三季报")
    fetch.add_argument("--year", required=True, help="报告年份")
    fetch.add_argument("--save-dir", default=".", help="保存目录")
    fetch.add_argument("--max-retries", type=int, default=3)

    pdf = sub.add_parser("pdf", help="年报 PDF 章节预处理")
    pdf.add_argument("--pdf", required=True, help="年报 PDF 路径")
    pdf.add_argument("--output", default=None, help="输出 JSON 路径")
    pdf.add_argument("--hints", default=None, help="TOC hints JSON")
    pdf.add_argument("--verbose", action="store_true")
    pdf.add_argument("--dry-run", action="store_true")

    html = sub.add_parser("html", help="将 Markdown 报告转换为 HTML")
    html.add_argument("--input", required=True, help="Markdown 路径")
    html.add_argument("--output", default=None, help="HTML 输出路径")
    html.add_argument("--title", default=None, help="HTML 标题")

    pdf_numbers = sub.add_parser("pdf-numbers", help="从年报 PDF 抽取审计数字")
    pdf_numbers.add_argument("--pdf", required=True, help="年报 PDF 路径")
    pdf_numbers.add_argument("--year", required=True, type=int, help="报告年份")
    pdf_numbers.add_argument("--report-type", default="年报", help="年报/中报/一季报/三季报")
    pdf_numbers.add_argument("--output", default=None, help="reported_numbers.json 输出路径")
    pdf_numbers.add_argument("--max-pages", type=int, default=None, help="只扫描前 N 页")

    pdf_evidence = sub.add_parser("pdf-evidence", help="从 PDF 章节生成页级研究证据")
    pdf_evidence.add_argument("--sections", required=True, help="pdf_sections.json")
    pdf_evidence.add_argument("--output", default=None, help="evidence.json 输出")

    footnotes = sub.add_parser("pdf-footnotes", help="把 pdf_sections.json 的表格结构化为 footnotes.json")
    footnotes.add_argument("--sections", required=True, help="pdf_sections.json")
    footnotes.add_argument("--output", default=None, help="footnotes.json 输出路径")

    sub.add_parser("version", help="版本信息")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.output_dir:
        os.environ["TURTLE_OUTPUT_DIR"] = args.output_dir

    try:
        if args.command == "version":
            print(f"turtle-framework {__version__}")
            return 0
        if args.command == "run":
            return _run_cmd(
                args.code,
                args.rf,
                args.rf_source,
                args.currency,
                args.pdf_numbers,
                args.evidence,
                args.footnotes,
                args.pdf_sections,
                args.research,
                args.as_of,
                args.ttm,
                args.pit,
                args.html,
                args.strict,
                args.qa,
                args.min_claims,
                args.min_dimensions,
                args.allow_research_decisions,
            )
        if args.command == "analyze":
            return _demo_analyze() if args.demo else _live_analyze(
                args.code, args.save, args.currency, args.rf, args.rf_source, args.ttm
            )
        if args.command == "screen":
            return _screen(
                args.tier1_only,
                args.tier2_limit,
                args.csv_path,
                args.rf,
                args.rf_source,
                args.workers,
                args.fast,
                args.fast_limit,
                args.deep,
                args.api_interval,
                args.as_of,
            )
        if args.command == "golden":
            return _golden_cmd(args.init, args.codes, args.score, args.threshold)
        if args.command == "qa":
            return _qa_cmd(
                args.code,
                args.write,
                args.json_out,
                args.allow_missing_qualitative,
            )
        if args.command == "narrative":
            return _narrative_cmd(args.code, args.file)
        if args.command == "verify":
            return _verify_cmd(
                args.code, args.qualitative, args.threshold, args.timeout, args.write
            )
        if args.command == "state":
            return _state_cmd(
                args.code, args.init, args.phase, args.artifact, args.warning
            )
        if args.command == "audit":
            return _audit(args.code, args.doc, args.write, args.threshold)
        if args.command == "fetch-report":
            from .data import reports
            argv = [
                "--url", args.url,
                "--stock-code", args.stock_code,
                "--report-type", args.report_type,
                "--year", str(args.year),
                "--save-dir", args.save_dir,
                "--max-retries", str(args.max_retries),
            ]
            return _run_passthrough(reports.main, argv)
        if args.command == "pdf":
            from .pdf import preprocessor

            argv = ["--pdf", args.pdf]
            if args.output:
                argv += ["--output", args.output]
            if args.hints:
                argv += ["--hints", args.hints]
            if args.verbose:
                argv.append("--verbose")
            if args.dry_run:
                argv.append("--dry-run")
            return _run_passthrough(preprocessor.main, argv, patch_argv=True)
        if args.command == "html":
            return _html_cmd(args.input, args.output, args.title)
        if args.command == "pdf-numbers":
            return _pdf_numbers(
                args.pdf, args.year, args.report_type, args.output, args.max_pages
            )
        if args.command == "pdf-footnotes":
            return _pdf_footnotes(args.sections, args.output)
        if args.command == "pdf-evidence":
            return _pdf_evidence(args.sections, args.output)
        if args.command == "pack":
            return _pack(
                args.code,
                args.out,
                args.currency,
                args.rf,
                args.rf_source,
                args.pdf_numbers,
                args.footnotes,
                args.pdf_sections,
                args.as_of,
                args.pit,
            )
        if args.command == "report":
            return _report(
                args.code,
                args.out,
                args.currency,
                args.rf,
                args.rf_source,
                args.qualitative,
                args.pdf_numbers,
                args.save_snapshot,
                args.snapshot,
                args.research,
                args.as_of,
                args.ttm,
                args.pit,
                args.source_policy,
                args.strict_numeric,
                args.evidence,
                args.html,
                args.allow_research_decisions,
            )
        if args.command == "valuation":
            return _valuation(args.code, args.currency, args.rf, args.rf_source, args.ttm)
        if args.command == "qualitative":
            return _qualitative_cmd(args.code, args.init, args.check, args.out)
        if args.command == "research":
            return _research_cmd(args.file)
        if args.command == "research-audit":
            return _research_audit_cmd(
                args.file,
                args.metrics,
                args.facts,
                args.out,
                args.min_claims,
                args.min_dimensions,
            )
        if args.command == "research-context":
            return _research_context_cmd(args.snapshot, args.out, args.data_pack)
        if args.command == "research-provenance":
            return _research_provenance_cmd(
                args.research,
                args.snapshot,
                args.provider,
                args.model,
                args.out,
                args.generated_at,
            )
        if args.command == "sec-audit":
            return _sec_audit_cmd(
                args.snapshot, args.ticker, args.cik, args.out, args.tolerance
            )
        if args.command == "sec-evidence":
            return _sec_evidence_cmd(args.ticker, args.cik, args.out)
        if args.command == "coverage":
            return _coverage_cmd(args.code, args.json)
        if args.command == "hkex-news":
            return _hkex_news_cmd(
                args.code, args.from_date, args.to_date, args.keyword, args.out
            )
        if args.command == "research-agent":
            return _research_agent_cmd(
                args.snapshot,
                args.out,
                args.base_url,
                args.model,
                args.api_key,
                args.data_pack,
                args.retries,
                args.min_claims,
                args.min_dimensions,
                args.response,
            )
        if args.command == "snapshot":
            return _snapshot_cmd(
                args.code, args.as_of, args.out, args.report, args.research
            )
        if args.command == "finalize":
            return _finalize_cmd(
                args.snapshot,
                args.research,
                args.out,
                args.report,
                args.strict,
                args.min_claims,
                args.min_dimensions,
                args.html,
                args.allow_research_decisions,
            )
        if args.command == "agent":
            return _agent_cmd(
                args.dir,
                args.phase,
                args.phase_commands,
                args.timeout,
                args.retries,
                args.resume,
            )
        if args.command == "pit":
            return _pit_cmd(
                args.action,
                args.code,
                args.known_at,
                args.as_of,
                args.out,
                args.backfill,
                args.keep,
            )
        if args.command == "smoke":
            return _smoke_cmd(args.codes, args.rf, args.rf_source, args.snapshot)
        if args.command == "numeric-audit":
            return _numeric_audit_cmd(args.report, args.source, args.out, args.strict)
        if args.command == "cleanroom":
            return _cleanroom_cmd(
                args.snapshot,
                args.pdf_numbers,
                args.threshold,
                args.out,
                args.strict,
                args.pdf_file,
            )
    except TurtleError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
