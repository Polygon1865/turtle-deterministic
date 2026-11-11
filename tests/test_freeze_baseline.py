"""Tests for scripts/freeze_baseline.py — full-run baseline (roadmap W0.0)."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "freeze_baseline_script", ROOT / "scripts" / "freeze_baseline.py"
)
assert SPEC and SPEC.loader
freeze_baseline = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(freeze_baseline)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_day(tmp_path: Path, *, verdict: str = "观察", margin: str = "3.6100") -> Path:
    day = tmp_path / "2026-11-10"
    _write(
        day / "status.json",
        {
            "date": "2026-11-10",
            "trade_date": "20261110",
            "ok": True,
            "stocks": [
                {"code": "00506.HK", "name": "中国食品", "market": "HK", "qa": "PASS"},
                {"code": "00270.HK", "name": "粤海投资", "market": "HK", "qa": "PASS"},
            ],
        },
    )
    for code in ("00506.HK", "00270.HK"):
        _write(day / code / "analysis_report.md", f"# {code}\n\n**{verdict}** — 估值或数据仍待确认\n")
        _write(
            day / code / "snapshot" / "metrics.json",
            {
                "r": {"value": "3.16"},
                "gg": {"value": "8.61"},
                "ii": {"value": "5.00"},
                "margin": {"value": margin},
                "floor": {"value": "2.48"},
                "price": {"value": "3.70"},
            },
        )
        _write(day / code / "qa.json", {"code": code, "status": "pass", "rows": []})
        _write(
            day / code / "snapshot" / "research.json",
            {"evidence": [{"id": "ev-1"}], "claims": [{"claim_id": "D1.x"}], "params": [{}, {}]},
        )
    return day


def test_collect_reads_verdict_metrics_and_counts(tmp_path: Path) -> None:
    day = _make_day(tmp_path)
    payload = freeze_baseline.collect(day)
    assert payload["stocks"] == 2
    row = payload["rows"][0]
    assert row["code"] == "00506.HK"
    assert row["verdict"] == "观察"
    assert row["reason"] == "估值或数据仍待确认"
    assert row["margin"] == "3.6100"
    assert row["claims"] == 1 and row["params"] == 2
    assert row["report_sha256"] and payload["hashes"]["00506.HK"]["report"]


def test_freeze_writes_summary_hashes_and_artifacts(tmp_path: Path) -> None:
    _make_day(tmp_path)
    out = tmp_path / "baseline"
    artifacts = tmp_path / "artifacts"
    payload = freeze_baseline.freeze(
        "2026-11-10", runs_root=tmp_path, out=out, artifacts=artifacts
    )
    assert payload["stocks"] == 2
    summary = out / "summary-2026-11-10.csv"
    assert summary.is_file()
    with summary.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["code"] for row in rows] == ["00506.HK", "00270.HK"]
    assert (out / "hashes-2026-11-10.json").is_file()
    assert (out / "meta-2026-11-10.json").is_file()
    assert (artifacts / "2026-11-10" / "00506.HK" / "analysis_report.md").is_file()


def test_check_reports_no_diff_then_flags_changes(tmp_path: Path) -> None:
    day = _make_day(tmp_path)
    freeze_baseline.freeze(
        "2026-11-10", runs_root=tmp_path, out=tmp_path / "baseline", artifacts=None
    )
    assert freeze_baseline.check("2026-11-10", runs_root=tmp_path, out=tmp_path / "baseline") == []

    _write(day / "00506.HK" / "analysis_report.md", "# x\n\n**排除** — 估值未通过门槛\n")
    _write(
        day / "00506.HK" / "snapshot" / "metrics.json",
        {"margin": {"value": "-1.00"}},
    )
    diffs = freeze_baseline.check("2026-11-10", runs_root=tmp_path, out=tmp_path / "baseline")
    text = "\n".join(diffs)
    assert "verdict" in text and "排除" in text
    assert "margin" in text and "Δ -4.6100" in text


def test_check_flags_added_and_removed_codes(tmp_path: Path) -> None:
    day = _make_day(tmp_path)
    freeze_baseline.freeze(
        "2026-11-10", runs_root=tmp_path, out=tmp_path / "baseline", artifacts=None
    )
    status = json.loads((day / "status.json").read_text(encoding="utf-8"))
    status["stocks"] = [status["stocks"][0]]
    _write(day / "status.json", status)
    diffs = freeze_baseline.check("2026-11-10", runs_root=tmp_path, out=tmp_path / "baseline")
    assert any("00270.HK" in line and "消失" in line for line in diffs)


def test_invalid_date_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        freeze_baseline.freeze("2026-13", runs_root=tmp_path, out=tmp_path / "baseline")
