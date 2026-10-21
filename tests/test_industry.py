from decimal import Decimal
from types import SimpleNamespace

import pytest

from turtlefw import demo
from turtlefw.cli import _peer_metrics_for_inputs
from turtlefw.facts import MetricPoint, MetricRegistry
from turtlefw.report.industry import TEMPLATES, render_section, template_for


def test_templates_cover_three_industries():
    assert set(TEMPLATES) == {"telecom", "food", "internet"}
    assert template_for("600941.SH").key == "telecom"
    assert template_for("600887.SH").key == "food"
    assert template_for("00700.HK").key == "internet"
    assert template_for("600276.SH") is None
    assert template_for("000333.SZ") is None
    assert template_for("99999.SZ") is None


@pytest.mark.parametrize(
    ("code", "title"),
    [
        ("600941.SH", "行业模板：运营商"),
        ("600887.SH", "行业模板：食品饮料"),
        ("00700.HK", "行业模板：互联网"),
    ],
)
def test_all_three_templates_render_with_missing_values(code, title):
    text = render_section(code, MetricRegistry())
    assert title in text
    assert "Peer 组" in text
    assert "—" in text


def test_peer_metrics_fetch_for_a_share_template():
    class FakeProvider:
        def statements(self, code, report_type=None):
            return demo.demo_rows()

    inputs = SimpleNamespace(code="600887.SH", rows=demo.demo_rows())
    rows = _peer_metrics_for_inputs(FakeProvider(), inputs)
    assert rows
    assert {row["name"] for row in rows} >= {"伊利股份"}
    assert all("revenue_cagr" in row for row in rows)


def test_render_section_with_peer_financials():
    text = render_section(
        "600887.SH",
        MetricRegistry(),
        [
            {
                "name": "伊利股份",
                "code": "600887.SH",
                "revenue_cagr": "8.00%",
                "net_margin": "9.00%",
                "roe": "18.00%",
            }
        ],
    )
    assert "Peer 财务对比" in text
    assert "8.00%" in text
    assert "18.00%" in text


def test_industry_classification_overrides_legacy_code():
    assert template_for("600887.SH", "电信").key == "telecom"
    assert template_for("600887.SH", "银行") is None
    text = render_section("600887.SH", MetricRegistry(), industry_name="银行")
    assert "## 行业分类" in text
    assert "暂无专用模板" in text
    assert "申万一级：银行" in text


def test_render_section_marks_missing_and_shows_peers():
    ledger = MetricRegistry()
    ledger.add(
        MetricPoint(
            id="revenue.cagr",
            name="营业收入 CAGR",
            value=Decimal("8.0"),
            unit="%",
            display="8.00%",
        )
    )
    text = render_section("600887.SH", ledger)
    assert "行业模板：食品饮料" in text
    assert "8.00%" in text
    assert "—" in text
    assert "Peer 组" in text
    assert "伊利股份" in text
    assert "未核实数字" in text
