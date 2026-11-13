"""W5.3 report consistency: the rendered report must match its frozen metrics."""

from __future__ import annotations

import json
from pathlib import Path

from turtlefw.qa import _report_consistency_check

ROWS = """| 粗算回报率 R | 6.00% |
| 精算回报率 GG | 9.84% |
| 门槛 II | 5.00% |
| 安全边际 | 4.84% |
| 底价（综合） | 4.62 |
| 结论 | 买入 |
"""

METRICS = {
    "r": {"display": "6.00%"},
    "gg": {"display": "9.84%"},
    "ii": {"display": "5.00%"},
    "margin": {"display": "4.84%"},
    "floor": {"display": "4.62"},
}


def _base(
    tmp_path: Path,
    *,
    rows: str = ROWS,
    metrics: dict | None = None,
    verdict_line: str = "买入",
    verdict_record: str | None = "买入",
) -> Path:
    base = tmp_path / "600887.SH"
    (base / "snapshot").mkdir(parents=True)
    (base / "snapshot" / "metrics.json").write_text(
        json.dumps(metrics if metrics is not None else METRICS), encoding="utf-8"
    )
    (base / "analysis_report.md").write_text(
        f"# 600887.SH\n\n**{verdict_line}** — test\n\n{rows}\n", encoding="utf-8"
    )
    if verdict_record is not None:
        (base / "snapshot" / "verdict.json").write_text(
            json.dumps({"verdict": verdict_record, "evidence_hash": "abc123"}),
            encoding="utf-8",
        )
    return base


def _check(base: Path) -> tuple[bool, str]:
    return _report_consistency_check(base, base / "analysis_report.md")


def test_consistent_report_passes(tmp_path: Path) -> None:
    ok, detail = _check(_base(tmp_path))
    assert ok is True
    assert "项数字/结论一致" in detail


def test_number_mismatch_fails(tmp_path: Path) -> None:
    base = _base(tmp_path, rows=ROWS.replace("| 粗算回报率 R | 6.00% |", "| 粗算回报率 R | 6.01% |"))
    ok, detail = _check(base)
    assert ok is False
    assert "粗算回报率 R" in detail and "6.01%" in detail


def test_summary_verdict_mismatch_fails(tmp_path: Path) -> None:
    base = _base(tmp_path, rows=ROWS.replace("| 结论 | 买入 |", "| 结论 | 观察 |"))
    ok, detail = _check(base)
    assert ok is False
    assert "汇总表" in detail


def test_verdict_record_mismatch_fails(tmp_path: Path) -> None:
    base = _base(tmp_path, verdict_record="观察")
    ok, detail = _check(base)
    assert ok is False
    assert "verdict.json" in detail


def test_missing_metrics_skips_check(tmp_path: Path) -> None:
    base = _base(tmp_path)
    (base / "snapshot" / "metrics.json").unlink()
    ok, detail = _check(base)
    assert ok is True
    assert "跳过一致性检查" in detail
