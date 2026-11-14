"""W6.3: quality dashboard aggregation and rendering."""

from __future__ import annotations

import json
from pathlib import Path

from turtlefw.quality import build_dashboard, render, write_dashboard


def _day(
    root: Path,
    date: str,
    *,
    stocks: list[tuple[str, str, str, str]],
    warn: int = 0,
    fail: int = 0,
    conflicts: int = 0,
    site: str = "",
) -> Path:
    day = root / date
    day.mkdir(parents=True)
    rows = [{"code": code, "qa": qa, "research": research} for code, qa, research, _ in stocks]
    (day / "status.json").write_text(
        json.dumps({"stocks": rows, "site": site}, ensure_ascii=False), encoding="utf-8"
    )
    for code, _, _, verdict in stocks:
        base = day / code
        base.mkdir()
        (base / "analysis_report.md").write_text(f"**{verdict}** — 示例\n", encoding="utf-8")
        qa_rows = [{"name": "ok", "status": "PASS", "detail": ""}]
        qa_rows += [{"name": f"w{i}", "status": "WARN", "detail": ""} for i in range(warn)]
        qa_rows += [{"name": f"f{i}", "status": "FAIL", "detail": ""} for i in range(fail)]
        (base / "qa.json").write_text(json.dumps({"rows": qa_rows}), encoding="utf-8")
        if conflicts:
            (base / "snapshot").mkdir()
            (base / "snapshot" / "metric_conflicts.json").write_text(
                json.dumps([{"id": f"m{i}"} for i in range(conflicts)]), encoding="utf-8"
            )
    return day


def test_dashboard_counts(tmp_path: Path) -> None:
    root = tmp_path / "daily"
    _day(
        root,
        "2026-11-10",
        stocks=[("A.SH", "PASS", "on", "买入"), ("B.HK", "PASS", "fallback", "排除")],
        conflicts=1,
        site="C:/site/releases/2026-11-10",
    )
    dashboard = build_dashboard(root, days=15)
    assert len(dashboard.days) == 1
    item = dashboard.days[0]
    assert item.stocks == 2
    assert item.qa_pass == 2
    assert item.research_on == 1
    assert item.research_fallback == 1
    assert item.conflicts == 2
    assert item.verdicts == {"买入": 1, "排除": 1}
    assert dashboard.totals["stocks"] == 2


def test_fallback_rate_alert(tmp_path: Path) -> None:
    root = tmp_path / "daily"
    stocks = [(f"{i}.HK", "PASS", "fallback" if i < 5 else "on", "观察") for i in range(20)]
    _day(root, "2026-11-10", stocks=stocks)
    dashboard = build_dashboard(root, days=5)
    assert any("研究回退" in alert for alert in dashboard.alerts)
    assert dashboard.ok is False


def test_fail_and_conflict_alerts(tmp_path: Path) -> None:
    root = tmp_path / "daily"
    _day(root, "2026-11-10", stocks=[("A.SH", "PASS", "on", "买入")], fail=1, conflicts=1)
    dashboard = build_dashboard(root, days=5)
    text = "\n".join(dashboard.alerts)
    assert "QA FAIL" in text
    assert "重复指标" in text


def test_no_alert_when_clean(tmp_path: Path) -> None:
    root = tmp_path / "daily"
    _day(root, "2026-11-10", stocks=[("A.SH", "PASS", "on", "买入")])
    dashboard = build_dashboard(root, days=5)
    assert dashboard.ok is True
    assert "无告警" in render(dashboard)


def test_render_table_and_weekend_row(tmp_path: Path) -> None:
    root = tmp_path / "daily"
    _day(
        root,
        "2026-11-10",
        stocks=[("A.SH", "PASS", "on", "买入"), ("B.SH", "PASS", "on", "观察")],
        site="C:/site/releases/2026-11-10",
    )
    _day(root, "2026-11-14", stocks=[])
    text = render(build_dashboard(root, days=5))
    assert "| 数据日 |" in text
    assert "2026-11-10" in text
    assert "2026-11-10 |" in text and "2/2" in text
    assert "无运行" in text
    assert "2026-11-10 |" in text and "2026-11-14 |" in text
    assert "releases" not in text  # 站点列只显示 release 名


def test_write_dashboard(tmp_path: Path) -> None:
    root = tmp_path / "daily"
    _day(root, "2026-11-10", stocks=[("A.SH", "PASS", "on", "买入")])
    path, dashboard = write_dashboard(root, tmp_path / "out" / "quality.md", days=5)
    assert path.is_file()
    assert path.read_text(encoding="utf-8").startswith("# 质量看板")
    assert dashboard.totals["days"] == 1


def test_quality_cli(tmp_path: Path, capsys) -> None:
    from turtlefw.cli import main

    root = tmp_path / "daily"
    _day(root, "2026-11-10", stocks=[("A.SH", "PASS", "on", "买入")])
    out = tmp_path / "q.md"
    code = main(["quality", "--runs-root", str(root), "--days", "5", "--out", str(out)])
    assert code == 0
    assert out.is_file()
    assert "质量看板" in capsys.readouterr().out


def test_quality_cli_missing_root(tmp_path: Path, capsys) -> None:
    from turtlefw.cli import main

    code = main(["quality", "--runs-root", str(tmp_path / "nope")])
    assert code == 2
    assert "没有找到运行目录" in capsys.readouterr().err
