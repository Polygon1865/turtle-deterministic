from turtlefw.narrative import check, normalize, tokens, unknown_numbers, whitelist


def test_tokens_normalize_commas():
    assert tokens("营收 115,636.23 百万，增长 0.25%") == ["115636.23", "0.25"]


def test_normalize():
    assert normalize("1,234.50") == "1234.50"


def test_whitelisted_numbers_pass():
    allowed = whitelist(["营收 115,636.23 百万，增长 0.25%"])
    assert unknown_numbers("营收 115636.23 百万", allowed) == []


def test_unknown_number_flagged():
    allowed = whitelist(["营收 115,636.23"])
    assert unknown_numbers("营收 999.99", allowed) == ["999.99"]


def test_decimal_variant_passes():
    allowed = whitelist(["ROE 13.60%"])
    assert unknown_numbers("ROE 13.6%", allowed) == []


def test_check_reads_sources(tmp_path):
    code_dir = tmp_path / "600887.SH"
    code_dir.mkdir(exist_ok=True)
    (code_dir / "analysis_report.md").write_text("结论：买入 ｜ R 7.48%", encoding="utf-8")
    narrative = tmp_path / "narrative.md"
    narrative.write_text("R 为 7.48%", encoding="utf-8")
    assert check("600887.SH", narrative, root=tmp_path) == []
    narrative.write_text("R 为 9.99%", encoding="utf-8")
    assert check("600887.SH", narrative, root=tmp_path) == ["9.99"]
