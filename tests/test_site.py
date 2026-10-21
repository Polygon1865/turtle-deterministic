from __future__ import annotations

from pathlib import Path

import pytest

from turtlefw.site import build_site, collect_reports, qa_status


def _make_code(day_dir: Path, code: str, *, qa: str, name: str = "") -> None:
    code_dir = day_dir / code
    code_dir.mkdir(parents=True)
    (code_dir / "qa.json").write_text(
        f'{{"status":"{qa}","rows":[]}}', encoding="utf-8"
    )
    snapshot = code_dir / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(
        f'{{"snapshot_id":"snap-{code}","numeric_coverage":"1.0"}}',
        encoding="utf-8",
    )
    (code_dir / "analysis_report.html").write_text(
        f"<html>{name or code}</html>", encoding="utf-8"
    )


def test_qa_status_uses_top_level_status() -> None:
    assert qa_status(Path("missing.json")) == "UNKNOWN"


def test_collect_reports_scans_code_directories(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-21"
    _make_code(day_dir, "600887.SH", qa="pass", name="伊利")
    _make_code(day_dir, "000858.SZ", qa="fail")
    reports = collect_reports(day_dir)
    assert [report.code for report in reports] == ["000858.SZ", "600887.SH"]
    assert reports[1].qa == "PASS"
    assert reports[1].numeric_coverage == "1.0"


def test_build_site_copies_reports_and_writes_health(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-21"
    _make_code(day_dir, "600887.SH", qa="pass", name="伊利")
    (day_dir / "status.json").write_text(
        '{"stocks":[{"code":"600887.SH","name":"伊利","rank":1,"status":"ok",'
        '"qa":"PASS","research":"off","numeric_coverage":"1.0"}]}',
        encoding="utf-8",
    )
    release = build_site(day_dir, tmp_path / "site")
    assert (release / "index.html").is_file()
    assert (release / "600887.SH.html").read_text(encoding="utf-8") == "<html>伊利</html>"
    health = (release / "health.txt").read_text(encoding="utf-8")
    assert "status=ok" in health
    assert "qa_pass=1" in health
    index = (release / "index.html").read_text(encoding="utf-8")
    assert "600887.SH" in index
    assert "伊利" in index


def test_build_site_rejects_empty_day(tmp_path: Path) -> None:
    day_dir = tmp_path / "empty"
    day_dir.mkdir()
    with pytest.raises(ValueError, match="no reports"):
        build_site(day_dir, tmp_path / "site")
