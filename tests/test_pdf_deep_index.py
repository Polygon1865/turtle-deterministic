import json

from turtlefw.cli import _pdf_index
from turtlefw.pdf.deep_index import (
    build_index,
    deep_context,
    load_index,
    search,
    write_index,
)


def _pages():
    return [
        (1, "封面\n某某股份有限公司 2025 年年度报告"),
        (2, "第一节 公司简介\n公司主要从事乳制品业务。"),
        (3, "第三节 管理层讨论与分析\n营业收入增长，毛利率保持稳定。"),
        (4, "公司收入与现金流情况。"),
        (5, "第四节 公司治理\n董事会及关联交易管理。"),
        (6, "第十节 财务报告\n财务报表附注。"),
    ]


def test_build_index_detects_sections_and_citations():
    index = build_index(_pages(), document_hash="abc123", source_name="demo.pdf")
    assert index["document"]["page_count"] == 6
    assert index["document"]["sha256"] == "abc123"
    assert [section["kind"] for section in index["sections"]] == [
        "front",
        "section",
        "mda",
        "governance",
        "financial",
    ]
    mda = next(section for section in index["sections"] if section["kind"] == "mda")
    assert mda["start_page"] == 3
    assert mda["end_page"] == 4
    page = next(item for item in index["pages"] if item["page"] == 3)
    assert page["section_id"] == mda["id"]
    assert page["citation"] == "pdf://abc123/p3"


def test_deep_context_selects_priority_sections_and_quotes():
    index = build_index(_pages(), document_hash="abc123")
    context = deep_context(index, max_chars=2000, max_pages=5)
    selected = {page["page"] for page in context["pages"]}
    assert 3 in selected
    assert 5 in selected
    assert context["stats"]["pages_total"] == 6
    assert context["stats"]["pages_selected"] == len(context["pages"])
    assert context["stats"]["chars_selected"] <= 2000
    page = next(item for item in context["pages"] if item["page"] == 3)
    assert page["citation"] in context["citations"]
    assert "毛利率" in context["citations"][page["citation"]]["quote"]
    assert len(context["citations"][page["citation"]]["quote"]) <= 400


def test_deep_context_honours_char_budget():
    index = build_index([(page, "管理层讨论与分析\n" + "数" * 500) for page in range(1, 6)])
    context = deep_context(index, max_chars=2000, max_pages=10)
    assert context["stats"]["chars_selected"] <= 2000
    assert context["stats"]["truncated_pages"] >= 1


def test_search_ranks_title_hits():
    index = build_index(_pages(), document_hash="abc123")
    hits = search(index, "公司治理")
    assert hits
    assert hits[0]["page"] == 5
    assert hits[0]["citation"] == "pdf://abc123/p5"


def test_financial_subheadings_stay_in_one_section():
    index = build_index(
        [
            (1, "第十节 财务报告\n合并资产负债表。"),
            (2, "财务报表项目 期初余额 本期变动 期末余额\n货币资金。"),
            (3, "财务报表项目 负债合计 期末余额\n应付账款。"),
        ],
        document_hash="abc123",
    )
    financial = [section for section in index["sections"] if section["kind"] == "financial"]
    assert len(financial) == 1
    assert financial[0]["start_page"] == 1
    assert financial[0]["end_page"] == 3


def test_index_roundtrip(tmp_path):
    index = build_index(_pages())
    target = write_index(index, tmp_path / "pdf_index.json")
    loaded = load_index(target)
    assert loaded == json.loads(json.dumps(index, ensure_ascii=False))
    context = deep_context(loaded, max_chars=1200, max_pages=3)
    assert context["pages"]


def test_pdf_index_command_writes_index(tmp_path, monkeypatch):
    source = tmp_path / "annual.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    target = tmp_path / "pdf_index.json"

    def fake_build(path, *, max_pages=None):
        assert path == source
        assert max_pages == 2
        return build_index(_pages(), document_hash="abc123", source_name=source.name)

    monkeypatch.setattr("turtlefw.pdf.deep_index.build_from_pdf", fake_build)
    assert _pdf_index(str(source), str(target), 2) == 0
    loaded = load_index(target)
    assert loaded["document"]["sha256"] == "abc123"
    assert (tmp_path / "pdf_notes.json").is_file()
