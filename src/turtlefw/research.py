"""Research-layer schema: claims must be evidence-backed and number-free.

The deterministic engine owns numbers. A research claim may reference a metric
placeholder (``{{metric:r}}``) or a fact placeholder (``{{fact:...}}``), but it
must not contain a raw numeric literal; the numeric guard rejects it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .facts import ResearchClaim

DIMENSIONS = {
    "D1": "商业模式与资本特征",
    "D2": "竞争优势与护城河",
    "D3": "外部环境与政策",
    "D4": "管理层与治理",
    "D5": "MD&A 与前瞻信号",
    "D6": "控股结构与股东",
}
JUDGMENTS = {"positive", "neutral", "negative", "unknown"}
CONFIDENCES = {"high", "medium", "low"}

_NUMBER = re.compile(r"(?<!\{)\b\d+(?:\.\d+)?%?\b")
_YEAR = re.compile(r"^(19|20)\d{2}$")
_PLACEHOLDER = re.compile(r"\{\{(metric|fact):([^}]+)\}\}")


def render_markdown(
    document: ResearchDocument,
    metrics: Mapping[str, str],
) -> str:
    """Render D1–D6 claims with citations; unresolved placeholders fail loudly."""
    lines: list[str] = []
    by_dimension: dict[str, list[ResearchClaim]] = {}
    for claim in document.claims:
        by_dimension.setdefault(claim.dimension, []).append(claim)
    for dimension, label in DIMENSIONS.items():
        claims = by_dimension.get(dimension, [])
        if not claims:
            continue
        lines.extend(["", f"### {dimension} {label}", ""])
        for claim in claims:
            def replace(match: re.Match[str]) -> str:
                kind, key = match.group(1), match.group(2).strip()
                if kind == "metric" and key in metrics:
                    return metrics[key]
                raise ValueError(f"{claim.claim_id}: unresolved placeholder {match.group(0)}")

            statement = _PLACEHOLDER.sub(replace, claim.statement)
            lines.append(
                f"- **{claim.claim_id}**（{claim.judgment} / {claim.confidence}）：{statement}"
            )
            for evidence_id in claim.evidence_ids:
                evidence = document.evidence.get(evidence_id)
                if not evidence:
                    continue
                source = str(evidence.get("url", ""))
                page = str(evidence.get("page", ""))
                quote = str(evidence.get("quote", ""))
                label = f"{source} {page}".strip()
                lines.append(f"  - 证据：{label} — “{quote}”")
            if claim.unknowns:
                lines.append(f"  - 未验证：{'、'.join(claim.unknowns)}")
    return "\n".join(lines).strip()


@dataclass(frozen=True, slots=True)
class ResearchDocument:
    claims: tuple[ResearchClaim, ...]
    evidence: dict[str, dict[str, object]]


def _raw_numbers(text: str) -> list[str]:
    """Numbers not inside ``{{...}}`` and not standalone years."""
    without_placeholders = re.sub(r"\{\{.*?\}\}", "", text)
    numbers = []
    for match in _NUMBER.finditer(without_placeholders):
        token = match.group(0).rstrip("%")
        if _YEAR.match(token):
            continue
        numbers.append(match.group(0))
    return numbers


def load(path: Path | str) -> ResearchDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return load_payload(payload)


def load_payload(payload: Mapping[str, Any]) -> ResearchDocument:
    evidence_raw = payload.get("evidence", [])
    evidence: dict[str, dict[str, object]] = {}
    for item in evidence_raw:
        key = str(item.get("id", "")).strip()
        if not key:
            raise ValueError("evidence missing id")
        evidence[key] = dict(item)
    validate_evidence(
        item for item in evidence.values() if str(item.get("source_type", "web")) != "data"
    )

    claims: list[ResearchClaim] = []
    for raw in payload.get("claims", []):
        claim_id = str(raw.get("claim_id", "")).strip()
        dimension = str(raw.get("dimension", "")).strip().upper()
        statement = str(raw.get("statement", "")).strip()
        judgment = str(raw.get("judgment", "")).strip().lower()
        confidence = str(raw.get("confidence", "medium")).strip().lower()
        evidence_ids = tuple(str(x) for x in raw.get("evidence_ids", []))
        if not claim_id or not statement:
            raise ValueError("claim missing claim_id/statement")
        if dimension not in DIMENSIONS:
            raise ValueError(f"{claim_id}: invalid dimension {dimension!r}")
        if judgment not in JUDGMENTS:
            raise ValueError(f"{claim_id}: invalid judgment {judgment!r}")
        if confidence not in CONFIDENCES:
            raise ValueError(f"{claim_id}: invalid confidence {confidence!r}")
        if judgment != "unknown" and not evidence_ids:
            raise ValueError(f"{claim_id}: non-unknown claim requires evidence")
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                raise ValueError(f"{claim_id}: unknown evidence {evidence_id!r}")
        numbers = _raw_numbers(statement)
        if numbers:
            raise ValueError(
                f"{claim_id}: raw numbers in claim {numbers}; use {{{{metric:...}}}}"
            )
        claims.append(
            ResearchClaim(
                claim_id=claim_id,
                dimension=dimension,
                statement=statement,
                judgment=judgment,
                confidence=confidence,
                evidence_ids=evidence_ids,
                as_of=str(raw.get("as_of", "")),
                unknowns=tuple(str(x) for x in raw.get("unknowns", [])),
            )
        )
    return ResearchDocument(claims=tuple(claims), evidence=evidence)


def validate_evidence(items: Iterable[Mapping[str, object]]) -> None:
    for item in items:
        url = str(item.get("url", "")).strip()
        quote = str(item.get("quote", "")).strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"evidence {item.get('id')}: invalid url")
        if not quote:
            raise ValueError(f"evidence {item.get('id')}: empty quote")
