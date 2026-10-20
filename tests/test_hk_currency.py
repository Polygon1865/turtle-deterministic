from decimal import Decimal

import pandas as pd

from turtlefw import demo
from turtlefw.cli import _fx_history, _unit_for
from turtlefw.config import load_settings
from turtlefw.data.normalize import hk_dividend_events
from turtlefw.metrics.dividends import DividendEvent
from turtlefw.report.pack import average_dps, render_data_pack
from turtlefw.types import Currency, Money, StockCode


class _FakeProvider:
    def reporting_currency(self, code):
        return Currency.CNY


class TestUnitDetection:
    def test_explicit_currency_wins(self):
        assert _unit_for(StockCode.parse("00700.HK"), "HKD", _FakeProvider()) is Currency.HKD

    def test_provider_reporting_currency(self):
        assert _unit_for(StockCode.parse("00700.HK"), None, _FakeProvider()) is Currency.CNY

    def test_a_share_is_cny(self):
        assert _unit_for(StockCode.parse("600887"), None, None) is Currency.CNY


class TestHistoryConversion:
    def test_ohlc_converted(self):
        history = [
            {"trade_date": "20261016", "close": "100", "high": "110", "low": "90"},
        ]
        converted = _fx_history(history, Decimal("0.92"))
        assert Decimal(converted[0]["close"]) == Decimal("92.00")
        assert Decimal(converted[0]["high"]) == Decimal("101.20")
        assert Decimal(converted[0]["low"]) == Decimal("82.80")
        # original is not mutated
        assert history[0]["close"] == "100"

    def test_fx_one_is_noop(self):
        history = [{"close": "100"}]
        assert _fx_history(history, Decimal("1")) == history


class TestHkDividendReliability:
    def test_repeated_dps_is_marked_unreliable(self):
        df = pd.DataFrame(
            [
                {"end_date": f"{year}1231", "dps_hkd": "4.876", "divi_ratio": "0.2"}
                for year in (2023, 2024, 2025)
            ]
        )
        events = hk_dividend_events(df, currency=Currency.CNY)
        assert len(events) == 3
        assert all(not event.dps_reliable for event in events)
        assert average_dps(events) is None

    def test_varying_dps_stays_reliable(self):
        df = pd.DataFrame(
            [
                {"end_date": f"{year}1231", "dps_hkd": dps, "divi_ratio": "0.2"}
                for year, dps in ((2023, "1.0"), (2024, "2.0"), (2025, "3.0"))
            ]
        )
        events = hk_dividend_events(df, currency=Currency.CNY)
        assert all(event.dps_reliable for event in events)
        assert average_dps(events) == Decimal("2")

    def test_average_dps_excludes_incomplete_fiscal_year(self):
        events = [
            DividendEvent(
                fiscal_year=year,
                event_id=f"{year}-12-31:{dps}",
                dps=Decimal(dps),
                currency=Currency.CNY,
            )
            for year, dps in ((2023, "1.0"), (2024, "2.0"), (2025, "3.0"))
        ]
        events.append(
            DividendEvent(
                fiscal_year=2026,
                event_id="2026-06-30:9.0",
                dps=Decimal("9.0"),
                currency=Currency.CNY,
            )
        )
        # FY2026 has only an interim event; it must not enter the 3-year mean.
        assert average_dps(events) == Decimal("2")


class TestPackDisplay:
    def test_hk_total_and_dps_show_dash(self):
        text = render_data_pack(
            StockCode.parse("00700.HK"),
            demo.demo_rows(),
            [
                DividendEvent(
                    fiscal_year=2024,
                    event_id="2024",
                    dps=Decimal("4.876"),
                    currency=Currency.CNY,
                    total=None,
                    payout_pct=Decimal("20"),
                    dps_reliable=False,
                )
            ],
            quote={"trade_date": "20261016", "close": 92.0},
            history=[
                {"trade_date": "20261016", "close": 92.0, "high": 100.0, "low": 80.0},
            ],
            market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
            shares=demo.DEMO_SHARES,
            rf_pct=demo.DEMO_RF,
            settings=load_settings(),
        )
        assert "| 2024 | 1 | — | — | 20.00% |" in text
        assert "DPS 为「—」" in text
