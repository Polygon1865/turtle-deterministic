import json

import pytest

from turtlefw.cli import _research_context
from turtlefw.pdf.deep_index import build_index, write_index
from turtlefw.research import validate_evidence


def test_research_context_collects_snapshot_sources(tmp_path):
    (tmp_path / "inputs.json").write_text(
        json.dumps(
            {
                "code": "600887.SH",
                "as_of": "2026-10-16",
                "currency": "CNY",
                "parent_cash": "100",
                "pledge_pct": "0",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"snapshot_id": "snap-1"}), encoding="utf-8"
    )
    (tmp_path / "metrics.json").write_text('{"r": {"display": "3.36%"}}', encoding="utf-8")
    (tmp_path / "evidence.json").write_text(
        json.dumps([{"id": "pdf:section:MDA", "quote": "MDA text"}]),
        encoding="utf-8",
    )
    (tmp_path / "pdf_sections.json").write_text(
        json.dumps({"metadata": {}, "MDA": "MDA text"}),
        encoding="utf-8",
    )
    context = _research_context(str(tmp_path))
    assert context["code"] == "600887.SH"
    assert context["snapshot_id"] == "snap-1"
    assert context["governance"]["parent_cash"] == "100"
    assert any(row["id"] == "data:governance" for row in context["facts"])
    assert any(row["key"] == "parent_cash" for row in context["coverage"])
    assert context["metrics"]["r"]["display"] == "3.36%"
    assert context["facts"][0]["id"] == "pdf:section:MDA"
    assert context["pdf_sections"]["MDA"] == "MDA text"


def test_research_context_includes_deep_pdf_index(tmp_path):
    (tmp_path / "inputs.json").write_text(
        json.dumps({"code": "600887.SH", "as_of": "2026-10-16"}),
        encoding="utf-8",
    )
    index = build_index(
        [
            (1, "重要提示\n本报告..." ),
            (2, "第三节 管理层讨论与分析\n营业收入同比增长。"),
            (3, "第四节 公司治理\n董事会运作。"),
        ],
        document_hash="abc123",
        source_name="annual.pdf",
    )
    write_index(index, tmp_path / "pdf_index.json")
    context = _research_context(str(tmp_path), pdf_max_chars=2000)
    deep = context["pdf_deep"]
    assert deep["document"]["sha256"] == "abc123"
    assert deep["stats"]["pages_selected"] >= 1
    citations = {page["citation"] for page in deep["pages"]}
    assert "pdf://abc123/p2" in citations
    assert set(deep["citations"]) == citations
    assert "pdf_sections" not in context


def test_research_context_rejects_missing_explicit_index(tmp_path):
    (tmp_path / "inputs.json").write_text(
        json.dumps({"code": "600887.SH", "as_of": "2026-10-16"}),
        encoding="utf-8",
    )
    with pytest.raises(FileNotFoundError, match="PDF 索引不存在"):
        _research_context(
            str(tmp_path),
            pdf_index=str(tmp_path / "missing.pdf_index.json"),
        )


def test_validate_evidence_accepts_pdf_page_address():
    validate_evidence(
        [
            {
                "id": "pdf:1",
                "source_type": "pdf",
                "url": "pdf://abc123/p2",
                "page": 2,
                "quote": "营业收入同比增长。",
            }
        ]
    )
    with pytest.raises(ValueError, match="invalid url"):
        validate_evidence(
            [
                {
                    "id": "pdf:2",
                    "source_type": "pdf",
                    "url": "abc123/p2",
                    "quote": "x",
                }
            ]
        )
