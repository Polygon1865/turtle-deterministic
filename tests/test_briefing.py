"""Tests for the daily briefing renderer."""

from __future__ import annotations

import json
from pathlib import Path

from turtlefw.briefing import build_briefing, notify_briefing, to_plain, write_briefing


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _day(tmp_path: Path) -> Path:
    day = tmp_path / "2026-10-30"
    day.mkdir(parents=True)
    status = {
        "date": "2026-10-30",
        "started_at": "2026-10-30T19:00:02",
        "finished_at": "2026-10-30T19:57:22",
        "screen": "ok",
        "screen_source": "tushare:screen",
        "ok": True,
        "stocks": [
            {
                "code": "600519.SH",
                "name": "贵州茅台",
                "market": "A",
                "rank": 1,
                "status": "ok",
                "qa": "PASS",
                "research": "on",
                "numeric_coverage": "1.0",
            },
            {
                "code": "06862.HK",
                "name": "海底捞",
                "market": "HK",
                "rank": 21,
                "status": "ok",
                "qa": "PASS",
                "research": "on",
                "numeric_coverage": "1.0",
            },
            {
                "code": "000001.SZ",
                "name": "平安银行",
                "market": "A",
                "rank": 3,
                "status": "failed",
                "qa": "FAIL",
                "research": "off",
                "error": "错误：行情缺失",
            },
        ],
    }
    _write(day / "status.json", json.dumps(status, ensure_ascii=False))
    _write(
        day / "600519.SH" / "analysis_report.md",
        "# 贵州茅台\n\n**观察** — 估值或数据仍待确认\n",
    )
    _write(
        day / "06862.HK" / "analysis_report.md",
        "# 海底捞\n\n**买入** — 估值达标且未触发价值陷阱\n",
    )
    _write(
        day / "ranking.csv",
        "ts_code,name,R%,GG%\n600519.SH,贵州茅台,3.1,4.2\n",
    )
    _write(
        day / "ranking_hk.csv",
        "ts_code,name,R%,GG%,II%,margin,pe,pb,market_cap\n"
        "06862.HK,海底捞,16.58,38.14,5.0,33.14,4.35,0.64,6230000000\n",
    )
    _write(day / "screen.log", "漏斗：全部上市 2787，通过筛选 471\n")
    return day


def test_build_briefing_contains_run_facts(tmp_path: Path) -> None:
    briefing = build_briefing(_day(tmp_path))
    assert briefing.day == "2026-10-30"
    assert briefing.verdicts == {"买入": 1, "观察": 1, "排除": 0}
    assert briefing.total == 3
    text = briefing.markdown
    assert "每日运行简报 · 2026-10-30" in text
    assert "QA 通过 2 · WARN 0 · 失败 1（共 3 只）" in text
    assert "研究 开启 2 · 回退 0 · 关闭 1" in text
    assert "**结论分布**：买入 1 · 观察 1 · 排除 0" in text
    assert "600519.SH 贵州茅台" in text
    assert "06862.HK 海底捞 — R 16.58% / GG 38.14% / 门槛 5.0% / 边际 +33.14%" in text
    assert "市值 62 亿" in text
    assert "港股漏斗" in text
    assert "失败 1 只" in text


def test_plain_text_strips_markdown(tmp_path: Path) -> None:
    plain = build_briefing(_day(tmp_path)).plain
    assert "**" not in plain
    assert plain.startswith("每日运行简报")
    assert "每日运行简报 · 2026-10-30" in plain
    assert "· 06862.HK 海底捞" in plain


def test_write_briefing_writes_both_files(tmp_path: Path) -> None:
    day = _day(tmp_path)
    written = write_briefing(day)
    assert [path.name for path in written] == ["briefing.md", "briefing.txt"]
    assert (day / "briefing.md").read_text(encoding="utf-8").startswith("# 每日运行简报")
    assert "**" not in (day / "briefing.txt").read_text(encoding="utf-8")


def test_write_briefing_single_out_file(tmp_path: Path) -> None:
    target = tmp_path / "out" / "brief.txt"
    written = write_briefing(_day(tmp_path), fmt="txt", out=target)
    assert written == [target]
    assert target.is_file()
    assert "**" not in target.read_text(encoding="utf-8")


def test_write_briefing_rejects_bad_format(tmp_path: Path) -> None:
    try:
        write_briefing(_day(tmp_path), fmt="html")
    except ValueError as exc:
        assert "html" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("expected ValueError")


def test_notify_briefing_without_webhook(monkeypatch) -> None:
    monkeypatch.delenv("TURTLE_BRIEFING_WEBHOOK", raising=False)
    assert notify_briefing("hello") is False


def test_cli_brief_writes_into_day_dir(tmp_path: Path, capsys) -> None:
    from turtlefw import cli

    day = _day(tmp_path)
    code = cli.main(
        ["brief", "--date", "2026-10-30", "--runs-root", str(tmp_path), "--format", "both"]
    )
    assert code == 0
    output = capsys.readouterr().out
    assert "简报：2026-10-30" in output
    assert (day / "briefing.txt").is_file()


def test_cli_brief_missing_day(tmp_path: Path, capsys) -> None:
    from turtlefw import cli

    code = cli.main(["brief", "--date", "2026-01-01", "--runs-root", str(tmp_path)])
    assert code == 1
    assert "没有找到运行目录" in capsys.readouterr().err
