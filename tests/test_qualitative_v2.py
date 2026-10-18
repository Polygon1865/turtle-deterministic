import json

import pytest

from turtlefw.qualitative import Evidence, all_evidence, load, template
from turtlefw.types import TurtleError


def write(tmp_path, payload):
    path = tmp_path / "q.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_template_has_discrepancies():
    assert template()["discrepancies"] == []


def test_evidence_source_type_and_page(tmp_path):
    path = write(
        tmp_path,
        {
            "modules": {
                "moat": {
                    "judgment": "positive",
                    "confidence": "high",
                    "evidence": [
                        {
                            "url": "https://example.com/annual.pdf",
                            "quote": "市占率第一",
                            "source_type": "document",
                            "page": "p.42",
                        }
                    ],
                    "notes": "",
                }
            }
        },
    )
    item = load(path).get("moat")
    assert item.evidence[0].source_type == "document"
    assert item.evidence[0].page == "p.42"


def test_invalid_source_type_rejected(tmp_path):
    path = write(
        tmp_path,
        {
            "modules": {
                "moat": {
                    "judgment": "positive",
                    "confidence": "high",
                    "evidence": [
                        {"url": "https://x.com/a", "quote": "q", "source_type": "blog"}
                    ],
                }
            }
        },
    )
    with pytest.raises(TurtleError):
        load(path)


def test_discrepancies_parsed(tmp_path):
    path = write(
        tmp_path,
        {
            "discrepancies": [
                {
                    "item": "营业收入",
                    "cli_value": "115,636.23",
                    "doc_value": "115,931.00",
                    "source": "2025 年报 p.12",
                    "note": "差异 0.25%",
                }
            ],
            "modules": {},
        },
    )
    qualitative = load(path)
    assert len(qualitative.discrepancies) == 1
    assert qualitative.discrepancies[0].item == "营业收入"


def test_discrepancy_requires_item(tmp_path):
    path = write(tmp_path, {"discrepancies": [{"cli_value": "1"}], "modules": {}})
    with pytest.raises(TurtleError):
        load(path)


def test_all_evidence_tuple():
    from turtlefw.qualitative import Judgment, Qualitative

    judgment = Judgment(
        module="moat",
        judgment="positive",
        confidence="high",
        evidence=(Evidence("https://x.com", "q", "web", ""),),
    )
    rows = all_evidence(Qualitative(items={"moat": judgment}))
    assert rows[0][0] == "护城河与竞争格局"
    assert rows[0][3] == "web"
