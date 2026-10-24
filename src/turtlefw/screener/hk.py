"""Market-wide HK screen.

There is no Tushare batch HK financial endpoint.  The screen therefore starts
from the whole listed HK universe, applies a cheap market/liquidity filter,
then asks for one annual indicator per surviving listing.  The result is a
ranked quality/valuation shortlist, not a replacement for the deterministic
per-stock analysis.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from ..types import Currency, StockCode


class HkScreenError(ValueError):
    """Raised when an HK screen cannot produce a usable universe."""


# Companies whose financial statements are reported in USD.  The deterministic
# report path only supports CNY/HKD statements and fails explicitly on USD; we
# exclude them before they consume a report slot.
USD_REPORTING_CODES = frozenset(
    {"00005.HK", "01299.HK", "02378.HK", "02888.HK"}
)


@dataclass(frozen=True)
class HkScreenRow:
    rank: int
    code: str
    name: str
    market: str
    price: Decimal
    turnover: Decimal
    roe: Decimal | None
    net_margin: Decimal | None
    gross_margin: Decimal | None
    debt_ratio: Decimal | None
    revenue_growth: Decimal | None
    pe: Decimal | None
    pb: Decimal | None
    score: Decimal
    period: str
    source: str = "tushare:hk_basic+hk_daily+hk_fina_indicator"

    def to_dict(self) -> dict[str, str]:
        def text(value: Decimal | None) -> str:
            return "" if value is None else str(value)

        return {
            "rank": str(self.rank),
            "ts_code": self.code,
            "code": self.code,
            "name": self.name,
            "market": self.market,
            "channel": "HK",
            "price": text(self.price),
            "turnover": text(self.turnover),
            "roe": text(self.roe),
            "net_margin": text(self.net_margin),
            "gross_margin": text(self.gross_margin),
            "debt_ratio": text(self.debt_ratio),
            "revenue_growth": text(self.revenue_growth),
            "pe": text(self.pe),
            "pb": text(self.pb),
            "score": text(self.score),
            "period": self.period,
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


def _score(
    *,
    roe: Decimal,
    net_margin: Decimal,
    gross_margin: Decimal,
    debt_ratio: Decimal,
    growth: Decimal | None,
) -> Decimal:
    """Transparent quality score in percentage-point units.

    The score is intentionally simple and fully visible in the CSV: no hidden
    model, no LLM.  It rewards returns/margins and penalises leverage; growth is
    capped so one explosive year cannot dominate the ranking.
    """

    capped_growth = min(growth or Decimal(0), Decimal(50))
    # Cap one-off margins/ROE so a single exceptional year cannot dominate the
    # ranking; the raw values remain in the CSV for inspection.
    capped_roe = min(roe, Decimal(50))
    capped_net = min(net_margin, Decimal(50))
    capped_gross = min(gross_margin, Decimal(100))
    capped_debt = min(max(debt_ratio, Decimal(0)), Decimal(100))
    return (
        capped_roe * Decimal("0.40")
        + capped_net * Decimal("0.25")
        + capped_gross * Decimal("0.15")
        - capped_debt * Decimal("0.20")
        + capped_growth * Decimal("0.10")
    )


def _is_annual(indicator: dict[str, Any]) -> bool:
    report_type = str(indicator.get("report_type") or "").upper()
    end_date = str(indicator.get("end_date") or "")
    return (
        report_type in {"Q4", "Y", "年报"}
        or "年报" in report_type
        or end_date.endswith("1231")
    )


def screen_hk(
    provider: Any,
    *,
    trade_date: str,
    limit: int = 100,
    candidate_limit: int = 300,
    min_turnover: Decimal = Decimal("5000000"),
    min_price: Decimal = Decimal("1"),
    min_list_years: int = 3,
    period: str | None = None,
) -> list[HkScreenRow]:
    """Screen the listed HK market and return the top ``limit`` rows.

    ``candidate_limit`` caps the number of per-stock financial calls after the
    market/liquidity filter.  Set it to ``0`` to fetch indicators for every
    surviving listing (slower, useful for a full refresh).
    """

    if limit <= 0:
        raise HkScreenError("limit must be positive")
    basic = provider.hk_universe()
    snapshot = provider.hk_market_snapshot(trade_date)
    if not basic:
        raise HkScreenError("no HK universe")
    if not snapshot:
        raise HkScreenError(f"no HK quote snapshot for {trade_date}")

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
            continue
        market = str(item.get("market") or "")
        if "创业" in market:
            continue
        listed = _date(item.get("list_date"))
        if listed is None or listed > oldest:
            continue
        quote = quotes.get(code)
        if quote is None:
            continue
        price = _dec(quote.get("close"))
        turnover = _dec(quote.get("amount"))
        if price is None or turnover is None:
            continue
        if price < min_price or turnover < min_turnover:
            continue
        candidates.append((item, quote))

    candidates.sort(key=lambda pair: _dec(pair[1].get("amount")) or Decimal(0), reverse=True)
    if candidate_limit > 0:
        candidates = candidates[:candidate_limit]

    rows: list[HkScreenRow] = []
    for item, quote in candidates:
        code_text = str(item.get("ts_code") or "")
        try:
            stock = StockCode.parse(code_text)
        except ValueError:
            continue
        indicator = provider.hk_indicator(stock, period=period)
        if not indicator:
            # Some HK issuers have a non-December fiscal year.  Fall back to
            # the latest annual indicator, but never mix an interim period into
            # an annual screen.
            indicator = provider.hk_indicator(stock)
            if indicator and not _is_annual(indicator):
                indicator = None
        if not indicator:
            continue
        currency = str(indicator.get("currency") or "").upper()
        if currency and currency not in {"HKD", "CNY", "港元", "人民币", "RMB"}:
            # The deterministic report path supports HKD/CNY statements only.
            continue
        if not _is_annual(indicator):
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
        if roe is None or net_margin is None or gross_margin is None:
            continue
        if debt_ratio is None or revenue is None or profit is None:
            continue
        if revenue <= 0 or profit <= 0:
            continue
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
                roe=roe,
                net_margin=net_margin,
                gross_margin=gross_margin,
                debt_ratio=debt_ratio,
                revenue_growth=growth,
                pe=pe,
                pb=pb,
                score=_score(
                    roe=roe,
                    net_margin=net_margin,
                    gross_margin=gross_margin,
                    debt_ratio=debt_ratio,
                    growth=growth,
                ),
                period=str(indicator.get("end_date") or period),
            )
        )

    rows.sort(key=lambda row: (row.score, row.turnover), reverse=True)
    source = getattr(
        provider,
        "hk_market_source",
        "tushare:hk_daily",
    )
    source = f"{source} + tushare:hk_basic + tushare:hk_fina_indicator"
    ranked: list[HkScreenRow] = []
    for row in rows:
        if len(ranked) >= limit:
            break
        reporting = getattr(provider, "reporting_currency", None)
        if reporting is not None and reporting(StockCode.parse(row.code)) is Currency.USD:
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
                roe=row.roe,
                net_margin=row.net_margin,
                gross_margin=row.gross_margin,
                debt_ratio=row.debt_ratio,
                revenue_growth=row.revenue_growth,
                pe=row.pe,
                pb=row.pb,
                score=row.score,
                period=row.period,
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
