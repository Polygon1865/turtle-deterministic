"""HK holder rows: Yahoo positions must be labelled, not passed off as top-10."""

from __future__ import annotations

import sys
import types

import pandas as pd

from turtlefw import demo
from turtlefw.config import load_settings
from turtlefw.data.tushare_provider import TushareProvider
from turtlefw.report.pack import render_data_pack
from turtlefw.types import Currency, Money, StockCode

YAHOO_ROWS = [
    {
        "holder_name": "Baillie Gifford & Co",
        "hold_amount": 1_120_000_000.0,
        "hold_ratio": 0.42,
        "holder_type": "公募基金",
        "as_of": "2026-06-30",
        "source": "yahoo",
    },
    {
        "holder_name": "Vanguard Group Inc",
        "hold_amount": 980_000_000.0,
        "hold_ratio": 0.37,
        "holder_type": "公募基金",
        "as_of": "2026-06-30",
        "source": "yahoo",
    },
]


def render(**overrides) -> str:
    kwargs = dict(
        quote={"trade_date": "20261016", "close": 28.2},
        history=[{"trade_date": "20261016", "close": 28.2}],
        market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
        shares=demo.DEMO_SHARES,
        rf_pct=demo.DEMO_RF,
        settings=load_settings(),
    )
    kwargs.update(overrides)
    return render_data_pack(
        demo.DEMO_CODE, demo.demo_rows(), demo.demo_dividends(), **kwargs
    )


class TestHkHoldersSection:
    def test_yahoo_rows_are_labelled_as_third_party(self):
        text = render(holders=YAHOO_ROWS)
        assert "机构与基金持仓（Yahoo，第三方，可能滞后）" in text
        assert "前十大股东" not in text
        assert "Baillie Gifford & Co" in text
        assert "11.20" in text  # 亿股
        assert "0.42%" in text
        assert "来源 Yahoo Finance" in text
        assert "披露日期 2026-06-30" in text

    def test_a_share_rows_keep_top10_heading(self):
        rows = [
            {"holder_name": "示例股东", "hold_amount": 86_000_000.0, "hold_ratio": 15.35}
        ]
        text = render(holders=rows)
        assert "**前十大股东**" in text
        assert "Yahoo" not in text

    def test_business_summary_fills_the_section_without_segments(self):
        text = render(
            holders=YAHOO_ROWS,
            industry_label="Consumer Cyclical / Restaurants",
            business_summary="公司以火锅餐饮连锁为主业，门店覆盖中国内地及海外。",
        )
        assert "**主营描述（Consumer Cyclical / Restaurants）**" in text
        assert "火锅餐饮连锁" in text
        assert "未接入股东/主营数据" not in text

    def test_empty_inputs_still_report_the_gap(self):
        text = render(holders=[], main_business=[], business_summary="")
        assert "未接入股东/主营数据。" in text


class _FakeFrame:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.empty = not rows

    def to_dict(self, orient: str) -> list[dict]:
        assert orient == "records"
        return list(self._rows)


class _FakeTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.institutional_holders = _FakeFrame(
            [{"Holder": "Pacer Advisors", "Shares": 445_244, "pctHeld": 0.0001}]
        )
        self.mutualfund_holders = _FakeFrame(
            [
                {"Holder": "Baillie Gifford", "Shares": 9_800_000, "pctHeld": 0.0042},
                {"Holder": "", "Shares": 1, "pctHeld": 0.0},
            ]
        )


def test_provider_normalises_yahoo_holders(monkeypatch):
    fake = types.SimpleNamespace(Ticker=_FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    provider = TushareProvider("token", cache_dir=None)

    rows = provider.holders(StockCode.parse("06862.HK"))

    assert [row["holder_name"] for row in rows] == ["Pacer Advisors", "Baillie Gifford"]
    assert rows[0]["source"] == "yahoo"
    assert rows[0]["holder_type"] == "机构"
    assert rows[1]["holder_type"] == "公募基金"
    assert rows[0]["hold_ratio"] == 0.01  # pctHeld fraction -> percent points
    # Cached: the second call must not touch yfinance again.
    fake.Ticker = lambda symbol: (_ for _ in ()).throw(AssertionError("cache miss"))
    assert provider.holders(StockCode.parse("06862.HK")) == rows


def test_provider_degrades_to_empty_on_yahoo_failure(monkeypatch):
    def boom(symbol: str):
        raise RuntimeError("network down")

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=boom))
    provider = TushareProvider("token", cache_dir=None)
    assert provider.holders(StockCode.parse("00700.HK")) == []
    assert pd is not None


def test_business_summary_is_trimmed_at_a_sentence():
    from turtlefw.data.tushare_provider import _summary_excerpt

    text = ("The company operates restaurants. " * 40).strip()
    excerpt = _summary_excerpt(text, limit=200)
    assert len(excerpt) <= 201
    assert excerpt.endswith("…")
    assert excerpt.rstrip("…").endswith("restaurants.")
    assert _summary_excerpt("short summary") == "short summary"
