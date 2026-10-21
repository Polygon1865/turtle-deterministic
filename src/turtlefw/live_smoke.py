"""Live smoke harness for the deterministic report pipeline.

The harness runs the real CLI against a small set of stocks and checks the
artifacts that can be verified without re-implementing the model:

- command exit status
- QA status and failing rows
- snapshot manifest identity and numeric audit status
- required report/data-pack artifacts

It is intentionally separate from pytest: CI is offline, while this runner is
meant for a nightly job or a local pre-release check with a Tushare token.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_CODES = ("600887.SH", "000858.SZ", "600519.SH")
DEFAULT_MIN_COVERAGE = 0.9999
Runner = Callable[[str, Path], int]


@dataclass(frozen=True, slots=True)
class SmokeResult:
    code: str
    ok: bool
    detail: str
    snapshot_id: str = ""
    numeric_coverage: float = 0.0
    qa_status: str = ""


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected object: {path}")
    return payload


def _default_runner(code: str, root: Path) -> int:
    command = [
        sys.executable,
        "-m",
        "turtlefw",
        "--output-dir",
        str(root),
        "run",
        code,
        "--no-html",
        "--rf",
        "2.0",
        "--rf-source",
        "live-smoke",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            timeout=900,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"live smoke command failed: {exc}", file=sys.stderr)
        return 2
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)
    return completed.returncode


def run_case(
    code: str,
    root: Path | str,
    *,
    runner: Runner | None = None,
    run: bool = True,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> SmokeResult:
    root = Path(root)
    rc = 0
    if run:
        rc = (runner or _default_runner)(code, root)

    failures: list[str] = []
    if run and rc != 0:
        failures.append(f"run exit={rc}")

    base = root / code
    qa_path = base / "qa.json"
    qa_status = ""
    if not qa_path.is_file():
        failures.append("qa.json missing")
    else:
        try:
            qa = _read_json(qa_path)
        except (OSError, ValueError, TypeError) as exc:
            failures.append(f"qa.json invalid: {exc}")
        else:
            qa_status = str(qa.get("status", ""))
            failed = [
                str(row.get("name", ""))
                for row in qa.get("rows", [])
                if str(row.get("status", "")).upper() == "FAIL"
            ]
            if qa_status != "pass" or failed:
                failures.append(f"qa status={qa_status or 'missing'} failed={failed}")

    manifest_path = base / "snapshot" / "manifest.json"
    snapshot_id = ""
    coverage = 0.0
    if not manifest_path.is_file():
        failures.append("snapshot/manifest.json missing")
    else:
        try:
            manifest = _read_json(manifest_path)
        except (OSError, ValueError, TypeError) as exc:
            failures.append(f"manifest invalid: {exc}")
        else:
            snapshot_id = str(manifest.get("snapshot_id", ""))
            if len(snapshot_id) != 32:
                failures.append(f"snapshot_id invalid={snapshot_id!r}")
            if str(manifest.get("code", "")) != code:
                failures.append(f"manifest code={manifest.get('code')!r}")
            numeric_status = str(manifest.get("numeric_status", ""))
            try:
                coverage = float(manifest.get("numeric_coverage", 0) or 0)
            except (TypeError, ValueError):
                coverage = 0.0
            if numeric_status != "pass":
                failures.append(f"numeric status={numeric_status or 'missing'}")
            if coverage < min_coverage:
                failures.append(f"numeric coverage={coverage:.4f}")

    for name in ("analysis_report.md", "data_pack.md"):
        if not (base / name).is_file():
            failures.append(f"{name} missing")

    ok = not failures
    return SmokeResult(
        code=code,
        ok=ok,
        detail="ok" if ok else "; ".join(failures),
        snapshot_id=snapshot_id,
        numeric_coverage=coverage,
        qa_status=qa_status,
    )


def run_suite(
    codes: Sequence[str],
    root: Path | str,
    *,
    runner: Runner | None = None,
    run: bool = True,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> list[SmokeResult]:
    return [
        run_case(
            code,
            root,
            runner=runner,
            run=run,
            min_coverage=min_coverage,
        )
        for code in codes
    ]


def format_report(results: Sequence[SmokeResult]) -> str:
    passed = sum(1 for result in results if result.ok)
    lines = [f"live smoke: {passed}/{len(results)} passed"]
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        snapshot = result.snapshot_id[:8] if result.snapshot_id else "-"
        lines.append(
            f"  {status:<4} {result.code:<12} snapshot={snapshot:<8} "
            f"numeric={result.numeric_coverage:.4f} {result.detail}"
        )
    return "\n".join(lines)


def to_payload(results: Sequence[SmokeResult]) -> dict[str, Any]:
    return {
        "passed": sum(1 for result in results if result.ok),
        "total": len(results),
        "results": [
            {
                "code": result.code,
                "ok": result.ok,
                "detail": result.detail,
                "snapshot_id": result.snapshot_id,
                "numeric_coverage": result.numeric_coverage,
                "qa_status": result.qa_status,
            }
            for result in results
        ],
    }
