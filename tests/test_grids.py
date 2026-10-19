from decimal import Decimal

import pytest

from turtlefw.config import ReturnsConfig, ValuationConfig, load_settings
from turtlefw.metrics import grids, valuation
from turtlefw.metrics.dividends import DividendEvent
from turtlefw.types import ConfigError, Currency, StockCode


def event(year: int, dps: str, total: str | None = None, currency=Currency.CNY) -> DividendEvent:
    return DividendEvent(
        fiscal_year=year,
        event_id=str(year),
        dps=Decimal(dps),
        currency=currency,
        total=Decimal(total) if total else None,
    )


class TestTaxScenarios:
    def test_a_share_has_three_holding_periods(self):
        scenarios = grids.tax_scenarios(StockCode.parse("600887"))
        assert [s.rate for s in scenarios] == [Decimal("0"), Decimal("10"), Decimal("20")]
        assert grids.default_tax_rate(StockCode.parse("600887")) == 0

    def test_hk_default_is_connect(self):
        code = StockCode.parse("00700.HK")
        assert grids.default_tax_rate(code) == Decimal("20")
        assert [s.label for s in grids.tax_scenarios(code)] == ["H股直接", "港股通", "红筹/开曼"]

    def test_us_default_is_w8ben(self):
        code = StockCode.parse("AAPL.US")
        assert grids.default_tax_rate(code) == Decimal("10")


class TestPayoutCrosscheck:
    def test_three_methods_agree(self):
        dividends = [event(2024, "0.5", "500")]
        check = grids.payout_crosscheck(
            dividends,
            {2024: Decimal("1000")},
            eps={2024: Decimal("1.0")},
            shares=Decimal("1000"),
        )
        assert check.recommended == Decimal("50")
        assert check.reliable is True

    def test_disagreement_marks_unreliable_but_keeps_events(self):
        # 法1 says 30%, event totals say 60%; event totals are canonical but
        # the shareholder-level disagreement must cap the verdict.
        dividends = [event(2024, "0.3", "600")]
        check = grids.payout_crosscheck(
            dividends,
            {2024: Decimal("1000")},
            eps={2024: Decimal("1.0")},
            shares=Decimal("1000"),
            cash_dividends={2024: Decimal("600")},
        )
        assert check.recommended == Decimal("60")
        assert check.reliable is False
        assert "15%" in check.note

    def test_cashflow_upper_bound_does_not_invalidate_event_totals(self):
        dividends = [event(2024, "0.5", "500")]
        check = grids.payout_crosscheck(
            dividends,
            {2024: Decimal("1000")},
            eps={2024: Decimal("1.0")},
            shares=Decimal("1000"),
            cash_dividends={2024: Decimal("970")},
        )
        assert check.recommended == Decimal("50")
        assert check.reliable is True
        assert "上界" in check.note

    def test_cashflow_is_used_when_event_total_is_unknown(self):
        dividends = [event(2024, "0.3")]  # no total, no shares
        check = grids.payout_crosscheck(
            dividends,
            {2024: Decimal("1000")},
            cash_dividends={2024: Decimal("600")},
        )
        assert check.recommended == Decimal("60")
        assert check.recommended_label == "法2 现金流"

    def test_no_events_returns_none(self):
        check = grids.payout_crosscheck([], {2024: Decimal("1000")})
        assert check.recommended is None
        assert check.reliable is False


class TestGGrid:
    def test_light_asset_uses_low_g(self):
        _rows, chosen, reason = grids.g_grid(
            Decimal("100"), Decimal("50"), Decimal("0.5"), ReturnsConfig()
        )
        assert chosen.g == Decimal("0.85")
        assert chosen.owner_earnings == Decimal("107.5")
        assert "轻资产" in reason

    def test_mid_and_heavy(self):
        mid = grids.g_grid(Decimal("100"), Decimal("50"), Decimal("1.0"), ReturnsConfig())[1]
        heavy = grids.g_grid(Decimal("100"), Decimal("50"), Decimal("1.5"), ReturnsConfig())[1]
        assert mid.g == Decimal("1.15")
        assert heavy.g == Decimal("1.50")

    def test_missing_da_keeps_net_income(self):
        _rows, chosen, _reason = grids.g_grid(
            Decimal("100"), None, None, ReturnsConfig()
        )
        assert chosen.owner_earnings == Decimal("100")

    def test_grid_has_twelve_rows(self):
        rows, _chosen, _reason = grids.g_grid(
            Decimal("100"), Decimal("50"), Decimal("1.0"), ReturnsConfig()
        )
        assert len(rows) == 12
        assert rows[0].g == Decimal("0.7")
        assert rows[-1].g == Decimal("1.8")


class TestAAAndLambda:
    def test_aa_variants(self):
        variants = grids.aa_variants({2020: Decimal("10"), 2021: Decimal("12"),
                                      2022: Decimal("20"), 2023: Decimal("14"),
                                      2024: Decimal("16")})
        values = {v.label: v.value for v in variants}
        assert values["AA_2y"] == Decimal("15")
        assert values["AA_all"] == Decimal("14.4")
        assert values["AA_excl"] == Decimal("14")

    def test_lambda_median(self):
        lam, note = grids.operating_lambda(
            {2021: Decimal("100"), 2022: Decimal("110"), 2023: Decimal("121")},
            {2021: Decimal("10"), 2022: Decimal("12"), 2023: Decimal("15")},
        )
        assert lam is not None
        assert Decimal("0.2") < lam < Decimal("0.3")
        assert note == ""

    def test_sensitivity_and_break_even(self):
        rows = grids.revenue_sensitivity(
            Decimal("1000"),
            Decimal("5000"),
            Decimal("0.2"),
            payout_pct=Decimal("50"),
            tax_pct=Decimal("0"),
            market_cap=Decimal("10000"),
            ii_pct=Decimal("5"),
        )
        assert len(rows) == 4
        assert rows[0][0] == Decimal("1.0")
        assert rows[-1][0] == Decimal("0.7")
        k_star = grids.break_even_revenue_multiple(
            Decimal("1000"),
            Decimal("5000"),
            Decimal("0.2"),
            payout_pct=Decimal("50"),
            tax_pct=Decimal("0"),
            market_cap=Decimal("10000"),
            ii_pct=Decimal("5"),
        )
        assert k_star == Decimal("1")


class TestConfidence:
    def test_high_confidence(self):
        result = grids.confidence_rating(
            revenue_cv=Decimal("5"),
            payout_years=3,
            fcf_positive_years=5,
            history_years=5,
            hh=Decimal("0.5"),
        )
        assert result.overall == "high"

    def test_two_lows_force_low(self):
        result = grids.confidence_rating(
            revenue_cv=Decimal("40"),
            payout_years=0,
            fcf_positive_years=5,
            history_years=5,
            hh=Decimal("0.5"),
        )
        assert result.overall == "low"


class TestCompositeChoice:
    def test_negative_anchor_is_skipped(self):
        baselines = valuation.five_baselines(
            cash=Decimal("10"),
            trad_assets=Decimal("0"),
            debt=Decimal("40"),
            equity=Decimal("500"),
            shares=Decimal("10"),
            closes=[Decimal("5"), Decimal("3")],
            average_dps=Decimal("0"),
            min_fcf=Decimal("-1"),
            rf_pct=Decimal("2"),
        )
        names = [item.name for item in baselines]
        assert "净流动资产/股" not in names
        assert all(item.value > 0 for item in baselines)

    def test_choose_composite_respects_method(self):
        baselines = [
            valuation.Baseline("a", Decimal("10"), ""),
            valuation.Baseline("b", Decimal("20"), ""),
            valuation.Baseline("c", Decimal("60"), ""),
        ]
        median, stats = valuation.choose_composite(baselines, "median", Decimal("20"))
        mean, _ = valuation.choose_composite(baselines, "mean", Decimal("20"))
        assert median == Decimal("20")
        assert mean == Decimal("30")
        assert stats.status == "divergent"

    def test_config_default_is_median(self):
        assert load_settings().valuation.composite_method == "median"

    def test_invalid_composite_rejected(self):
        with pytest.raises(ConfigError):
            ValuationConfig(composite_method="mode").validate()
