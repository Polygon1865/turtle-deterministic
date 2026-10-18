"""Core domain types.

Everything in this module is dependency-free so it can be imported from any layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class TurtleError(Exception):
    """Base class for all framework errors."""


class ConfigError(TurtleError):
    """Configuration is missing or invalid."""


class CurrencyMismatchError(TurtleError, ValueError):
    """Two amounts in different currencies were combined without an FX rate."""


class Currency(StrEnum):
    CNY = "CNY"
    HKD = "HKD"
    USD = "USD"


@dataclass(frozen=True, slots=True)
class Money:
    """An amount together with its currency.

    Cross-currency arithmetic raises instead of silently mixing units.
    """

    amount: Decimal
    currency: Currency

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            object.__setattr__(self, "amount", Decimal(str(self.amount)))
        if not isinstance(self.currency, Currency):
            object.__setattr__(self, "currency", Currency(self.currency))

    # -- arithmetic -------------------------------------------------------
    def _same_currency(self, other: "Money") -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"cannot combine {self.currency} and {other.currency}; call .to() first"
            )

    def __add__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: "Money") -> "Money":
        self._same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def __mul__(self, factor: Decimal | int | float | str) -> "Money":
        return Money(self.amount * Decimal(str(factor)), self.currency)

    __rmul__ = __mul__

    def __truediv__(self, divisor: Decimal | int | float | str) -> "Money":
        return Money(self.amount / Decimal(str(divisor)), self.currency)

    def __abs__(self) -> "Money":
        return Money(abs(self.amount), self.currency)

    # -- conversion / display --------------------------------------------
    def to(self, target: Currency, fx: Decimal | str) -> "Money":
        """Convert to ``target`` using ``1 self.currency = fx target``."""
        if self.currency == target:
            return self
        return Money(self.amount * Decimal(str(fx)), target)

    def millions(self) -> Decimal:
        return self.amount / Decimal("1000000")

    def fmt(self, decimals: int = 2) -> str:
        return f"{self.amount:,.{decimals}f} {self.currency}"

    def __str__(self) -> str:
        return self.fmt()

    @classmethod
    def zero(cls, currency: Currency) -> "Money":
        return cls(Decimal("0"), currency)


class Market(StrEnum):
    SH = "SH"
    SZ = "SZ"
    BJ = "BJ"
    HK = "HK"
    US = "US"


_A_SHARE_PREFIX: dict[str, Market] = {
    "6": Market.SH,
    "9": Market.SH,
    "0": Market.SZ,
    "3": Market.SZ,
    "4": Market.BJ,
    "8": Market.BJ,
}


@dataclass(frozen=True, slots=True)
class StockCode:
    """Normalised ticker, e.g. ``600887.SH``, ``00700.HK``, ``AAPL.US``."""

    code: str
    market: Market

    def __str__(self) -> str:
        return self.code

    @property
    def numeric(self) -> str:
        return self.code.split(".", 1)[0]

    @property
    def is_a_share(self) -> bool:
        return self.market in (Market.SH, Market.SZ, Market.BJ)

    @classmethod
    def parse(cls, raw: str) -> "StockCode":
        text = raw.strip().upper()

        if m := re.fullmatch(r"(\d{6})\.(SH|SZ|BJ)", text):
            number, market = m.groups()
            expected = _A_SHARE_PREFIX.get(number[0])
            if expected is None or expected.value != market:
                raise TurtleError(f"code {number} does not belong to exchange {market}")
            return cls(f"{number}.{market}", Market(market))

        if m := re.fullmatch(r"(\d{1,5})\.HK", text):
            number = m.group(1).zfill(5)
            return cls(f"{number}.HK", Market.HK)

        if re.fullmatch(r"[A-Z]{1,5}\.US", text):
            return cls(text, Market.US)

        if re.fullmatch(r"\d{6}", text):
            market = _A_SHARE_PREFIX.get(text[0])
            if market is None:
                raise TurtleError(f"unrecognised A-share prefix: {text!r}")
            return cls(f"{text}.{market.value}", market)

        if re.fullmatch(r"\d{1,5}", text):
            return cls(f"{text.zfill(5)}.HK", Market.HK)

        if re.fullmatch(r"[A-Z]{1,5}", text):
            return cls(f"{text}.US", Market.US)

        raise TurtleError(f"unrecognised stock code: {raw!r}")


class Status(StrEnum):
    OK = "ok"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class Metric:
    """A single computed metric with an explicit availability state."""

    name: str
    value: Decimal | None
    status: Status
    source: str = ""
    note: str = ""

    @classmethod
    def ok(cls, name: str, value: Decimal, source: str = "") -> "Metric":
        return cls(name=name, value=value, status=Status.OK, source=source)

    @classmethod
    def missing(cls, name: str, note: str = "") -> "Metric":
        return cls(name=name, value=None, status=Status.MISSING, note=note)

    @classmethod
    def not_applicable(cls, name: str, note: str = "") -> "Metric":
        return cls(name=name, value=None, status=Status.NOT_APPLICABLE, note=note)

    def __bool__(self) -> bool:
        return self.status is Status.OK and self.value is not None


@dataclass(frozen=True, slots=True)
class FetchIssue:
    """A non-fatal data problem, surfaced in the report instead of swallowed."""

    endpoint: str
    code: str
    message: str
    retryable: bool = False

    def __str__(self) -> str:
        return f"[{self.endpoint}] {self.code}: {self.message}"


@dataclass(frozen=True, slots=True)
class DividendEvent:
    """One cash-dividend event.

    ``total`` is filled when the event carries a share base (A-share rows do);
    for HK rows only ``dps`` is known and ``total`` stays ``None`` until the
    caller supplies the share count.
    """

    fiscal_year: int
    event_id: str
    dps: Decimal
    currency: Currency
    total: Decimal | None = None
    ann_date: date | None = None
    payout_pct: Decimal | None = None
