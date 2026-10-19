import json

from turtlefw.pdf.research_facts import (
    fact_map,
    hk_facts,
    parent_company_facts,
    section_facts,
    write,
)


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


def test_hk_holder_and_segment_evidence():
    payload = {
        "metadata": {"section_pages": {"P4": [78], "MDA": [8]}},
        "P4": (
            "INTERESTS OF SUBSTANTIAL SHAREHOLDERS\n"
            "MIH Internet Holdings B.V. Long position 2,079,512,000 22.80%\n"
        ),
        "MDA": (
            "revenues of the Group and its segments\n"
            "VAS 369,281 319,168 16% 49% 49%\n"
            "The Group 751,766 660,257 14% 100% 100%\n"
        ),
    }
    facts = hk_facts(payload)
    ids = {item["id"] for item in facts}
    assert "pdf:holder:MIH Internet Holdings B.V." in ids
    assert "pdf:segment:VAS" in ids


def test_parent_company_statement_is_optional_evidence():
    payload = {
        "metadata": {"section_pages": {"P6": [120]}},
        "P6": "Company statement of financial position\nCash 100\nTotal assets 200",
    }
    facts = parent_company_facts(payload)
    assert len(facts) == 1
    assert facts[0]["id"] == "pdf:parent_company"
    assert facts[0]["page"] == 120
