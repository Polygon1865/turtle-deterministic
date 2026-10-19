import json

from turtlefw import numeric_audit, qa
from turtlefw.facts import file_hash


def setup_run(tmp_path, with_all=True):
    base = tmp_path / "600887.SH"
    base.mkdir(exist_ok=True)
    (base / "run_state.json").write_text(
        json.dumps({"code": "600887.SH", "run_id": "x", "phase": "report"}),
        encoding="utf-8",
    )
    (base / "analysis_report.md").write_text("结论：买入 ｜ R 7.48%", encoding="utf-8")
    payload = {
        "modules": {
            "moat": {
                "judgment": "positive",
                "confidence": "high",
                "evidence": [
                    {"url": "https://x.test/a", "quote": "营收一百亿", "source_type": "web"}
                ],
                "notes": "",
            }
        },
        "discrepancies": [],
    }
    (base / "qualitative.json").write_text(json.dumps(payload), encoding="utf-8")
    (base / "metrics.json").write_text('{"r": "7.48"}', encoding="utf-8")
    audit = numeric_audit.audit(base / "analysis_report.md", [base / "metrics.json"])
    audit["sources"] = ["metrics.json"]
    (base / "numeric_audit.json").write_text(json.dumps(audit), encoding="utf-8")
    (base / "manifest.json").write_text(
        json.dumps(
            {
                "code": "600887.SH",
                "as_of": "2026-10-16",
                "currency": "CNY",
                "facts_hash": "0" * 64,
                "config_hash": "1" * 64,
                "numeric_coverage": str(audit["coverage"]),
                "numeric_status": str(audit["status"]),
                "numeric_unknown": audit["unknown"],
                "numeric_hash": file_hash(base / "numeric_audit.json"),
                "numeric_sources": ["metrics.json"],
            }
        ),
        encoding="utf-8",
    )
    if with_all:
        (base / "narrative.md").write_text("R 为 7.48%", encoding="utf-8")
    return base


def test_all_pass(tmp_path):
    setup_run(tmp_path)
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert qa.failed(rows) == []


def test_missing_report_fails(tmp_path):
    base = setup_run(tmp_path)
    (base / "analysis_report.md").unlink()
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "report" in qa.failed(rows)


def test_untraceable_narrative_fails(tmp_path):
    base = setup_run(tmp_path)
    (base / "narrative.md").write_text("R 为 9.99%", encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "narrative" in qa.failed(rows)


def test_all_unknown_fails(tmp_path):
    base = setup_run(tmp_path)
    payload = {
        "modules": {
            "moat": {
                "judgment": "unknown",
                "confidence": "low",
                "evidence": [],
                "notes": "",
            }
        }
    }
    (base / "qualitative.json").write_text(json.dumps(payload), encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "unknown_ratio" in qa.failed(rows)


def test_numeric_coverage_fails_below_one(tmp_path):
    base = setup_run(tmp_path)
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    manifest["numeric_coverage"] = "0.95"
    manifest["numeric_unknown"] = ["9.99"]
    (base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "numeric_coverage" in qa.failed(rows)


def test_numeric_audit_hash_tamper_fails(tmp_path):
    base = setup_run(tmp_path)
    (base / "numeric_audit.json").write_text(
        (base / "numeric_audit.json").read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "numeric_coverage" in qa.failed(rows)


def test_qa_json_artifact(tmp_path):
    base = setup_run(tmp_path)
    rows = qa.run_qa("600887.SH", root=tmp_path)
    target = qa.write_json("600887.SH", rows, root=tmp_path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert any(row["name"] == "numeric_coverage" for row in payload["rows"])
    assert target.parent == base


def test_research_provenance_tamper_fails(tmp_path):
    base = setup_run(tmp_path)
    research = base / "research.json"
    research.write_text('{"claims": []}', encoding="utf-8")
    provenance = {
        "provider": "dsh",
        "research_sha256": file_hash(research),
        "context_sha256": "",
    }
    (base / "research_provenance.json").write_text(
        json.dumps(provenance), encoding="utf-8"
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert ("research_provenance", "PASS",) in [(r[0], r[1]) for r in rows]
    research.write_text('{"claims": [], "tampered": true}', encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research_provenance" in qa.failed(rows)


def test_research_artifact_is_validated(tmp_path):
    base = setup_run(tmp_path)
    (base / "research.json").write_text(
        json.dumps(
            {
                "evidence": [
                    {"id": "ev1", "url": "https://example.com/a", "quote": "原文"}
                ],
                "claims": [
                    {
                        "claim_id": "D2.1",
                        "dimension": "D2",
                        "statement": "护城河 R={{metric:r}}",
                        "judgment": "positive",
                        "confidence": "high",
                        "evidence_ids": ["ev1"],
                    }
                ],
                "params": [
                    {
                        "param_id": "d2.rating",
                        "label": "护城河评级",
                        "value": "neutral",
                        "dimension": "D2",
                        "evidence_ids": ["ev1"],
                    }
                ],
                "decisions": [
                    {
                        "decision_id": "g",
                        "metric_id": "g",
                        "selected": "1.15",
                        "candidates": ["0.85", "1.15", "1.50"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research" not in qa.failed(rows)
    assert any(name == "research" and status == "PASS" for name, status, _ in rows)
