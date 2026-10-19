from turtlefw.data.coverage import capabilities, coverage_markdown
from turtlefw.types import StockCode


def test_a_share_has_parent_and_pledge():
    rows = {row.key: row for row in capabilities(StockCode.parse("600887.SH"))}
    assert rows["parent_cash"].status == "available"
    assert rows["pledge"].status == "available"
    assert rows["pit"].status == "partial"


def test_us_marks_parent_and_holder_gaps():
    rows = {row.key: row for row in capabilities(StockCode.parse("AAPL.US"))}
    assert rows["statements_sec"].status == "partial"
    assert rows["sec_evidence"].status == "available"
    assert rows["parent_cash"].status == "not_applicable"
    assert rows["holders"].status == "external"
    assert rows["segments"].status == "external"


def test_hk_buyback_is_partial_and_parent_is_not_applicable():
    rows = {row.key: row for row in capabilities(StockCode.parse("00700.HK"))}
    assert rows["buyback"].status == "partial"
    assert rows["parent_cash"].status == "pdf_optional"
    assert rows["pledge"].status == "not_applicable"


def test_coverage_markdown_is_a_table():
    text = coverage_markdown(StockCode.parse("00700.HK"))
    assert "| 能力 | 状态 | 说明 |" in text
    assert "母公司现金" in text
