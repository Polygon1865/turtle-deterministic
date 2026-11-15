"""Daily briefing: compress one finished run directory into an IM-friendly digest.

The daily pipeline writes ``status.json`` plus per-code reports, rankings and a
screen log under ``.runs/daily/<date>/``.  This module turns that directory into
a short Markdown/plain-text briefing so the run can be reported without opening
the site or the reports one by one.

Usage::

    from turtlefw.briefing import write_briefing

    paths = write_briefing(Path(".runs/daily/2026-10-30"))

The daily pipeline calls :func:`write_briefing` automatically when
``configs/daily.toml`` sets ``briefing = true`` (the default), and the CLI
exposes the same helper as ``python -m turtlefw.cli brief --date <date>``.
"""

from __future__ import annotations

import csv
import json
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

HKT = ZoneInfo("Asia/Hong_Kong")
VERDICT_RE = re.compile(r"^\*\*(买入|观察|排除)\*\*\s*[—-]\s*(.+?)\s*$", re.MULTILINE)
VERDICTS = ("买入", "观察", "排除")


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _verdict_of(code_dir: Path) -> tuple[str, str]:
    report = code_dir / "analysis_report.md"
    if not report.is_file():
        return "—", ""
    try:
        text = report.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "—", ""
    match = VERDICT_RE.search(text)
    if not match:
        return "—", ""
    return match.group(1), " ".join(match.group(2).split())


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open(encoding="utf-8-sig", newline="") as handle:
            return list(csv.DictReader(handle))
    except (OSError, csv.Error):
        return []


def _screen_funnel(day: Path) -> str:
    log = day / "screen.log"
    if not log.is_file():
        return ""
    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = [line.strip() for line in text.splitlines() if "漏斗" in line]
    return lines[-1] if lines else ""


def _duration(started: str, finished: str) -> str:
    if not started or not finished:
        return "—"
    try:
        begin = datetime.fromisoformat(started)
        end = datetime.fromisoformat(finished)
    except ValueError:
        return "—"
    return f"{int((end - begin).total_seconds() // 60)} 分钟"


def _fmt_pct(value: str) -> str:
    try:
        return f"{float(value):.1f}%"
    except (TypeError, ValueError):
        return value or "—"


def _cell(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True)
class Briefing:
    """Rendered briefing plus the numbers behind it."""

    markdown: str
    plain: str
    day: str
    verdicts: dict[str, int]
    total: int


def build_briefing(day_dir: Path, *, limit: int = 6) -> Briefing:
    """Render the Markdown/plain-text briefing for one run directory."""

    day = Path(day_dir)
    status = _load_json(day / "status.json")
    stocks: list[dict[str, Any]] = [row for row in status.get("stocks") or [] if isinstance(row, dict)]
    started = str(status.get("started_at") or "")
    finished = str(status.get("finished_at") or "")
    screen = str(status.get("screen") or "—")

    rows: list[tuple[dict[str, Any], str, str]] = []
    for stock in stocks:
        code = str(stock.get("code") or "")
        verdict, reason = _verdict_of(day / code)
        rows.append((stock, verdict, reason))

    verdicts = Counter(verdict for _, verdict, _ in rows)
    qa_ok = sum(1 for row, _, _ in rows if str(row.get("qa")) == "PASS")
    qa_warn = sum(1 for row, _, _ in rows if str(row.get("qa")).upper() == "WARN")
    qa_fail = sum(1 for row, _, _ in rows if str(row.get("qa")).upper() == "FAIL")
    research_on = sum(1 for row, _, _ in rows if str(row.get("research")) == "on")
    research_fallback = sum(1 for row, _, _ in rows if str(row.get("research")) == "fallback")
    research_off = sum(1 for row, _, _ in rows if str(row.get("research")) in {"off", ""})
    markets = Counter(str(row.get("market") or "?") for row, _, _ in rows)
    failed = [row for row, _, _ in rows if str(row.get("status")) != "ok"]
    low_cover = [
        row
        for row, _, _ in rows
        if str(row.get("numeric_coverage") or "1.0") not in {"1.0", "1"}
    ]
    no_research = [row for row, _, _ in rows if str(row.get("research")) == "off"]

    hk_rows = _read_csv(day / "ranking_hk.csv")
    a_rows = _read_csv(day / "ranking.csv")

    lines: list[str] = [f"# 每日运行简报 · {status.get('date') or day.name}", ""]
    state = "已完成" if finished else "运行中（截至生成时）"
    lines.append(
        f"**状态**：{state} ｜ 开始 {started[11:19] or '—'} → 结束 {finished[11:19] or '—'}"
        f"（{_duration(started, finished)}）｜ screen={screen}"
    )
    lines.extend(
        [
            "",
            (
                "**规模**："
                f"A股 {markets.get('A', 0)} 只 / 港股 {markets.get('HK', 0)} 只；"
                f"QA 通过 {qa_ok} · WARN {qa_warn} · 失败 {qa_fail}（共 {len(rows)} 只）；"
                f"研究 开启 {research_on} · 回退 {research_fallback} · 关闭 {research_off}"
            ),
        ]
    )

    bits: list[str] = []
    if a_rows:
        bits.append(f"A股排名 {len(a_rows)} 条")
    if hk_rows:
        bits.append(f"港股候选 {len(hk_rows)} 条")
    if bits:
        lines.extend(["", "**筛选**：" + "；".join(bits)])
    funnel = _screen_funnel(day)
    if funnel:
        lines.extend(["", "**港股漏斗**：" + funnel.replace("漏斗：", "").strip()])

    lines.extend(
        [
            "",
            "**结论分布**：" + " · ".join(f"{name} {verdicts.get(name, 0)}" for name in VERDICTS),
            "",
        ]
    )

    highlighted = [item for item in rows if item[1] in {"买入", "观察"}]
    highlighted.sort(key=lambda item: (item[1] != "买入", str(item[0].get("rank") or 999)))
    if highlighted:
        lines.append(f"## 重点结论（前 {min(limit, len(highlighted))} 只）")
        lines.append("")
        for stock, verdict, reason in highlighted[:limit]:
            code = str(stock.get("code") or "")
            name = str(stock.get("name") or "")
            brief = reason if len(reason) <= 48 else reason[:46] + "…"
            lines.append(f"- {code} {name} — {verdict}：{brief}")
        lines.append("")

    if hk_rows:
        ranked = hk_rows[:limit]
        lines.append(f"## 港股候选 Top {len(ranked)}")
        lines.append("")
        for index, row in enumerate(ranked, start=1):
            code = _cell(row, "ts_code", "code")
            name = _cell(row, "name")
            r = _cell(row, "R%")
            gg = _cell(row, "GG%")
            ii = _cell(row, "II%")
            margin = _cell(row, "margin")
            pe = _cell(row, "pe")
            pb = _cell(row, "pb")
            cap = _cell(row, "market_cap", "total_market_cap")
            parts: list[str] = []
            try:
                parts.append(
                    f"R {float(r):.2f}% / GG {float(gg):.2f}% / 门槛 {float(ii):.1f}% / 边际 {float(margin):+.2f}%"
                )
            except (TypeError, ValueError):
                parts.append(f"ROE {_fmt_pct(_cell(row, 'roe'))} 净利率 {_fmt_pct(_cell(row, 'net_margin'))}")
            if pe or pb:
                parts.append(f"PE {pe or '—'} / PB {pb or '—'}")
            if cap:
                try:
                    parts.append(f"市值 {float(cap) / 1e8:.0f} 亿")
                except ValueError:
                    pass
            lines.append(f"{index}. {code} {name} — " + " ｜ ".join(parts))
        lines.append("")

    notes: list[str] = []
    if failed:
        groups: dict[str, list[str]] = {}
        for stock in failed:
            reason = str(stock.get("error") or "").strip()
            reason = reason.removeprefix("错误：").split("：")[0].strip() or str(stock.get("status"))
            groups.setdefault(reason, []).append(f"{stock.get('code')} {stock.get('name') or ''}".strip())
        grouped: list[str] = []
        for reason, codes in groups.items():
            listed = "、".join(codes[:8])
            more = f" 等 {len(codes)} 只" if len(codes) > 8 else ""
            grouped.append(f"{reason}（{listed}{more}）")
        notes.append(f"失败 {len(failed)} 只：" + "；".join(grouped))
    if no_research:
        notes.append("未做研究：" + "、".join(str(row.get("code")) for row in no_research[:5]))
    if low_cover:
        notes.append(
            "数字覆盖 <1.0："
            + "、".join(f"{row.get('code')} {row.get('numeric_coverage')}" for row in low_cover[:5])
        )
    failed_codes = {str(row.get("code")) for row in failed}
    qa_missed = [
        row
        for row, _, _ in rows
        if str(row.get("qa")).upper() == "FAIL" and str(row.get("code")) not in failed_codes
    ]
    if qa_missed:
        notes.append("QA 失败：" + "、".join(str(row.get("code")) for row in qa_missed[:8]))
    if not finished:
        notes.append("管线仍在运行，本简报为阶段性快照")
    if notes:
        lines.extend(["## 需要留意", ""] + [f"- {note}" for note in notes] + [""])

    lines.append(
        f"_生成时间 {datetime.now(HKT).strftime('%Y-%m-%d %H:%M')} HKT ｜"
        f" 数据源 {status.get('screen_source') or '—'}_"
    )
    lines.append("")

    markdown = "\n".join(lines)
    return Briefing(
        markdown=markdown,
        plain=to_plain(markdown),
        day=str(status.get("date") or day.name),
        verdicts={name: verdicts.get(name, 0) for name in VERDICTS},
        total=len(rows),
    )


def to_plain(markdown: str) -> str:
    """Render the briefing as plain text that survives WeChat previews."""

    out: list[str] = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if not line.strip():
            if out and out[-1] != "":
                out.append("")
            continue
        if line.lstrip().startswith("|"):
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if all(cell.replace("-", "").replace(":", "") == "" for cell in cells):
                continue
            out.append(" ｜ ".join(cells))
            continue
        if line.startswith("#"):
            line = line.lstrip("#").strip()
        line = line.replace("**", "").replace("__", "").replace("`", "")
        if line.startswith("_") and line.endswith("_") and len(line) > 1:
            line = line[1:-1]
        if line.startswith("- "):
            line = "· " + line[2:]
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out).strip() + "\n"


def write_briefing(
    day_dir: Path,
    *,
    limit: int = 6,
    fmt: str = "both",
    out: Path | None = None,
) -> list[Path]:
    """Write ``briefing.md`` / ``briefing.txt`` (or a single ``out`` path)."""

    if fmt not in {"md", "txt", "both"}:
        raise ValueError(f"unsupported briefing format: {fmt}")
    briefing = build_briefing(day_dir, limit=limit)
    written: list[Path] = []
    if out is not None:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(briefing.plain if fmt == "txt" else briefing.markdown, encoding="utf-8")
        return [target]
    day = Path(day_dir)
    if fmt in {"md", "both"}:
        target = day / "briefing.md"
        target.write_text(briefing.markdown, encoding="utf-8")
        written.append(target)
    if fmt in {"txt", "both"}:
        target = day / "briefing.txt"
        target.write_text(briefing.plain, encoding="utf-8")
        written.append(target)
    return written


def notify_briefing(text: str, *, webhook: str | None = None) -> bool:
    """Push the plain-text briefing to an optional IM webhook.

    WeChat Work (企业微信) robot webhooks accept ``{"msgtype": "text", ...}``;
    Server酱 accepts ``{"title": ..., "desp": ...}``.  The payload here is the
    WeChat Work shape, which is also what most generic relays accept.  Returns
    ``False`` when no webhook is configured or the push fails; the run itself
    is never failed by a notification error.
    """

    url = (webhook or os.environ.get("TURTLE_BRIEFING_WEBHOOK", "")).strip()
    if not url:
        return False
    payload = {"msgtype": "text", "text": {"content": text.strip()}}
    try:
        import requests

        response = requests.post(url, json=payload, timeout=10)
    except Exception:  # noqa: BLE001 - notification must never break a run
        return False
    return 200 <= response.status_code < 300
