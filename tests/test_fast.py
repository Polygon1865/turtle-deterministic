from decimal import Decimal

import pandas as pd

from turtlefw.config import load_settings
from turtlefw.screener.fast import fast_screen


class FakeProvider:
    issues: list = []

    def market_statements(self, period, statement):
        row = {"ts_code": "600887.SH", "end_date": period}
        if statement == "income":
            row.update(
                revenue=1_000_000_000, n_income_attr_p=100_000_000,
                operate_profit=120_000_000, finance_exp=5_000_000,
            )
        elif statement == "balance":
            row.update(
                money_cap=50_000_000, total_hldr_eqy_exc_min_int=200_000_000,
                st_borr=30_000_000,
            )
        else:
            row.update(
                n_cashflow_act=110_000_000, c_pay_acq_const_fiolta=10_000_000,
                depr_fa_coga_dpba=20_000_000,
            )
        return pd.DataFrame([row])

    def market_fina_indicator(self, period):
        return pd.DataFrame(
            [{"ts_code": "600887.SH", "roe_waa": 12.0, "grossprofit_margin": 30.0, "debt_to_assets": 40.0}]
        )


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "600887.SH",
                "name": "示例",
                "channel": "main",
                "total_mv": 100_000.0,  # 万元 -> 10 亿
                "pe_ttm": 10.0,
                "dv_ttm": 3.0,
            }
        ]
    )


class TestFastScreen:
    def test_computes_market_metrics(self):
        result = fast_screen(frame(), FakeProvider(), load_settings(), Decimal("1.8"), limit=10)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["R%"] == 3.0  # 1亿净利 * 30% / 10亿市值
        assert row["payout"] == 30.0
        assert row["payout_ok"]
        assert row["EV/EBITDA"] > 0

    def test_impossible_payout_is_nan_not_100(self):
        inflated = frame()
        inflated.loc[0, "dv_ttm"] = 30.0  # 30% yield * PE 10 = 300% payout
        result = fast_screen(inflated, FakeProvider(), load_settings(), Decimal("1.8"), limit=10)
        row = result.iloc[0]
        assert pd.isna(row["payout"])
        assert not row["payout_ok"]
