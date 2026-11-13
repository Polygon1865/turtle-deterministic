"""ADR-08: version-mismatched snapshots are read-only archives, not migrations.

The check must say why re-rendering is refused (版本标签 + 只读), instead of
raising a bare ``*_hash mismatch`` that looks like a data corruption bug.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from turtlefw.config import load_settings
from turtlefw.facts import FORMULA_VERSION, SNAPSHOT_VERSION
from turtlefw.report.manifest import build_manifest
from turtlefw.report.snapshot import ReportInputs, verify_manifest


def _inputs() -> ReportInputs:
    return ReportInputs(
        code="600887.SH",
        currency="CNY",
        as_of="20261021",
        rows=[],
        dividends=[],
        quote=None,
        history=[],
        market_cap="100000",
        shares="1000",
        price="10",
        rf_pct="1.8",
        rf_source="default",
    )


def _manifest(inputs: ReportInputs, root: Path):
    return build_manifest(inputs, load_settings(), root)


def test_current_version_renders_cleanly(tmp_path: Path) -> None:
    inputs = _inputs()
    manifest = _manifest(inputs, tmp_path)
    assert verify_manifest(inputs, load_settings(), "", manifest, tmp_path) == []


def test_old_snapshot_version_is_labelled_read_only(tmp_path: Path) -> None:
    inputs = _inputs()
    manifest = replace(_manifest(inputs, tmp_path), snapshot_version=SNAPSHOT_VERSION - 1)
    errors = verify_manifest(inputs, load_settings(), "", manifest, tmp_path)
    text = "\n".join(errors)
    assert "snapshot_version" in text
    assert "旧版本快照" in text and "只读" in text and "不自动迁移" in text


def test_old_formula_version_is_labelled_read_only(tmp_path: Path) -> None:
    inputs = _inputs()
    manifest = replace(_manifest(inputs, tmp_path), formula_version="2020-01-01")
    errors = verify_manifest(inputs, load_settings(), "", manifest, tmp_path)
    text = "\n".join(errors)
    assert "formula_version mismatch" in text
    assert f"current={FORMULA_VERSION}" in text
    assert "旧版本快照只读" in text and "重新生成快照" in text
