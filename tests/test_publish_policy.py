"""ADR-04: partial publishing must be opt-in.

The old default (``publish_partial = True``) shipped a site with missing names
whenever a single stock failed.  The decision recorded in
``docs/roadmap-2026-11.md`` (ADR-04) flips the default: a failed stock blocks
publishing unless ``--publish-partial`` (or ``publish_partial = true``) is set
explicitly.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

from turtlefw.daily import CommandResult, DailyConfig, DailyPaths, run_daily

ROOT = Path(__file__).resolve().parents[1]


def _paths(tmp_path: Path) -> DailyPaths:
    return DailyPaths(
        day=date(2026, 11, 10),
        runs_root=tmp_path / "runs",
        site_root=tmp_path / "site",
        pdf_root=tmp_path / "pdfs",
    )


def _write_success(code_dir: Path) -> None:
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "qa.json").write_text(
        '{"status":"pass","rows":[{"name":"report","status":"PASS"}]}',
        encoding="utf-8",
    )
    snapshot = code_dir / "snapshot"
    snapshot.mkdir(exist_ok=True)
    (snapshot / "manifest.json").write_text(
        '{"snapshot_id":"abc123","numeric_coverage":"1.0"}', encoding="utf-8"
    )
    (code_dir / "analysis_report.html").write_text("<html>ok</html>", encoding="utf-8")


def test_publish_partial_defaults_to_false() -> None:
    assert DailyConfig().publish_partial is False


def _run_with_one_failure(
    tmp_path: Path, *, partial: bool, monkeypatch
) -> tuple[dict, list[Path]]:
    paths = _paths(tmp_path)
    built: list[Path] = []
    release = paths.site_root / "releases" / "test"

    def fake_build_site(day_dir: Path, site_root: Path) -> Path:
        built.append(day_dir)
        release.mkdir(parents=True, exist_ok=True)
        return release

    monkeypatch.setattr("turtlefw.site.build_site", fake_build_site)
    monkeypatch.setattr("turtlefw.site.publish_site", lambda release_path, site_root: None)

    def fake_run(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        code = command[command.index("run") + 1]
        if code == "000858.SZ":
            return CommandResult(tuple(command), 1, "boom")
        _write_success(paths.day_dir / code)
        return CommandResult(tuple(command), 0, "ok")

    result = run_daily(
        paths,
        DailyConfig(top_n=2, llm_top_n=0, publish_partial=partial),
        codes=["600887.SH", "000858.SZ"],
        skip_screen=True,
        publish=True,
        run_command=fake_run,
        sleep=lambda seconds: None,
    )
    return result, built


def test_run_daily_blocks_publish_when_a_stock_fails(
    tmp_path: Path, monkeypatch
) -> None:
    result, built = _run_with_one_failure(tmp_path, partial=False, monkeypatch=monkeypatch)
    assert built == []
    assert str(result.get("site") or "").startswith("blocked: 1 failed")
    status = json.loads(
        (_paths(tmp_path).status_path).read_text(encoding="utf-8")
    )
    assert str(status.get("site") or "").startswith("blocked: 1 failed")


def test_run_daily_publishes_when_partial_explicitly_allowed(
    tmp_path: Path, monkeypatch
) -> None:
    result, built = _run_with_one_failure(tmp_path, partial=True, monkeypatch=monkeypatch)
    assert len(built) == 1
    assert str(result.get("site") or "").startswith("partial:")


def test_pipeline_exposes_publish_partial_override() -> None:
    spec = importlib.util.spec_from_file_location(
        "daily_pipeline_publish", ROOT / "scripts" / "daily_pipeline.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parser = module.build_parser()
    default_args = parser.parse_args([])
    assert default_args.publish_partial is None
    opted_in = parser.parse_args(["--publish-partial"])
    assert opted_in.publish_partial is True
