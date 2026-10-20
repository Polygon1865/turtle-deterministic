import json

from turtlefw.numeric_audit import audit


def test_numeric_audit_detects_untraceable(tmp_path):
    report = tmp_path / "report.md"
    source = tmp_path / "metrics.json"
    report.write_text("R 5.13%，价格 28.20", encoding="utf-8")
    source.write_text('{"r": "5.13", "price": "28.20"}', encoding="utf-8")
    result = audit(report, [source])
    assert result["coverage"] == 1.0
    assert result["status"] == "pass"

    report.write_text("R 5.13%，其他 9.99", encoding="utf-8")
    assert audit(report, [source])["status"] == "review"


def test_strict_mode_excludes_raw_inputs(tmp_path):
    report = tmp_path / "report.md"
    metrics = tmp_path / "metrics.json"
    inputs = tmp_path / "inputs.json"
    report.write_text("R 5.13，其他 9.99", encoding="utf-8")
    metrics.write_text('{"r": "5.13"}', encoding="utf-8")
    inputs.write_text('{"raw": "9.99"}', encoding="utf-8")
    assert audit(report, [metrics, inputs])["status"] == "pass"
    assert audit(report, [metrics, inputs], strict=True)["status"] == "review"


def test_research_structural_counts_are_traceable(tmp_path):
    report = tmp_path / "report.md"
    research = tmp_path / "research.json"
    research.write_text(
        json.dumps(
            {
                "claims": [{"claim_id": "c"}] * 11,
                "params": [{"param_id": "p"}] * 4,
                "decisions": [],
                "evidence": [{"id": "e"}] * 17,
            }
        ),
        encoding="utf-8",
    )
    report.write_text(
        "claims：11\nparams：4\ndecisions：0\nevidence：17\n", encoding="utf-8"
    )
    assert audit(report, [research], strict=True)["status"] == "pass"

    report.write_text("evidence：17，其他 99\n", encoding="utf-8")
    assert audit(report, [research], strict=True)["status"] == "review"