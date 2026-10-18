from decimal import Decimal

import pytest

from turtlefw.types import (
    Currency,
    CurrencyMismatchError,
    Money,
    StockCode,
    TurtleError,
)


class TestMoney:
    def test_add_same_currency(self):
        assert Money(Decimal("1.5"), Currency.CNY) + Money(Decimal("2.5"), Currency.CNY) == Money(
            Decimal("4"), Currency.CNY
        )

    def test_mixing_currencies_raises(self):
        with pytest.raises(CurrencyMismatchError):
            Money(Decimal("1"), Currency.CNY) + Money(Decimal("1"), Currency.HKD)

    def test_conversion(self):
        usd = Money(Decimal("100"), Currency.CNY).to(Currency.USD, Decimal("0.14"))
        assert usd.amount == Decimal("14.00")
        assert usd.currency is Currency.USD

    def test_same_currency_conversion_is_noop(self):
        cny = Money(Decimal("100"), Currency.CNY)
        assert cny.to(Currency.CNY, Decimal("99")) is cny

    def test_millions(self):
        assert Money(Decimal("96886000000"), Currency.CNY).millions() == Decimal("96886")

    def test_float_input_is_normalised(self):
        assert Money(1.1, Currency.CNY).amount == Decimal("1.1")


class TestStockCode:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("600887", "600887.SH"),
            ("600887.SH", "600887.SH"),
            ("000858", "000858.SZ"),
            ("300750", "300750.SZ"),
            ("830799", "830799.BJ"),
            ("920892.BJ", "920892.BJ"),
            ("920892", "920892.BJ"),
            ("900901.SH", "900901.SH"),
            ("00700", "00700.HK"),
            ("700", "00700.HK"),
            ("0700.HK", "00700.HK"),
            ("AAPL", "AAPL.US"),
            ("AAPL.US", "AAPL.US"),
        ],
    )
    def test_parse(self, raw, expected):
        assert str(StockCode.parse(raw)) == expected

    def test_market_mismatch_rejected(self):
        with pytest.raises(TurtleError):
            StockCode.parse("600887.SZ")

    def test_garbage_rejected(self):
        with pytest.raises(TurtleError):
            StockCode.parse("not a code")

    def test_is_a_share(self):
        assert StockCode.parse("600887").is_a_share
        assert not StockCode.parse("00700.HK").is_a_share
