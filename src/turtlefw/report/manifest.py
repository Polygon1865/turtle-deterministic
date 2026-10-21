"""Build a ReportManifest from frozen report inputs."""

from __future__ import annotations

from pathlib import Path

from .. import __version__
from ..config import Settings
from ..facts import (
    ReportManifest,
    config_payload,
    content_hash,
    file_hash,
    statement_payload,
    template_hash,
)
from .pdf_facts import apply_document_facts


def build_manifest(
    inputs: object,
    settings: Settings,
    root: Path,
    report_hash: str = "",
    metrics_hash: str = "",
    resolved_hash: str = "",
    pdf_fact_hash: str = "",
    research_audit_hash: str = "",
    numeric_coverage: str = "",
    numeric_status: str = "",
    numeric_unknown: tuple[str, ...] = (),
    numeric_hash: str = "",
    numeric_sources: tuple[str, ...] = (),
) -> ReportManifest:
    snapshot_root = Path(root)
    research_file = snapshot_root / "research.json"
    rows = getattr(inputs, "rows")
    rows = apply_document_facts(
        list(rows), list(getattr(inputs, "document_facts", []))
    )
    return ReportManifest(
        code=str(getattr(inputs, "code")),
        as_of=str(getattr(inputs, "as_of")),
        currency=str(getattr(inputs, "currency")),
        facts_hash=content_hash(statement_payload(rows)),
        config_hash=content_hash(config_payload(settings)),
        pdf_fact_hash=pdf_fact_hash,
        pdf_fact_hash_version=1,
        extras_hash=content_hash(getattr(inputs, "fundamental_extras", {}) or {}),
        market_hash=content_hash(getattr(inputs, "market_extras", {}) or {}),
        peers_hash=content_hash(getattr(inputs, "industry_peers", []) or []),
        research_hash=file_hash(research_file) if research_file.is_file() else "",
        research_audit_hash=research_audit_hash,
        template_hash=template_hash(
            Path(__file__).resolve().parent / "templates"
        ),
        engine_version=__version__,
        report_hash=report_hash,
        metrics_hash=metrics_hash,
        resolved_hash=resolved_hash,
        numeric_coverage=numeric_coverage,
        numeric_status=numeric_status,
        numeric_unknown=numeric_unknown,
        numeric_hash=numeric_hash,
        numeric_sources=numeric_sources,
        source_id=str(getattr(inputs, "source_id", "")),
    )
