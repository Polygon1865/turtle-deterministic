"""Tests for scripts/golden.py — daily-run baseline (roadmap T1).

The module name is ``golden_baseline`` to avoid clashing with
``tests/test_golden.py``, which covers ``turtlefw.golden`` (qualitative labels).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("golden_script", ROOT / "scripts" / "golden.py")
assert SPEC and SPEC.loader
golden = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(golden)


def _write(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_day(tmp_path: Path, *, r: float = 6.29, verdict: str = "观察") -> Path:
    day = tmp_path / "2026-11-10"
    _write(
        day / "status.json",
        {
            "date": "2026-11-10",
            "trade_date": "20261110",
            "ok": True,
            "stocks": [
                {
                    "code": "00270.HK",
                    "name": "粤海投资",
                    "market": "HK",
                    "status": "ok",
                    "qa": "PASS",
                    "research": "on",
                    "numeric_coverage": "1.0",
                },
                {
                    "code": "601088.SH",
                    "name": "中国神华",
                    "market": "A",
                    "status": "failed",
                    "qa": "FAIL",
                    "research": "fallback",
                    "numeric_coverage": "0.9",
                    "error": "timeout",
                },
            ],
        },
    )
    _write(
        day / "00270.HK" / "analysis_report.md",
        "\n".join(
            [
                "# 粤海投资（00270.HK）",
                "",
                f"**{verdict}** — 估值或数据仍待确认",
                "",
                "## 一、结论",
            ]
        ),
    )
    _write(
        day / "00270.HK" / "snapshot" / "metrics.json",
        {"r": r, "gg": 10.32, "ii": 5.0, "margin": 5.32, "floor": 4.62, "premium": 71.03},
    )
    _write(
        day / "00270.HK" / "qa.json",
        {
            "code": "00270.HK",
            "status": "PASS",
            "rows": [
                {"name": "report", "status": "PASS", "detail": ""},
                {"name": "report_structure", "status": "PASS", "detail": ""},
            ],
        },
    )
    _write(
        day / "00270.HK" / "snapshot" / "research.json",
        {"claims": [{"claim_id": "D1.1"}, {"claim_id": "D2.1"}, {"claim_id": "D6.3"}]},
    )
    return day


def test_collect_summarises_run(tmp_path: Path) -> None:
    day = _make_day(tmp_path)
    payload = golden.collect(day)

    assert payload["date"] == "2026-11-10"
    assert payload["trade_date"] == "20261110"
    assert payload["counts"] == {"stocks": 2, "ok": 1, "qa_pass": 1, "research_on": 1}
    stock = payload["stocks"]["00270.HK"]
    assert stock["verdict"] == "观察"
    assert stock["reason"] == "估值或数据仍待确认"
    assert stock["claims"] == 3
    assert stock["metrics"]["r"] == 6.29
    assert stock["metrics"]["gg"] == 10.32
    assert stock["structure"] == "PASS"
    assert stock["qa_fail"] == []
    failed = payload["stocks"]["601088.SH"]
    assert failed["status"] == "failed"
    assert failed["verdict"] == ""
    assert failed["claims"] == 0


def test_freeze_and_check_roundtrip(tmp_path: Path) -> None:
    _make_day(tmp_path)
    out = tmp_path / "golden.json"
    assert golden.freeze("2026-11-10", runs_root=tmp_path, out=out) == 0
    assert out.is_file()

    assert (
        golden.check(
            "2026-11-10", runs_root=tmp_path, golden_path=out, tol=0.01, fail_on_diff=True
        )
        == 0
    )


def test_check_detects_metric_drift(tmp_path: Path) -> None:
    day = _make_day(tmp_path)
    out = tmp_path / "golden.json"
    golden.freeze("2026-11-10", runs_root=tmp_path, out=out)

    _write(day / "00270.HK" / "snapshot" / "metrics.json", {"r": 6.79, "gg": 10.32})

    assert (
        golden.check(
            "2026-11-10", runs_root=tmp_path, golden_path=out, tol=0.01, fail_on_diff=True
        )
        == 1
    )
    assert (
        golden.check(
            "2026-11-10", runs_root=tmp_path, golden_path=out, tol=0.01, fail_on_diff=False
        )
        == 0
    )

    saved = json.loads(out.read_text(encoding="utf-8"))
    changes = golden.compare(saved, golden.collect(day))
    assert ("00270.HK", "metrics.r", 6.29, 6.79) in changes


def test_check_detects_verdict_change(tmp_path: Path) -> None:
    day = _make_day(tmp_path)
    out = tmp_path / "golden.json"
    golden.freeze("2026-11-10", runs_root=tmp_path, out=out)

    _write(day / "00270.HK" / "analysis_report.md", "**排除** — 因子1A「看不懂」触发否决\n")

    saved = json.loads(out.read_text(encoding="utf-8"))
    changes = golden.compare(saved, golden.collect(day))
    assert ("00270.HK", "verdict", "观察", "排除") in changes


def test_check_requires_golden(tmp_path: Path) -> None:
    _make_day(tmp_path)
    assert (
        golden.check(
            "2026-11-10",
            runs_root=tmp_path,
            golden_path=tmp_path / "missing.json",
            tol=0.01,
            fail_on_diff=True,
        )
        == 2
    )


def test_freeze_requires_day_dir(tmp_path: Path) -> None:
    assert golden.freeze("2026-11-11", runs_root=tmp_path, out=tmp_path / "x.json") == 1


def test_compare_reports_added_and_removed(tmp_path: Path) -> None:
    day = _make_day(tmp_path)
    saved = golden.collect(day)
    saved["stocks"]["99999.HK"] = {"name": "旧票", "verdict": "买入"}
    changes = golden.compare(saved, golden.collect(day))
    assert ("99999.HK", "stock", "存在", "消失") in changes
