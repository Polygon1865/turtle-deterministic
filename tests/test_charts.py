from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from turtlefw.report.charts import chart_for, price_chart
from turtlefw.report.html import convert_file, markdown_to_html


def test_price_chart_draws_price_and_floor():
    history = [
        {"trade_date": "20260101", "close": "100"},
        {"trade_date": "20260102", "close": "110"},
        {"trade_date": "20260103", "close": "120"},
    ]
    svg = price_chart(
        history,
        price=Decimal("118"),
        floor=Decimal("80"),
    )
    assert "<svg" in svg
    assert "polyline" in svg
    assert "当前价 118.00" in svg
    assert "综合底价 80.00" in svg
    assert "20260101" in svg


def test_price_chart_needs_two_points():
    assert price_chart([{"trade_date": "20260101", "close": "100"}]) == ""
    assert price_chart([{"trade_date": "20260101", "close": "0"}, {"trade_date": "20260102", "close": "1"}]) == ""


def test_chart_for_reads_snapshot_files(tmp_path: Path):
    source = tmp_path / "analysis_report.md"
    source.write_text("# report\n", encoding="utf-8")
    (tmp_path / "inputs.json").write_text(
        json.dumps(
            {
                "history": [
                    {"trade_date": "20260101", "close": "10"},
                    {"trade_date": "20260102", "close": "11"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "metrics.json").write_text(
        json.dumps(
            {
                "price": {"value": "11"},
                "floor": {"value": "9"},
            }
        ),
        encoding="utf-8",
    )
    svg = chart_for(source)
    assert "当前价 11.00" in svg
    assert "综合底价 9.00" in svg


def test_convert_file_injects_chart_and_css(tmp_path: Path):
    source = tmp_path / "analysis_report.md"
    source.write_text("# 测试报告\n\n正文\n", encoding="utf-8")
    target = convert_file(
        source,
        tmp_path / "report.html",
        chart_html='<figure class="chart"><svg></svg></figure>',
    )
    text = target.read_text(encoding="utf-8")
    assert '<figure class="chart">' in text
    assert ".chart svg" in text


def test_markdown_to_html_without_chart_unchanged():
    text = markdown_to_html("# 标题")
    assert "<h1>标题</h1>" in text
    assert "<figure" not in text
