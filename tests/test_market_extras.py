"""Tests for market/macro normalisation and rendering."""

from __future__ import annotations

from decimal import Decimal

from turtlefw.data.market_extras import (
    normalize_announcements,
    normalize_governance,
    normalize_index_valuation,
    normalize_index_weights,
    normalize_macro,
    normalize_major_holders,
    normalize_margin,
    normalize_moneyflow,
    normalize_research,
)
from turtlefw.report.market import render_market


def test_research_amounts_are_converted_from_ten_thousand_yuan() -> None:
    rows = [
        {
            "report_date": "20260820",
            "org_name": "示例证券",
            "quarter": "2028Q2",
            "op_rt": 13430,
            "np": 1380,
            "eps": 1.5,
            "pe": 18.2,
            "rating": "买入",
        }
    ]
    result = normalize_research(rows)
    assert result[0]["revenue"] == Decimal(134300000)
    assert result[0]["net_profit"] == Decimal(13800000)
    assert result[0]["report_date"] == "2026-08-20"
    assert result[0]["source"] == "tushare:report_rc"


def test_moneyflow_net_and_margin_balances() -> None:
    flow = normalize_moneyflow(
        [
            {
                "trade_date": "20261020",
                "buy_lg_amount": 10,
                "buy_elg_amount": 5,
                "sell_lg_amount": 2,
                "sell_elg_amount": 1,
                "net_mf_amount": 3,
            }
        ]
    )
    assert flow[0]["main_net"] == Decimal(120000)
    assert flow[0]["net_amount"] == Decimal(30000)
    margin = normalize_margin(
        [{"trade_date": "20261020", "rzye": 100, "rqye": 20, "rzrqye": 120}]
    )
    assert margin[0]["total_balance"] == Decimal(120)


def test_index_valuation_percentile_and_weights() -> None:
    valuation = normalize_index_valuation(
        [
            {"trade_date": "20260101", "pe_ttm": 10, "pb": 1},
            {"trade_date": "20260102", "pe_ttm": 20, "pb": 2},
            {"trade_date": "20260103", "pe_ttm": 30, "pb": 3},
        ]
    )
    assert valuation is not None
    assert valuation["trade_date"] == "2026-01-03"
    assert valuation["pe_percentile"] == Decimal(100)
    assert valuation["samples"] == 3
    weights = normalize_index_weights(
        [
            {"con_code": "000001.SZ", "con_name": "A", "weight": 1.2},
            {"con_code": "600000.SH", "con_name": "B", "weight": 3.6},
        ]
    )
    assert [row["code"] for row in weights] == ["600000.SH", "000001.SZ"]


def test_macro_units_and_pmi_fallback() -> None:
    rows = normalize_macro(
        cpi=[{"month": "202609", "nt_val": 100.5, "nt_yoy": 0.4}],
        ppi=[{"month": "202609", "ppi_yoy": -1.2}],
        gdp=[{"quarter": "2026Q2", "gdp": 600000, "gdp_yoy": 5.2}],
        pmi=[{"month": "202609", "pmi020100": 50.1}],
    )
    by_name = {row["indicator"]: row for row in rows}
    assert by_name["CPI"]["period"] == "2026-09"
    assert by_name["CPI"]["unit"] == "指数"
    assert by_name["GDP（累计）"]["unit"] == "亿元"
    assert by_name["非制造业 PMI"]["value"] == Decimal("50.1")


def test_announcements_are_dated_and_render_has_footer() -> None:
    announcements = normalize_announcements(
        [{"ann_date": "20261020", "title": "季度报告", "url": "https://example.test"}]
    )
    text = render_market(
        {
            "research": normalize_research(
                [{"report_date": "20260820", "org_name": "示例证券", "np": 1}]
            ),
            "announcements": announcements,
            "sources": ["tushare:report_rc", "tushare:anns_d"],
            "missing": ["news"],
        }
    )
    assert "### 卖方盈利预测" in text
    assert "季度报告" in text
    assert "tushare:report_rc" in text
    assert "未取得：news" in text
    assert "不进入 StatementRow 或确定性估值" in text


def test_governance_percent_and_date() -> None:
    rows = normalize_governance(
        [
            {
                "Holder": "Blackrock Inc.",
                "pctHeld": 0.0797,
                "Shares": 1162996939,
                "Value": 394837460790,
                "Date Reported": "2026-06-30 00:00:00",
            }
        ]
    )
    assert rows[0]["pct"] == Decimal("7.97")
    assert rows[0]["as_of"] == "2026-06-30"
    assert rows[0]["source"] == "yfinance:institutional_holders"


def test_major_holders_percent_and_render() -> None:
    rows = normalize_major_holders(
        [
            {"Breakdown": "institutionsPercentHeld", "Value": 0.65},
            {"Breakdown": "institutionsCount", "Value": 1200},
        ]
    )
    assert rows[0]["value"] == Decimal("65.0")
    assert rows[0]["percent"] is True
    assert rows[1]["value"] == Decimal(1200)
    assert rows[1]["percent"] is False
    text = render_market({"major_holders": rows, "sources": ["yfinance:major_holders"]})
    assert "股东结构（Yahoo Finance）" in text
    assert "65.00%" in text
    assert "1,200.00" in text


def test_render_market_accepts_serialized_numbers() -> None:
    text = render_market(
        {
            "research": [
                {
                    "report_date": "2026-08-20",
                    "org": "示例证券",
                    "revenue": "134300000000.0",
                    "net_profit": "13800000000.0",
                    "eps": "1.5",
                    "pe": "13.0",
                }
            ],
            "sources": ["tushare:report_rc"],
        }
    )
    assert "134,300.00" in text
    assert "13,800.00" in text


def test_empty_market_payload_renders_nothing() -> None:
    assert render_market({}) == ""
    assert render_market(None) == ""
