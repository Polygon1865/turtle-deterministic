"""W6.3: local quality dashboard over archived daily runs.

The daily pipeline already writes everything needed to see whether the system
is trusting its own output: ``status.json`` per day, ``qa.json`` per stock,
``snapshot/metric_conflicts.json`` and the verdict line of each report.  This
module turns those files into one markdown table plus a short alert list, so
degradation (research fallbacks, duplicate metrics, QA warnings) is visible
before it shows up in a report.

It deliberately reads only archived files — no network, no LLM, no rerender.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

VERDICT = re.compile(r"^\*\*(买入|观察|排除|减持)\*\*", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class DayQuality:
    date: str
    stocks: int
    qa_pass: int
    qa_fail: int
    research_on: int
    research_fallback: int
    conflicts: int
    warn_rows: int
    fail_rows: int
    verdicts: dict[str, int] = field(default_factory=dict)
    site: str = ""


@dataclass(frozen=True, slots=True)
class Dashboard:
    days: tuple[DayQuality, ...]
    alerts: tuple[str, ...]
    totals: dict[str, int]

    @property
    def ok(self) -> bool:
        return not self.alerts


def _load(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def _day_dirs(runs_root: Path, days: int) -> list[Path]:
    candidates = [
        path
        for path in runs_root.iterdir()
        if path.is_dir() and (path / "status.json").is_file()
    ]
    return sorted(candidates)[-days:]


def _qa_rows(base: Path) -> tuple[int, int]:
    payload = _load(base / "qa.json")
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return 0, 0
    warn = sum(1 for row in rows if str(row.get("status", "")).upper() == "WARN")
    fail = sum(1 for row in rows if str(row.get("status", "")).upper() == "FAIL")
    return warn, fail


def _verdict(base: Path) -> str:
    path = base / "analysis_report.md"
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")[:800]
    except OSError:
        return ""
    match = VERDICT.search(text)
    return match.group(1) if match else ""


def _day_quality(day_dir: Path) -> DayQuality | None:
    status = _load(day_dir / "status.json")
    if not isinstance(status, dict):
        return None
    stocks = status.get("stocks")
    if not isinstance(stocks, list):
        stocks = []
    qa_pass = qa_fail = research_on = research_fallback = 0
    conflicts = warn_rows = fail_rows = 0
    verdicts: dict[str, int] = {}
    for stock in stocks:
        if not isinstance(stock, dict):
            continue
        code = str(stock.get("code") or "")
        if not code:
            continue
        base = day_dir / code
        if stock.get("qa") == "PASS":
            qa_pass += 1
        elif stock.get("qa") == "FAIL":
            qa_fail += 1
        research = stock.get("research")
        if research == "on":
            research_on += 1
        elif research == "fallback":
            research_fallback += 1
        verdict = _verdict(base)
        if verdict:
            verdicts[verdict] = verdicts.get(verdict, 0) + 1
        payload = _load(base / "snapshot" / "metric_conflicts.json")
        if isinstance(payload, list):
            conflicts += len(payload)
        warn, fail = _qa_rows(base)
        warn_rows += warn
        fail_rows += fail
    return DayQuality(
        date=day_dir.name,
        stocks=len(stocks),
        qa_pass=qa_pass,
        qa_fail=qa_fail,
        research_on=research_on,
        research_fallback=research_fallback,
        conflicts=conflicts,
        warn_rows=warn_rows,
        fail_rows=fail_rows,
        verdicts=verdicts,
        site=str(status.get("site") or ""),
    )


def build_dashboard(runs_root: Path | str, *, days: int = 15) -> Dashboard:
    root = Path(runs_root)
    quality = [item for item in (_day_quality(day) for day in _day_dirs(root, days)) if item]
    alerts: list[str] = []
    for item in quality:
        if item.stocks and item.research_fallback / item.stocks > 0.10:
            alerts.append(
                f"{item.date}: 研究回退 {item.research_fallback}/{item.stocks} 超过 10%"
            )
        if item.fail_rows:
            alerts.append(f"{item.date}: {item.fail_rows} 条 QA FAIL")
        if item.conflicts:
            alerts.append(f"{item.date}: {item.conflicts} 个重复指标（已按权威源解析）")
    totals = {
        "days": len(quality),
        "stocks": sum(item.stocks for item in quality),
        "qa_fail": sum(item.qa_fail for item in quality),
        "research_fallback": sum(item.research_fallback for item in quality),
        "conflicts": sum(item.conflicts for item in quality),
        "buy": sum(item.verdicts.get("买入", 0) for item in quality),
        "watch": sum(item.verdicts.get("观察", 0) for item in quality),
        "reject": sum(item.verdicts.get("排除", 0) for item in quality),
    }
    return Dashboard(days=tuple(quality), alerts=tuple(alerts), totals=totals)


def _site_label(site: str) -> str:
    if not site:
        return "—"
    if site.startswith("blocked"):
        return "blocked"
    if site.startswith("partial"):
        return "partial"
    name = Path(site).name
    return name or "ok"


def render(dashboard: Dashboard, *, title: str = "质量看板") -> str:
    lines = [f"# {title}", ""]
    totals = dashboard.totals
    lines.append(
        f"样本：{totals['days']} 个数据日 / {totals['stocks']} 只次；"
        f"QA 失败 {totals['qa_fail']}；研究回退 {totals['research_fallback']}；"
        f"重复指标 {totals['conflicts']}；"
        f"结论 买入 {totals['buy']} / 观察 {totals['watch']} / 排除 {totals['reject']}。"
    )
    lines.append("")
    lines.append(
        "| 数据日 | 股票 | QA 通过 | 研究 on | 回退 | 重复指标 | QA WARN | QA FAIL | 买入 | 观察 | 排除 | 站点 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for item in dashboard.days:
        if item.stocks == 0:
            lines.append(
                f"| {item.date} | — | — | — | — | — | — | — | — | — | — | —（无运行） |"
            )
            continue
        lines.append(
            f"| {item.date} | {item.stocks} | {item.qa_pass}/{item.stocks} | {item.research_on} | "
            f"{item.research_fallback} | {item.conflicts} | {item.warn_rows} | {item.fail_rows} | "
            f"{item.verdicts.get('买入', 0)} | {item.verdicts.get('观察', 0)} | "
            f"{item.verdicts.get('排除', 0)} | {_site_label(item.site)} |"
        )
    lines.append("")
    lines.append("## 告警")
    lines.append("")
    if dashboard.alerts:
        lines.extend(f"- {alert}" for alert in dashboard.alerts)
    else:
        lines.append("无告警：回退率、重复指标、QA FAIL 均在阈值内。")
    lines.append("")
    return "\n".join(lines)


def write_dashboard(
    runs_root: Path | str,
    out: Path | str,
    *,
    days: int = 15,
    title: str = "质量看板",
) -> tuple[Path, Dashboard]:
    dashboard = build_dashboard(runs_root, days=days)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render(dashboard, title=title), encoding="utf-8")
    return target, dashboard
