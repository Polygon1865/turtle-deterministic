from decimal import Decimal

from helpers import make_rows
from turtlefw.metrics import cashflow


class TestCashBridge:
    def test_complete_bridge(self):
        rows = make_rows(
            {
                ("income", "revenue"): {2024: "1000"},
                ("cashflow", "c_fr_sale_sg"): {2024: "1200"},
                ("balance", "accounts_receiv"): {2023: "100", 2024: "150"},
                ("balance", "adv_receipts"): {2023: "80", 2024: "60"},
                ("cashflow", "c_paid_goods_srv"): {2024: "500"},
                ("cashflow", "c_paid_to_for_empl"): {2024: "100"},
                ("cashflow", "c_paid_for_taxes"): {2024: "50"},
                ("cashflow", "c_pay_oth_act"): {2024: "50"},
                ("cashflow", "c_pay_acq_const_fiolta"): {2024: "100"},
                ("cashflow", "n_cashflow_act"): {2024: "450"},
            }
        )
        bridge = cashflow.build_cash_bridge(rows)
        item = bridge[2024]
        assert item.true_cash_income == Decimal("1200")
        assert item.operating_outflows == Decimal("700")
        assert item.surplus == Decimal("400")
        assert item.source == "cash_bridge"
        assert item.complete is True

    def test_revenue_minus_ar_and_advance_when_cash_received_missing(self):
        rows = make_rows(
            {
                ("income", "revenue"): {2024: "1000"},
                ("balance", "accounts_receiv"): {2023: "100", 2024: "150"},
                ("balance", "adv_receipts"): {2023: "80", 2024: "60"},
                ("cashflow", "c_paid_goods_srv"): {2024: "500"},
                ("cashflow", "c_paid_to_for_empl"): {2024: "100"},
                ("cashflow", "c_paid_for_taxes"): {2024: "50"},
                ("cashflow", "c_pay_oth_act"): {2024: "50"},
                ("cashflow", "c_pay_acq_const_fiolta"): {2024: "100"},
            }
        )
        item = cashflow.build_cash_bridge(rows)[2024]
        # 1000 - AR increase 50 - advance decrease 20 = 930
        assert item.true_cash_income == Decimal("930")
        assert item.surplus == Decimal("130")

    def test_derived_outflow_uses_revenue_based_cash_income(self):
        rows = make_rows(
            {
                ("income", "revenue"): {2023: "1000", 2024: "1000"},
                ("cashflow", "c_fr_sale_sg"): {2024: "900"},
                ("cashflow", "c_inf_fr_operate_a"): {2024: "800"},
                ("cashflow", "n_cashflow_act"): {2024: "300"},
                ("cashflow", "c_pay_acq_const_fiolta"): {2024: "100"},
                ("balance", "accounts_receiv"): {2023: "100", 2024: "100"},
                ("balance", "adv_receipts"): {2023: "50", 2024: "50"},
            }
        )
        item = cashflow.build_cash_bridge(rows)[2024]
        assert item.operating_outflows == Decimal("500")
        assert item.true_cash_income == Decimal("1000")
        assert item.surplus == Decimal("400")
        assert item.complete is True

    def test_indirect_bridge_for_hk(self):
        rows = make_rows(
            {
                ("income", "revenue"): {2023: "1000", 2024: "1000"},
                ("balance", "accounts_receiv"): {2023: "100", 2024: "150"},
                ("balance", "prepayments"): {2023: "50", 2024: "60"},
                ("balance", "contract_liab"): {2023: "80", 2024: "70"},
                ("cashflow", "n_cashflow_act"): {2024: "300"},
                ("cashflow", "c_pay_acq_const_fiolta"): {2024: "100"},
            }
        )
        item = cashflow.build_cash_bridge(rows)[2024]
        # 1000 - AR+50 - prepay+10 - advance-10 = 930
        assert item.true_cash_income == Decimal("930")
        assert item.operating_outflows == Decimal("630")
        assert item.surplus == Decimal("200")
        assert item.source == "indirect_bridge"
        assert cashflow.bridge_label({2024: item}) == "间接现金桥"

    def test_fallback_to_ocf(self):
        rows = make_rows(
            {
                ("income", "revenue"): {2024: "1000"},
                ("cashflow", "n_cashflow_act"): {2024: "300"},
                ("cashflow", "c_pay_acq_const_fiolta"): {2024: "100"},
            }
        )
        item = cashflow.build_cash_bridge(rows)[2024]
        assert item.source == "ocf_fallback"
        assert item.surplus == Decimal("200")
        assert item.complete is False

    def test_coverage(self):
        rows = make_rows(
            {
                ("income", "revenue"): {2023: "1000", 2024: "1100"},
                ("cashflow", "n_cashflow_act"): {2023: "300", 2024: "400"},
            }
        )
        bridge = cashflow.build_cash_bridge(rows)
        assert cashflow.coverage(bridge) == (0, 2)
        assert cashflow.surplus_series(bridge) == {2023: Decimal("300"), 2024: Decimal("400")}
