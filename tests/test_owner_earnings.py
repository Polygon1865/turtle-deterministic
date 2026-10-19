from decimal import Decimal

from helpers import make_rows
from turtlefw.metrics import owner_earnings


def test_normalized_owner_earnings_averages_years():
    rows = make_rows(
        {
            ("income", "n_income_attr_p"): {2022: "100", 2023: "110", 2024: "120"},
            ("cashflow", "depr_fa_coga_dpba"): {2022: "20", 2023: "20", 2024: "20"},
            ("balance", "accounts_receiv"): {2021: "10", 2022: "10", 2023: "12", 2024: "14"},
            ("balance", "inventories"): {2021: "5", 2022: "5", 2023: "5", 2024: "5"},
            ("balance", "acct_payable"): {2021: "4", 2022: "4", 2023: "5", 2024: "6"},
        }
    )
    # G=1 -> maintenance capex=20; 2024 WC = +2 AR -1 AP = +1
    value = owner_earnings.normalized_owner_earnings(rows, g=Decimal("1"), years=5)
    assert value is not None
    assert value > Decimal("0")


def test_missing_inputs_return_none():
    rows = make_rows({("income", "revenue"): {2024: "100"}})
    assert owner_earnings.normalized_owner_earnings(rows, g=Decimal("1")) is None
