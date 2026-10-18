from decimal import Decimal

import pytest

from helpers import make_rows
from turtlefw.config import ReturnsConfig
from turtlefw.metrics import returns, statements, valuation
from turtlefw.types import Currency, Money, StockCode

ROWS = make_rows(
    {
        ("income", "revenue"): {2022: "100", 2023: "110", 2024: "121"},
        ("income", "n_income_attr_p"): {2022: "10", 2023: "11", 2024: "12.1"},
        ("cashflow", "n_cashflow_act"): {2022: "20", 2023: "22", 2024: "24"},
        ("cashflow", "c_pay_acq_const_fiolta"): {2022: "5", 2023: "6", 2024: "7"},
        ("cashflow", "depr_fa_coga_dpba"): {2022: "3", 2023: "3", 2024: "3"},
        ("balance", "money_cap"): {2022: "50", 2023: "55", 2024: "60"},
        ("balance", "st_borr"): {2022: "10", 2023: "10", 2024: "10"},
        ("balance", "lt_borr"): {2022: "5", 2023: "5", 2024: "5"},
        ("balance", "total_hldr_eqy_exc_min_int"): {2022: "100", 2023: "110", 2024: "121"},
        ("balance", "total_assets"): {2022: "200", 2023: "210", 2024: "220"},
    }
)


class TestStatements:
    def test_fcf(self):
        assert statements.fcf_series(ROWS) == {
            2022: Decimal("15"),
            2023: Decimal("16"),
            2024: Decimal("17"),
        }

    def test_interest_bearing_debt(self):
        assert statements.interest_bearing_debt(ROWS)[2024] == Decimal("15")

    def test_net_cash(self):
        assert statements.net_cash(ROWS, Currency.CNY)[2024] == Money(Decimal("45"), Currency.CNY)

    def test_missing_components_stay_missing(self):
        rows = make_rows({("balance", "money_cap"): {2024: "10"}})
        assert statements.interest_bearing_debt(rows) == {}

    def test_cagr(self):
        value = statements.cagr({2022: Decimal("100"), 2024: Decimal("121")})
        assert value is not None
        assert value.quantize(Decimal("0.0001")) == Decimal("0.1000")

    def test_cagr_ignores_negative_base(self):
        assert statements.cagr({2022: Decimal("-100"), 2024: Decimal("121")}) is None

    def test_cagr_uses_last_five_years(self):
        # 2015 -> 2025 includes 1992-style history; only 2021..2025 should count
        series = {
            2015: Decimal("10"),
            2016: Decimal("20"),
            2017: Decimal("40"),
            2018: Decimal("60"),
            2019: Decimal("80"),
            2020: Decimal("100"),
            2021: Decimal("110"),
            2022: Decimal("120"),
            2023: Decimal("130"),
            2024: Decimal("140"),
            2025: Decimal("150"),
        }
        value = statements.cagr(series)
        assert value is not None
        expected = (Decimal("150") / Decimal("110")) ** (Decimal("1") / Decimal("4")) - 1
        assert value.quantize(Decimal("0.000001")) == expected.quantize(Decimal("0.000001"))

    def test_annual_only(self):
        rows = make_rows({("income", "revenue"): {2024: "100"}})
        interim = rows[0].__class__(
            code="600887.SH",
            period_end=__import__("datetime").date(2024, 6, 30),
            period_type="interim",
            statement="income",
            item="revenue",
            value=Decimal("50"),
            currency=Currency.CNY,
            source="test",
        )
        assert statements.revenue(rows + [interim]) == {2024: Decimal("100")}


class TestReturns:
    def test_threshold_a_share(self):
        cfg = ReturnsConfig()
        assert returns.threshold_ii(Decimal("1.8"), StockCode.parse("600887"), cfg) == Decimal("3.8")

    def test_threshold_hk(self):
        cfg = ReturnsConfig()
        assert returns.threshold_ii(Decimal("1.8"), StockCode.parse("00700.HK"), cfg) == Decimal("5")

    def test_penetration_return(self):
        r = returns.penetration_return(
            Money(Decimal("1000"), Currency.CNY),
            Decimal("50"),
            Decimal("0"),
            Money.zero(Currency.CNY),
            Money(Decimal("10000"), Currency.CNY),
            Decimal("1"),
        )
        assert r == Decimal("5.0")

    def test_penetration_return_with_tax(self):
        r = returns.penetration_return(
            Money(Decimal("1000"), Currency.CNY),
            Decimal("50"),
            Decimal("20"),
            Money.zero(Currency.CNY),
            Money(Decimal("10000"), Currency.CNY),
            Decimal("1"),
        )
        assert r == Decimal("4.0")

    def test_zero_market_cap(self):
        assert (
            returns.penetration_return(
                Money(Decimal("1"), Currency.CNY),
                Decimal("50"),
                Decimal("0"),
                Money.zero(Currency.CNY),
                Money.zero(Currency.CNY),
                Decimal("1"),
            )
            is None
        )

    @pytest.mark.parametrize(
        ("r", "expected"),
        [
            ("1.5", "below_rf"),
            ("2.0", "fail"),
            ("4.0", "marginal"),
            ("5.0", "pass"),
            (None, "unknown"),
        ],
    )
    def test_classify(self, r, expected):
        value = Decimal(r) if r else None
        assert returns.classify_return(value, Decimal("5"), Decimal("1.8")) == expected


class TestValuation:
    def baselines(self):
        return [
            valuation.Baseline("a", Decimal("10"), ""),
            valuation.Baseline("b", Decimal("20"), ""),
            valuation.Baseline("c", Decimal("60"), ""),
        ]

    def test_mean(self):
        assert valuation.composite(self.baselines(), "mean") == Decimal("30")

    def test_median(self):
        assert valuation.composite(self.baselines(), "median") == Decimal("20")

    def test_empty(self):
        assert valuation.composite([]) is None

    def test_premium(self):
        assert valuation.premium(Decimal("120"), Decimal("100")) == Decimal("20")

    def test_five_baselines_skips_invalid(self):
        items = valuation.five_baselines(
            cash=Decimal("100"),
            trad_assets=Decimal("20"),
            debt=Decimal("30"),
            equity=Decimal("500"),
            shares=Decimal("10"),
            closes=[Decimal("5"), Decimal("3")],
            average_dps=Decimal("0"),
            min_fcf=Decimal("-1"),
            rf_pct=Decimal("2"),
        )
        names = [b.name for b in items]
        assert names == ["净流动资产/股", "每股净资产", "10年最低价"]
        assert valuation.ten_year_low([Decimal("5"), Decimal("3")]) == Decimal("3")


class TestFloorStats:
    def baselines(self, *values):
        return [valuation.Baseline(str(i), Decimal(v), "") for i, v in enumerate(values)]

    def test_stable_when_mean_close_to_median(self):
        stats = valuation.floor_stats(self.baselines("10", "11", "12"))
        assert stats.status == "stable"
        assert stats.mean == Decimal("11")
        assert stats.median == Decimal("11")

    def test_divergent_with_outlier(self):
        stats = valuation.floor_stats(self.baselines("-5", "9", "10", "11", "60"))
        assert stats.status == "divergent"
        assert stats.divergence > 50

    def test_negative_median_is_unavailable(self):
        stats = valuation.floor_stats(self.baselines("-10", "-5", "-1"))
        assert stats.status == "unavailable"
        assert stats.divergence is None

    def test_empty(self):
        assert valuation.floor_stats([]).status == "unavailable"
