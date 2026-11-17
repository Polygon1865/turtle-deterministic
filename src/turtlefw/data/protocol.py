"""Data-provider contracts (v2).

A provider turns an external API into :class:`StatementRow` values in the
canonical long format. No unit scaling happens here: values stay in the
reporting currency's base unit (yuan / HKD).

The v1 protocol listed seven methods while callers used more than thirty, so a
second provider (Wind, iFinD) could not be type-checked at all.  v2 lists every
member the app actually calls, with the exact signatures implemented by
``TushareProvider``; ``tests/test_provider_protocol.py`` fails if the two drift
apart.  Endpoints that an upstream cannot serve return an empty result instead
of raising (e.g. Tushare has no HK segment endpoint, so ``main_business`` is
empty for HK codes).

Adding a member here is a contract change: implement it in every provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol, Sequence

from ..types import Currency, DividendEvent, StockCode


@dataclass(frozen=True, slots=True)
class StatementRow:
    code: str
    period_end: date
    period_type: str  # annual | interim | q1 | q3
    statement: str  # income | balance | cashflow
    item: str
    value: Decimal
    currency: Currency
    source: str
    ann_date: date | None = None


class ProviderError(Exception):
    """The upstream provider failed after retries."""


class Provider(Protocol):
    """Everything the app may call on a data provider."""

    name: str

    # Read-only attributes. ``issues`` accumulates fetch problems for the
    # runner; ``hk_market_source`` says whether HK quotes came from Tushare,
    # yfinance, or a stale cache.
    @property
    def issues(self) -> Sequence[Any]: ...

    @property
    def hk_market_source(self) -> str: ...

    @property
    def stale_endpoints(self) -> tuple[str, ...]:
        """Endpoints served from a stale cache after a failed refresh (W1.2)."""
        ...

    # -- reference data ---------------------------------------------------
    def stock_basic(
        self, code: StockCode | None = None, *, list_status: str = "L"
    ) -> list[dict[str, Any]]: ...

    def latest_trade_date(self) -> str: ...

    def company_name(self, code: StockCode) -> str: ...

    def company_profile(self, code: StockCode) -> dict[str, str]: ...

    def reporting_currency(self, code: StockCode) -> Currency | None: ...

    # -- statements (A-share, HK and US share the long format) ------------
    def statements(
        self,
        code: StockCode,
        *,
        report_type: str = "1",
        currency: Currency | None = None,
        years: int = 6,
    ) -> list[StatementRow]: ...

    def market_statements(self, period: str, statement: str) -> Any:
        """Batch statement fetch (DataFrame); used by market-wide screens."""
        ...

    def market_fina_indicator(self, period: str) -> Any:
        """Batch indicator fetch (DataFrame); used by market-wide screens."""
        ...

    # -- market data ------------------------------------------------------
    def daily_basic(
        self, code: StockCode | None = None, trade_date: str | None = None
    ) -> list[dict[str, Any]]: ...

    def weekly(self, code: StockCode, *, years: int = 10) -> list[dict[str, Any]]: ...

    def audit(self, code: StockCode, *, years: int = 5) -> list[dict[str, Any]]: ...

    def pledge(self, code: StockCode, *, years: int = 5) -> list[dict[str, Any]]: ...

    def pledge_ratio(self, code: StockCode) -> Decimal | None: ...

    def repurchase(self, code: StockCode, *, years: int = 5) -> list[dict[str, Any]]: ...

    def buyback_amount(self, code: StockCode, *, years: int = 3) -> Decimal | None: ...

    def hk_buyback_events(
        self, code: StockCode, *, years: int = 2
    ) -> list[dict[str, Any]]: ...

    def hk_buyback_amount(
        self, code: StockCode, *, years: int = 3
    ) -> Decimal | None: ...

    def holders(self, code: StockCode) -> list[dict[str, Any]]: ...

    def main_business(self, code: StockCode) -> list[dict[str, Any]]: ...

    def peer_candidates(
        self, code: StockCode, limit: int = 8
    ) -> list[dict[str, Any]]: ...

    # -- dividends / valuation inputs -------------------------------------
    def dividends(
        self,
        code: StockCode,
        *,
        currency: Currency | None = None,
        years: int = 10,
        dps_fx: Decimal = Decimal("1"),
    ) -> list[DividendEvent]: ...

    def prefetch_dividends(self, periods: list[str]) -> None: ...

    def risk_free_rate(self, code: StockCode) -> Decimal | None: ...

    def market_extras(self, code: StockCode) -> dict[str, Any]: ...

    def fundamental_extras(self, code: StockCode) -> dict[str, Any]: ...

    # -- Hong Kong / US experimental --------------------------------------
    def hk_universe(self) -> list[dict[str, Any]]: ...

    def hk_market_snapshot(
        self, trade_date: str, *, allow_yfinance: bool = True
    ) -> list[dict[str, Any]]: ...

    def hk_indicator(
        self, code: StockCode, *, period: str | None = None
    ) -> dict[str, Any] | None: ...

    def hk_cashflow_rows(
        self, code: StockCode, *, currency: Currency | None = None
    ) -> list[StatementRow]: ...
