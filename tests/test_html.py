from turtlefw.report.html import markdown_to_html


def test_headings_paragraphs_and_bold():
    html = markdown_to_html("# 标题\n\n这是 **重点** 和 `code`。")
    assert "<h1>标题</h1>" in html
    assert "<strong>重点</strong>" in html
    assert "<code>code</code>" in html


def test_table_and_separator():
    html = markdown_to_html("| 项目 | 数值 |\n|:---|---:|\n| R | 4.5% |")
    assert "<table>" in html
    assert "<th>项目</th>" in html
    assert "<td>R</td>" in html
    assert "<td>4.5%</td>" in html
    assert ":---" not in html


def test_list_and_blockquote():
    html = markdown_to_html("- 第一项\n- 第二项\n\n> 提示")
    assert "<ul>" in html and "<li>第一项</li>" in html
    assert "<blockquote>提示</blockquote>" in html


def test_script_is_escaped():
    html = markdown_to_html("<script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_report_shell_has_toc_and_scrollable_table():
    html = markdown_to_html(
        "# 伊利股份（600887.SH）\n\n## 一、结论\n\n| 项目 | 数值 |\n|---|---|\n| R | 3.5% |",
        title="analysis_report",
    )
    assert '<span class="badge">600887.SH</span>' in html
    assert 'class="toc"' in html
    assert 'class="table-wrap"' in html
    assert "返回研究终端" in html
    assert "确定性报告" in html


def test_llm_report_is_labeled_and_has_research_banner():
    html = markdown_to_html(
        "# 正丹股份（300641.SZ）\n\n## 研究摘要\n\n**研究覆盖**\n\n- claims：3"
    )
    assert "LLM 研究 + 确定性数字" in html
    assert "本报告包含 LLM 研究判断" in html
    assert "D1–D6" in html
    assert "研究判断由 LLM 生成" in html


def test_quick_read_replaces_summary_table_and_folds_appendix():
    html = markdown_to_html(
        "# 正丹股份（300641.SZ）\n\n## 一、结论\n\n"
        "**观察** — 估值或数据仍待确认\n\n"
        "| 项目 | 数值 |\n|---|---|\n| 粗算回报率 R | 4.42% |\n| 安全边际 | 5.33% |\n\n"
        "## 八、数据问题与待验证事项\n\n- 供应商权限不足\n\n"
        "**证据索引**\n\n| 证据 | 页面 |\n|---|---|\n| e1 | p10 |"
    )
    assert 'class="quickread"' in html
    assert 'qr-verdict' in html and "观察" in html
    assert "粗算 R / 精算 GG" in html
    assert "<td>粗算回报率 R</td>" not in html
    assert 'class="fold section-fold"' in html
    assert "数据问题与待验证事项" in html
    assert '<a class="toc-l3"' not in html
