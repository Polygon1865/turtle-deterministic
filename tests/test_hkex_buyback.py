"""Tests for the HKEXnews Next Day Disclosure Return buy-back parser."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from turtlefw.data import hkex
from turtlefw.data.tushare_provider import TushareProvider
from turtlefw.types import StockCode

PART_B = """\
FF305
Next Day Disclosure Return
B. Shares redeemed or repurchased for cancellation but not yet cancelled as at the closing balance date
1). Shares repurchased for cancellation but not yet cancelled 227,000 0.0025 % HKD 442.3505
Date of changes 23 September 2026
2). Shares repurchased for cancellation but not yet cancelled 230,000 0.00253 % HKD 437.0791
Date of changes 24 September 2026
"""

TABLE = """\
Share Buy-back Report
Buy-back date Number of Shares bought back Purchase price per Share Aggregate price paid
Highest Lowest
20/03/2026 1,000,000 400.00 390.00 395,000,000.00
23/03/2026 500,000 405.00 398.00 200,500,000.00
"""


def test_parse_part_b_rows_compute_amount_from_vwap() -> None:
    events = hkex.parse_buyback_text(PART_B)

    assert [event.trade_date for event in events] == [date(2026, 9, 23), date(2026, 9, 24)]
    assert events[0].shares == 227000
    assert events[0].price == Decimal("442.3505")
    assert events[0].amount == (Decimal("442.3505") * 227000).quantize(Decimal("0.01"))
    assert events[0].currency == "HKD"


def test_parse_part_b_ignores_row_without_date() -> None:
    text = "1). Shares repurchased for cancellation but not yet cancelled 100,000 0.001 % HKD 10.50\n"

    assert hkex.parse_buyback_text(text) == []


def test_parse_table_layout_uses_aggregate_amount() -> None:
    events = hkex.parse_buyback_text(TABLE)

    assert len(events) == 2
    assert events[0].trade_date == date(2026, 3, 20)
    assert events[0].amount == Decimal("395000000.00")
    assert events[1].shares == 500000


def test_parse_text_without_buyback_returns_empty() -> None:
    assert hkex.parse_buyback_text("Just a circular about annual general meeting.") == []


def test_is_next_day_disclosure_title() -> None:
    assert hkex.is_next_day_disclosure("Next Day Disclosure Return")
    assert hkex.is_next_day_disclosure("Next Day Disclosure Return - Changes in issued shares")
    assert not hkex.is_next_day_disclosure("Monthly Return of Equity Issuer")


def test_buyback_amount_averages_completed_years_only(monkeypatch) -> None:
    provider = TushareProvider(token="dummy")
    rows = [
        {"trade_date": "2024-05-27", "shares": 1, "amount": "100", "currency": "HKD"},
        {"trade_date": "2024-06-03", "shares": 1, "amount": "100", "currency": "HKD"},
        {"trade_date": "2025-01-10", "shares": 1, "amount": "300", "currency": "HKD"},
        {"trade_date": "2026-02-01", "shares": 1, "amount": "999", "currency": "HKD"},
    ]
    monkeypatch.setattr(provider, "hk_buyback_events", lambda code, years=2: rows)

    amount = provider.hk_buyback_amount(StockCode.parse("00700.HK"), years=3)

    # 2024 total 200, 2025 total 300 -> average 250; the partial 2026 year is excluded.
    assert amount == Decimal("250")


def test_buyback_events_rejects_non_hk(monkeypatch) -> None:
    provider = TushareProvider(token="dummy")
    assert provider.hk_buyback_events(StockCode.parse("600519.SH")) == []
