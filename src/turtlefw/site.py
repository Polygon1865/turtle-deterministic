"""Static site builder for the daily Windows host.

The published site is plain HTML with one shared stylesheet.  A failed daily run
must never replace the last successful release: the builder writes a new release
directory first and only then moves the ``current`` junction/symlink.

Release layout::

    index.html                  home for the newest data day
    screener.html               candidate pool (A / HK)
    method.html                 methodology
    report/<code>.html          full report (back link -> stock page)
    stock/<code>.html           stock page: decision header, history, files
    archive/index.html          list of data days
    archive/<date>/index.html   one data day
    archive/<date>/<code>.html  report copy for that day
    archive/<date>/ranking*.csv candidate CSVs
    assets/site.css|site.js|favicon.svg
    health.txt / status.json / site_data.json
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .daily import qa_status
from .report.format import TEMPLATE_DIR
from .site_assets import SITE_CSS, SITE_JS

SITE_NAME = "龟龟策略 · 每日研究"
DEFAULT_BASE_URL = "https://daily.polygon1865.com"
FAVICON_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<rect width="64" height="64" rx="14" fill="#1f6f4a"/>'
    '<text x="32" y="45" font-family="system-ui,sans-serif" font-size="34" '
    'font-weight="700" text-anchor="middle" fill="#fff">龟</text></svg>'
)

_VERDICT_RE = re.compile(r"\*\*(买入|观察|排除|减持)\*\*")
_QR_VERDICT_RE = re.compile(r'class="qr-verdict[^"]*">\s*(买入|观察|排除|减持)\s*<')
_VERDICT_CLASS = {"买入": "buy", "观察": "watch", "排除": "reject", "减持": "reject"}
_VERDICT_ORDER = {"买入": 0, "观察": 1, "排除": 2, "减持": 3}


@dataclass(frozen=True)
class SiteReport:
    code: str
    name: str = ""
    market: str = ""
    rank: int = 0
    market_rank: int = 0
    status: str = "unknown"
    qa: str = "UNKNOWN"
    research: str = "off"
    research_reason: str = ""
    pdf: str = "none"
    snapshot_id: str = ""
    numeric_coverage: str = ""
    report_href: str = ""
    error: str = ""
    industry: str = ""
    floor: str = ""
    price: str = ""
    premium: str = ""
    margin: str = ""
    gg: str = ""
    r: str = ""
    ii: str = ""
    payout: str = ""
    verdict: str = ""
    thesis: str = ""


@dataclass(frozen=True)
class Candidate:
    rank: int
    market_rank: int = 0
    code: str = ""
    name: str = ""
    market: str = "A"
    channel: str = ""
    roe: str = ""
    payout: str = ""
    r: str = ""
    gg: str = ""
    ii: str = ""
    margin: str = ""
    pe: str = ""
    pb: str = ""
    score: str = ""
    turnover: str = ""
    verdict: str = ""
    deep: bool = False


@dataclass(frozen=True)
class DayRecord:
    date: str
    trade_date: str = ""
    reports: tuple[SiteReport, ...] = ()
    a_candidates: int = 0
    hk_candidates: int = 0
    screen_source: str = ""


@dataclass(frozen=True)
class SiteBuild:
    release: Path
    reports: tuple[SiteReport, ...]
    health: str

    @property
    def path(self) -> Path:
        return self.release


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _manifest_values(path: Path) -> tuple[str, str]:
    payload = _load_json(path)
    return (
        str(payload.get("snapshot_id") or ""),
        str(payload.get("numeric_coverage") or ""),
    )


def _metric_display(metrics: dict[str, Any], key: str) -> str:
    metric = metrics.get(key)
    if not isinstance(metric, dict):
        return ""
    return str(metric.get("display") or "")


def _fmt_local(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return ""


_PLACEHOLDER = re.compile(r"\{\{(?:metric|fact):([^}]+)\}\}")


def _replace_placeholders(text: str, metrics: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = _metric_display(metrics, match.group(1))
        return value or "—"

    return _PLACEHOLDER.sub(replace, text)


def _date_key(label: str) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", label)
    return match.group(1) if match else label


def _percent(value: str) -> str:
    if not value:
        return ""
    if value.endswith("%"):
        return value
    try:
        return f"{float(value):.2f}%"
    except ValueError:
        return value


def _number(value: str) -> str:
    if not value:
        return ""
    try:
        return f"{float(value):,.2f}"
    except ValueError:
        return value


def _numeric(value: str) -> float:
    """Parse a display string such as ``"5.33%"`` or ``"1,234.5"``."""

    cleaned = str(value or "").strip().replace(",", "").rstrip("%")
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _row_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _verdict_class(verdict: str) -> str:
    return _VERDICT_CLASS.get(verdict, "muted")


def _verdict_from_markdown(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    for line in text.splitlines()[:60]:
        match = _VERDICT_RE.search(line)
        if match:
            return match.group(1)
    return ""


def _verdict_from_html(text: str) -> str:
    match = _QR_VERDICT_RE.search(text)
    return match.group(1) if match else ""


def _canonical(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _copy_file(source: Path, destination: Path) -> None:
    """Hardlink when possible: archive copies dominate a release's size."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, destination)
        return
    except OSError:
        pass
    shutil.copyfile(source, destination)


def _rewrite_back_links(text: str, back_href: str) -> str:
    for pattern in (
        r'href="(?:\.\./)*(?:day|archive)/[^"]+/index\.html"',
        r'href="(?:\.\./)*index\.html"',
        r'href="/"',
    ):
        text = re.sub(pattern, f'href="{back_href}"', text)
    return text


# ---------------------------------------------------------------------------
# Collection
# ---------------------------------------------------------------------------


def _report_lede(
    *,
    verdict: str,
    industry: str,
    r: str,
    gg: str,
    ii: str,
    margin: str,
    floor: str,
    price: str,
    premium: str,
    currency: str = "",
    price_local: str = "",
    currency_local: str = "",
) -> str:
    """Controlled first-screen summary.

    Deliberately not free text: the site used to print the first research
    claim here, which turned LLM fabrication into the company's public profile.
    """

    parts: list[str] = []
    if verdict:
        parts.append(f"结论 {verdict}")
    if industry:
        parts.append(f"行业 {industry}")
    if r or gg:
        parts.append(f"R {r} / GG {gg} vs 门槛 {ii}")
    if margin:
        parts.append(f"安全边际 {margin}")
    if floor and price:
        price_text = f"{price} {currency}".strip() if currency else price
        if price_local and currency_local and currency_local != currency:
            parts.append(
                f"底价 {floor} / 现价 {price_text}（报价 {price_local} {currency_local}，溢价 {premium}）"
            )
        else:
            parts.append(f"底价 {floor} / 现价 {price_text}（溢价 {premium}）")
    return " ｜ ".join(parts) or "暂无结论数据"


def _report_details(code_dir: Path) -> dict[str, Any]:
    snapshot = code_dir / "snapshot"
    metrics = _load_json(snapshot / "metrics.json")
    inputs = _load_json(snapshot / "inputs.json")
    details = {
        "industry": str(
            inputs.get("industry_label") or inputs.get("industry_name") or ""
        ),
        "floor": _metric_display(metrics, "floor"),
        "price": _metric_display(metrics, "price"),
        "premium": _metric_display(metrics, "premium"),
        "margin": _metric_display(metrics, "margin"),
        "gg": _metric_display(metrics, "gg"),
        "r": _metric_display(metrics, "r"),
        "ii": _metric_display(metrics, "ii"),
        "payout": _metric_display(metrics, "payout"),
        "verdict": _verdict_from_markdown(code_dir / "analysis_report.md"),
    }
    details["thesis"] = _report_lede(
        verdict=details["verdict"],
        industry=details["industry"],
        r=details["r"],
        gg=details["gg"],
        ii=details["ii"],
        margin=details["margin"],
        floor=details["floor"],
        price=details["price"],
        premium=details["premium"],
        currency=str(inputs.get("currency") or ""),
        price_local=_fmt_local((inputs.get("quote") or {}).get("close_local")),
        currency_local=str((inputs.get("quote") or {}).get("currency_local") or ""),
    )
    return details


def _report_from_dir(code_dir: Path) -> SiteReport:
    qa = qa_status(code_dir / "qa.json")
    snapshot_id, coverage = _manifest_values(code_dir / "snapshot" / "manifest.json")
    research_path = code_dir / "snapshot" / "research.json"
    report_path = code_dir / "analysis_report.html"
    status = "ok" if qa in {"PASS", "WARN"} and report_path.is_file() else "failed"
    details = _report_details(code_dir)
    return SiteReport(
        code=code_dir.name,
        name=str(
            (_load_json(code_dir / "snapshot" / "inputs.json").get("name") or "")
        ),
        market="HK" if code_dir.name.endswith(".HK") else "A",
        status=status,
        qa=qa,
        research="on" if research_path.is_file() else "off",
        research_reason="",
        snapshot_id=snapshot_id,
        numeric_coverage=coverage,
        report_href="",
        **details,
    )


def collect_reports(day_dir: Path) -> list[SiteReport]:
    """Collect status records, falling back to scanning code directories."""

    status = _load_json(day_dir / "status.json")
    rows = status.get("stocks")
    if isinstance(rows, list) and rows:
        reports: list[SiteReport] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "").strip()
            if not code:
                continue
            details = _report_details(day_dir / code)
            reports.append(
                SiteReport(
                    code=code,
                    name=str(row.get("name") or ""),
                    market=str(row.get("market") or ("HK" if code.endswith(".HK") else "A")),
                    rank=int(row.get("rank") or 0),
                    status=str(row.get("status") or "failed"),
                    qa=str(row.get("qa") or "UNKNOWN"),
                    research=str(row.get("research") or "off"),
                    research_reason=str(row.get("research_reason") or ""),
                    pdf=str(row.get("pdf") or "none"),
                    snapshot_id=str(row.get("snapshot_id") or ""),
                    numeric_coverage=str(row.get("numeric_coverage") or ""),
                    report_href="",
                    error=str(row.get("error") or ""),
                    **details,
                )
            )
        return reports

    reports = []
    for code_dir in sorted(day_dir.iterdir() if day_dir.is_dir() else []):
        if not code_dir.is_dir() or not (code_dir / "qa.json").is_file():
            continue
        reports.append(_report_from_dir(code_dir))
    return reports


def collect_candidates(day_dir: Path) -> list[Candidate]:
    """Read the fast rankings (A share + HK) and join the deep verdicts."""

    candidates: list[Candidate] = []
    fast_path = day_dir / "ranking.csv"
    if fast_path.is_file():
        with fast_path.open(encoding="utf-8-sig", newline="") as handle:
            fast_rows = list(csv.DictReader(handle))
        deep_rows: dict[str, dict[str, str]] = {}
        deep_path = day_dir / "ranking_deep.csv"
        if deep_path.is_file():
            with deep_path.open(encoding="utf-8-sig", newline="") as handle:
                for row in csv.DictReader(handle):
                    code = _row_value(row, "code", "ts_code")
                    if code:
                        deep_rows[code] = row
        for index, row in enumerate(fast_rows, start=1):
            code = _row_value(row, "code", "ts_code")
            if not code:
                continue
            deep_row = deep_rows.get(code, {})
            candidates.append(
                Candidate(
                    rank=index,
                    code=code,
                    name=_row_value(row, "name"),
                    market="A",
                    channel=_row_value(row, "channel"),
                    roe=_percent(_row_value(row, "roe")),
                    payout=_percent(_row_value(row, "payout")),
                    r=_percent(_row_value(deep_row, "R%") or _row_value(row, "R%")),
                    gg=_percent(_row_value(deep_row, "GG%") or _row_value(row, "GG%")),
                    ii=_percent(_row_value(deep_row, "II%") or _row_value(row, "II%")),
                    margin=_percent(
                        _row_value(deep_row, "margin") or _row_value(row, "margin")
                    ),
                    pe=_number(_row_value(row, "pe")),
                    pb=_number(_row_value(row, "pb")),
                    verdict=_row_value(deep_row, "verdict"),
                    deep=bool(deep_row),
                )
            )
    hk_path = day_dir / "ranking_hk.csv"
    if hk_path.is_file():
        with hk_path.open(encoding="utf-8-sig", newline="") as handle:
            for index, row in enumerate(csv.DictReader(handle), start=1):
                code = _row_value(row, "code", "ts_code")
                if not code:
                    continue
                candidates.append(
                    Candidate(
                        rank=index,
                        code=code,
                        name=_row_value(row, "name"),
                        market="HK",
                        channel=_row_value(row, "channel") or "HK",
                        roe=_percent(_row_value(row, "roe")),
                        payout=_percent(_row_value(row, "payout")),
                        r=_percent(_row_value(row, "R%")),
                        gg=_percent(_row_value(row, "GG%")),
                        ii=_percent(_row_value(row, "II%")),
                        margin=_percent(_row_value(row, "margin")),
                        pe=_number(_row_value(row, "pe")),
                        pb=_number(_row_value(row, "pb")),
                        score=_number(_row_value(row, "score")),
                        turnover=_number(_row_value(row, "turnover")),
                        verdict=_row_value(row, "verdict"),
                        deep=True,
                    )
                )
    return candidates


# ---------------------------------------------------------------------------
# History from prior releases
# ---------------------------------------------------------------------------


def _report_from_payload(payload: dict[str, Any]) -> SiteReport | None:
    code = str(payload.get("code") or "").strip()
    if not code:
        return None
    return SiteReport(
        code=code,
        name=str(payload.get("name") or ""),
        market=str(payload.get("market") or ("HK" if code.endswith(".HK") else "A")),
        rank=int(payload.get("rank") or 0),
        market_rank=int(payload.get("market_rank") or 0),
        status=str(payload.get("status") or "failed"),
        qa=str(payload.get("qa") or "UNKNOWN"),
        research=str(payload.get("research") or "off"),
        research_reason=str(payload.get("research_reason") or ""),
        pdf=str(payload.get("pdf") or "none"),
        snapshot_id=str(payload.get("snapshot_id") or ""),
        numeric_coverage=str(payload.get("numeric_coverage") or ""),
        report_href="",
        error=str(payload.get("error") or ""),
        industry=str(payload.get("industry") or ""),
        floor=str(payload.get("floor") or ""),
        price=str(payload.get("price") or ""),
        premium=str(payload.get("premium") or ""),
        margin=str(payload.get("margin") or ""),
        gg=str(payload.get("gg") or ""),
        r=str(payload.get("r") or ""),
        ii=str(payload.get("ii") or ""),
        payout=str(payload.get("payout") or ""),
        verdict=str(payload.get("verdict") or ""),
        thesis=str(payload.get("thesis") or ""),
    )


def _candidate_from_payload(payload: dict[str, Any]) -> Candidate | None:
    code = str(payload.get("code") or "").strip()
    if not code:
        return None
    return Candidate(
        rank=int(payload.get("rank") or 0),
        market_rank=int(payload.get("market_rank") or 0),
        code=code,
        name=str(payload.get("name") or ""),
        market=str(payload.get("market") or ("HK" if code.endswith(".HK") else "A")),
        channel=str(payload.get("channel") or ""),
        roe=str(payload.get("roe") or ""),
        payout=str(payload.get("payout") or ""),
        r=str(payload.get("r") or ""),
        gg=str(payload.get("gg") or ""),
        ii=str(payload.get("ii") or ""),
        margin=str(payload.get("margin") or ""),
        pe=str(payload.get("pe") or ""),
        pb=str(payload.get("pb") or ""),
        score=str(payload.get("score") or ""),
        turnover=str(payload.get("turnover") or ""),
        verdict=str(payload.get("verdict") or ""),
        deep=bool(payload.get("deep")),
    )


def _counts_from_payloads(payloads: Any) -> tuple[int, int]:
    a_count = hk_count = 0
    if isinstance(payloads, list):
        for payload in payloads:
            if not isinstance(payload, dict):
                continue
            code = str(payload.get("code") or "")
            market = str(payload.get("market") or ("HK" if code.endswith(".HK") else "A"))
            if market == "HK":
                hk_count += 1
            else:
                a_count += 1
    return a_count, hk_count


def _records_from_release(release: Path) -> list[DayRecord]:
    data = _load_json(release / "site_data.json")
    records: list[DayRecord] = []
    history = data.get("history")
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            date = str(item.get("date") or "")
            if not date:
                continue
            reports = [
                report
                for report in (
                    _report_from_payload(payload)
                    for payload in item.get("reports") or []
                    if isinstance(payload, dict)
                )
                if report is not None
            ]
            records.append(
                DayRecord(
                    date=_date_key(date),
                    trade_date=str(item.get("trade_date") or ""),
                    reports=tuple(reports),
                    a_candidates=int(item.get("a_candidates") or 0),
                    hk_candidates=int(item.get("hk_candidates") or 0),
                    screen_source=str(item.get("screen_source") or ""),
                )
            )
    date = str(data.get("date") or "")
    if date:
        reports = [
            report
            for report in (
                _report_from_payload(payload)
                for payload in data.get("reports") or []
                if isinstance(payload, dict)
            )
            if report is not None
        ]
        a_candidates, hk_candidates = _counts_from_payloads(data.get("candidates"))
        records.append(
            DayRecord(
                date=_date_key(date),
                trade_date=str(data.get("trade_date") or ""),
                reports=tuple(reports),
                a_candidates=a_candidates,
                hk_candidates=hk_candidates,
                screen_source=str(data.get("screen_source") or ""),
            )
        )
    if records:
        return records
    # Legacy release: status.json only.
    status = _load_json(release / "status.json")
    label = str(status.get("date") or release.name)
    rows = status.get("stocks")
    reports = [
        report
        for report in (
            _report_from_payload(row) for row in rows or [] if isinstance(row, dict)
        )
        if report is not None
    ]
    return [
        DayRecord(
            date=_date_key(label),
            trade_date=str(status.get("trade_date") or ""),
            reports=tuple(reports),
        )
    ]


def history_days(site_root: Path) -> dict[str, DayRecord]:
    """Return the newest record per data day across prior releases."""

    releases = site_root / "releases"
    if not releases.is_dir():
        return {}
    days: dict[str, DayRecord] = {}
    ordered = sorted(
        (child for child in releases.iterdir() if child.is_dir()),
        key=lambda child: child.stat().st_mtime if child.exists() else 0,
    )
    for release in ordered:
        for record in _records_from_release(release):
            days[record.date] = record
    return days


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _sorted_reports(reports: Sequence[SiteReport]) -> list[SiteReport]:
    def key(report: SiteReport) -> tuple[int, float, int]:
        order = _VERDICT_ORDER.get(report.verdict, 9)
        return (order, -_numeric(report.margin), report.rank)

    return sorted(reports, key=key)


def _report_row(
    report: SiteReport,
    *,
    stock_prefix: str | None = None,
    report_prefix: str | None = None,
    priority: bool = False,
) -> dict[str, Any]:
    return {
        "rank": report.rank,
        "code": report.code,
        "name": report.name,
        "market": report.market or ("HK" if report.code.endswith(".HK") else "A"),
        "verdict": report.verdict,
        "verdict_class": _verdict_class(report.verdict),
        "qa": report.qa,
        "status": report.status,
        "error": report.error,
        "research": report.research,
        "research_reason": report.research_reason,
        "r": report.r,
        "gg": report.gg,
        "ii": report.ii,
        "margin": report.margin,
        "floor": report.floor,
        "price": report.price,
        "premium": report.premium,
        "payout": report.payout,
        "stock_href": (
            f"{stock_prefix}{quote(report.code)}.html" if stock_prefix is not None else ""
        ),
        "report_href": (
            f"{report_prefix or ''}{quote(report.code)}.html"
            if report_prefix is not None
            else ""
        ),
        "priority": priority,
    }


def _candidate_row(
    candidate: Candidate,
    *,
    verdict_map: dict[str, SiteReport],
    stock_prefix: str = "",
) -> dict[str, Any]:
    report = verdict_map.get(candidate.code)
    verdict = report.verdict if report else candidate.verdict
    return {
        "rank": candidate.market_rank or candidate.rank,
        "code": candidate.code,
        "name": candidate.name,
        "market": candidate.market,
        "channel": candidate.channel,
        "r": candidate.r,
        "gg": candidate.gg,
        "ii": candidate.ii or (report.ii if report else ""),
        "margin": candidate.margin,
        "margin_number": _numeric(candidate.margin),
        "pe": candidate.pe,
        "pb": candidate.pb,
        "turnover": candidate.turnover,
        "verdict": verdict,
        "verdict_class": _verdict_class(verdict),
        "stock_href": (
            f"{stock_prefix}{quote(candidate.code)}.html" if report and stock_prefix else ""
        ),
    }


def _diff_rows(
    current: Sequence[SiteReport], previous: Sequence[SiteReport]
) -> dict[str, Any]:
    now = {report.code: report for report in current}
    before = {report.code: report for report in previous}
    new = [now[code] for code in now if code not in before]
    dropped = [before[code] for code in before if code not in now]
    changed = [
        (before[code], now[code])
        for code in now
        if code in before and before[code].verdict and now[code].verdict
        and before[code].verdict != now[code].verdict
    ]
    new_rows = [
        {
            "code": report.code,
            "name": report.name,
            "href": f"stock/{quote(report.code)}.html",
        }
        for report in _sorted_reports(new)
    ]
    changed_rows = [
        {
            "code": report.code,
            "name": report.name,
            "href": f"stock/{quote(report.code)}.html",
            "was": old.verdict,
            "now": report.verdict,
        }
        for old, report in sorted(
            changed, key=lambda pair: _VERDICT_ORDER.get(pair[1].verdict, 9)
        )
    ]
    dropped_rows = [
        {"code": report.code, "name": report.name}
        for report in _sorted_reports(dropped)
    ]
    return {
        "new": new_rows,
        "dropped": dropped_rows,
        "changed": changed_rows,
        "total": len(new_rows) + len(dropped_rows) + len(changed_rows),
    }


def _page_context(
    *,
    base: str,
    nav_active: str,
    day: str,
    trade_date: str,
    generated_at: str,
    title: str,
    description: str,
    canonical_path: str,
    base_url: str,
) -> dict[str, Any]:
    assets = _asset_names()
    return {
        "base": base,
        "nav_active": nav_active,
        "date_label": day,
        "date_key": day,
        "trade_date": trade_date,
        "generated_at": generated_at,
        "title": title,
        "description": description,
        "canonical": _canonical(base_url, canonical_path),
        "site_name": SITE_NAME,
        "asset_css": assets["css"],
        "asset_js": assets["js"],
        "asset_favicon": assets["favicon"],
    }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _unique_release(site_root: Path, label: str) -> Path:
    release = site_root / "releases" / label
    if not release.exists():
        return release
    counter = 1
    while release.exists():
        release = site_root / "releases" / f"{label}-{counter}"
        counter += 1
    return release


def _asset_names() -> dict[str, str]:
    """Content-hashed asset URLs so browsers and CDNs never pair new HTML with old CSS."""

    def digest(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:10]

    return {
        "css": f"assets/site.{digest(SITE_CSS)}.css",
        "js": f"assets/site.{digest(SITE_JS)}.js",
        "favicon": f"assets/favicon.{digest(FAVICON_SVG)}.svg",
    }


def _write_assets(release: Path) -> None:
    names = _asset_names()
    assets = release / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "site.css").write_text(SITE_CSS, encoding="utf-8")
    (assets / "site.js").write_text(SITE_JS, encoding="utf-8")
    (assets / "favicon.svg").write_text(FAVICON_SVG, encoding="utf-8")
    (release / names["css"]).write_text(SITE_CSS, encoding="utf-8")
    (release / names["js"]).write_text(SITE_JS, encoding="utf-8")
    (release / names["favicon"]).write_text(FAVICON_SVG, encoding="utf-8")


def build_site(
    day_dir: Path,
    site_root: Path,
    *,
    date_label: str | None = None,
    reports: Sequence[SiteReport] | None = None,
    candidates: Sequence[Candidate] | None = None,
    base_url: str | None = None,
) -> Path:
    """Build an archived release; never touches ``current``."""

    reports = list(reports) if reports is not None else collect_reports(day_dir)
    candidates = (
        list(candidates) if candidates is not None else collect_candidates(day_dir)
    )
    if not reports:
        raise ValueError(f"no reports to publish: {day_dir}")

    status = _load_json(day_dir / "status.json")
    trade_date = str(status.get("trade_date") or "")
    screen_source = str(status.get("screen_source") or "")
    label = _date_key(date_label or day_dir.name)
    base_url = base_url or os.environ.get("TURTLE_SITE_BASE_URL") or DEFAULT_BASE_URL
    generated_at = datetime.now().isoformat(timespec="seconds")

    a_candidates = sum(candidate.market == "A" for candidate in candidates)
    hk_candidates = sum(candidate.market == "HK" for candidate in candidates)
    days = history_days(site_root)
    days[label] = DayRecord(
        date=label,
        trade_date=trade_date,
        reports=tuple(reports),
        a_candidates=a_candidates,
        hk_candidates=hk_candidates,
        screen_source=screen_source,
    )

    release = _unique_release(site_root, label)
    release.mkdir(parents=True)
    _write_assets(release)
    environment = _environment()

    # Current day: full report copies + archived copies.
    current_reports: list[SiteReport] = []
    for report in reports:
        source = day_dir / report.code / "analysis_report.html"
        if source.is_file():
            text = source.read_text(encoding="utf-8")
            (release / "report").mkdir(parents=True, exist_ok=True)
            (release / "report" / f"{report.code}.html").write_text(
                _rewrite_back_links(text, f"../stock/{quote(report.code)}.html"),
                encoding="utf-8",
            )
            archive_path = release / "archive" / label / f"{report.code}.html"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text(
                _rewrite_back_links(text, f"../../archive/{label}/index.html"),
                encoding="utf-8",
            )
        current_reports.append(
            replace(
                report,
                report_href=f"report/{quote(report.code)}.html",
                market=report.market or ("HK" if report.code.endswith(".HK") else "A"),
            )
        )

    for ranking_name in ("ranking.csv", "ranking_deep.csv", "ranking_hk.csv"):
        ranking = day_dir / ranking_name
        if ranking.is_file():
            _copy_file(ranking, release / ranking_name)
            _copy_file(ranking, release / "archive" / label / ranking_name)

    # Prior days: copy archived reports, rewriting their back links.
    for key, record in sorted(days.items()):
        if key == label:
            continue
        sources = {
            report.code: _prior_report_source(
                site_root, key, report.code, exclude=release
            )
            for report in record.reports
        }
        destination = release / "archive" / key
        destination.mkdir(parents=True, exist_ok=True)
        updated: list[SiteReport] = []
        for report in record.reports:
            verdict = report.verdict
            report_source = sources.get(report.code)
            if report_source is not None:
                text = report_source.read_text(encoding="utf-8")
                if not verdict:
                    verdict = _verdict_from_html(text)
                target = destination / f"{report.code}.html"
                back_href = f"../../archive/{key}/index.html"
                if f'href="{back_href}"' in text:
                    _copy_file(report_source, target)
                else:
                    target.write_text(
                        _rewrite_back_links(text, back_href), encoding="utf-8"
                    )
            updated.append(replace(report, verdict=verdict))
        days[key] = replace(record, reports=tuple(updated))
        for ranking_name in ("ranking.csv", "ranking_deep.csv", "ranking_hk.csv"):
            ranking_source = _prior_ranking_source(
                site_root, key, ranking_name, exclude=release
            )
            if ranking_source is not None:
                _copy_file(ranking_source, destination / ranking_name)

    ordered_days = sorted(days)

    # --- home ---------------------------------------------------------------
    ordered_reports = _sorted_reports(current_reports)
    rows = [
        _report_row(
            report,
            stock_prefix="stock/",
            report_prefix="report/",
            priority=index < 5,
        )
        for index, report in enumerate(ordered_reports)
    ]
    previous_key = ordered_days[-2] if len(ordered_days) > 1 else ""
    diff: dict[str, Any] = {}
    if previous_key:
        diff = _diff_rows(current_reports, list(days[previous_key].reports))
        diff["previous"] = previous_key
    passed = sum(
        report.status == "ok" and report.qa in {"PASS", "WARN"} for report in reports
    )
    failed = len(reports) - passed
    llm_on = sum(1 for report in reports if report.research == "on")
    research_fallback = sum(
        1 for report in reports if report.research in {"fallback", "off"}
    )
    home = environment.get_template("site_home.html.j2").render(
        **_page_context(
            base="",
            nav_active="home",
            day=label,
            trade_date=trade_date,
            generated_at=generated_at,
            title=f"{SITE_NAME} · {label}",
            description=f"{label} 的 A 股与港股研究报告：{len(reports)} 份报告，按结论与安全边际排序。",
            canonical_path="",
            base_url=base_url,
        ),
        reports=rows,
        total=len(reports),
        passed=passed,
        failed=failed,
        a_count=sum((report.market or "") == "A" for report in current_reports),
        hk_count=sum(report.market == "HK" for report in current_reports),
        a_candidates=a_candidates,
        hk_candidates=hk_candidates,
        llm_on=llm_on,
        research_fallback=research_fallback,
        diff=diff,
    )
    (release / "index.html").write_text(home, encoding="utf-8")

    # --- screener -----------------------------------------------------------
    verdict_map = {report.code: report for report in current_reports}
    a_rows = [
        _candidate_row(candidate, verdict_map=verdict_map, stock_prefix="stock/")
        for candidate in candidates
        if candidate.market == "A"
    ]
    hk_rows = [
        _candidate_row(candidate, verdict_map=verdict_map, stock_prefix="stock/")
        for candidate in candidates
        if candidate.market == "HK"
    ]
    screener = environment.get_template("site_screener.html.j2").render(
        **_page_context(
            base="",
            nav_active="screener",
            day=label,
            trade_date=trade_date,
            generated_at=generated_at,
            title=f"筛选器 · {SITE_NAME}",
            description=f"{label} 候选池：A 股 {len(a_rows)} 只、港股 {len(hk_rows)} 只，含穿透回报率与安全边际。",
            canonical_path="screener.html",
            base_url=base_url,
        ),
        market="A",
        a_rows=a_rows,
        hk_rows=hk_rows,
    )
    (release / "screener.html").write_text(screener, encoding="utf-8")

    # --- method -------------------------------------------------------------
    method = environment.get_template("site_method.html.j2").render(
        **_page_context(
            base="",
            nav_active="method",
            day=label,
            trade_date=trade_date,
            generated_at=generated_at,
            title=f"方法说明 · {SITE_NAME}",
            description="日报的计算口径、数据来源与已知限制。",
            canonical_path="method.html",
            base_url=base_url,
        )
    )
    (release / "method.html").write_text(method, encoding="utf-8")

    # --- archive index ------------------------------------------------------
    archive_rows = []
    for key in sorted(ordered_days, reverse=True):
        record = days[key]
        verdicts = [report.verdict for report in record.reports]
        archive_rows.append(
            {
                "date": key,
                "href": f"{key}/index.html",
                "reports": len(record.reports),
                "passed": sum(
                    report.status == "ok" and report.qa == "PASS"
                    for report in record.reports
                ),
                "failed": sum(
                    not (report.status == "ok" and report.qa == "PASS")
                    for report in record.reports
                ),
                "buy": verdicts.count("买入"),
                "watch": verdicts.count("观察"),
                "reject": verdicts.count("排除") + verdicts.count("减持"),
                "a_candidates": record.a_candidates,
                "hk_candidates": record.hk_candidates,
            }
        )
    archive = environment.get_template("site_archive.html.j2").render(
        **_page_context(
            base="../",
            nav_active="archive",
            day=label,
            trade_date=trade_date,
            generated_at=generated_at,
            title=f"存档 · {SITE_NAME}",
            description=f"共 {len(archive_rows)} 个数据日的研究记录。",
            canonical_path="archive/",
            base_url=base_url,
        ),
        days=archive_rows,
    )
    (release / "archive").mkdir(exist_ok=True)
    (release / "archive" / "index.html").write_text(archive, encoding="utf-8")

    # --- per-day pages ------------------------------------------------------
    for index, key in enumerate(ordered_days):
        record = days[key]
        day_reports = [
            _report_row(
                report,
                report_prefix="",
                priority=position < 5,
            )
            for position, report in enumerate(_sorted_reports(record.reports))
        ]
        page = environment.get_template("site_day.html.j2").render(
            **_page_context(
                base="../../",
                nav_active="archive",
                day=key,
                trade_date=record.trade_date,
                generated_at=generated_at,
                title=f"{key} 研究记录 · {SITE_NAME}",
                description=f"{key} 的 {len(record.reports)} 份研究报告与候选池。",
                canonical_path=f"archive/{key}/",
                base_url=base_url,
            ),
            reports=day_reports,
            total=len(record.reports),
            passed=sum(
                report.status == "ok" and report.qa == "PASS"
                for report in record.reports
            ),
            failed=sum(
                not (report.status == "ok" and report.qa == "PASS")
                for report in record.reports
            ),
            a_candidates=record.a_candidates,
            hk_candidates=record.hk_candidates,
            prev_href=(
                f"../{ordered_days[index - 1]}/index.html" if index > 0 else ""
            ),
            next_href=(
                f"../{ordered_days[index + 1]}/index.html"
                if index + 1 < len(ordered_days)
                else ""
            ),
        )
        (release / "archive" / key / "index.html").write_text(page, encoding="utf-8")

    # --- stock pages --------------------------------------------------------
    current_codes = {report.code for report in current_reports}
    latest_by_code: dict[str, tuple[str, SiteReport]] = {}
    for key in ordered_days:
        for report in days[key].reports:
            latest_by_code[report.code] = (key, report)
    for code in sorted(latest_by_code):
        last_key, report = latest_by_code[code]
        points = []
        for key in sorted(ordered_days, reverse=True):
            match = next(
                (item for item in days[key].reports if item.code == code), None
            )
            if match is None:
                continue
            archived = release / "archive" / key / f"{code}.html"
            points.append(
                {
                    "date": key,
                    "verdict": match.verdict,
                    "verdict_class": _verdict_class(match.verdict),
                    "price": match.price,
                    "floor": match.floor,
                    "margin": match.margin,
                    "report_href": (
                        f"../archive/{key}/{quote(code)}.html" if archived.is_file() else ""
                    ),
                }
            )
        if code in current_codes:
            report_href = f"../report/{quote(code)}.html"
            day_href = f"../archive/{label}/index.html"
            day_label = label
        else:
            report_href = f"../archive/{last_key}/{quote(code)}.html"
            day_href = f"../archive/{last_key}/index.html"
            day_label = last_key
        page = environment.get_template("site_stock.html.j2").render(
            **_page_context(
                base="../",
                nav_active="home",
                day=label,
                trade_date=trade_date,
                generated_at=generated_at,
                title=f"{report.name or code} · {SITE_NAME}",
                description=(
                    f"{report.name or code}（{code}）的决策摘要、历史记录与报告入口。"
                ),
                canonical_path=f"stock/{code}.html",
                base_url=base_url,
            ),
            report={
                "code": code,
                "name": report.name,
                "market": report.market,
                "verdict": report.verdict,
                "verdict_class": _verdict_class(report.verdict),
                "industry": report.industry,
                "qa": report.qa,
                "numeric_coverage": report.numeric_coverage,
                "price": report.price,
                "floor": report.floor,
                "premium": report.premium,
                "margin": report.margin,
                "r": report.r,
                "gg": report.gg,
                "ii": report.ii,
                "payout": report.payout,
                "thesis": report.thesis,
                "report_href": report_href,
                "day_href": day_href,
                "date_label": day_label,
            },
            history=points,
        )
        (release / "stock").mkdir(exist_ok=True)
        (release / "stock" / f"{code}.html").write_text(page, encoding="utf-8")

    # --- health + data ------------------------------------------------------
    llm_fallback = sum(1 for report in reports if report.research == "fallback")
    llm_off = len(reports) - llm_on - llm_fallback
    pdf_ok = sum(1 for report in reports if report.pdf == "ok")
    health = (
        f"status={'ok' if failed == 0 else ('partial' if passed else 'fail')}\n"
        f"date={label}\n"
        f"trade_date={trade_date}\n"
        f"reports={len(reports)}\n"
        f"candidates={len(candidates)}\n"
        f"days={len(ordered_days)}\n"
        f"qa_pass={passed}\n"
        f"qa_fail={failed}\n"
        f"llm_on={llm_on}\n"
        f"llm_fallback={llm_fallback}\n"
        f"llm_off={llm_off}\n"
        f"pdf_ok={pdf_ok}\n"
        f"pdf_none={len(reports) - pdf_ok}\n"
        f"screen_source={screen_source}\n"
        f"generated_at={generated_at}\n"
    )
    (release / "health.txt").write_text(health, encoding="utf-8")
    status_path = day_dir / "status.json"
    if status_path.is_file():
        shutil.copyfile(status_path, release / "status.json")

    history_payload = [
        {
            "date": key,
            "trade_date": days[key].trade_date,
            "a_candidates": days[key].a_candidates,
            "hk_candidates": days[key].hk_candidates,
            "screen_source": days[key].screen_source,
            "reports": [asdict(report) for report in days[key].reports],
        }
        for key in ordered_days
        if key != label
    ]
    site_data = {
        "date": label,
        "trade_date": trade_date,
        "screen_source": screen_source,
        "reports": [asdict(report) for report in current_reports],
        "candidates": [asdict(candidate) for candidate in candidates],
        "history": history_payload,
    }
    (release / "site_data.json").write_text(
        json.dumps(site_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return release


def _prior_release_for(
    site_root: Path, key: str, *, exclude: Path | None = None
) -> Path | None:
    """Best release that carries the archived report for ``key``."""

    releases = site_root / "releases"
    if not releases.is_dir():
        return None
    skip = exclude.resolve() if exclude is not None else None
    best: tuple[float, Path] | None = None
    for child in releases.iterdir():
        if not child.is_dir():
            continue
        if skip is not None and child.resolve() == skip:
            continue
        archive_dir = child / "archive" / key
        if not archive_dir.is_dir():
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if best is None or mtime > best[0]:
            best = (mtime, child)
    return best[1] if best else None


def _prior_report_source(
    site_root: Path, key: str, code: str, *, exclude: Path | None = None
) -> Path | None:
    release = _prior_release_for(site_root, key, exclude=exclude)
    if release is None:
        return None
    for candidate in (release / "archive" / key / f"{code}.html", release / f"{code}.html"):
        if candidate.is_file():
            return candidate
    return None


def _prior_ranking_source(
    site_root: Path, key: str, name: str, *, exclude: Path | None = None
) -> Path | None:
    release = _prior_release_for(site_root, key, exclude=exclude)
    if release is None:
        return None
    for candidate in (release / "archive" / key / name, release / name):
        if candidate.is_file():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Publishing
# ---------------------------------------------------------------------------


def _remove_current(current: Path) -> None:
    if not os.path.lexists(current):
        return
    if os.name == "nt":
        if current.is_symlink() or current.is_file():
            current.unlink()
            return
        result = subprocess.run(
            ["cmd", "/c", "rmdir", str(current)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            return
        shutil.rmtree(current)
        return
    current.unlink()


def _link_current(release: Path, current: Path) -> bool:
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(current), str(release)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return result.returncode == 0
    try:
        os.symlink(release, current, target_is_directory=True)
    except OSError:
        return False
    return True


def publish_site(release: Path, site_root: Path) -> Path:
    """Point ``current`` at a completed release."""

    site_root.mkdir(parents=True, exist_ok=True)
    current = site_root / "current"
    _remove_current(current)
    if not _link_current(release, current):
        shutil.copytree(release, current)
    return current


def build_and_publish(day_dir: Path, site_root: Path) -> SiteBuild:
    release = build_site(day_dir, site_root)
    publish_site(release, site_root)
    reports = tuple(collect_reports(day_dir))
    health = (release / "health.txt").read_text(encoding="utf-8")
    return SiteBuild(release=release, reports=reports, health=health)
