from __future__ import annotations

import json
from pathlib import Path

from turtlefw.live_smoke import (
    _default_runner,
    format_report,
    run_case,
    run_suite,
    to_payload,
)


def _artifacts(
    root: Path,
    code: str,
    *,
    qa_status: str = "pass",
    numeric_status: str = "pass",
    coverage: str = "1.0",
) -> None:
    base = root / code
    (base / "snapshot").mkdir(parents=True)
    (base / "qa.json").write_text(
        json.dumps(
            {
                "status": qa_status,
                "rows": [
                    {"name": "numeric_coverage", "status": "PASS"},
                    {"name": "data_coverage", "status": "PASS"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (base / "snapshot" / "manifest.json").write_text(
        json.dumps(
            {
                "code": code,
                "snapshot_id": "a" * 32,
                "numeric_status": numeric_status,
                "numeric_coverage": coverage,
            }
        ),
        encoding="utf-8",
    )
    (base / "analysis_report.md").write_text("report", encoding="utf-8")
    (base / "data_pack.md").write_text("pack", encoding="utf-8")


def test_live_smoke_passes_artifacts(tmp_path: Path):
    _artifacts(tmp_path, "600887.SH")
    calls: list[tuple[str, Path]] = []

    def runner(code: str, root: Path) -> int:
        calls.append((code, root))
        return 0

    result = run_case("600887.SH", tmp_path, runner=runner)
    assert result.ok is True
    assert result.detail == "ok"
    assert result.snapshot_id == "a" * 32
    assert result.numeric_coverage == 1.0
    assert calls == [("600887.SH", tmp_path)]


def test_live_smoke_reports_qa_failure(tmp_path: Path):
    _artifacts(tmp_path, "600887.SH", qa_status="fail")
    result = run_case("600887.SH", tmp_path, run=False)
    assert result.ok is False
    assert "qa status=fail" in result.detail


def test_live_smoke_reports_missing_manifest(tmp_path: Path):
    base = tmp_path / "600887.SH"
    base.mkdir()
    (base / "qa.json").write_text('{"status": "pass", "rows": []}', encoding="utf-8")
    (base / "analysis_report.md").write_text("report", encoding="utf-8")
    (base / "data_pack.md").write_text("pack", encoding="utf-8")
    result = run_case("600887.SH", tmp_path, run=False)
    assert result.ok is False
    assert "snapshot/manifest.json missing" in result.detail


def test_live_smoke_suite_and_payload(tmp_path: Path):
    _artifacts(tmp_path, "600887.SH")
    _artifacts(tmp_path, "000858.SZ", coverage="0.5")
    results = run_suite(("600887.SH", "000858.SZ"), tmp_path, run=False)
    assert [result.ok for result in results] == [True, False]
    report = format_report(results)
    assert "live smoke: 1/2 passed" in report
    payload = to_payload(results)
    assert payload["passed"] == 1
    assert payload["total"] == 2


def test_live_smoke_runner_decodes_utf8(monkeypatch):
    captured: dict[str, object] = {}

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured.update(kwargs)
        return Completed()

    monkeypatch.setattr("turtlefw.live_smoke.subprocess.run", fake_run)
    assert _default_runner("600887.SH", Path(".")) == 0
    assert captured["encoding"] == "utf-8"
    assert captured["errors"] == "replace"
