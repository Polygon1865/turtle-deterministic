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

from .facts import ResearchClaim, ResearchDecision, ResearchParam

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
    facts: Mapping[str, str] | None = None,
    *,
    include_meta: bool = True,
    include_heading: bool = True,
) -> str:
    """Render D1–D6 claims, params and decisions; unresolved refs fail loudly."""
    lines: list[str] = []
    fact_map = facts or {}
    by_dimension: dict[str, list[ResearchClaim]] = {}
    for claim in document.claims:
        by_dimension.setdefault(claim.dimension, []).append(claim)

    def resolve(text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            kind, key = match.group(1), match.group(2).strip()
            if kind == "metric" and key in metrics:
                return metrics[key]
            if kind == "fact" and key in fact_map:
                return fact_map[key]
            raise ValueError(f"unresolved placeholder {match.group(0)}")

        return _PLACEHOLDER.sub(replace, text)

    for dimension, label in DIMENSIONS.items():
        claims = by_dimension.get(dimension, [])
        if not claims:
            continue
        lines.extend(["", f"### {dimension} {label}", ""] if include_heading else [""])
        for claim in claims:
            statement = resolve(claim.statement)
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
    if document.params:
        lines.extend(["", "### 研究参数", "", "| 参数 | 值 | 置信度 |", "|:--|:--|:--|"])
        for param in document.params:
            lines.append(
                f"| {param.label or param.param_id} | {resolve(param.value)} | {param.confidence} |"
            )
    if document.decisions:
        lines.extend(["", "### 研究决策", "", "| 决策 | 选择 | 理由 |", "|:--|:--|:--|"])
        for decision in document.decisions:
            lines.append(
                f"| {decision.metric_id} | {decision.selected} | {resolve(decision.reason)} |"
            )
    parts = [coverage_markdown(document), "\n".join(lines).strip()]
    evidence_table = evidence_markdown(document)
    if evidence_table:
        parts.append(evidence_table)
    if not include_meta:
        return "\n".join(lines).strip()
    return "\n\n".join(part for part in parts if part).strip()


def render_dimensions(
    document: ResearchDocument,
    metrics: Mapping[str, str],
    facts: Mapping[str, str] | None = None,
) -> dict[str, str]:
    sections: dict[str, str] = {}
    for dimension in DIMENSIONS:
        claims = tuple(
            claim for claim in document.claims if claim.dimension == dimension
        )
        if not claims:
            continue
        params = tuple(
            param for param in document.params if param.dimension == dimension
        )
        filtered = ResearchDocument(
            claims=claims,
            evidence=document.evidence,
            params=params,
        )
        body = render_markdown(
            filtered, metrics, facts, include_meta=False, include_heading=False
        )
        if body:
            sections[dimension] = body
    return sections


def quality(document: ResearchDocument) -> dict[str, Any]:
    dimensions = {
        dimension: sum(1 for claim in document.claims if claim.dimension == dimension)
        for dimension in DIMENSIONS
    }
    unknown = sum(1 for claim in document.claims if claim.judgment == "unknown")
    evidence_backed = sum(
        1
        for claim in document.claims
        if claim.judgment != "unknown" and claim.evidence_ids
    )
    non_unknown = len(document.claims) - unknown
    return {
        "claims": len(document.claims),
        "dimensions": dimensions,
        "covered_dimensions": [key for key, count in dimensions.items() if count],
        "unknown": unknown,
        "evidence_backed": evidence_backed,
        "evidence_ratio": (
            round(evidence_backed / non_unknown, 4) if non_unknown else 1.0
        ),
        "params": len(document.params),
        "decisions": len(document.decisions),
        "evidence": len(document.evidence),
    }


def thesis_markdown(
    document: ResearchDocument,
    metrics: Mapping[str, str] | None = None,
    facts: Mapping[str, str] | None = None,
) -> str:
    metric_map = metrics or {}
    fact_map = facts or {}
    rows = [
        param
        for param in document.params
        if param.param_id.startswith("thesis.")
    ]
    if not rows:
        return ""

    def resolve(text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            kind, key = match.group(1), match.group(2).strip()
            if kind == "metric" and key in metric_map:
                return metric_map[key]
            if kind == "fact" and key in fact_map:
                return fact_map[key]
            raise ValueError(f"unresolved placeholder {match.group(0)}")

        return _PLACEHOLDER.sub(replace, text)

    lines = ["| 项目 | 内容 |", "|:--|:--|"]
    for param in rows:
        lines.append(f"| {param.label or param.param_id} | {resolve(param.value)} |")
    return "\n".join(lines)


def summary_markdown(document: ResearchDocument) -> str:
    covered = sorted({claim.dimension for claim in document.claims})
    decisions = "；".join(
        f"{decision.metric_id}={decision.selected}"
        for decision in document.decisions
    )
    unknown = sum(1 for claim in document.claims if claim.judgment == "unknown")
    lines = [
        "**研究摘要**",
        "",
        f"- 覆盖维度：{'、'.join(covered) if covered else '无'}",
        f"- claims：{len(document.claims)}（unknown {unknown}）",
        f"- params：{len(document.params)}；evidence：{len(document.evidence)}",
    ]
    if decisions:
        lines.append(f"- 关键决策：{decisions}")
    if unknown:
        lines.append(
            "- 未验证："
            + "、".join(
                claim.claim_id for claim in document.claims if claim.judgment == "unknown"
            )
        )
    return "\n".join(lines)


def render_meta(document: ResearchDocument) -> str:
    parts = [coverage_markdown(document), evidence_markdown(document)]
    return "\n\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class ResearchDocument:
    claims: tuple[ResearchClaim, ...]
    evidence: dict[str, dict[str, object]]
    params: tuple[ResearchParam, ...] = ()
    decisions: tuple[ResearchDecision, ...] = ()


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


def audit(
    document: ResearchDocument,
    metrics: Mapping[str, str] | None = None,
    facts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Check claim/param/decision references against rendered value maps."""
    metric_map = metrics or {}
    fact_map = facts or {}
    errors: list[str] = []
    metric_refs: set[str] = set()
    fact_refs: set[str] = set()

    def check_text(label: str, text: str) -> None:
        for match in _PLACEHOLDER.finditer(text):
            kind, key = match.group(1), match.group(2).strip()
            if kind == "metric":
                metric_refs.add(key)
                if key not in metric_map:
                    errors.append(f"{label}: unresolved metric {key!r}")
            else:
                fact_refs.add(key)
                if key not in fact_map:
                    errors.append(f"{label}: unresolved fact {key!r}")

    for claim in document.claims:
        check_text(claim.claim_id, claim.statement)
        if claim.judgment != "unknown" and not claim.evidence_ids:
            errors.append(f"{claim.claim_id}: non-unknown claim has no evidence")
    for param in document.params:
        check_text(param.param_id, param.value)
    for decision in document.decisions:
        check_text(decision.decision_id, decision.reason)
        if decision.selected not in decision.candidates:
            errors.append(f"{decision.decision_id}: selected is not a candidate")
    return {
        "status": "pass" if not errors else "review",
        "claims": len(document.claims),
        "params": len(document.params),
        "decisions": len(document.decisions),
        "evidence": len(document.evidence),
        "metric_refs": sorted(metric_refs),
        "fact_refs": sorted(fact_refs),
        "errors": errors,
        "quality": quality(document),
    }


def coverage_markdown(document: ResearchDocument) -> str:
    unknown = sum(1 for claim in document.claims if claim.judgment == "unknown")
    lines = [
        "**研究覆盖**",
        "",
        f"- claims：{len(document.claims)}（unknown {unknown}）",
        f"- params：{len(document.params)}",
        f"- decisions：{len(document.decisions)}",
        f"- evidence：{len(document.evidence)}",
        "",
        "| 维度 | claims | unknown | evidence |",
        "|:--|--:|--:|--:|",
    ]
    for dimension, label in DIMENSIONS.items():
        claims = [claim for claim in document.claims if claim.dimension == dimension]
        dimension_evidence = {
            evidence_id
            for claim in claims
            for evidence_id in claim.evidence_ids
        }
        dim_unknown = sum(1 for claim in claims if claim.judgment == "unknown")
        lines.append(
            f"| {dimension} {label} | {len(claims)} | {dim_unknown} | "
            f"{len(dimension_evidence)} |"
        )
    if unknown:
        lines.append(
            "- unknown claims："
            + "、".join(
                claim.claim_id for claim in document.claims if claim.judgment == "unknown"
            )
        )
    return "\n".join(lines)


def evidence_markdown(document: ResearchDocument) -> str:
    if not document.evidence:
        return ""
    lines = [
        "**证据索引**",
        "",
        "| id | 来源 | 页 | 引文 |",
        "|:--|:--|:--|:--|",
    ]
    for evidence_id, item in sorted(document.evidence.items()):
        url = str(item.get("url", ""))
        page = str(item.get("page", ""))
        quote = " ".join(str(item.get("quote", "")).split())[:180]
        lines.append(f"| {evidence_id} | {url} | {page} | {quote} |")
    return "\n".join(lines)


def to_payload(document: ResearchDocument) -> dict[str, Any]:    return {
        "evidence": list(document.evidence.values()),
        "claims": [
            {
                "claim_id": claim.claim_id,
                "dimension": claim.dimension,
                "statement": claim.statement,
                "judgment": claim.judgment,
                "confidence": claim.confidence,
                "evidence_ids": list(claim.evidence_ids),
                "as_of": claim.as_of,
                "unknowns": list(claim.unknowns),
            }
            for claim in document.claims
        ],
        "params": [
            {
                "param_id": param.param_id,
                "label": param.label,
                "value": param.value,
                "dimension": param.dimension,
                "evidence_ids": list(param.evidence_ids),
                "confidence": param.confidence,
            }
            for param in document.params
        ],
        "decisions": [
            {
                "decision_id": decision.decision_id,
                "metric_id": decision.metric_id,
                "selected": decision.selected,
                "candidates": list(decision.candidates),
                "reason": decision.reason,
                "evidence_ids": list(decision.evidence_ids),
            }
            for decision in document.decisions
        ],
    }


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

    params: list[ResearchParam] = []
    for raw in payload.get("params", []):
        param_id = str(raw.get("param_id", "")).strip()
        label = str(raw.get("label", "")).strip()
        value = str(raw.get("value", "")).strip()
        dimension = str(raw.get("dimension", "")).strip().upper()
        if not param_id or not value:
            raise ValueError("param missing param_id/value")
        if dimension and dimension not in DIMENSIONS:
            raise ValueError(f"{param_id}: invalid dimension {dimension!r}")
        evidence_ids = tuple(str(x) for x in raw.get("evidence_ids", []))
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                raise ValueError(f"{param_id}: unknown evidence {evidence_id!r}")
        numbers = _raw_numbers(value)
        if numbers:
            raise ValueError(
                f"{param_id}: raw numbers in param {numbers}; use {{{{metric:...}}}}"
            )
        params.append(
            ResearchParam(
                param_id=param_id,
                label=label or param_id,
                value=value,
                dimension=dimension,
                evidence_ids=evidence_ids,
                confidence=str(raw.get("confidence", "medium")).strip().lower(),
            )
        )

    decisions: list[ResearchDecision] = []
    for raw in payload.get("decisions", []):
        decision_id = str(raw.get("decision_id", "")).strip()
        metric_id = str(raw.get("metric_id", "")).strip()
        selected = str(raw.get("selected", "")).strip()
        candidates = tuple(str(item) for item in raw.get("candidates", []))
        reason = str(raw.get("reason", "")).strip()
        evidence_ids = tuple(str(x) for x in raw.get("evidence_ids", []))
        if not decision_id or not metric_id or not selected:
            raise ValueError("decision missing decision_id/metric_id/selected")
        if not candidates or selected not in candidates:
            raise ValueError(f"{decision_id}: selected must be one of candidates")
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                raise ValueError(f"{decision_id}: unknown evidence {evidence_id!r}")
        if _raw_numbers(reason):
            raise ValueError(f"{decision_id}: raw numbers in decision reason")
        decisions.append(
            ResearchDecision(
                decision_id=decision_id,
                metric_id=metric_id,
                selected=selected,
                candidates=candidates,
                reason=reason,
                evidence_ids=evidence_ids,
            )
        )
    return ResearchDocument(
        claims=tuple(claims),
        evidence=evidence,
        params=tuple(params),
        decisions=tuple(decisions),
    )


def validate_evidence(items: Iterable[Mapping[str, object]]) -> None:
    for item in items:
        url = str(item.get("url", "")).strip()
        quote = str(item.get("quote", "")).strip()
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"evidence {item.get('id')}: invalid url")
        if not quote:
            raise ValueError(f"evidence {item.get('id')}: empty quote")
