"""T2 — QA row that keeps ranking payout and report payout identical (HK)."""

from __future__ import annotations

import json
from pathlib import Path

from turtlefw.qa import _payout_consistency


def _day(tmp_path: Path, *, rank_payout: str = "66.97", metric: str = "66.97", code: str = "00270.HK") -> Path:
    base = tmp_path / code
    (base / "snapshot").mkdir(parents=True)
    (base / "snapshot" / "metrics.json").write_text(
        json.dumps({"payout.latest": {"value": metric}}), encoding="utf-8"
    )
    (tmp_path / "ranking_hk.csv").write_text(
        "rank,code,name,payout,margin\n"
        f"1,{code},粤海投资,{rank_payout},\n",
        encoding="utf-8",
    )
    return base


def test_payout_matches(tmp_path: Path) -> None:
    base = _day(tmp_path)
    ok, detail = _payout_consistency(base, "00270.HK")
    assert ok is True
    assert "66.97" in detail


def test_payout_mismatch_fails(tmp_path: Path) -> None:
    base = _day(tmp_path, rank_payout="100.00", metric="1.41")
    ok, detail = _payout_consistency(base, "00270.HK")
    assert ok is False
    assert "100.00" in detail and "1.41" in detail


def test_non_hk_is_skipped(tmp_path: Path) -> None:
    base = _day(tmp_path, code="600887.SH")
    ok, detail = _payout_consistency(base, "600887.SH")
    assert ok is True
    assert "跳过" in detail


def test_missing_ranking_is_not_a_failure(tmp_path: Path) -> None:
    base = _day(tmp_path)
    (tmp_path / "ranking_hk.csv").unlink()
    ok, detail = _payout_consistency(base, "00270.HK")
    assert ok is True
    assert "无榜单" in detail


def test_missing_metric_is_not_a_failure(tmp_path: Path) -> None:
    base = tmp_path / "00270.HK"
    (base / "snapshot").mkdir(parents=True)
    (base / "snapshot" / "metrics.json").write_text("{}", encoding="utf-8")
    (tmp_path / "ranking_hk.csv").write_text(
        "code,payout\n00270.HK,66.97\n", encoding="utf-8"
    )
    ok, detail = _payout_consistency(base, "00270.HK")
    assert ok is True
    assert "无最新年支付率" in detail
