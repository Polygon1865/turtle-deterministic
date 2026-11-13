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


def test_calendar_dates_are_provenance_not_metrics(tmp_path):
    report = tmp_path / "report.md"
    source = tmp_path / "metrics.json"
    source.write_text('{"r": "5.13"}', encoding="utf-8")

    report.write_text("数据截至：2026-10-28\nR 5.13\n", encoding="utf-8")
    assert audit(report, [source], strict=True)["status"] == "pass"

    report.write_text("数据截至：20261028\nR 5.13\n", encoding="utf-8")
    assert audit(report, [source], strict=True)["status"] == "pass"


def test_source_class_attribution(tmp_path):
    report = tmp_path / "report.md"
    metrics = tmp_path / "metrics.json"
    inputs = tmp_path / "inputs.json"
    report.write_text("R 5.13，营收 43,225.36，9.99", encoding="utf-8")
    metrics.write_text('{"r": "5.13"}', encoding="utf-8")
    inputs.write_text('{"revenue": "43225.36"}', encoding="utf-8")

    result = audit(report, [metrics, inputs], strict=False)
    assert result["by_class"]["metric"] == 1
    assert result["by_class"]["financial"] == 1
    assert result["multi_class"] == 0
    assert result["unattributed"] == 1

    strict_result = audit(report, [metrics, inputs], strict=True)
    assert "financial" not in strict_result["by_class"]


def test_multi_class_when_number_appears_in_two_sources(tmp_path):
    report = tmp_path / "report.md"
    metrics = tmp_path / "metrics.json"
    research = tmp_path / "research.json"
    report.write_text("R 5.13\n", encoding="utf-8")
    metrics.write_text('{"r": "5.13"}', encoding="utf-8")
    research.write_text(
        json.dumps({"claims": [{"statement": "R 5.13"}], "params": [], "decisions": []}),
        encoding="utf-8",
    )

    result = audit(report, [metrics, research], strict=True)
    assert result["multi_class"] == 1
    assert result["by_class"]["metric"] == 1, "priority class is metric"


def test_pack_only_numbers_are_reported_separately(tmp_path):
    report = tmp_path / "report.md"
    metrics = tmp_path / "metrics.json"
    pack = tmp_path / "data_pack.md"
    report.write_text("R 5.13，额外 77.77\n", encoding="utf-8")
    metrics.write_text('{"r": "5.13"}', encoding="utf-8")
    pack.write_text("77.77\n", encoding="utf-8")

    result = audit(report, [metrics, pack], strict=True)
    assert result["by_class"]["metric"] == 1
    assert result["pack_only"] == 1
    assert result["status"] == "pass"