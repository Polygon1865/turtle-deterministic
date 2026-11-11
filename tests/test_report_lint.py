"""Contract tests for the rendered-report linter and section renumbering."""

from __future__ import annotations

from turtlefw.report.lint import lint_report
from turtlefw.report.normalize import numeral, renumber


def codes(markdown: str) -> list[str]:
    return [finding.code for finding in lint_report(markdown)]


def test_clean_report_has_no_findings() -> None:
    markdown = (
        "# 报告\n\n"
        "## 一、结论\n\n"
        "**观察** — 待确认\n\n"
        "| 项目 | 数值 |\n|:--|--:|\n| R | 1.00 |\n\n"
        "## 二、因子 1A\n\n"
        "- 通过\n"
    )
    assert lint_report(markdown) == []


def test_unnumbered_heading_is_reported() -> None:
    markdown = "## 一、结论\n\n正文\n\n## 行业分类\n\n- 银行\n"
    findings = lint_report(markdown)
    assert [item.code for item in findings] == ["heading.unnumbered"]
    assert findings[0].line == 5


def test_out_of_order_numbers_are_reported() -> None:
    markdown = "## 一、结论\n\n正文\n\n## 三、因子 1A\n\n正文\n"
    assert "heading.order" in codes(markdown)


def test_duplicate_heading_is_reported() -> None:
    markdown = "## 一、结论\n\n正文\n\n## 二、结论\n\n正文\n"
    assert "heading.duplicate" in codes(markdown)


def test_empty_section_is_reported() -> None:
    markdown = "## 一、结论\n\n## 二、因子 1A\n\n- 有内容\n"
    assert "section.empty" in codes(markdown)


def test_ragged_table_is_reported() -> None:
    markdown = (
        "## 一、结论\n\n"
        "| 项目 | 数值 |\n|:--|--:|\n| R | 1.00 | 多余 |\n"
    )
    assert "table.ragged" in codes(markdown)


def test_escaped_pipe_does_not_split_cells() -> None:
    markdown = (
        "## 一、结论\n\n"
        "| 项目 | 数值 | 说明 |\n|:--|--:|:--|\n"
        "| 外推可信度 | 观察 | medium（粗算偏差 \\|HH\\|） |\n"
    )
    assert "table.ragged" not in codes(markdown)


def test_raw_date_and_glued_punctuation_are_reported() -> None:
    markdown = "## 一、结论\n\n数据截至 20261027，。；\n"
    found = codes(markdown)
    assert "date.raw" in found
    assert "punct.glued" in found


def test_blockquote_is_exempt_from_inline_rules() -> None:
    markdown = "## 一、结论\n\n> 20261027 的原始引文，。；\n"
    assert codes(markdown) == []


def test_unbalanced_fence_is_reported() -> None:
    markdown = "## 一、结论\n\n```\n未闭合\n"
    assert "fence.unbalanced" in codes(markdown)


def test_renumber_rewrites_in_document_order() -> None:
    markdown = "## 三、结论\n\n正文\n\n## 行业分类\n\n- 银行\n"
    assert renumber(markdown) == "## 一、结论\n\n正文\n\n## 二、行业分类\n\n- 银行\n"


def test_renumber_keeps_fenced_code_untouched() -> None:
    markdown = "## 一、结论\n\n```\n## 不是标题\n```\n"
    assert "## 不是标题" in renumber(markdown)


def test_numeral_covers_teens_and_tens() -> None:
    assert numeral(1) == "一"
    assert numeral(10) == "十"
    assert numeral(11) == "十一"
    assert numeral(20) == "二十"
    assert numeral(21) == "二十一"
