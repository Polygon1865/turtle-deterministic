"""Run the real-PDF gold set from a single command.

This is intentionally small: it loads ``tests/fixtures/pdf_gold_*.json``,
skips missing PDFs (CI/fresh checkout), and reports value/page mismatches.
It does not download reports or write snapshots.
"""

from __future__ import annotations

import json
from pathlib import Path

from .extract import extract_pdf


def check(root: Path | str = ".", fixtures: Path | str | None = None) -> dict[str, object]:
    base = Path(root)
    fixture_dir = Path(fixtures) if fixtures else base / "tests" / "fixtures"
    results: list[dict[str, object]] = []
    for gold in sorted(fixture_dir.glob("pdf_gold_*.json")):
        payload = json.loads(gold.read_text(encoding="utf-8"))
        pdf = base / str(payload["source"])
        if not pdf.is_file():
            results.append({"fixture": gold.name, "status": "skip"})
            continue
        items = {item["item"]: item for item in extract_pdf(pdf, year=int(payload["year"]))}
        errors: list[str] = []
        for item, expected in payload["items"].items():
            found = items.get(item)
            if found is None:
                errors.append(f"{item}: missing")
                continue
            if found["value"] != expected["value"]:
                errors.append(f"{item}: value {found['value']} != {expected['value']}")
            if expected.get("page") and found["page"] != expected["page"]:
                errors.append(f"{item}: page {found['page']} != {expected['page']}")
        results.append(
            {
                "fixture": gold.name,
                "status": "pass" if not errors else "fail",
                "errors": errors,
            }
        )
    passed = sum(1 for item in results if item["status"] == "pass")
    failed = sum(1 for item in results if item["status"] == "fail")
    return {
        "status": "pass" if failed == 0 else "fail",
        "passed": passed,
        "failed": failed,
        "results": results,
    }
