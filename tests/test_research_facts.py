import json

from turtlefw.pdf.research_facts import fact_map, section_facts, write


def _payload():
    return {
        "metadata": {
            "pdf_file": "demo.pdf",
            "total_pages": 10,
            "section_pages": {"MDA": [3], "P4": [5]},
        },
        "MDA": "管理层讨论与分析\n收入增长 12%",
        "P4": "关联方交易\n向关联方销售",
        "P2": None,
    }


def test_section_facts_have_page_and_quote():
    facts = section_facts(_payload(), document_hash="abc")
    assert len(facts) == 2
    mda = next(item for item in facts if item["id"] == "pdf:section:MDA")
    assert mda["page"] == 3
    assert mda["section"] == "MDA"
    assert mda["confidence"] == "medium"
    assert "收入增长" in str(mda["quote"])
    assert mda["document_hash"] == "abc"


def test_write_and_fact_map(tmp_path):
    target = tmp_path / "evidence.json"
    write_payload = _payload()
    source = tmp_path / "sections.json"
    source.write_text(json.dumps(write_payload, ensure_ascii=False), encoding="utf-8")
    facts = write(source, target)
    assert target.is_file()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert len(loaded) == len(facts)
    mapped = fact_map(loaded)
    assert "pdf:section:MDA" in mapped
