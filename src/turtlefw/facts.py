"""Facts, evidence and report-snapshot primitives.

This module is the contract behind the target architecture:

* deterministic canonical serialization (stable hashes);
* ``MetricPoint`` for every number that reaches a report;
* ``Evidence`` / ``ResearchClaim`` for the research layer;
* ``ReportManifest`` linking facts/config/research/templates/renderer.

It deliberately contains no provider calls and no rendering. The current CLI
can adopt it incrementally without changing the formulas.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

SNAPSHOT_VERSION = 1
FORMULA_VERSION = "2026-10-20.2"

SOURCE_RANKS = {
    "pdf": 1,
    "annual_report": 1,
    "exchange": 2,
    "tushare": 3,
    "yfinance": 4,
    "sec": 3,
    "web": 5,
}


def source_rank(kind: str) -> int:
    return SOURCE_RANKS.get(str(kind).lower(), 9)


def _canonical(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value, key=str)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, set):
        return [_canonical(item) for item in sorted(value, key=str)]
    return value


def canonical_json(value: Any) -> str:
    """Stable JSON used for hashes (sorted keys, UTF-8, Decimal as string)."""
    return json.dumps(
        _canonical(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def file_hash(path: Path | str) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def config_payload(settings: Any) -> dict[str, Any]:
    """Deterministic config payload; exclude the absolute config path."""
    payload = settings.save_snapshot()
    payload = dict(payload)
    payload.pop("config_path", None)
    return payload


def template_hash(template_dir: Path | str) -> str:
    root = Path(template_dir)
    files = sorted(path for path in root.rglob("*") if path.is_file())
    payload = {path.relative_to(root).as_posix(): file_hash(path) for path in files}
    return content_hash(payload)


def statement_payload(rows: Sequence[Any]) -> list[dict[str, Any]]:
    return [
        {
            "code": row.code,
            "period_end": row.period_end.isoformat(),
            "period_type": row.period_type,
            "statement": row.statement,
            "item": row.item,
            "value": str(row.value),
            "currency": row.currency.value,
            "source": row.source,
        }
        for row in sorted(rows, key=lambda r: (r.period_end, r.statement, r.item, r.source))
    ]


@dataclass(frozen=True, slots=True)
class MetricPoint:
    id: str
    name: str
    value: Decimal | None
    unit: str = ""
    currency: str = ""
    period: str = ""
    basis: str = "consolidated"
    annualized: bool = False
    formula_id: str = ""
    source_fact_ids: tuple[str, ...] = ()
    coverage: str = "ok"
    display: str = ""
    source_rank: int = 0


@dataclass(slots=True)
class MetricRegistry:
    """The only numbers a research/report composer should resolve."""

    points: dict[str, MetricPoint]

    def __init__(self) -> None:
        self.points = {}

    def add(self, point: MetricPoint) -> None:
        self.points[point.id] = point

    def get(self, metric_id: str) -> MetricPoint | None:
        return self.points.get(metric_id)

    def display(self, metric_id: str) -> str:
        point = self.points.get(metric_id)
        if point is None:
            return "—"
        if point.display:
            return point.display
        if point.value is None:
            return "—"
        if point.unit == "%":
            return f"{point.value:.2f}%"
        if point.unit == "x":
            return f"{point.value:.2f}x"
        return f"{point.value:,.2f}"

    def resolve(self, text: str) -> str:
        pattern = re.compile(r"\{\{metric:([^}]+)\}\}")

        def replace(match: re.Match[str]) -> str:
            metric_id = match.group(1).strip()
            point = self.points.get(metric_id)
            if point is None:
                raise ValueError(f"unknown metric placeholder: {metric_id}")
            return self.display(metric_id)

        return pattern.sub(replace, text)

    def coverage(self, required: Sequence[str]) -> str:
        missing = [metric_id for metric_id in required if metric_id not in self.points]
        return "ok" if not missing else "missing:" + ",".join(missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            metric_id: {
                "id": point.id,
                "name": point.name,
                "value": str(point.value) if point.value is not None else None,
                "unit": point.unit,
                "currency": point.currency,
                "period": point.period,
                "formula_id": point.formula_id,
                "source_fact_ids": list(point.source_fact_ids),
                "coverage": point.coverage,
                "display": self.display(metric_id),
            }
            for metric_id, point in self.points.items()
        }


@dataclass(frozen=True, slots=True)
class Evidence:
    id: str
    url: str
    quote: str
    source_type: str = "web"  # web | document | data
    page: str = ""
    retrieved_at: str = ""
    content_hash: str = ""


@dataclass(frozen=True, slots=True)
class SourceValue:
    key: tuple[str, str, str, str, str]
    value: Decimal
    source: str
    source_rank: int
    confidence: str = ""
    ann_date: str = ""
    source_id: str = ""
    page: str = ""
    document_hash: str = ""
    display: str = ""


@dataclass(frozen=True, slots=True)
class ResolvedFact:
    key: tuple[str, str, str, str, str]
    primary: SourceValue | None
    candidates: tuple[SourceValue, ...]
    status: str
    diff_pct: Decimal
    reason: str
    selected_for_display: SourceValue | None = None
    selected_for_engine: SourceValue | None = None


@dataclass(frozen=True, slots=True)
class DocumentFact:
    id: str
    document_hash: str
    page: str
    section: str
    label: str
    value: Decimal | None
    unit: str = ""
    currency: str = ""
    extraction_method: str = "pdfplumber"
    confidence: str = ""
    source_url: str = ""
    source_rank: int = 0


@dataclass(frozen=True, slots=True)
class ResearchClaim:
    claim_id: str
    dimension: str
    statement: str
    judgment: str
    confidence: str = "medium"
    evidence_ids: tuple[str, ...] = ()
    as_of: str = ""
    unknowns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResearchParam:
    param_id: str
    label: str
    value: str
    dimension: str = ""
    evidence_ids: tuple[str, ...] = ()
    confidence: str = "medium"


@dataclass(frozen=True, slots=True)
class ResearchDecision:
    decision_id: str
    metric_id: str
    selected: str
    candidates: tuple[str, ...]
    reason: str = ""
    evidence_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReportManifest:
    code: str
    as_of: str
    currency: str
    facts_hash: str
    config_hash: str
    research_hash: str = ""
    research_audit_hash: str = ""
    template_hash: str = ""
    source_id: str = ""
    engine_version: str = ""
    formula_version: str = FORMULA_VERSION
    report_format_version: int = 1
    report_hash: str = ""
    metrics_hash: str = ""
    resolved_hash: str = ""
    numeric_coverage: str = ""
    numeric_status: str = ""
    numeric_unknown: tuple[str, ...] = ()
    numeric_hash: str = ""
    numeric_sources: tuple[str, ...] = ()
    created_at: str = ""
    snapshot_version: int = SNAPSHOT_VERSION

    def _identity_payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "as_of": self.as_of,
            "currency": self.currency,
            "facts_hash": self.facts_hash,
            "config_hash": self.config_hash,
            "research_hash": self.research_hash,
            "template_hash": self.template_hash,
            "engine_version": self.engine_version,
            "formula_version": self.formula_version,
            "report_format_version": self.report_format_version,
            "snapshot_version": self.snapshot_version,
        }

    @property
    def snapshot_id(self) -> str:
        return content_hash(self._identity_payload())[:32]

    def to_dict(self) -> dict[str, Any]:
        payload = self._identity_payload()
        payload.update(
            {
                "snapshot_id": self.snapshot_id,
                "source_id": self.source_id,
                "research_audit_hash": self.research_audit_hash,
                "report_hash": self.report_hash,
                "metrics_hash": self.metrics_hash,
                "resolved_hash": self.resolved_hash,
                "numeric_coverage": self.numeric_coverage,
                "numeric_status": self.numeric_status,
                "numeric_unknown": list(self.numeric_unknown),
                "numeric_hash": self.numeric_hash,
                "numeric_sources": list(self.numeric_sources),
                "created_at": self.created_at,
            }
        )
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReportManifest":
        return cls(
            code=str(payload["code"]),
            as_of=str(payload["as_of"]),
            currency=str(payload["currency"]),
            facts_hash=str(payload["facts_hash"]),
            config_hash=str(payload["config_hash"]),
            research_hash=str(payload.get("research_hash", "")),
            research_audit_hash=str(payload.get("research_audit_hash", "")),
            template_hash=str(payload.get("template_hash", "")),
            source_id=str(payload.get("source_id", "")),
            engine_version=str(payload.get("engine_version", "")),
            formula_version=str(payload.get("formula_version", FORMULA_VERSION)),
            report_format_version=int(payload.get("report_format_version", 1)),
            report_hash=str(payload.get("report_hash", "")),
            metrics_hash=str(payload.get("metrics_hash", "")),
            resolved_hash=str(payload.get("resolved_hash", "")),
            numeric_coverage=str(payload.get("numeric_coverage", "")),
            numeric_status=str(payload.get("numeric_status", "")),
            numeric_unknown=tuple(str(item) for item in payload.get("numeric_unknown", [])),
            numeric_hash=str(payload.get("numeric_hash", "")),
            numeric_sources=tuple(str(item) for item in payload.get("numeric_sources", [])),
            created_at=str(payload.get("created_at", "")),
            snapshot_version=int(payload.get("snapshot_version", SNAPSHOT_VERSION)),
        )

    @classmethod
    def read(cls, path: Path | str) -> "ReportManifest":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8-sig")))

    def write(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True)
        target.write_bytes((payload + "\n").encode("utf-8"))
        return target
