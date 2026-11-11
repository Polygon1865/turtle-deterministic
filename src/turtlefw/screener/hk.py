"""Market-wide HK screen ranked by the Turtle return spread.

There is no Tushare batch HK financial endpoint.  The screen therefore starts
from the whole listed HK universe, applies cheap market filters, then asks for
one annual indicator and one cash-flow statement per surviving listing.  The
ranking is the same 穿透回报率 spread the A-share ``fast_screen`` uses:

    R      = 归母净利 x 支付率 / 市值           股东现金回报
    GG     = 两年平均自由现金流 x 支付率 / 市值   现金可支撑的回报
    II     = max(hk_floor, Rf + hk_spread)      门槛
    margin = GG - II                            安全边际

The previous ROE/net-margin weighted score ignored valuation entirely: a name
trading at PE 112 could rank above a cash-generative business paying out 90% of
its earnings.  Ranking on the spread fixes that by construction, because R is
payout/PE and GG is FCF yield x payout.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..config import Settings
from ..metrics import payout as payout_metrics
from ..types import Currency, StockCode


class HkScreenError(ValueError):
    """Raised when an HK screen cannot produce a usable universe."""


# Companies whose financial statements are reported in USD.  The deterministic
# report path only supports CNY/HKD statements and fails explicitly on USD; we
# exclude them before they consume a report slot.
USD_REPORTING_CODES = frozenset(
    {"00005.HK", "01299.HK", "02378.HK", "02888.HK"}
)

# Tushare reports ``hk_fina_indicator.currency`` as HKD for some mainland
# issuers that actually report in RMB.  Treat the common variants as CNY.
_CNY_LABELS = frozenset({"CNY", "RMB", "人民币"})


@dataclass(frozen=True)
class HkScreenRow:
    rank: int
    code: str
    name: str
    market: str
    price: Decimal
    turnover: Decimal
    market_cap: Decimal | None
    currency: str
    roe: Decimal | None
    net_margin: Decimal | None
    gross_margin: Decimal | None
    debt_ratio: Decimal | None
    revenue_growth: Decimal | None
    payout: Decimal | None
    payout_ok: bool
    r: Decimal | None
    gg: Decimal | None
    ii: Decimal
    margin: Decimal | None
    fcf_yield: Decimal | None
    pe: Decimal | None
    pb: Decimal | None
    period: str
    return_period: str = ""
    source: str = (
        "tushare:hk_basic+hk_daily+hk_fina_indicator+hk_cashflow"
    )

    def to_dict(self) -> dict[str, str]:
        def text(value: Decimal | None) -> str:
            if value is None:
                return ""
            try:
                return str(value.quantize(Decimal("0.01")))
            except InvalidOperation:
                return str(value)

        return {
            "rank": str(self.rank),
            "ts_code": self.code,
            "code": self.code,
            "name": self.name,
            "market": self.market,
            "channel": "HK",
            "price": text(self.price),
            "turnover": text(self.turnover),
            "market_cap": text(self.market_cap),
            "currency": self.currency,
            "roe": text(self.roe),
            "net_margin": text(self.net_margin),
            "gross_margin": text(self.gross_margin),
            "debt_ratio": text(self.debt_ratio),
            "revenue_growth": text(self.revenue_growth),
            "payout": text(self.payout),
            "payout_ok": "true" if self.payout_ok else "false",
            "R%": text(self.r),
            "GG%": text(self.gg),
            "II%": text(self.ii),
            "margin": text(self.margin),
            "FCF yield%": text(self.fcf_yield),
            "pe": text(self.pe),
            "pb": text(self.pb),
            "period": self.period,
            "return_period": self.return_period,
            "verdict": "入选",
            "source": self.source,
        }


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _date(value: Any) -> date | None:
    text = str(value or "").strip()
    if len(text) < 8:
        return None
    try:
        return datetime.strptime(text[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _years_before(anchor: date, years: int) -> date:
    try:
        return anchor.replace(year=anchor.year - years)
    except ValueError:  # 29 February
        return anchor.replace(year=anchor.year - years, day=28)


def _is_annual(indicator: dict[str, Any]) -> bool:
    report_type = str(indicator.get("report_type") or "").upper()
    end_date = str(indicator.get("end_date") or "")
    return (
        report_type in {"Q4", "Y", "年报"}
        or "年报" in report_type
        or end_date.endswith("1231")
    )


def _payout(
    indicator: dict[str, Any], *, currency: Currency, fx: Decimal
) -> tuple[Decimal, bool]:
    """Dividend payout in percent plus a reliability flag.

    Arithmetic lives in :mod:`turtlefw.metrics.payout` so the screener, the
    normaliser and the report cannot disagree about the fraction/percent
    boundary (roadmap T2).
    """

    ratio = payout_metrics.vendor_ratio(indicator.get("divi_ratio"))
    if ratio.pct is not None:
        return ratio.pct, ratio.reliable
    fallback = payout_metrics.dps_ratio(
        indicator.get("dps_hkd"),
        indicator.get("basic_eps"),
        eps_fx=Decimal("1") if currency is Currency.HKD else fx,
    )
    if fallback.pct is None:
        return Decimal("0"), False
    return fallback.pct, fallback.reliable


def _annual_cashflow(
    rows: list[Any], *, fiscal_month: int
) -> dict[date, dict[str, Decimal]]:
    """Group cash-flow rows by fiscal year end (same month as the annual row)."""

    grouped: dict[date, dict[str, Decimal]] = {}
    for row in rows:
        if getattr(row, "statement", "") != "cashflow":
            continue
        if row.period_end.month != fiscal_month:
            continue
        grouped.setdefault(row.period_end, {})[row.item] = row.value
    return grouped


def _fcf(items: dict[str, Decimal] | None) -> Decimal | None:
    if not items:
        return None
    ocf = items.get("n_cashflow_act")
    capex = items.get("c_pay_acq_const_fiolta")
    if ocf is None or capex is None:
        return None
    return ocf - abs(capex)


def screen_hk(
    provider: Any,
    *,
    trade_date: str,
    settings: Settings,
    rf_pct: Decimal,
    limit: int = 100,
    candidate_limit: int = 300,
    min_market_cap: Decimal = Decimal("5000000000"),
    min_list_years: int = 3,
    period: str | None = None,
    stats: dict[str, int] | None = None,
    on_progress: Any = None,
) -> list[HkScreenRow]:
    """Screen the listed HK market and return the top ``limit`` rows.

    ``min_market_cap`` drops listings whose total market cap (as reported by
    ``hk_fina_indicator.total_market_cap``, in HKD) is below the threshold.

    ``candidate_limit`` caps the number of per-stock financial calls after the
    market filter.  Set it to ``0`` to fetch indicators for every surviving
    listing (slower, useful for a full refresh).

    ``stats`` (optional) is filled with a per-stage drop count: HK's screen is a
    long funnel (2.8k listings -> a few hundred rows) and callers need to see
    where names disappear instead of guessing from the final list.
    """

    def bump(key: str) -> None:
        if stats is not None:
            stats[key] = stats.get(key, 0) + 1

    if limit <= 0:
        raise HkScreenError("limit must be positive")
    basic = provider.hk_universe()
    snapshot = provider.hk_market_snapshot(trade_date)
    if not basic:
        raise HkScreenError("no HK universe")
    if not snapshot:
        raise HkScreenError(f"no HK quote snapshot for {trade_date}")

    if stats is not None:
        stats["universe"] = len(basic)
        stats["quotes"] = len(snapshot)

    anchor = _date(trade_date)
    if anchor is None:
        raise HkScreenError(f"invalid HK trade date: {trade_date}")
    oldest = _years_before(anchor, min_list_years)
    period = period or f"{anchor.year - 1}1231"
    quotes = {str(row.get("ts_code") or ""): row for row in snapshot}

    candidates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for item in basic:
        code = str(item.get("ts_code") or "").strip()
        if not code or code in USD_REPORTING_CODES:
            bump("drop_usd")
            continue
        # Dual-counter listings: 8xxxx.HK is the RMB counter of 0xxxx.HK and
        # would otherwise duplicate the same company in the ranking
        # (82333.HK 长城汽车-R next to 02333.HK 长城汽车).
        name_text = str(item.get("name") or "").strip()
        if code.startswith("8") and name_text.endswith("-R"):
            bump("drop_rmb_counter")
            continue
        market = str(item.get("market") or "")
        if "创业" in market:
            bump("drop_gem")
            continue
        listed = _date(item.get("list_date"))
        if listed is None or listed > oldest:
            bump("drop_recent_ipo")
            continue
        quote = quotes.get(code)
        if (
            quote is None
            or _dec(quote.get("close")) is None
            or _dec(quote.get("amount")) is None
        ):
            bump("drop_no_quote")
            continue
        candidates.append((item, quote))

    candidates.sort(key=lambda pair: _dec(pair[1].get("amount")) or Decimal(0), reverse=True)
    if candidate_limit > 0:
        candidates = candidates[:candidate_limit]
    if stats is not None:
        stats["candidates"] = len(candidates)

    screening = settings.screening
    fx = settings.fx.cny_per_hkd
    rows: list[HkScreenRow] = []
    examined = 0
    for item, quote in candidates:
        examined += 1
        if on_progress is not None and examined % 250 == 0:
            on_progress(examined, len(candidates))
        code_text = str(item.get("ts_code") or "")
        try:
            stock = StockCode.parse(code_text)
        except ValueError:
            bump("drop_bad_code")
            continue
        indicator = provider.hk_indicator(stock, period=period)
        if not indicator:
            # Some HK issuers have a non-December fiscal year.  Fall back to
            # the latest annual indicator, but never mix an interim period into
            # an annual screen.
            fallback = provider.hk_indicator(stock)
            if fallback and not _is_annual(fallback):
                bump("drop_no_annual")
                continue
            indicator = fallback
        if not indicator:
            bump("drop_no_indicator")
            continue
        currency_text = str(indicator.get("currency") or "").upper()
        if currency_text and currency_text not in {"HKD", "CNY", "港元", "人民币", "RMB"}:
            # The deterministic report path supports HKD/CNY statements only.
            bump("drop_currency")
            continue
        if not _is_annual(indicator):
            bump("drop_no_annual")
            continue
        market_cap = _dec(indicator.get("total_market_cap"))
        if market_cap is None:
            bump("drop_no_market_cap")
            continue
        if market_cap < min_market_cap:
            bump("drop_market_cap")
            continue
        roe = _dec(indicator.get("roe_avg"))
        net_margin = _dec(indicator.get("net_profit_ratio"))
        gross_margin = _dec(indicator.get("gross_profit_ratio"))
        debt_ratio = _dec(indicator.get("debt_asset_ratio"))
        growth = _dec(indicator.get("operate_income_yoy"))
        revenue = _dec(indicator.get("operate_income"))
        profit = _dec(indicator.get("holder_profit"))
        eps = _dec(indicator.get("basic_eps"))
        bps = _dec(indicator.get("bps"))
        if roe is None or revenue is None or profit is None:
            bump("drop_missing_core")
            continue
        if revenue <= 0:
            bump("drop_no_revenue")
            continue
        if profit <= 0:
            bump("drop_loss")
            continue
        # Quality gates mirror ``fast_screen``.  A missing gross margin is
        # tolerated for HK: exchanges, conglomerates and financials legitimately
        # do not report one, and dropping them hid names such as 00388.HK.
        if roe < screening.min_roe:
            bump("drop_quality")
            continue
        if debt_ratio is None or debt_ratio > screening.max_debt_ratio:
            bump("drop_quality")
            continue
        if gross_margin is not None and gross_margin < screening.min_gross_margin:
            bump("drop_quality")
            continue

        currency = (
            Currency.CNY if currency_text in {"CNY", "人民币", "RMB"} else Currency.HKD
        )
        fx_div = fx if currency is Currency.CNY else Decimal(1)
        payout, payout_ok = _payout(indicator, currency=currency, fx=fx)
        fy_end = _date(indicator.get("end_date"))
        if fy_end is None:
            bump("drop_missing_core")
            continue
        cash = _annual_cashflow(
            provider.hk_cashflow_rows(stock, currency=currency),
            fiscal_month=fy_end.month,
        )
        latest_fcf = _fcf(cash.get(fy_end))
        if latest_fcf is None:
            bump("drop_no_cashflow")
            continue
        previous = _years_before(fy_end, 1)
        previous_fcf = _fcf(cash.get(previous))
        average_fcf = (
            (latest_fcf + previous_fcf) / 2
            if previous_fcf is not None
            else latest_fcf
        )

        net_income_hkd = profit / fx_div
        fcf_hkd = latest_fcf / fx_div
        average_fcf_hkd = average_fcf / fx_div
        r_pct = net_income_hkd * payout / 100 / market_cap * 100
        gg_pct = average_fcf_hkd * payout / 100 / market_cap * 100
        ii_pct = settings.returns.threshold(rf_pct, stock)
        margin = gg_pct - ii_pct
        fcf_yield = fcf_hkd / market_cap * 100

        price = _dec(quote.get("close")) or Decimal(0)
        turnover = _dec(quote.get("amount")) or Decimal(0)
        pe = _dec(indicator.get("pe_ttm"))
        if pe is None and eps and eps > 0:
            pe = price / eps
        pb = _dec(indicator.get("pb_ttm"))
        if pb is None and bps and bps > 0:
            pb = price / bps
        rows.append(
            HkScreenRow(
                rank=0,
                code=code_text,
                name=str(item.get("name") or ""),
                market="HK",
                price=price,
                turnover=turnover,
                market_cap=market_cap,
                currency=currency_text or "HKD",
                roe=roe,
                net_margin=net_margin,
                gross_margin=gross_margin,
                debt_ratio=debt_ratio,
                revenue_growth=growth,
                payout=payout,
                payout_ok=payout_ok,
                r=r_pct,
                gg=gg_pct,
                ii=ii_pct,
                margin=margin,
                fcf_yield=fcf_yield,
                pe=pe,
                pb=pb,
                period=str(indicator.get("end_date") or period),
                return_period=fy_end.isoformat(),
            )
        )

    rows.sort(
        key=lambda row: (row.margin if row.margin is not None else Decimal("-999"), row.turnover),
        reverse=True,
    )
    if stats is not None:
        stats["rows"] = len(rows)
    source = getattr(
        provider,
        "hk_market_source",
        "tushare:hk_daily",
    )
    source = f"{source} + tushare:hk_basic + tushare:hk_fina_indicator + tushare:hk_cashflow"
    ranked: list[HkScreenRow] = []
    reporting = getattr(provider, "reporting_currency", None)
    for row in rows:
        if len(ranked) >= limit:
            break
        # ``hk_fina_indicator.currency`` is wrong for some mainland issuers and
        # for USD reporters such as WH Group (00288.HK).  The deterministic
        # report path reads the unit from yfinance, so mirror it here and drop
        # USD reporters instead of wasting a report slot on them later.
        if reporting is not None and row.currency not in {"CNY", "人民币"}:
            try:
                actual = reporting(StockCode.parse(row.code))
            except (ValueError, OSError):
                actual = None
            if actual is Currency.USD:
                if stats is not None:
                    stats["drop_currency"] = stats.get("drop_currency", 0) + 1
                continue
        index = len(ranked) + 1
        ranked.append(
            HkScreenRow(
                rank=index,
                code=row.code,
                name=row.name,
                market=row.market,
                price=row.price,
                turnover=row.turnover,
                market_cap=row.market_cap,
                currency=row.currency,
                roe=row.roe,
                net_margin=row.net_margin,
                gross_margin=row.gross_margin,
                debt_ratio=row.debt_ratio,
                revenue_growth=row.revenue_growth,
                payout=row.payout,
                payout_ok=row.payout_ok,
                r=row.r,
                gg=row.gg,
                ii=row.ii,
                margin=row.margin,
                fcf_yield=row.fcf_yield,
                pe=row.pe,
                pb=row.pb,
                period=row.period,
                return_period=row.return_period,
                source=source,
            )
        )
    if not ranked:
        raise HkScreenError("HK screen produced no rows")
    return ranked


def write_ranking(path: Path, rows: list[HkScreenRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].to_dict()))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_dict())
