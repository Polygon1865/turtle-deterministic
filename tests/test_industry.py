from decimal import Decimal

import pytest

from turtlefw.facts import MetricPoint, MetricRegistry
from turtlefw.report.industry import TEMPLATES, render_section, template_for


def test_templates_cover_three_industries():
    assert set(TEMPLATES) == {"telecom", "food", "internet"}
    assert template_for("600941.SH").key == "telecom"
    assert template_for("600887.SH").key == "food"
    assert template_for("00700.HK").key == "internet"
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
