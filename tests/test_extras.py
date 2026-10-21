from decimal import Decimal

import pandas as pd

from turtlefw.data.extras import (
    normalize_fina_indicator,
    normalize_forecast,
    normalize_holder_count,
    normalize_industry,
    normalize_managers,
)
from turtlefw.data.tushare_provider import US_INDICATOR_FIELDS, TushareProvider
from turtlefw.report.extras import render_extras
from turtlefw.types import StockCode


def test_a_share_indicator_normalizes_ratio_to_percent():
    rows = normalize_fina_indicator(
        [
            {
                "end_date": "20241231",
                "ann_date": "20250301",
                "eps": 1.2,
                "roe_waa": 20.5,
                "grossprofit_margin": 30.0,
                "netprofit_margin": 12.0,
                "debt_to_assets": 45.0,
                "ocf_to_or": 0.1517,
            }
        ],
        "A",
    )
    assert rows[0]["roe"] == Decimal("20.5")
    assert rows[0]["ocf_to_revenue"] == Decimal("15.1700")
    assert rows[0]["source"] == "tushare:fina_indicator"


def test_hk_and_us_indicators_use_basic_eps_without_ratio_conversion():
    hk = normalize_fina_indicator(
        [
            {
                "end_date": "20241231",
                "basic_eps": 2.0,
                "roe_avg": 18.0,
                "gross_profit_ratio": 40.0,
                "net_profit_ratio": 20.0,
                "debt_asset_ratio": 30.0,
                "ocf_sales": 38.0,
                "bps": 10.0,
            }
        ],
        "HK",
    )[0]
    assert hk["eps"] == Decimal("2.0")
    assert hk["ocf_to_revenue"] == Decimal("38.0")
    assert hk["source"] == "tushare:hk_fina_indicator"

    us = normalize_fina_indicator(
        [{"end_date": "20241231", "basic_eps": 3.0, "roe_avg": 25.0}], "US"
    )[0]
    assert us["eps"] == Decimal("3.0")
    assert us["ocf_to_revenue"] is None
    assert us["bps"] is None


def test_forecast_profit_is_converted_from_ten_thousand_yuan():
    rows = normalize_forecast(
        [
            {
                "end_date": "20241231",
                "ann_date": "20250110",
                "type": "预增",
                "net_profit_min": 10000,
                "net_profit_max": 12000,
                "p_change_min": 10,
                "p_change_max": 20,
            }
        ]
    )
    assert rows[0]["net_profit_min"] == Decimal(100000000)
    assert rows[0]["net_profit_max"] == Decimal(120000000)


def test_manager_and_holder_count_vendor_columns():
    managers = normalize_managers(
        [{"name": "张三", "title": "董事长", "begin_date": "20240101"}]
    )
    assert managers[0]["beg_date"] == "2024-01-01"
    counts = normalize_holder_count([{"end_date": "20241231", "holder_num": 12345}])
    assert counts[0]["holder_count"] == Decimal(12345)


def test_industry_prefers_current_membership_and_classification_name():
    industry = normalize_industry(
        [
            {"l1_code": "801120", "l1_name": "旧分类", "in_date": "20200101", "is_new": "N"},
            {"l1_code": "801120", "l1_name": "", "in_date": "20240101", "is_new": "Y"},
        ],
        [{"index_code": "801120", "industry_name": "食品饮料"}],
    )
    assert industry["level1"] == "食品饮料"
    assert industry["in_date"] == "2024-01-01"
    assert normalize_industry([{"l1_code": "801120", "is_new": "Y"}], []) == {}


def test_render_extras_is_empty_without_any_data():
    assert render_extras({}) == ""
    assert render_extras({"sources": [], "missing": ["forecasts"]}) == ""


def test_render_extras_omits_sections_with_no_data():
    text = render_extras(
        {"financial_indicators": [{"period_end": "2024-12-31", "roe": "20.5"}]}
    )
    assert "### 财务指标（Tushare）" in text
    assert "业绩预告" not in text
    assert "公司与管理层" not in text
    assert "股东结构" not in text
    assert "行业分类" not in text


def test_render_extras_contains_cross_check_note():
    text = render_extras(
        {
            "financial_indicators": [
                {
                    "period_end": "2024-12-31",
                    "roe": "20.5",
                    "gross_margin": "30",
                    "net_margin": "12",
                    "debt_ratio": "45",
                    "ocf_to_revenue": "15.17",
                }
            ],
            "sources": ["tushare:fina_indicator"],
        }
    )
    assert "### 财务指标（Tushare）" in text
    assert "20.50%" in text
    assert "不进入 StatementRow" in text


def test_render_extras_shows_per_share_and_rewards():
    text = render_extras(
        {
            "financial_indicators": [
                {
                    "period_end": "2024-12-31",
                    "eps": "1.20",
                    "bps": "10.50",
                }
            ],
            "rewards": [
                {
                    "ann_date": "2025-03-01",
                    "name": "张三",
                    "title": "董事长",
                    "reward": "1200000",
                    "hold_vol": "10000",
                }
            ],
        }
    )
    assert "| EPS | BPS |" in text
    assert "| 1.20 | 10.50 |" in text
    assert "高管薪酬" in text
    assert "薪酬（百万元）" in text
    assert "| 2025-03-01 | 张三 | 董事长 | 1.20 | 10,000 |" in text
    assert "张三" in text
    assert "1.20" in text


class _FakeProvider(TushareProvider):
    def __init__(self, frames, calls):
        self.frames = frames
        self.calls = calls
        self._issues = []

    def _safe(self, endpoint, **params):
        self.calls.append((endpoint, params))
        return self.frames.get(endpoint, pd.DataFrame())


def test_provider_collects_a_share_extras_and_reports_missing():
    calls = []
    frames = {
        "fina_indicator": pd.DataFrame(
            [
                {
                    "end_date": "20241231",
                    "ann_date": "20250301",
                    "eps": 1.2,
                    "roe_waa": 20.5,
                }
            ]
        ),
        "index_member_all": pd.DataFrame(
            [{"l1_code": "801120", "l1_name": "食品饮料", "in_date": "20240101", "is_new": "Y"}]
        ),
        "index_classify": pd.DataFrame(
            [{"index_code": "801120", "industry_name": "食品饮料"}]
        ),
    }
    provider = _FakeProvider(frames, calls)
    payload = provider.fundamental_extras(StockCode.parse("600887.SH"))
    assert payload["financial_indicators"][0]["roe"] == Decimal("20.5")
    assert payload["industry"]["level1"] == "食品饮料"
    assert "tushare:fina_indicator" in payload["sources"]
    assert "forecasts" in payload["missing"]


def test_provider_uses_us_endpoint_without_market_suffix():
    calls = []
    provider = _FakeProvider({}, calls)
    provider.fundamental_extras(StockCode.parse("AAPL.US"))
    assert calls == [
        (
            "us_fina_indicator",
            {"fields": US_INDICATOR_FIELDS, "ts_code": "AAPL"},
        )
    ]
