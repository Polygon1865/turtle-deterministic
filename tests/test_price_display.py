"""Dual-currency price display: report header, data pack, site lede."""

from __future__ import annotations

from turtlefw.report.analysis import _price_text
from turtlefw.report.pack import _quote_note
from turtlefw.site import _report_lede

QUOTE = {"close": 3.634, "close_local": 3.95, "currency_local": "HKD", "fx": 0.92}


def test_price_text_appends_quote_currency() -> None:
    assert _price_text("3.63", QUOTE, "CNY") == "3.63 CNY（报价 3.95 HKD）"


def test_price_text_skips_same_currency() -> None:
    quote = {"close": 2.365, "close_local": 2.365, "currency_local": "HKD", "fx": 1.0}
    assert _price_text("2.37", quote, "HKD") == "2.37"


def test_price_text_without_quote_is_plain() -> None:
    assert _price_text("3.63", None, "CNY") == "3.63"


def test_quote_note_for_data_pack() -> None:
    assert _quote_note(QUOTE, "CNY") == "报价 HKD 3.95（1 HKD = 0.92 CNY）"


def test_quote_note_skips_hkd_reporting() -> None:
    quote = {"close_local": 2.365, "currency_local": "HKD", "fx": 1.0}
    assert _quote_note(quote, "HKD") == ""


def test_report_lede_shows_both_prices() -> None:
    lede = _report_lede(
        verdict="观察",
        industry="Beverages",
        r="6.29%",
        gg="10.32%",
        ii="5.00%",
        margin="5.32%",
        floor="4.62",
        price="3.63",
        premium="71.03%",
        currency="CNY",
        price_local="3.95",
        currency_local="HKD",
    )
    assert "现价 3.63 CNY（报价 3.95 HKD，溢价 71.03%）" in lede
