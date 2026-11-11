"""Tests for the sell discipline / holdings layer (C6)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from turtlefw.holdings import (
    SELL,
    WATCH,
    Holding,
    Snapshot,
    check,
    evaluate,
    load_holdings,
    render,
    snapshot_from_run,
)


def _write_day(root: Path, code: str, *, verdict: str, margin: str, price: str, floor: str, traps: int = 0) -> Path:
    code_dir = root / code / "snapshot"
    code_dir.mkdir(parents=True)
    metrics = {
        "margin": {"value": margin},
        "price": {"value": price},
        "floor": {"value": floor},
    }
    (code_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    (code_dir / "verdict.json").write_text(
        json.dumps({"verdict": verdict, "evidence_hash": "abc123"}), encoding="utf-8"
    )
    (root / code / "analysis_report.md").write_text(
        f"# 报告\n\n**{verdict}** — 理由\n\n| 价值陷阱 | {traps} 项 |\n", encoding="utf-8"
    )
    return root


def test_load_holdings_defaults_and_validation(tmp_path: Path) -> None:
    path = tmp_path / "holdings.json"
    path.write_text(
        json.dumps({"holdings": [{"code": "00270.hk", "entry_date": "2026-11-02"}]}),
        encoding="utf-8",
    )
    holdings = load_holdings(path)
    assert holdings[0].code == "00270.HK"
    assert holdings[0].entry_verdict == "买入"
    assert holdings[0].stop_loss == Decimal("0.25")
    with pytest.raises(ValueError):
        load_holdings(tmp_path / "missing.json")
    path.write_text(json.dumps({"holdings": [{"entry_date": "x"}]}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_holdings(path)
    path.write_text(
        json.dumps({"holdings": [{"code": "X", "stop_loss": 1.5}]}), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_holdings(path)


def test_snapshot_from_run_reads_published_artifacts(tmp_path: Path) -> None:
    day = _write_day(
        tmp_path / "2026-11-10", "00270.HK", verdict="排除", margin="-1.25", price="8.3", floor="4.62", traps=2
    )
    snap = snapshot_from_run(day, "00270.HK")
    assert snap is not None
    assert snap.verdict == "排除"
    assert snap.margin == Decimal("-1.25")
    assert snap.price == Decimal("8.3")
    assert snap.floor == Decimal("4.62")
    assert snap.traps == 2
    assert snap.evidence_hash == "abc123"
    assert snapshot_from_run(day, "99999.HK") is None


def test_healthy_position_has_no_signals() -> None:
    holding = Holding(code="00270.HK", entry_date="2026-11-02", entry_price=Decimal("8.03"))
    snap = Snapshot(date="2026-11-10", verdict="买入", margin=Decimal("4.84"), price=Decimal("8.3"), floor=Decimal("4.62"))
    assert evaluate(holding, snap) == ()


def test_verdict_downgrade_and_margin_loss_are_sells() -> None:
    holding = Holding(code="00270.HK", entry_date="2026-11-02")
    snap = Snapshot(date="2026-11-06", verdict="排除", margin=Decimal("-0.5"), price=Decimal("8.0"), floor=Decimal("4.6"))
    rules = {signal.rule for signal in evaluate(holding, snap)}
    assert rules == {"verdict_downgrade", "margin_lost"}
    assert all(signal.severity == SELL for signal in evaluate(holding, snap))


def test_value_trap_and_stop_loss_and_floor_break() -> None:
    holding = Holding(
        code="00270.HK",
        entry_date="2026-11-02",
        entry_price=Decimal("10"),
        entry_verdict="观察",
        stop_loss=Decimal("0.25"),
    )
    snap = Snapshot(date="2026-11-10", verdict="观察", margin=Decimal("1"), price=Decimal("7"), floor=Decimal("7.5"), traps=2)
    signals = {signal.rule: signal for signal in evaluate(holding, snap)}
    assert set(signals) == {"value_trap", "stop_loss", "floor_break"}
    assert signals["stop_loss"].severity == SELL
    assert signals["floor_break"].severity == WATCH


def test_check_skips_missing_day_and_render_lists_signals(tmp_path: Path) -> None:
    day = _write_day(tmp_path / "2026-11-06", "00270.HK", verdict="排除", margin="-0.5", price="8", floor="4.6")
    holdings = [
        Holding(code="00270.HK", entry_date="2026-11-02"),
        Holding(code="03877.HK", entry_date="2026-11-02"),
    ]
    results = check(holdings, day)
    assert results[0][1] is not None
    assert results[1][1] is None
    text = render(results)
    assert "00270.HK" in text and "结论降级" in text and "当日无报告" in text
    assert text.endswith("合计：2 条卖出信号")


def test_window_drops_single_day_soft_signal(tmp_path: Path) -> None:
    from turtlefw.holdings import check_window

    _write_day(tmp_path / "2026-11-09", "00270.HK", verdict="买入", margin="4", price="8", floor="4.6")
    _write_day(tmp_path / "2026-11-10", "00270.HK", verdict="排除", margin="4", price="8", floor="4.6")
    holding = Holding(code="00270.HK", entry_date="2026-11-02")
    days = [tmp_path / "2026-11-09", tmp_path / "2026-11-10"]
    assert check_window([holding], days, confirm=2)[0][2] == ()
    assert [s.rule for s in check_window([holding], days, confirm=1)[0][2]] == ["verdict_downgrade"]


def test_window_keeps_soft_signal_when_it_persists(tmp_path: Path) -> None:
    from turtlefw.holdings import check_window

    _write_day(tmp_path / "2026-11-10", "00270.HK", verdict="排除", margin="4", price="8", floor="4.6")
    _write_day(tmp_path / "2026-11-11", "00270.HK", verdict="观察", margin="4", price="8", floor="4.6")
    holding = Holding(code="00270.HK", entry_date="2026-11-02")
    days = [tmp_path / "2026-11-10", tmp_path / "2026-11-11"]
    assert [s.rule for s in check_window([holding], days, confirm=2)[0][2]] == ["verdict_downgrade"]


def test_window_keeps_hard_rule_immediate(tmp_path: Path) -> None:
    from turtlefw.holdings import check_window

    _write_day(tmp_path / "2026-11-09", "00270.HK", verdict="买入", margin="4", price="8", floor="4.6")
    _write_day(tmp_path / "2026-11-10", "00270.HK", verdict="买入", margin="-1", price="8", floor="4.6")
    holding = Holding(code="00270.HK", entry_date="2026-11-02")
    days = [tmp_path / "2026-11-09", tmp_path / "2026-11-10"]
    assert [s.rule for s in check_window([holding], days, confirm=2)[0][2]] == ["margin_lost"]
