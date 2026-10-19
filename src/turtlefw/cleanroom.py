"""Advisory clean-room: independent-source numeric comparison.

This is intentionally simple: compare the PDF-reported six items against the
snapshot's canonical statement rows without importing the factor/valuation
engine. It catches unit/period/field mistakes but does not claim to be a full
independent reimplementation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from .metrics import statements
from .metrics.audit import LABELS, parse_doc_items
from .report.snapshot import load as load_snapshot


def run(
    snapshot_dir: Path | str,
    pdf_numbers: Path | str,
    *,
    threshold_pct: Decimal = Decimal("1"),
    pdf_file: Path | str | None = None,
) -> dict[str, Any]:
    return run_independent(
        snapshot_dir, pdf_numbers, threshold_pct=threshold_pct, pdf_file=pdf_file
    )


def run_independent(
    snapshot_dir: Path | str,
    pdf_numbers: Path | str,
    *,
    threshold_pct: Decimal = Decimal("1"),
    pdf_file: Path | str | None = None,
) -> dict[str, Any]:
    """Run the audit in a separate Python process (raw snapshot + PDF only)."""
    import os
    import tempfile
    import uuid

    target = Path(tempfile.gettempdir()) / f"turtle-cleanroom-{os.getpid()}-{uuid.uuid4().hex}.json"
    command = [
        sys.executable,
        "-m",
        "turtlefw.cleanroom_worker",
        "--snapshot",
        str(snapshot_dir),
        "--pdf",
        str(pdf_numbers),
        "--threshold",
        str(threshold_pct),
        "--out",
        str(target),
    ]
    if pdf_file is not None:
        command.extend(["--pdf-file", str(pdf_file)])
    completed = subprocess.run(
        command,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(f"cleanroom worker failed with exit {completed.returncode}")
    try:
        return cast(dict[str, Any], json.loads(target.read_text(encoding="utf-8")))
    finally:
        target.unlink(missing_ok=True)


def run_in_process(
    snapshot_dir: Path | str,
    pdf_numbers: Path | str,
    *,
    threshold_pct: Decimal = Decimal("1"),
) -> dict[str, Any]:
    """Legacy in-process comparison, retained for unit tests/fallback."""
    inputs, _settings = load_snapshot(snapshot_dir)
    payload = json.loads(Path(pdf_numbers).read_text(encoding="utf-8-sig"))
    documents = parse_doc_items(payload.get("items", []))
    rows = inputs.rows
    series = statements.annual_series
    years = sorted({row.period_end.year for row in rows if row.period_type == "annual"})
    latest = max(years) if years else None
    latest_key = latest if latest is not None else 0
    canonical = {
        "revenue": series(rows, "income", "revenue").get(latest_key),
        "net_income": series(rows, "income", "n_income_attr_p").get(latest_key),
        "ocf": series(rows, "cashflow", "n_cashflow_act").get(latest_key),
        "capex": series(rows, "cashflow", "c_pay_acq_const_fiolta").get(latest_key),
        "equity": series(rows, "balance", "total_hldr_eqy_exc_min_int").get(latest_key),
        "total_assets": series(rows, "balance", "total_assets").get(latest_key),
    }
    checks: list[dict[str, Any]] = []
    for doc in documents:
        base = canonical.get(doc.item)
        if base is None or base == 0:
            checks.append(
                {
                    "item": doc.item,
                    "label": LABELS.get(doc.item, doc.item),
                    "status": "missing",
                    "note": "canonical value unavailable",
                }
            )
            continue
        diff = abs(doc.value - base) / abs(base) * Decimal("100")
        checks.append(
            {
                "item": doc.item,
                "label": LABELS.get(doc.item, doc.item),
                "snapshot_value": str(base),
                "document_value": str(doc.value),
                "diff_pct": str(diff.quantize(Decimal("0.01"))),
                "status": "pass" if diff <= threshold_pct else "review",
                "source": f"{doc.source} {doc.page}".strip(),
                "source_rank": doc.source_rank,
            }
        )
    review = [check for check in checks if check["status"] == "review"]
    document_facts = payload.get("document_facts", [])
    fact_issues = [
        fact.get("id", "?")
        for fact in document_facts
        if not fact.get("document_hash") or not fact.get("page") or fact.get("value") in (None, "")
    ]
    return {
        "snapshot": str(snapshot_dir),
        "source_id": inputs.source_id,
        "document_hash": str(payload.get("document_hash", "")),
        "document_fact_count": len(document_facts),
        "document_fact_issues": fact_issues,
        "pdf_numbers": str(pdf_numbers),
        "threshold_pct": str(threshold_pct),
        "checks": checks,
        "review": review,
        "status": "review" if review or fact_issues else "pass",
    }
