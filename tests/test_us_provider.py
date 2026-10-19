from datetime import date

import pandas as pd

from turtlefw.data.tushare_provider import TushareProvider
from turtlefw.types import StockCode


class FakeTicker:
    info = {"financialCurrency": "USD"}

    financials = pd.DataFrame(
        {pd.Timestamp("2025-09-30"): [1000.0, 100.0]},
        index=["Total Revenue", "Net Income"],
    )
    balance_sheet = pd.DataFrame(
        {pd.Timestamp("2025-09-30"): [500.0, 200.0, 75.0, 20.0]},
        index=["Total Assets", "Stockholders Equity", "Total Debt", "Goodwill"],
    )
    cashflow = pd.DataFrame(
        {pd.Timestamp("2025-09-30"): [300.0, -50.0, 12.0]},
        index=["Operating Cash Flow", "Capital Expenditure", "Share Based Compensation"],
    )


def test_us_statement_mapping():
    provider = TushareProvider.__new__(TushareProvider)
    provider._us_yf = {"AAPL.US": FakeTicker()}
    rows = provider._yf_us_statements(StockCode.parse("AAPL"))
    values = {(row.statement, row.item): row.value for row in rows}
    assert values[("income", "revenue")] == 1000
    assert values[("balance", "total_assets")] == 500
    assert values[("balance", "st_borr")] == 75
    assert values[("balance", "goodwill")] == 20
    assert values[("cashflow", "n_cashflow_act")] == 300
    assert values[("cashflow", "c_pay_acq_const_fiolta")] == 50
    assert values[("cashflow", "sbc")] == 12
    assert all(row.currency.value == "USD" for row in rows)
    assert all(row.period_end == date(2025, 9, 30) for row in rows)
