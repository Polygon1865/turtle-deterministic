"""Static site builder for the daily Windows host.

The site is intentionally plain HTML.  A failed daily run must never replace
the last successful release: the builder writes a new release directory first
and only then moves the ``current`` junction/symlink.
"""

from __future__ import annotations

import csv
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


@dataclass(frozen=True)
class SiteReport:
    code: str
    name: str = ""
    market: str = ""
    rank: int = 0
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
    payout: str = ""
    thesis: str = ""
    market_rank: int = 0


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
class SiteBuild:
    release: Path
    reports: tuple[SiteReport, ...]
    health: str

    @property
    def path(self) -> Path:
        return self.release


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


_PLACEHOLDER = re.compile(r"\{\{(?:metric|fact):([^}]+)\}\}")


def _replace_placeholders(text: str, metrics: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        value = _metric_display(metrics, match.group(1))
        return value or "—"

    return _PLACEHOLDER.sub(replace, text)


def _report_details(code_dir: Path) -> dict[str, Any]:
    snapshot = code_dir / "snapshot"
    metrics = _load_json(snapshot / "metrics.json")
    inputs = _load_json(snapshot / "inputs.json")
    research = _load_json(snapshot / "research.json")
    thesis = ""
    claims = research.get("claims")
    if isinstance(claims, list) and claims and isinstance(claims[0], dict):
        thesis = _replace_placeholders(str(claims[0].get("statement") or ""), metrics)
    return {
        "industry": str(inputs.get("industry_name") or ""),
        "floor": _metric_display(metrics, "floor"),
        "price": _metric_display(metrics, "price"),
        "premium": _metric_display(metrics, "premium"),
        "margin": _metric_display(metrics, "margin"),
        "gg": _metric_display(metrics, "gg"),
        "r": _metric_display(metrics, "r"),
        "payout": _metric_display(metrics, "payout"),
        "thesis": thesis,
    }


def _report_from_dir(code_dir: Path) -> SiteReport:
    qa = qa_status(code_dir / "qa.json")
    snapshot_id, coverage = _manifest_values(code_dir / "snapshot" / "manifest.json")
    research_path = code_dir / "snapshot" / "research.json"
    report_path = code_dir / "analysis_report.html"
    status = "ok" if qa in {"PASS", "WARN"} and report_path.is_file() else "failed"
    details = _report_details(code_dir)
    return SiteReport(
        code=code_dir.name,
        market="HK" if code_dir.name.endswith(".HK") else "A",
        status=status,
        qa=qa,
        research="on" if research_path.is_file() else "off",
        research_reason="",
        snapshot_id=snapshot_id,
        numeric_coverage=coverage,
        report_href=f"{quote(code_dir.name)}.html" if report_path.is_file() else "",
        industry=details["industry"],
        floor=details["floor"],
        price=details["price"],
        premium=details["premium"],
        margin=details["margin"],
        gg=details["gg"],
        r=details["r"],
        payout=details["payout"],
        thesis=details["thesis"],
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
            qa = str(row.get("qa") or "UNKNOWN")
            report_path = day_dir / code / "analysis_report.html"
            details = _report_details(day_dir / code)
            reports.append(
                SiteReport(
                    code=code,
                    name=str(row.get("name") or ""),
                    market=str(row.get("market") or ("HK" if code.endswith(".HK") else "A")),
                    rank=int(row.get("rank") or 0),
                    status=str(row.get("status") or "failed"),
                    qa=qa,
                    research=str(row.get("research") or "off"),
                    research_reason=str(row.get("research_reason") or ""),
                    pdf=str(row.get("pdf") or "none"),
                    snapshot_id=str(row.get("snapshot_id") or ""),
                    numeric_coverage=str(row.get("numeric_coverage") or ""),
                    report_href=f"{quote(code)}.html" if report_path.is_file() else "",
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


def _row_value(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


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


def collect_candidates(day_dir: Path) -> list[Candidate]:
    """Read the 100-row fast ranking and join the 20-row deep verdicts."""

    fast_path = day_dir / "ranking.csv"
    if not fast_path.is_file():
        return []
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
    candidates: list[Candidate] = []
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
                verdict=_row_value(deep_row, "verdict"),
                deep=bool(deep_row),
            )
        )
    hk_path = day_dir / "ranking_hk.csv"
    if hk_path.is_file():
        with hk_path.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                code = _row_value(row, "code", "ts_code")
                if not code:
                    continue
                candidates.append(
                    Candidate(
                        rank=len(candidates) + 1,
                        code=code,
                        name=_row_value(row, "name"),
                        market="HK",
                        channel=_row_value(row, "channel") or "HK",
                        roe=_percent(_row_value(row, "roe")),
                        pe=_number(_row_value(row, "pe")),
                        pb=_number(_row_value(row, "pb")),
                        score=_number(_row_value(row, "score")),
                        turnover=_number(_row_value(row, "turnover")),
                        verdict=_row_value(row, "verdict"),
                        deep=True,
                    )
                )
    return candidates


def _date_key(label: str) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})", label)
    return match.group(1) if match else label


def _report_from_payload(payload: dict[str, Any]) -> SiteReport | None:
    code = str(payload.get("code") or "").strip()
    if not code:
        return None
    fields: dict[str, Any] = {
        "code": code,
        "name": str(payload.get("name") or ""),
        "market": str(
            payload.get("market") or ("HK" if code.endswith(".HK") else "A")
        ),
        "rank": int(payload.get("rank") or 0),
        "status": str(payload.get("status") or "failed"),
        "qa": str(payload.get("qa") or "UNKNOWN"),
        "research": str(payload.get("research") or "off"),
        "research_reason": str(payload.get("research_reason") or ""),
        "pdf": str(payload.get("pdf") or "none"),
        "snapshot_id": str(payload.get("snapshot_id") or ""),
        "numeric_coverage": str(payload.get("numeric_coverage") or ""),
        "report_href": "",
        "error": str(payload.get("error") or ""),
        "industry": str(payload.get("industry") or ""),
        "floor": str(payload.get("floor") or ""),
        "price": str(payload.get("price") or ""),
        "premium": str(payload.get("premium") or ""),
        "margin": str(payload.get("margin") or ""),
        "gg": str(payload.get("gg") or ""),
        "r": str(payload.get("r") or ""),
        "payout": str(payload.get("payout") or ""),
        "thesis": str(payload.get("thesis") or ""),
    }
    return SiteReport(**fields)


def _reports_from_release(release: Path) -> tuple[str, str, list[SiteReport]]:
    status = _load_json(release / "status.json")
    data = _load_json(release / "site_data.json")
    date_label = str(data.get("date") or status.get("date") or release.name)
    trade_date = str(data.get("trade_date") or status.get("trade_date") or "")
    payloads = data.get("reports")
    reports: list[SiteReport] = []
    if isinstance(payloads, list):
        for payload in payloads:
            if isinstance(payload, dict):
                report = _report_from_payload(payload)
                if report is not None:
                    reports.append(report)
    if not reports:
        rows = status.get("stocks")
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    report = _report_from_payload(row)
                    if report is not None:
                        reports.append(report)
    return date_label, trade_date, reports


def _prior_releases(site_root: Path) -> list[Path]:
    releases = site_root / "releases"
    if not releases.is_dir():
        return []
    chosen: dict[str, tuple[float, str, Path]] = {}
    for child in releases.iterdir():
        if not child.is_dir() or not (child / "status.json").is_file():
            continue
        date_label, _, _ = _reports_from_release(child)
        key = _date_key(date_label)
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        current = chosen.get(key)
        if current is None or (mtime, child.name) > (current[0], current[1]):
            chosen[key] = (mtime, child.name, child)
    return [item[2] for item in sorted(chosen.values(), key=lambda value: value[0])]


def _tabs(dates: Sequence[str], active: str, *, root: bool) -> list[dict[str, Any]]:
    latest = dates[-1] if dates else active
    tabs: list[dict[str, Any]] = []
    for item in sorted(dates, reverse=True):
        if root:
            href = "index.html" if item == latest else f"day/{item}/index.html"
        elif item == latest:
            href = "../../index.html"
        elif item == active:
            href = "index.html"
        else:
            href = f"../{item}/index.html"
        tabs.append({"date": item, "href": href, "active": item == active})
    return tabs


def _render_index(
    *,
    day: str,
    trade_date: str,
    reports: Sequence[SiteReport],
    candidates: Sequence[Candidate],
    generated_at: str,
    tabs: Sequence[dict[str, Any]],
    ranking_href: str,
    deep_href: str,
    health_href: str,
    ranking_hk_href: str = "",
    screen_source: str = "",
) -> str:
    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("site_index.html.j2")
    candidate_by_code = {candidate.code: candidate for candidate in candidates}
    normalized: list[SiteReport] = []
    market_counts: dict[str, int] = {}
    for report in reports:
        candidate = candidate_by_code.get(report.code)
        name = candidate.name if candidate and candidate.name else report.name
        rank = report.rank or (candidate.rank if candidate else 0)
        market = report.market or "A"
        market_counts[market] = market_counts.get(market, 0) + 1
        normalized.append(
            replace(
                report,
                name=name,
                rank=rank,
                market=market,
                market_rank=market_counts[market],
            )
        )
    passed = sum(report.status == "ok" and report.qa == "PASS" for report in normalized)
    failed = len(normalized) - passed
    hk_count = sum(report.market == "HK" for report in normalized)
    a_count = len(normalized) - hk_count
    candidate_counts: dict[str, int] = {}
    normalized_candidates: list[Candidate] = []
    for candidate in candidates:
        candidate_counts[candidate.market] = candidate_counts.get(candidate.market, 0) + 1
        normalized_candidates.append(
            replace(candidate, market_rank=candidate_counts[candidate.market])
        )
    candidates = normalized_candidates
    return template.render(
        day=day,
        trade_date=trade_date,
        reports=normalized,
        top_reports=normalized[:3],
        candidates=candidates,
        generated_at=generated_at,
        total=len(normalized),
        candidate_count=len(candidates),
        a_candidate_count=sum(candidate.market == "A" for candidate in candidates),
        hk_candidate_count=sum(candidate.market == "HK" for candidate in candidates),
        a_count=a_count,
        hk_count=hk_count,
        passed=passed,
        failed=failed,
        ok=bool(normalized) and failed == 0,
        tabs=tabs,
        ranking_href=ranking_href,
        deep_href=deep_href,
        health_href=health_href,
        ranking_hk_href=ranking_hk_href,
        screen_source=screen_source,
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


def _copy_report_html(source: Path, destination: Path, back_href: str) -> None:
    text = source.read_text(encoding="utf-8")
    for pattern in (
        r'href="/"',
        r'href="(?:\.\./)*day/[^"]+/index\.html"',
    ):
        replaced, count = re.subn(pattern, f'href="{back_href}"', text)
        if count:
            text = replaced
            break
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def build_site(
    day_dir: Path,
    site_root: Path,
    *,
    date_label: str | None = None,
    reports: Sequence[SiteReport] | None = None,
    candidates: Sequence[Candidate] | None = None,
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
    label = date_label or day_dir.name
    day_key = _date_key(label)
    release = site_root / "releases" / label
    if release.exists():
        counter = 1
        while release.exists():
            release = site_root / "releases" / f"{label}-{counter}"
            counter += 1
    release.mkdir(parents=True)
    archive = release / "archive"
    generated_at = datetime.now().isoformat(timespec="seconds")

    # Current day: keep root-level report copies for backward compatibility and
    # write an archive copy used by the date-tab pages.
    current_reports: list[SiteReport] = []
    for report in reports:
        source = day_dir / report.code / "analysis_report.html"
        destination = archive / day_key / f"{report.code}.html"
        if source.is_file():
            _copy_report_html(
                source, release / f"{report.code}.html", f"day/{day_key}/index.html"
            )
            _copy_report_html(
                source,
                destination,
                f"../../day/{day_key}/index.html",
            )
            href = f"archive/{day_key}/{quote(report.code)}.html"
        else:
            href = ""
        current_reports.append(
            replace(
                report,
                report_href=href,
                market=report.market
                or ("HK" if report.code.endswith(".HK") else "A"),
            )
        )
    for ranking_name in ("ranking.csv", "ranking_deep.csv", "ranking_hk.csv"):
        ranking = day_dir / ranking_name
        if ranking.is_file():
            shutil.copyfile(ranking, release / ranking_name)
            (archive / day_key).mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ranking, archive / day_key / ranking_name)

    days: dict[str, tuple[str, list[SiteReport], list[Candidate]]] = {
        day_key: (trade_date, current_reports, candidates)
    }

    # Merge the latest release for each prior date.  A same-date rebuild wins.
    for prior in _prior_releases(site_root):
        prior_label, prior_trade, prior_reports = _reports_from_release(prior)
        prior_key = _date_key(prior_label)
        if not prior_reports or prior_key == day_key:
            continue
        data = _load_json(prior / "site_data.json")
        raw_candidates = data.get("candidates")
        prior_candidates: list[Candidate] = []
        if isinstance(raw_candidates, list):
            for payload in raw_candidates:
                if isinstance(payload, dict):
                    candidate = _candidate_from_payload(payload)
                    if candidate is not None:
                        prior_candidates.append(candidate)
        if not prior_candidates:
            prior_candidates = collect_candidates(prior)
        page_reports: list[SiteReport] = []
        for report in prior_reports:
            source = prior / f"{report.code}.html"
            href = ""
            if source.is_file():
                destination = archive / prior_key / f"{report.code}.html"
                _copy_report_html(
                    source,
                    destination,
                    f"../../day/{prior_key}/index.html",
                )
                href = f"archive/{prior_key}/{quote(report.code)}.html"
            page_reports.append(
                replace(
                    report,
                    report_href=href,
                    market=report.market
                    or ("HK" if report.code.endswith(".HK") else "A"),
                )
            )
        for ranking_name in ("ranking.csv", "ranking_deep.csv", "ranking_hk.csv"):
            ranking = prior / ranking_name
            if ranking.is_file():
                (archive / prior_key).mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ranking, archive / prior_key / ranking_name)
        days[prior_key] = (prior_trade, page_reports, prior_candidates)

    dates = sorted(days)
    for date_key in dates:
        page_dir = release / "day" / date_key
        page_dir.mkdir(parents=True, exist_ok=True)
        page_trade, page_reports, page_candidates = days[date_key]
        page_hrefs = [
            replace(
                report,
                report_href=(
                    f"../../{report.report_href}" if report.report_href else ""
                ),
            )
            for report in page_reports
        ]
        index = _render_index(
            day=date_key,
            trade_date=page_trade,
            reports=page_hrefs,
            candidates=page_candidates,
            generated_at=generated_at,
            tabs=_tabs(dates, date_key, root=False),
            ranking_href=f"../../archive/{date_key}/ranking.csv",
            deep_href=f"../../archive/{date_key}/ranking_deep.csv",
            ranking_hk_href=(
                f"../../archive/{date_key}/ranking_hk.csv"
                if (release / "archive" / date_key / "ranking_hk.csv").is_file()
                else ""
            ),
            health_href="../../health.txt",
        )
        (page_dir / "index.html").write_text(index, encoding="utf-8")

    latest = dates[-1]
    latest_trade, latest_reports, latest_candidates = days[latest]
    index = _render_index(
        day=latest,
        trade_date=latest_trade,
        reports=latest_reports,
        candidates=latest_candidates,
        generated_at=generated_at,
        tabs=_tabs(dates, latest, root=True),
        ranking_href=f"archive/{latest}/ranking.csv",
        deep_href=f"archive/{latest}/ranking_deep.csv",
        ranking_hk_href=(
            f"archive/{latest}/ranking_hk.csv"
            if (release / "archive" / latest / "ranking_hk.csv").is_file()
            else ""
        ),
        health_href="health.txt",
        screen_source=screen_source,
    )
    (release / "index.html").write_text(index, encoding="utf-8")

    passed = sum(report.status == "ok" and report.qa == "PASS" for report in reports)
    failed = len(reports) - passed
    llm_on = sum(1 for report in reports if report.research == "on")
    llm_fallback = sum(1 for report in reports if report.research == "fallback")
    llm_off = len(reports) - llm_on - llm_fallback
    pdf_ok = sum(1 for report in reports if report.pdf == "ok")
    pdf_none = len(reports) - pdf_ok
    status_path = day_dir / "status.json"
    health = (
        f"status={'ok' if failed == 0 else ('partial' if passed else 'fail')}\n"
        f"date={label}\n"
        f"trade_date={trade_date}\n"
        f"reports={len(reports)}\n"
        f"candidates={len(candidates)}\n"
        f"days={len(dates)}\n"
        f"qa_pass={passed}\n"
        f"qa_fail={failed}\n"
        f"llm_on={llm_on}\n"
        f"llm_fallback={llm_fallback}\n"
        f"llm_off={llm_off}\n"
        f"pdf_ok={pdf_ok}\n"
        f"pdf_none={pdf_none}\n"
        f"screen_source={screen_source}\n"
        f"generated_at={generated_at}\n"
    )
    (release / "health.txt").write_text(health, encoding="utf-8")
    if status_path.is_file():
        shutil.copyfile(status_path, release / "status.json")
    site_data = {
        "date": label,
        "trade_date": trade_date,
        "reports": [asdict(report) for report in current_reports],
        "candidates": [asdict(candidate) for candidate in candidates],
    }
    (release / "site_data.json").write_text(
        json.dumps(site_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return release


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
        # A real directory can still be replaced safely by a fallback copy.
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
    """Point ``current`` at a completed release.

    Windows uses a directory junction (no admin rights required); POSIX uses a
    symlink.  If linking fails, a copied ``current`` directory is used so the
    site remains available.
    """

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
