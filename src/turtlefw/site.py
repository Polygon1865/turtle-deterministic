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
from dataclasses import dataclass, replace
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
    rank: int = 0
    status: str = "unknown"
    qa: str = "UNKNOWN"
    research: str = "off"
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


@dataclass(frozen=True)
class Candidate:
    rank: int
    code: str
    name: str = ""
    channel: str = ""
    roe: str = ""
    payout: str = ""
    r: str = ""
    gg: str = ""
    ii: str = ""
    margin: str = ""
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


def _report_details(code_dir: Path) -> dict[str, str]:
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
        status=status,
        qa=qa,
        research="on" if research_path.is_file() else "off",
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
                    rank=int(row.get("rank") or 0),
                    status=str(row.get("status") or "failed"),
                    qa=qa,
                    research=str(row.get("research") or "off"),
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
    return candidates


def _render_index(
    *,
    day: str,
    trade_date: str,
    reports: Sequence[SiteReport],
    candidates: Sequence[Candidate],
    generated_at: str,
) -> str:
    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("site_index.html.j2")
    candidate_by_code = {candidate.code: candidate for candidate in candidates}
    normalized: list[SiteReport] = []
    for report in reports:
        candidate = candidate_by_code.get(report.code)
        name = candidate.name if candidate and candidate.name else report.name
        rank = report.rank or (candidate.rank if candidate else 0)
        normalized.append(replace(report, name=name, rank=rank))
    passed = sum(report.qa == "PASS" for report in normalized)
    failed = sum(report.qa == "FAIL" for report in normalized)
    return template.render(
        day=day,
        trade_date=trade_date,
        reports=normalized,
        top_reports=normalized[:3],
        candidates=candidates,
        generated_at=generated_at,
        total=len(normalized),
        candidate_count=len(candidates),
        passed=passed,
        failed=failed,
        ok=bool(normalized) and failed == 0,
    )


def build_site(
    day_dir: Path,
    site_root: Path,
    *,
    date_label: str | None = None,
    reports: Sequence[SiteReport] | None = None,
    candidates: Sequence[Candidate] | None = None,
) -> Path:
    """Build a release directory; never touches ``current``."""

    reports = list(reports) if reports is not None else collect_reports(day_dir)
    candidates = (
        list(candidates) if candidates is not None else collect_candidates(day_dir)
    )
    if not reports:
        raise ValueError(f"no reports to publish: {day_dir}")
    status = _load_json(day_dir / "status.json")
    trade_date = str(status.get("trade_date") or "")
    label = date_label or day_dir.name
    release = site_root / "releases" / label
    if release.exists():
        counter = 1
        while release.exists():
            release = site_root / "releases" / f"{label}-{counter}"
            counter += 1
    release.mkdir(parents=True)

    for report in reports:
        source = day_dir / report.code / "analysis_report.html"
        if source.is_file():
            shutil.copyfile(source, release / f"{report.code}.html")
    generated_at = datetime.now().isoformat(timespec="seconds")
    index = _render_index(
        day=label,
        trade_date=trade_date,
        reports=reports,
        candidates=candidates,
        generated_at=generated_at,
    )
    (release / "index.html").write_text(index, encoding="utf-8")
    passed = sum(report.qa == "PASS" for report in reports)
    failed = sum(report.qa == "FAIL" for report in reports)
    health = (
        f"status={'ok' if failed == 0 else 'fail'}\n"
        f"date={label}\n"
        f"trade_date={trade_date}\n"
        f"reports={len(reports)}\n"
        f"candidates={len(candidates)}\n"
        f"qa_pass={passed}\n"
        f"qa_fail={failed}\n"
        f"generated_at={generated_at}\n"
    )
    (release / "health.txt").write_text(health, encoding="utf-8")
    status_path = day_dir / "status.json"
    if status_path.is_file():
        shutil.copyfile(status_path, release / "status.json")
    for ranking_name in ("ranking.csv", "ranking_deep.csv"):
        ranking = day_dir / ranking_name
        if ranking.is_file():
            shutil.copyfile(ranking, release / ranking_name)
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
