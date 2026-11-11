"""Archive replay and look-ahead audit for daily runs.

The project does not license vendor point-in-time fundamentals, so "PIT" here
means the two things we *can* prove offline:

1. **Look-ahead audit** — a frozen snapshot must not contain a statement row
   whose announcement date is later than the snapshot's ``as_of`` date.
2. **Replay panel** — re-read the archived snapshots day by day and report
   verdict churn, so a conclusion that flips while the deterministic numbers
   stay put becomes visible instead of invisible.

Both are read-only: nothing here re-fetches data or rewrites a report.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

_VERDICT_RE = re.compile(r"^\*\*(买入|观察|排除|减持)\*\*", re.MULTILINE)

_VERDICT_ORDER = {"买入": 0, "观察": 1, "排除": 2, "减持": 3}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _metric(metrics: dict[str, Any], key: str) -> float | None:
    point = metrics.get(key)
    if not isinstance(point, dict):
        return None
    raw = point.get("value")
    if raw in (None, ""):
        return None
    try:
        return float(Decimal(str(raw)))
    except (ArithmeticError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class LookaheadAudit:
    """Result of checking one snapshot for look-ahead leakage."""

    as_of: str
    checked: int
    unknown: int
    violations: tuple[str, ...] = ()

    @property
    def clean(self) -> bool:
        return not self.violations

    def summary(self) -> str:
        if not self.as_of:
            return "快照缺少 as_of，无法核验前视"
        if self.violations:
            return (
                f"{len(self.violations)} 条财务行公告日晚于 as_of={self.as_of}"
                f"（如 {self.violations[0]}）"
            )
        if self.checked == 0:
            return f"as_of={self.as_of}；{self.unknown} 行全部缺公告日（港股/第三方源），无法核验"
        return (
            f"as_of={self.as_of}；{self.checked} 行公告日均不晚于 as_of，"
            f"{self.unknown} 行缺公告日"
        )


def lookahead_audit(snapshot_dir: Path) -> LookaheadAudit:
    """Check that no stored statement row was announced after ``as_of``."""

    inputs = _load_json(Path(snapshot_dir) / "inputs.json")
    as_of_raw = str(inputs.get("as_of") or "")
    as_of = as_of_raw.replace("-", "")[:8]
    rows = inputs.get("rows") or []
    checked = 0
    unknown = 0
    violations: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        ann = str(row.get("ann_date") or "").replace("-", "")[:8]
        if not ann:
            unknown += 1
            continue
        checked += 1
        if as_of and ann > as_of:
            violations.append(
                f"{row.get('code')} {row.get('statement')}.{row.get('item')} "
                f"ann_date={ann} > as_of={as_of}"
            )
    unique = tuple(sorted(set(violations))[:20])
    return LookaheadAudit(as_of=as_of, checked=checked, unknown=unknown, violations=unique)


@dataclass(frozen=True, slots=True)
class PanelRow:
    """One archived stock-day: verdict plus the deterministic numbers behind it."""

    date: str
    code: str
    name: str
    market: str
    verdict: str
    r: float | None
    gg: float | None
    margin: float | None
    floor: float | None
    price: float | None


@dataclass(frozen=True, slots=True)
class ChurnRow:
    """Verdict history for one code across archived days."""

    code: str
    name: str
    days: int
    flips: int
    verdicts: tuple[str, ...]
    margin_span: float | None
    last: str


@dataclass(slots=True)
class ReplayReport:
    dates: list[str] = field(default_factory=list)
    rows: list[PanelRow] = field(default_factory=list)
    churn: list[ChurnRow] = field(default_factory=list)
    audits: list[tuple[str, LookaheadAudit]] = field(default_factory=list)


def _verdict_of(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = _VERDICT_RE.search(text)
    return match.group(1) if match else ""


def load_panel(runs_root: Path) -> ReplayReport:
    """Read every archived day under ``runs_root`` into a per-stock panel."""

    report = ReplayReport()
    root = Path(runs_root)
    if not root.is_dir():
        return report
    for day in sorted(p for p in root.iterdir() if p.is_dir()):
        status = _load_json(day / "status.json")
        stocks = status.get("stocks") or []
        if not stocks:
            continue
        date = str(status.get("date") or day.name)
        report.dates.append(date)
        for stock in stocks:
            if not isinstance(stock, dict):
                continue
            code = str(stock.get("code") or "")
            if not code:
                continue
            base = day / code
            metrics = _load_json(base / "snapshot" / "metrics.json")
            report.rows.append(
                PanelRow(
                    date=date,
                    code=code,
                    name=str(stock.get("name") or ""),
                    market=str(stock.get("market") or ""),
                    verdict=_verdict_of(base / "analysis_report.md"),
                    r=_metric(metrics, "r"),
                    gg=_metric(metrics, "gg"),
                    margin=_metric(metrics, "margin"),
                    floor=_metric(metrics, "floor"),
                    price=_metric(metrics, "price"),
                )
            )
        snapshot = day / next(
            (str(s.get("code")) for s in stocks if isinstance(s, dict)), ""
        ) / "snapshot"
        if (snapshot / "inputs.json").is_file():
            report.audits.append((date, lookahead_audit(snapshot)))
    report.rows.sort(key=lambda row: (row.code, row.date))
    report.churn = churn_rows(report.rows)
    return report


def churn_rows(rows: Sequence[PanelRow]) -> list[ChurnRow]:
    """Count verdict flips per code, ordered by the number of flips."""

    grouped: dict[str, list[PanelRow]] = {}
    for row in rows:
        grouped.setdefault(row.code, []).append(row)
    result: list[ChurnRow] = []
    for code, series in grouped.items():
        ordered = sorted(series, key=lambda item: item.date)
        verdicts: list[str] = []
        flips = 0
        for item in ordered:
            if not item.verdict:
                continue
            if verdicts and item.verdict != verdicts[-1]:
                flips += 1
            verdicts.append(item.verdict)
        margins = [item.margin for item in ordered if item.margin is not None]
        span = (max(margins) - min(margins)) if len(margins) >= 2 else None
        result.append(
            ChurnRow(
                code=code,
                name=ordered[-1].name,
                days=len(ordered),
                flips=flips,
                verdicts=tuple(verdicts),
                margin_span=span,
                last=verdicts[-1] if verdicts else "",
            )
        )
    result.sort(key=lambda row: (-row.flips, -row.days, row.code))
    return result


def render_markdown(report: ReplayReport, *, limit: int = 15) -> str:
    """Human-readable replay report for one archive root."""

    dates = report.dates
    lines = [
        "# 归档回放与 PIT 审计",
        "",
        f"- 归档日数：{len(dates)}" + (f"（{dates[0]} → {dates[-1]}）" if dates else ""),
        f"- 股票·日样本：{len(report.rows)}",
        f"- 标的数：{len({row.code for row in report.rows})}",
        "",
        "## 前视审计",
        "",
    ]
    if not report.audits:
        lines.append("没有可审计的快照（缺 `snapshot/inputs.json`）。")
    else:
        bad = [(day, audit) for day, audit in report.audits if not audit.clean]
        checked = sum(audit.checked for _day, audit in report.audits)
        unknown = sum(audit.unknown for _day, audit in report.audits)
        lines.append(
            f"- 审计快照 {len(report.audits)} 个：财务行 {checked} 条带公告日、"
            f"{unknown} 条缺公告日。"
        )
        lines.append(f"- 前视违规：**{len(bad)}** 个快照。")
        for day, audit in bad[:5]:
            lines.append(f"  - {day}：{audit.summary()}")
        if not bad:
            lines.append("- 结论：已审计快照中，没有任何财务行的公告日晚于 `as_of`。")
    lines += [
        "",
        "## 结论翻转",
        "",
        "| 标的 | 名称 | 天数 | 翻转次数 | 结论序列 | 安全边际极差(pp) | 末日结论 |",
        "|:--|:--|--:|--:|:--|--:|:--|",
    ]
    for row in report.churn[:limit]:
        span = f"{row.margin_span:.2f}" if row.margin_span is not None else "—"
        lines.append(
            f"| {row.code} | {row.name} | {row.days} | {row.flips} | "
            f"{' → '.join(row.verdicts) or '—'} | {span} | {row.last or '—'} |"
        )
    flipped = [row for row in report.churn if row.flips > 0]
    lines += [
        "",
        f"翻转过的标的：{len(flipped)} / {len(report.churn)}；"
        f"总翻转 {sum(row.flips for row in report.churn)} 次。",
        "",
        "> 口径：本报告只读归档产物，不重新取数。真正的前视保证仍依赖 Tushare 的",
        "> `ann_date`；港股/第三方源的财务行没有公告日时，只能标为「无法核验」。",
    ]
    return "\n".join(lines) + "\n"


def write_report(
    runs_root: Path, out: Path, *, limit: int = 15
) -> tuple[Path, ReplayReport]:
    report = load_panel(runs_root)
    text = render_markdown(report, limit=limit)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out, report


def panel_payload(report: ReplayReport) -> dict[str, Any]:
    """JSON payload for tooling (kept small: verdicts + churn)."""

    return {
        "dates": report.dates,
        "rows": [
            {
                "date": row.date,
                "code": row.code,
                "verdict": row.verdict,
                "margin": row.margin,
            }
            for row in report.rows
        ],
        "churn": [
            {
                "code": row.code,
                "flips": row.flips,
                "verdicts": list(row.verdicts),
                "margin_span": row.margin_span,
            }
            for row in report.churn
        ],
        "audits": [
            {
                "date": day,
                "as_of": audit.as_of,
                "checked": audit.checked,
                "unknown": audit.unknown,
                "violations": list(audit.violations),
            }
            for day, audit in report.audits
        ],
    }
