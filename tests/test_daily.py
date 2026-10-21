from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from turtlefw.daily import (
    CommandResult,
    DailyConfig,
    DailyError,
    DailyPaths,
    build_screen_command,
    daily_lock,
    extract_trade_date,
    load_config,
    parse_ranking,
    run_daily,
    run_stock,
)


def _paths(tmp_path: Path) -> DailyPaths:
    return DailyPaths(
        day=date(2026, 10, 21),
        runs_root=tmp_path / "runs",
        site_root=tmp_path / "site",
        pdf_root=tmp_path / "pdfs",
    )


def test_default_config_screens_100_and_reports_20():
    config = DailyConfig()
    assert (config.fast_limit, config.deep_limit, config.top_n, config.llm_top_n) == (
        100,
        30,
        20,
        0,
    )


def _write_success(code_dir: Path, *, research: bool = False) -> None:
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
    if research:
        (snapshot / "research.json").write_text("{}", encoding="utf-8")


def test_parse_ranking_deduplicates_and_limits(tmp_path: Path) -> None:
    path = tmp_path / "ranking_deep.csv"
    path.write_text(
        "ts_code,name\n600887.SH,伊利\n600887.SH,duplicate\n000858.SZ,五粮液\n",
        encoding="utf-8",
    )
    rows = parse_ranking(path, limit=2)
    assert rows == [
        {"code": "600887.SH", "name": "伊利", "rank": "1"},
        {"code": "000858.SZ", "name": "五粮液", "rank": "2"},
    ]


def test_parse_ranking_skips_failed_verdict(tmp_path: Path) -> None:
    path = tmp_path / "ranking_deep.csv"
    path.write_text(
        "ts_code,name,verdict\n"
        "600887.SH,伊利,分析失败:InvalidOperation\n"
        "000858.SZ,五粮液,买入\n"
        "600519.SH,贵州茅台,\n",
        encoding="utf-8",
    )
    rows = parse_ranking(path, limit=5)
    assert rows == [{"code": "000858.SZ", "name": "五粮液", "rank": "1"}]


def test_parse_ranking_rejects_unsafe_code(tmp_path: Path) -> None:
    path = tmp_path / "ranking.csv"
    path.write_text("ts_code\n../evil\n", encoding="utf-8")
    with pytest.raises(DailyError, match="invalid stock code"):
        parse_ranking(path, limit=1)


def test_extract_trade_date() -> None:
    assert extract_trade_date("交易日: 20261021\n") == "20261021"
    assert extract_trade_date("交易日：20261020\n") == "20261020"
    assert extract_trade_date("no date") is None


def test_screen_command_contains_global_refresh(tmp_path: Path) -> None:
    command = build_screen_command(
        _paths(tmp_path),
        DailyConfig(fast_limit=80, deep_limit=30, workers=2, refresh_market=True),
    )
    assert command[3] == "--output-dir"
    assert "--refresh-market" in command
    assert command[-4:] == ["--workers", "2", "--api-interval", "0.35"]
    assert "--fast-limit" in command


def test_screen_retries_until_expected_trade_date(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.day_dir.mkdir(parents=True)
    calls: list[int] = []

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        calls.append(1)
        if len(calls) == 2:
            (paths.day_dir / "ranking_deep.csv").write_text(
                "ts_code,name\n600887.SH,伊利\n", encoding="utf-8"
            )
            return CommandResult(tuple(command), 0, "交易日: 20261021\n")
        return CommandResult(tuple(command), 0, "交易日: 20261020\n")

    from turtlefw.daily import _screen

    ok, trade_date, rows = _screen(
        paths,
        DailyConfig(screen_attempts=2, retry_seconds=0),
        run_command=fake,
        sleep=lambda seconds: None,
    )
    assert ok is True
    assert trade_date == "20261021"
    assert rows[0]["code"] == "600887.SH"
    assert len(calls) == 2


def test_run_stock_deterministic_writes_status(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    commands: list[list[str]] = []

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        commands.append(list(command))
        _write_success(paths.day_dir / "600887.SH")
        return CommandResult(tuple(command), 0, "ok")

    record = run_stock(
        "600887.SH",
        2,
        paths,
        DailyConfig(llm_top_n=1),
        run_command=fake,
    )
    assert record["status"] == "ok"
    assert record["research"] == "off"
    assert record["numeric_coverage"] == "1.0"
    assert "--with-research" not in commands[0]


def test_run_stock_falls_back_when_research_fails(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    commands: list[list[str]] = []
    code_dir = paths.day_dir / "600887.SH"

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        commands.append(list(command))
        if len(commands) == 1:
            code_dir.mkdir(parents=True, exist_ok=True)
            (code_dir / "research.json").write_text("{}", encoding="utf-8")
            (code_dir / "research_provenance.json").write_text("{}", encoding="utf-8")
            (code_dir / "snapshot").mkdir(parents=True, exist_ok=True)
            (code_dir / "snapshot" / "research.json").write_text(
                "{}", encoding="utf-8"
            )
            return CommandResult(tuple(command), 3, "", "LLM unavailable")
        _write_success(code_dir, research=False)
        return CommandResult(tuple(command), 0, "ok")

    record = run_stock(
        "600887.SH",
        1,
        paths,
        DailyConfig(llm_top_n=1),
        run_command=fake,
    )
    assert record["status"] == "ok"
    assert record["research"] == "fallback"
    assert record["research_error"] == "LLM unavailable"
    assert not (code_dir / "research.json").exists()
    assert not (code_dir / "research_provenance.json").exists()
    assert not (code_dir / "snapshot" / "research.json").exists()
    assert len(commands) == 2
    assert "--with-research" in commands[0]
    assert "--research-retries" in commands[0]
    assert "--with-research" not in commands[1]


def test_run_daily_without_screen(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        code = command[command.index("run") + 1]
        _write_success(paths.day_dir / code)
        return CommandResult(tuple(command), 0, "ok")

    result = run_daily(
        paths,
        DailyConfig(top_n=2, llm_top_n=0),
        codes=["600887.SH", "000858.SZ"],
        skip_screen=True,
        publish=False,
        run_command=fake,
        sleep=lambda seconds: None,
    )
    assert result["ok"] is True
    assert len(result["stocks"]) == 2
    assert paths.status_path.is_file()
    assert not paths.lock_path.exists()


def test_daily_lock_rejects_overlapping_run(tmp_path: Path) -> None:
    path = tmp_path / "day" / ".daily.lock"
    with daily_lock(path), pytest.raises(DailyError, match="another daily run"), daily_lock(path):
        pass
    assert not path.exists()


def test_run_stock_pdf_failure_is_non_blocking(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    pdf_dir = paths.pdf_root / "600887.SH"
    pdf_dir.mkdir(parents=True)
    (pdf_dir / "2025.pdf").write_bytes(b"%PDF-1.4")

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        if "pdf-index" in command:
            return CommandResult(tuple(command), 1, "", "bad pdf")
        _write_success(paths.day_dir / "600887.SH")
        return CommandResult(tuple(command), 0, "ok")

    record = run_stock(
        "600887.SH", 2, paths, DailyConfig(llm_top_n=1), run_command=fake
    )
    assert record["status"] == "ok"
    assert record["pdf"] == "error"
    assert "bad pdf" in record["pdf_error"]
    assert record["error"] == ""


def test_daily_lock_reclaims_stale_lock(tmp_path: Path) -> None:
    path = tmp_path / "day" / ".daily.lock"
    path.parent.mkdir(parents=True)
    path.write_text("old", encoding="utf-8")
    old = 1_600_000_000
    path.touch()
    os.utime(path, (old, old))
    with daily_lock(path, stale_after_seconds=1):
        assert path.exists()
    assert not path.exists()


def test_run_daily_does_not_publish_partial_failure(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        code = command[command.index("run") + 1]
        if code == "600887.SH":
            _write_success(paths.day_dir / code)
            return CommandResult(tuple(command), 0, "ok")
        code_dir = paths.day_dir / code
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / "qa.json").write_text('{"status":"fail"}', encoding="utf-8")
        return CommandResult(tuple(command), 1, "", "boom")

    result = run_daily(
        paths,
        DailyConfig(top_n=2, llm_top_n=0, publish_partial=False),
        codes=["600887.SH", "000858.SZ"],
        skip_screen=True,
        publish=True,
        run_command=fake,
        sleep=lambda seconds: None,
    )
    assert result["ok"] is False
    assert result["site"].startswith("skipped: failed stocks")
    assert not (paths.site_root / "current").exists()


def test_run_daily_publishes_partial_when_configured(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        code = command[command.index("run") + 1]
        if code == "600887.SH":
            _write_success(paths.day_dir / code)
            return CommandResult(tuple(command), 0, "ok")
        code_dir = paths.day_dir / code
        code_dir.mkdir(parents=True, exist_ok=True)
        (code_dir / "qa.json").write_text('{"status":"fail"}', encoding="utf-8")
        return CommandResult(tuple(command), 1, "", "boom")

    result = run_daily(
        paths,
        DailyConfig(top_n=2, llm_top_n=0, publish_partial=True),
        codes=["600887.SH", "000858.SZ"],
        skip_screen=True,
        publish=True,
        run_command=fake,
        sleep=lambda seconds: None,
    )
    assert result["ok"] is False
    assert result["site"].startswith("partial: 1 failed")
    assert (paths.site_root / "current" / "index.html").is_file()


def test_load_config_and_unknown_key(tmp_path: Path) -> None:
    path = tmp_path / "daily.toml"
    path.write_text("top_n = 3\nllm_top_n = 1\n", encoding="utf-8")
    config = load_config(path)
    assert config.top_n == 3
    assert config.llm_top_n == 1

    path.write_text("top_n = 3\nunknown = true\n", encoding="utf-8")
    with pytest.raises(DailyError, match="unknown config keys"):
        load_config(path)
