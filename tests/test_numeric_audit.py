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
