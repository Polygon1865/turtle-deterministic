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
