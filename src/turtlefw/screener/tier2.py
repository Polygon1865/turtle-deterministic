"""Tier-2 deep screening: run the four-factor engine on Tier-1 survivors."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from decimal import Decimal

import pandas as pd

from ..config import Settings
from ..data.protocol import StatementRow
from ..factors.engine import FactorContext, final_verdict, run
from ..metrics import dividends as div_metrics
from ..metrics import statements, valuation
from ..types import Currency, Money, StockCode


@dataclass(frozen=True, slots=True)
class Tier2Result:
    ts_code: str
    name: str
    channel: str
    verdict: str
    r: Decimal | None
    gg: Decimal | None
    ii: Decimal | None
    margin: Decimal | None
    ev_ebitda: Decimal | None
    fcf_yield: Decimal | None
    floor_premium: Decimal | None
    issues: int
    payout_ok: bool = True
    floor_status: str = "unavailable"


def _latest(series: dict[int, Decimal]) -> Decimal | None:
    return series[max(series)] if series else None


def _safe_decimal(value) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except Exception:  # noqa: BLE001 - pandas NaN / None / strings
        return None
    return number if number.is_finite() else None


def analyze_one(provider, row: pd.Series, settings: Settings, rf_pct: Decimal) -> Tier2Result:
    code = StockCode.parse(str(row["ts_code"]))
    currency = Currency.CNY
    price = _safe_decimal(row.get("close"))
    total_mv = _safe_decimal(row.get("total_mv"))
    total_share = _safe_decimal(row.get("total_share"))
    if price is None or total_mv is None or total_share is None or total_share <= 0:
        return Tier2Result(
            ts_code=str(code), name=str(row.get("name", "")), channel=str(row.get("channel", "")),
            verdict="数据缺失（行情/股本）", r=None, gg=None, ii=None, margin=None,
            ev_ebitda=None, fcf_yield=None, floor_premium=None, issues=len(provider.issues),
        )
    rows: list[StatementRow] = provider.statements(code)
    if not rows:
        return Tier2Result(
            ts_code=str(code), name=str(row.get("name", "")), channel=str(row.get("channel", "")),
            verdict="数据缺失", r=None, gg=None, ii=None, margin=None,
            ev_ebitda=None, fcf_yield=None, floor_premium=None,
            issues=len(provider.issues),
        )

    dividends = provider.dividends(code)
    history = provider.weekly(code)
    market_cap = Money(total_mv * Decimal("10000"), currency)
    shares = total_share * Decimal("10000")

    years = sorted({r.period_end.year for r in rows if r.period_type == "annual"})
    latest = max(years) if years else None
    income = lambda item: statements.annual_series(rows, "income", item)  # noqa: E731
    balance = lambda item: statements.annual_series(rows, "balance", item)  # noqa: E731
    fcf = statements.fcf_series(rows)
    da = statements.da_series(rows)
    payouts = div_metrics.payout_by_year(
        dividends, income("n_income_attr_p"), shares=shares
    )
    mean_payout, _ = div_metrics.mean_payout(payouts)
    recent_years = sorted(payouts)[-3:]
    payout_ok = len(recent_years) >= 3 and all(
        payouts[year] is not None for year in recent_years
    )

    snapshot = valuation.build_valuation(
        market_cap=market_cap.amount,
        cash=statements.cash_and_equivalents(rows).get(latest) if latest else None,
        debt=statements.interest_bearing_debt(rows).get(latest) if latest else None,
        equity=statements.equity(rows).get(latest) if latest else None,
        net_income=income("n_income_attr_p").get(latest) if latest else None,
        revenue=income("revenue").get(latest) if latest else None,
        operate_profit=income("operate_profit").get(latest) if latest else None,
        finance_exp=income("finance_exp").get(latest) if latest else None,
        da=da.get(latest) if latest else None,
        fcf=fcf.get(latest) if latest else None,
        goodwill=balance("goodwill").get(latest) if latest else None,
        total_assets=balance("total_assets").get(latest) if latest else None,
        dps=None,
        price=price,
    )
    closes = [
        Decimal(str(item["close"]))
        for item in history
        if item.get("close") is not None
    ]
    pledge_pct = (
        provider.pledge_ratio(code) if hasattr(provider, "pledge_ratio") else None
    )
    buyback_amount = (
        provider.buyback_amount(code) if hasattr(provider, "buyback_amount") else None
    )
    buyback = Money(buyback_amount, currency) if buyback_amount is not None else None
    ctx = FactorContext(
        code=code, rows=rows, dividends=dividends, market_cap=market_cap, shares=shares,
        price=price, rf_pct=rf_pct, tax_pct=Decimal("0"), settings=settings,
        snapshot=snapshot, closes=closes, audit=provider.audit(code),
        payout_reliable=payout_ok, pledge_pct=pledge_pct, buyback=buyback,
    )
    results = run(ctx)
    verdict, _ = final_verdict(results)
    f2 = dict(results["2"].metrics)
    f3 = dict(results["3"].metrics)
    f4 = dict(results["4"].metrics)

    def _dec(text: str) -> Decimal | None:
        try:
            return Decimal(text.rstrip("%x").replace(",", ""))
        except Exception:  # noqa: BLE001 - display strings only
            return None

    # floor premium
    min_fcf_recent = dict(sorted(fcf.items())[-5:])
    min_fcf = (
        min(min_fcf_recent.values())
        if min_fcf_recent and min(min_fcf_recent.values()) > 0
        else None
    )
    from ..report.pack import average_dps

    baselines = valuation.five_baselines(
        cash=statements.cash_and_equivalents(rows).get(latest) if latest else None,
        trad_assets=balance("trad_asset").get(latest) if latest else None,
        debt=statements.interest_bearing_debt(rows).get(latest) if latest else None,
        equity=statements.equity(rows).get(latest) if latest else None,
        shares=shares,
        closes=closes,
        average_dps=average_dps(dividends),
        min_fcf=min_fcf,
        rf_pct=rf_pct,
        dividend_floor_pct=settings.valuation.dividend_discount_floor,
    )
    chosen, stats = valuation.choose_composite(
        baselines,
        settings.valuation.composite_method,
        settings.valuation.divergence_threshold,
    )
    premium = valuation.premium(price, chosen) if chosen else None
    if premium is not None:
        premium = premium.quantize(Decimal("0.01"))

    return Tier2Result(
        ts_code=str(code), name=str(row.get("name", "")), channel=str(row.get("channel", "")),
        verdict=verdict,
        r=_dec(f2.get("粗算回报率 R", "")),
        gg=_dec(f3.get("精算回报率 GG", "")),
        ii=_dec(f2.get("门槛 II", "")),
        margin=_dec(f4.get("安全边际 KK", "")),
        ev_ebitda=_dec(f4.get("EV/EBITDA", "")),
        fcf_yield=_dec(f4.get("FCF 收益率", "")),
        floor_premium=premium,
        issues=len(provider.issues),
        payout_ok=payout_ok,
        floor_status=stats.status,
    )


def run_tier2(
    frame: pd.DataFrame,
    provider,
    settings: Settings,
    rf_pct: Decimal,
    limit: int = 10,
    workers: int = 6,
) -> pd.DataFrame:
    """Analyse up to ``limit`` stocks, keeping input order.

    Concurrency is safe because the provider keeps one client per thread and
    serialises its throttle under a lock; the disk cache handles repeat runs.
    """
    items = list(frame.head(limit).iterrows())
    if not items:
        return pd.DataFrame()

    # One batch call per fiscal year replaces one dividend call per stock.
    periods = [f"{pd.Timestamp.now().year - 1 - i}1231" for i in range(6)]
    prefetch = getattr(provider, "prefetch_dividends", None)
    if callable(prefetch):
        prefetch(periods)

    def job(item):
        try:
            return analyze_one(provider, item[1], settings, rf_pct)
        except Exception as exc:  # noqa: BLE001 - one bad stock must not stop the batch
            row = item[1]
            return Tier2Result(
                ts_code=str(row.get("ts_code", "")),
                name=str(row.get("name", "")),
                channel=str(row.get("channel", "")),
                verdict=f"分析失败:{type(exc).__name__}",
                r=None, gg=None, ii=None, margin=None,
                ev_ebitda=None, fcf_yield=None, floor_premium=None,
                issues=len(provider.issues),
            )

    if workers > 1 and len(items) > 1:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            results = list(pool.map(job, items))
    else:
        results = [job(item) for item in items]

    return pd.DataFrame(
        [
            {
                "ts_code": r.ts_code,
                "name": r.name,
                "channel": r.channel,
                "verdict": r.verdict,
                "R%": r.r,
                "GG%": r.gg,
                "II%": r.ii,
                "margin": r.margin,
                "EV/EBITDA": r.ev_ebitda,
                "FCF yield%": r.fcf_yield,
                "floor premium%": r.floor_premium,
                "payout_ok": r.payout_ok,
                "floor_status": r.floor_status,
                "issues": r.issues,
            }
            for r in results
        ]
    )
