from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import pytest

from turtlefw.daily import (
    HK_DEFAULT_CODES,
    HK_DEFAULT_NAMES,
    CommandResult,
    DailyConfig,
    DailyError,
    DailyPaths,
    build_hk_screen_command,
    build_screen_command,
    classify_research_failure,
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
    assert config.hk_limit == 20
    assert len(HK_DEFAULT_CODES) == 20
    assert set(HK_DEFAULT_CODES) == set(HK_DEFAULT_NAMES)


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


def test_hk_screen_command_uses_market_wide_screen(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    command = build_hk_screen_command(
        paths,
        DailyConfig(hk_limit=7, hk_candidate_limit=100, refresh_market=True),
        "20261023",
    )
    assert "--market" in command
    assert command[command.index("--market") + 1] == "HK"
    assert command[command.index("--fast-limit") + 1] == "100"
    assert command[command.index("--as-of") + 1] == "20261023"
    assert command[command.index("--csv") + 1].endswith("ranking_hk.csv")


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


def test_run_stock_clears_stale_research_when_off(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    code_dir = paths.day_dir / "600887.SH"
    code_dir.mkdir(parents=True)
    (code_dir / "research.json").write_text("{}", encoding="utf-8")
    (code_dir / "snapshot").mkdir()
    (code_dir / "snapshot" / "research.json").write_text("{}", encoding="utf-8")
    (code_dir / "snapshot" / "research_audit.json").write_text("{}", encoding="utf-8")

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        _write_success(code_dir)
        return CommandResult(tuple(command), 0, "ok")

    record = run_stock(
        "600887.SH",
        2,
        paths,
        DailyConfig(llm_top_n=1),
        run_command=fake,
    )
    assert record["research"] == "off"
    assert not (code_dir / "research.json").exists()
    assert not (code_dir / "snapshot" / "research.json").exists()


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
    assert record["research_reason_code"] == "llm_error"
    assert record["research_reason"]
    assert record["research_failed"]
    assert (code_dir / "research_failed" / "research.json").is_file()
    assert not (code_dir / "research.json").exists()
    assert not (code_dir / "research_provenance.json").exists()
    assert not (code_dir / "snapshot" / "research.json").exists()
    assert len(commands) == 2
    assert "--with-research" in commands[0]
    assert "--research-retries" in commands[0]
    assert "--with-research" not in commands[1]
    assert "--research-note" in commands[1]


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


def test_run_daily_resumes_completed_stocks_and_keeps_attempt(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.day_dir.mkdir(parents=True)
    report = paths.day_dir / "600887.SH" / "analysis_report.md"
    report.parent.mkdir(parents=True)
    report.write_text("# report\n", encoding="utf-8")
    paths.status_path.write_text(
        '{"stocks":[{"code":"600887.SH","rank":1,"status":"ok","qa":"PASS",'
        '"research":"off"},{"code":"000858.SZ","rank":2,"status":"failed",'
        '"qa":"FAIL","research":"off"}]}',
        encoding="utf-8",
    )
    commands: list[list[str]] = []

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        commands.append(list(command))
        code = command[command.index("run") + 1]
        _write_success(paths.day_dir / code)
        return CommandResult(tuple(command), 0, "ok")

    result = run_daily(
        paths,
        DailyConfig(top_n=2, resume=True),
        codes=["600887.SH", "000858.SZ"],
        skip_screen=True,
        publish=False,
        run_command=fake,
        sleep=lambda seconds: None,
    )
    assert result["ok"] is True
    assert result["resumed"] == 1
    assert len(commands) == 1
    assert len(result["stocks"]) == 2
    attempt = paths.day_dir / "attempts" / result["attempt_id"] / "status.json"
    assert attempt.is_file()


def test_classify_research_failure_codes() -> None:
    assert classify_research_failure("LLM response is not valid JSON") == "json_invalid"
    assert (
        classify_research_failure("unresolved placeholder {{metric:x}}")
        == "placeholder"
    )
    assert classify_research_failure("numeric gate 未通过：coverage=0.9994") == "numeric_gate"
    assert classify_research_failure("未通过：research_provenance") == "provenance"
    assert classify_research_failure("LLM unavailable") == "llm_error"


def test_run_daily_skips_weekend_without_allow_stale(tmp_path: Path) -> None:
    paths = DailyPaths(
        day=date(2026, 10, 24),
        runs_root=tmp_path / "runs",
        site_root=tmp_path / "site",
        pdf_root=tmp_path / "pdfs",
    )

    def fail_if_called(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        raise AssertionError(f"weekend should not invoke {command}")

    result = run_daily(
        paths,
        DailyConfig(),
        publish=False,
        run_command=fail_if_called,
    )
    assert result["ok"] is True
    assert result["skipped"] == "weekend"
    assert result["stocks"] == []
    assert paths.status_path.is_file()


def test_run_daily_skip_screen_limits_each_market(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        code = command[command.index("run") + 1]
        _write_success(paths.day_dir / code)
        return CommandResult(tuple(command), 0, "ok")

    result = run_daily(
        paths,
        DailyConfig(markets=("A", "HK"), top_n=1, hk_limit=1, llm_top_n=0),
        codes=["600887.SH", "000858.SZ", "00700.HK", "09988.HK"],
        skip_screen=True,
        publish=False,
        run_command=fake,
        sleep=lambda seconds: None,
    )
    assert [row["code"] for row in result["stocks"]] == ["600887.SH", "00700.HK"]


def test_skip_screen_reads_names_from_rankings(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    paths.day_dir.mkdir(parents=True)
    (paths.day_dir / "ranking_deep.csv").write_text(
        "ts_code,name\n600887.SH,伊利股份\n", encoding="utf-8-sig"
    )
    (paths.day_dir / "ranking_hk.csv").write_text(
        "ts_code,name\n00700.HK,腾讯控股\n", encoding="utf-8-sig"
    )

    def fake(command: list[str], cwd: Path, timeout: int) -> CommandResult:
        code = command[command.index("run") + 1]
        _write_success(paths.day_dir / code)
        return CommandResult(tuple(command), 0, "ok")

    result = run_daily(
        paths,
        DailyConfig(
            markets=("A", "HK"), top_n=1, hk_limit=1, llm_top_n=0
        ),
        codes=["600887.SH", "00700.HK"],
        skip_screen=True,
        publish=False,
        run_command=fake,
        sleep=lambda seconds: None,
    )
    assert [row["name"] for row in result["stocks"]] == ["伊利股份", "腾讯控股"]


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


def test_hk_research_budget_uses_hk_rank(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    commands: list[list[str]] = []

    def fake(command, cwd, timeout):
        commands.append(list(command))
        code = command[command.index("run") + 1]
        _write_success(paths.day_dir / code, research=False)
        return CommandResult(command=command, returncode=0, stdout="ok", stderr="")

    first = run_stock(
        "00700.HK",
        21,
        paths,
        DailyConfig(hk_llm_top_n=1),
        run_command=fake,
        market="HK",
        research_rank=1,
    )
    second = run_stock(
        "09988.HK",
        22,
        paths,
        DailyConfig(hk_llm_top_n=1),
        run_command=fake,
        market="HK",
        research_rank=2,
    )
    assert first["market"] == "HK"
    assert first["research"] == "on"
    assert second["research"] == "off"
    assert any("--with-research" in command for command in commands)
    assert sum("--with-research" in command for command in commands) == 1


def test_load_config_and_unknown_key(tmp_path: Path) -> None:
    path = tmp_path / "daily.toml"
    path.write_text(
        'top_n = 3\nllm_top_n = 1\nmarkets = ["A", "HK"]\n', encoding="utf-8"
    )
    config = load_config(path)
    assert config.top_n == 3
    assert config.llm_top_n == 1
    assert config.markets == ("A", "HK")

    path.write_text("top_n = 3\nunknown = true\n", encoding="utf-8")
    with pytest.raises(DailyError, match="unknown config keys"):
        load_config(path)


def test_production_config_attempts_llm_for_all_reports() -> None:
    root = Path(__file__).resolve().parents[1]
    config = load_config(root / "configs" / "daily.toml")
    assert (config.top_n, config.llm_top_n) == (20, 20)
    assert (config.hk_limit, config.hk_llm_top_n) == (20, 20)
