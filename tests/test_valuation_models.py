from decimal import Decimal

from turtlefw.metrics import valuation_models as vm


class TestWacc:
    def test_simple_mix(self):
        value = vm.wacc(
            rf_pct=Decimal("3"),
            beta=Decimal("1"),
            erp_pct=Decimal("6"),
            cost_of_debt_pct=Decimal("5"),
            tax_pct=Decimal("25"),
            equity_value=Decimal("100"),
            debt_value=Decimal("100"),
        )
        # Ke = 9%, after-tax Kd = 3.75%, 50/50 mix -> 6.375%
        assert value == Decimal("6.375") or abs(value - Decimal("6.375")) < Decimal("1e-9")

    def test_invalid_weights(self):
        assert vm.wacc(
            rf_pct=Decimal("3"), beta=Decimal("1"), erp_pct=Decimal("6"),
            cost_of_debt_pct=Decimal("5"), tax_pct=Decimal("25"),
            equity_value=Decimal("0"), debt_value=Decimal("0"),
        ) is None


class TestDcf:
    def test_zero_growth_flat_fcf(self):
        result = vm.dcf(
            fcf_base=Decimal("100"),
            growth_rates_pct=[Decimal("0")] * 5,
            terminal_growth_pct=Decimal("0"),
            wacc_pct=Decimal("10"),
            cash=Decimal("0"),
            debt=Decimal("0"),
            shares=Decimal("100"),
        )
        # PV of 100 for 5 years + 100/0.10 discounted 5 years = 1000
        assert result["per_share"] is not None
        assert abs(result["per_share"] - Decimal("10")) < Decimal("0.0001")

    def test_negative_fcf_is_none(self):
        result = vm.dcf(
            fcf_base=Decimal("-1"),
            growth_rates_pct=[Decimal("0")] * 5,
            terminal_growth_pct=Decimal("0"),
            wacc_pct=Decimal("10"),
            cash=Decimal("0"), debt=Decimal("0"), shares=Decimal("100"),
        )
        assert result["per_share"] is None

    def test_terminal_must_be_below_wacc(self):
        result = vm.dcf(
            fcf_base=Decimal("100"), growth_rates_pct=[Decimal("0")] * 5,
            terminal_growth_pct=Decimal("10"), wacc_pct=Decimal("10"),
            cash=Decimal("0"), debt=Decimal("0"), shares=Decimal("100"),
        )
        assert result["per_share"] is None


class TestOtherModels:
    def test_ddm(self):
        assert vm.ddm(dps=Decimal("5"), ke_pct=Decimal("10"), growth_pct=Decimal("0")) == Decimal("50")

    def test_ddm_invalid(self):
        assert vm.ddm(dps=Decimal("5"), ke_pct=Decimal("5"), growth_pct=Decimal("5")) is None

    def test_pe_band(self):
        assert vm.pe_band(
            eps=Decimal("2"), pe_low=Decimal("10"),
            pe_mid=Decimal("15"), pe_high=Decimal("25"),
        ) == (Decimal("20"), Decimal("30"), Decimal("50"))

    def test_peg(self):
        value = vm.peg(eps=Decimal("2"), growth_pct=Decimal("20"), target_peg=Decimal("1"))
        assert value == Decimal("40")

    def test_ps(self):
        assert vm.ps(revenue_per_share=Decimal("10"), ps_multiple=Decimal("2")) == Decimal("20")


class TestCrossValidate:
    def test_weighted_average(self):
        value = vm.cross_validate(
            {"DCF": Decimal("10"), "DDM": Decimal("20"), "PE": None},
            {"DCF": Decimal("60"), "DDM": Decimal("40")},
        )
        assert value == Decimal("14")

    def test_equal_weights_when_missing(self):
        value = vm.cross_validate({"a": Decimal("10"), "b": Decimal("20")})
        assert value == Decimal("15")

    def test_upside(self):
        assert vm.blended_upside(Decimal("100"), Decimal("120")) == Decimal("20")
        assert vm.blended_upside(Decimal("0"), Decimal("120")) is None


class TestClassification:
    def test_blue_chip(self):
        profile, weights = vm.classify_company(
            roe_5y=Decimal("20"),
            payout_3y=Decimal("60"),
            revenue_cagr=Decimal("5"),
            profit_cagr=Decimal("8"),
        )
        assert profile == "蓝筹价值型"
        assert set(weights) == {"DCF", "DDM", "PE Band"}

    def test_growth(self):
        profile, weights = vm.classify_company(
            roe_5y=Decimal("10"),
            payout_3y=Decimal("10"),
            revenue_cagr=Decimal("30"),
            profit_cagr=Decimal("40"),
        )
        assert profile == "成长型"
        assert "PEG" in weights

    def test_mixed(self):
        profile, _ = vm.classify_company(
            roe_5y=Decimal("12"),
            payout_3y=Decimal("20"),
            revenue_cagr=Decimal("15"),
            profit_cagr=Decimal("15"),
        )
        assert profile == "混合型"


class TestSensitivityAndReverse:
    def test_sensitivity_shape(self):
        wacc_offsets, matrix = vm.dcf_sensitivity(
            fcf_base=Decimal("100"),
            growth_rates_pct=[Decimal("0")] * 5,
            terminal_growth_pct=Decimal("0"),
            wacc_pct=Decimal("10"),
            cash=Decimal("0"),
            debt=Decimal("0"),
            shares=Decimal("100"),
        )
        assert len(wacc_offsets) == 5
        assert len(matrix) == 5
        assert all(len(row) == 5 for row in matrix)

    def test_reverse_growth(self):
        # Flat FCF=100, WACC=10%, g=0, 100 shares -> per-share 10.
        implied = vm.implied_growth_pct(
            fcf_base=Decimal("100"),
            wacc_pct=Decimal("10"),
            terminal_growth_pct=Decimal("0"),
            cash=Decimal("0"),
            debt=Decimal("0"),
            shares=Decimal("100"),
            current_price=Decimal("10"),
            low=Decimal("-5"),
            high=Decimal("5"),
        )
        assert implied is not None
        assert abs(implied) < Decimal("0.01")
