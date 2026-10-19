from turtlefw.pdf.footnotes import structure_sections


def test_structure_tables_with_page_numbers():
    sections = {
        "P3": (
            "--- p.117 ---\n"
            "应收账款账龄\n\n"
            "[TABLE]\n| 账龄 | 金额 |\n| --- | --- |\n| 1年以内 | 100 |\n\n"
            "--- p.118 ---\n"
            "[TABLE]\n| 账龄 | 金额 |\n| --- | --- |\n| 1-2年 | 20 |"
        ),
        "P4": "关联方交易",
    }
    result = structure_sections(sections)
    assert result["P3"]["pages"] == [117, 118]
    assert len(result["P3"]["tables"]) == 2
    assert result["P3"]["tables"][0]["rows"][0] == ["账龄", "金额"]
    assert result["P3"]["tables"][1]["page"] == 118
    assert "关联方交易" in result["P4"]["text_excerpt"]


def test_empty_sections_are_skipped():
    assert structure_sections({"P3": "", "P4": None}) == {}
