"""Data-provider contracts.

A provider turns an external API into :class:`StatementRow` values in the
canonical long format. No unit scaling happens here: values stay in the
reporting currency's base unit (yuan / HKD).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol, Sequence

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
    name: str

    def stock_basic(self, code: StockCode | None = None) -> list[dict]: ...

    def daily_basic(
        self, code: StockCode | None = None, trade_date: str | None = None
    ) -> list[dict]: ...

    def statements(
        self, code: StockCode, *, report_type: str = "1", currency: Currency | None = None
    ) -> list[StatementRow]: ...

    def dividends(self, code: StockCode, *, currency: Currency | None = None) -> list[DividendEvent]: ...

    def weekly(self, code: StockCode, *, years: int = 10) -> list[dict]: ...

    def risk_free_rate(self, code: StockCode) -> Decimal | None: ...

    def issues(self) -> Sequence[object]: ...
