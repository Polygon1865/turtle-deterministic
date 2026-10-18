import json

from turtlefw import qa


def setup_run(tmp_path, with_all=True):
    base = tmp_path / "600887.SH"
    base.mkdir()
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
