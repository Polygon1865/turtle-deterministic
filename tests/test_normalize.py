from decimal import Decimal

import pandas as pd
import pytest

from turtlefw.data.normalize import (
    dividend_events,
    hk_dividend_events,
    parse_date,
    period_type,
    rows_from_hk_line_items,
    rows_from_wide,
)
from turtlefw.data.tushare_maps import HK_INCOME_MAP
from turtlefw.types import Currency


class TestDates:
    def test_parse_compact(self):
        assert parse_date("20241231") == __import__("datetime").date(2024, 12, 31)

    def test_parse_dashed(self):
        assert parse_date("2024-12-31") == __import__("datetime").date(2024, 12, 31)

    def test_period_type(self):
        d = __import__("datetime").date
        assert period_type(d(2024, 12, 31)) == "annual"
        assert period_type(d(2024, 6, 30)) == "interim"
        assert period_type(d(2024, 3, 31)) == "q1"


class TestWideRows:
    def test_maps_columns_to_items(self):
        df = pd.DataFrame(
            [
                {
                    "ts_code": "600887.SH",
                    "end_date": "20241231",
                    "ann_date": "20250420",
                    "revenue": 100.0,
                    "n_income_attr_p": "10",
                    "sell_exp": None,
                }
            ]
        )
        rows = rows_from_wide(
            df,
            statement="income",
            item_map={"revenue": "revenue", "n_income_attr_p": "n_income_attr_p"},
            currency=Currency.CNY,
        )
        assert len(rows) == 2
        assert rows[0].period_type == "annual"
        assert rows[0].currency is Currency.CNY
        assert rows[0].source == "tushare"

    def test_nan_is_skipped(self):
        df = pd.DataFrame([{"ts_code": "x", "end_date": "20241231", "revenue": float("nan")}])
        rows = rows_from_wide(
            df, statement="income", item_map={"revenue": "revenue"}, currency=Currency.CNY
        )
        assert rows == []


class TestHKLineItems:
    def test_pivot(self):
        df = pd.DataFrame(
            [
                {"ts_code": "00728.HK", "end_date": "20241231", "ind_name": "营业额", "ind_value": "100"},
                {"ts_code": "00728.HK", "end_date": "20241231", "ind_name": "股东应占溢利", "ind_value": "10"},
                {"ts_code": "00728.HK", "end_date": "20231231", "ind_name": "营业额", "ind_value": "90"},
            ]
        )
        rows = rows_from_hk_line_items(
            df,
            statement="income",
            item_map=HK_INCOME_MAP,
            currency=Currency.CNY,
        )
        assert len(rows) == 3
        by_year = {r.period_end.year: r for r in rows if r.item == "revenue"}
        assert by_year[2024].value == 100
        assert by_year[2024].currency is Currency.CNY


class TestDividendEvents:
    def test_total_uses_share_base(self):
        df = pd.DataFrame(
            [
                {
                    "ts_code": "600887.SH",
                    "end_date": "20241231",
                    "ann_date": "20250420",
                    "cash_div_tax": "1.0",
                    "base_share": "1000",
                    "div_proc": "实施",
                }
            ]
        )
        events = dividend_events(df, currency=Currency.CNY)
        assert len(events) == 1
        assert events[0].total == 10_000_000
        assert events[0].fiscal_year == 2024

    def test_hk_event_has_no_total(self):
        df = pd.DataFrame([{"end_date": "20241231", "dps_hkd": "2.0"}])
        events = hk_dividend_events(df, currency=Currency.HKD)
        assert events[0].total is None
        assert events[0].dps == 2

    def test_zero_dividend_skipped(self):
        df = pd.DataFrame([{"end_date": "20241231", "cash_div_tax": "0", "base_share": "1000"}])
        assert dividend_events(df, currency=Currency.CNY) == []


class TestDividendDedupe:
    """Tushare repeats one dividend for every process stage."""

    def rows(self):
        stages = ["预案", "股东大会通过", "实施"]
        return pd.DataFrame(
            [
                {
                    "end_date": "20241231",
                    "ann_date": "20250430",
                    "div_proc": stage,
                    "cash_div_tax": "1.22",
                    "base_share": "1000",
                }
                for stage in stages
            ]
        )

    def test_three_stages_collapse_to_one_event(self):
        events = dividend_events(self.rows(), currency=Currency.CNY)
        assert len(events) == 1
        assert events[0].total == Decimal("12200000")

    def test_interim_and_final_are_two_events(self):
        df = pd.DataFrame(
            [
                {"end_date": "20250930", "div_proc": "实施", "cash_div_tax": "0.48", "base_share": "1000"},
                {"end_date": "20251231", "div_proc": "实施", "cash_div_tax": "0.90", "base_share": "1000"},
            ]
        )
        assert len(dividend_events(df, currency=Currency.CNY)) == 2


class TestHKDividends:
    def test_quarterly_rows_collapse_to_one_annual_event(self):
        df = pd.DataFrame(
            [
                {"end_date": f"2025{month}30", "dps_hkd": "5.3", "divi_ratio": "0.1942"}
                for month in ("03", "06", "09")
            ]
            + [{"end_date": "20251231", "dps_hkd": "5.3", "divi_ratio": "0.1942"}]
        )
        events = hk_dividend_events(df, currency=Currency.CNY)
        assert len(events) == 1
        assert events[0].payout_pct == Decimal("19.42")

    def test_ratio_above_one_is_not_rescaled(self):
        df = pd.DataFrame([{"end_date": "20241231", "dps_hkd": "1", "divi_ratio": "35"}])
        assert hk_dividend_events(df, currency=Currency.HKD)[0].payout_pct == Decimal("35")
