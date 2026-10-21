"""Static site builder for the daily Windows host.

The site is intentionally plain HTML.  A failed daily run must never replace
the last successful release: the builder writes a new release directory first
and only then moves the ``current`` junction/symlink.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
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


def _report_from_dir(code_dir: Path) -> SiteReport:
    qa = qa_status(code_dir / "qa.json")
    snapshot_id, coverage = _manifest_values(code_dir / "snapshot" / "manifest.json")
    research_path = code_dir / "snapshot" / "research.json"
    report_path = code_dir / "analysis_report.html"
    status = "ok" if qa in {"PASS", "WARN"} and report_path.is_file() else "failed"
    return SiteReport(
        code=code_dir.name,
        status=status,
        qa=qa,
        research="on" if research_path.is_file() else "off",
        snapshot_id=snapshot_id,
        numeric_coverage=coverage,
        report_href=f"{quote(code_dir.name)}.html" if report_path.is_file() else "",
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
                )
            )
        return reports

    reports = []
    for code_dir in sorted(day_dir.iterdir() if day_dir.is_dir() else []):
        if not code_dir.is_dir() or not (code_dir / "qa.json").is_file():
            continue
        reports.append(_report_from_dir(code_dir))
    return reports


def _render_index(
    *,
    day: str,
    reports: Sequence[SiteReport],
    generated_at: str,
) -> str:
    environment = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = environment.get_template("site_index.html.j2")
    passed = sum(report.qa == "PASS" for report in reports)
    failed = sum(report.qa == "FAIL" for report in reports)
    return template.render(
        day=day,
        reports=reports,
        generated_at=generated_at,
        total=len(reports),
        passed=passed,
        failed=failed,
        ok=bool(reports) and failed == 0,
    )


def build_site(
    day_dir: Path,
    site_root: Path,
    *,
    date_label: str | None = None,
    reports: Sequence[SiteReport] | None = None,
) -> Path:
    """Build a release directory; never touches ``current``."""

    reports = list(reports) if reports is not None else collect_reports(day_dir)
    if not reports:
        raise ValueError(f"no reports to publish: {day_dir}")
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
    index = _render_index(day=label, reports=reports, generated_at=generated_at)
    (release / "index.html").write_text(index, encoding="utf-8")
    passed = sum(report.qa == "PASS" for report in reports)
    failed = sum(report.qa == "FAIL" for report in reports)
    health = (
        f"status={'ok' if failed == 0 else 'fail'}\n"
        f"date={label}\n"
        f"reports={len(reports)}\n"
        f"qa_pass={passed}\n"
        f"qa_fail={failed}\n"
        f"generated_at={generated_at}\n"
    )
    (release / "health.txt").write_text(health, encoding="utf-8")
    status = day_dir / "status.json"
    if status.is_file():
        shutil.copyfile(status, release / "status.json")
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
