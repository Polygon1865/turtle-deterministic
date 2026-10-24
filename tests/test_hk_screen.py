from __future__ import annotations

from decimal import Decimal

import pytest

from turtlefw.screener.hk import HkScreenError, screen_hk
from turtlefw.types import Currency


class _FakeProvider:
    def __init__(self) -> None:
        self.universe = [
            {
                "ts_code": "00700.HK",
                "name": "腾讯",
                "market": "主板",
                "list_date": "20040616",
            },
            {
                "ts_code": "09988.HK",
                "name": "阿里",
                "market": "主板",
                "list_date": "20191126",
            },
            {
                "ts_code": "03690.HK",
                "name": "美团",
                "market": "创业板",
                "list_date": "20180920",
            },
            {
                "ts_code": "01234.HK",
                "name": "新股",
                "market": "主板",
                "list_date": "20250101",
            },
            {
                "ts_code": "00005.HK",
                "name": "低成交",
                "market": "主板",
                "list_date": "19800102",
            },
            {
                "ts_code": "01299.HK",
                "name": "美元报表",
                "market": "主板",
                "list_date": "20101201",
            },
        ]
        self.snapshot = [
            {"ts_code": "00700.HK", "close": 600, "amount": 5_000_000_000},
            {"ts_code": "09988.HK", "close": 120, "amount": 2_000_000_000},
            {"ts_code": "03690.HK", "close": 100, "amount": 1_000_000_000},
            {"ts_code": "01234.HK", "close": 20, "amount": 900_000_000},
            {"ts_code": "00005.HK", "close": 60, "amount": 1_000_000},
            {"ts_code": "01299.HK", "close": 70, "amount": 9_000_000_000},
        ]
        self.indicators = {
            "00700.HK": self._indicator("20251231", 30, 25, 45, 40, 15, 10),
            "09988.HK": self._indicator("20251231", 12, 10, 35, 50, 5, 20),
            "00005.HK": self._indicator("20251231", 8, 20, 50, 80, 2, 70),
            "01299.HK": self._indicator("20251231", 99, 50, 90, 10, 50, 10),
        }

    @staticmethod
    def _indicator(period, roe, net, gross, debt, growth, eps):
        return {
            "end_date": period,
            "roe_avg": roe,
            "net_profit_ratio": net,
            "gross_profit_ratio": gross,
            "debt_asset_ratio": debt,
            "operate_income_yoy": growth,
            "operate_income": 100_000_000_000,
            "holder_profit": 10_000_000_000,
            "basic_eps": eps,
            "bps": 100,
        }

    def hk_universe(self):
        return self.universe

    def hk_market_snapshot(self, trade_date):
        return self.snapshot if trade_date == "20261023" else []

    def hk_indicator(self, code, *, period=None):
        return self.indicators.get(str(code))


def test_screen_hk_filters_and_ranks_market() -> None:
    rows = screen_hk(_FakeProvider(), trade_date="20261023", limit=10)
    assert [row.code for row in rows] == ["00700.HK", "09988.HK"]
    assert rows[0].rank == 1
    assert rows[0].name == "腾讯"
    assert rows[0].pe == Decimal("60")
    assert rows[0].pb == Decimal("6")
    assert rows[0].score > rows[1].score
    assert {row.market for row in rows} == {"HK"}


def test_screen_hk_limit_and_missing_snapshot() -> None:
    rows = screen_hk(_FakeProvider(), trade_date="20261023", limit=1)
    assert len(rows) == 1
    with pytest.raises(HkScreenError, match="no HK quote snapshot"):
        screen_hk(_FakeProvider(), trade_date="20261024")


def test_screen_hk_uses_documented_indicator_fields() -> None:
    from turtlefw.data.tushare_provider import HK_INDICATOR_FIELDS

    fields = set(HK_INDICATOR_FIELDS.split(","))
    assert "report_type" in fields
    assert "currency" in fields
    assert "pe_ttm" in fields
    # hk_fina_indicator does not document ann_date; an unknown field makes
    # Tushare reject the whole request.
    assert "ann_date" not in fields


def test_screen_hk_accepts_annual_report_type_variants() -> None:
    provider = _FakeProvider()
    provider.indicators["00700.HK"]["report_type"] = "2025年年报"
    provider.indicators["09988.HK"]["report_type"] = "Q4"

    rows = screen_hk(provider, trade_date="20261023", limit=10)

    assert [row.code for row in rows] == ["00700.HK", "09988.HK"]


def test_screen_hk_records_market_source() -> None:
    provider = _FakeProvider()
    provider.hk_market_source = "yfinance:hk_daily"

    rows = screen_hk(provider, trade_date="20261023", limit=1)

    assert rows[0].source.startswith("yfinance:hk_daily")


def test_screen_hk_does_not_fall_back_to_interim_indicator() -> None:
    class _NonDecemberProvider(_FakeProvider):
        def hk_indicator(self, code, *, period=None):
            if period:
                return None
            return self._indicator("20250630", 20, 10, 30, 50, 5, 10)

    with pytest.raises(HkScreenError, match="produced no rows"):
        screen_hk(_NonDecemberProvider(), trade_date="20261023", limit=5)


class _UsdProvider(_FakeProvider):
    def reporting_currency(self, code):  # noqa: ANN001
        return Currency.USD if str(code) == "09988.HK" else Currency.HKD


def test_screen_hk_skips_usd_reporting_listing() -> None:
    rows = screen_hk(_UsdProvider(), trade_date="20261023", limit=10)
    assert [row.code for row in rows] == ["00700.HK"]
