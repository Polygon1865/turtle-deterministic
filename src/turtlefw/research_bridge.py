"""Map evidence-backed research claims into qualitative factor judgements.

The bridge is deliberately narrow: it only consumes D1-D6 claims that carry
explicit evidence and a non-unknown judgement.  It never turns a research
parameter or a bare narrative sentence into a factor input.
"""

from __future__ import annotations

from .facts import ResearchClaim
from .qualitative import Evidence, Judgment, Qualitative
from .research import ResearchDocument

DIMENSION_MODULES: dict[str, str] = {
    "D1": "understandability",
    "D2": "moat",
    "D3": "policy",
    "D4": "management",
    "D6": "controller",
}

_CONFIDENCE_RANK = {"high": 0, "medium": 1, "low": 2}
_JUDGMENT_RANK = {"negative": 0, "positive": 1, "neutral": 2}
_D4_NON_MANAGEMENT = ("payout", "buyback", "capital_allocation", "dividend")


def _claim_in_scope(dimension: str, claim_id: str) -> bool:
    """Keep capital-allocation claims out of the management judgement.

    A payout or buyback deviation is useful input for factor 4, but it is not
    sufficient evidence that management destroys value.  Management stays
    unknown unless a management/governance claim is available.
    """
    if dimension != "D4":
        return True
    lowered = claim_id.lower()
    return not any(token in lowered for token in _D4_NON_MANAGEMENT)


def _source_type(raw: dict[str, object]) -> str:
    value = str(raw.get("source_type", "web") or "web").lower()
    if value == "pdf" or str(raw.get("url", "")).startswith("pdf://"):
        return "pdf"
    if value == "data":
        return "data"
    if value == "document":
        return "document"
    return "web"


def _evidence(document: ResearchDocument, claim: ResearchClaim) -> tuple[Evidence, ...]:
    evidence: list[Evidence] = []
    seen: set[tuple[str, str]] = set()
    for evidence_id in claim.evidence_ids:
        raw = document.evidence.get(evidence_id)
        if not isinstance(raw, dict):
            continue
        quote = str(raw.get("quote", "")).strip()
        if not quote:
            continue
        kind = _source_type(raw)
        url = str(raw.get("url", "")).strip()
        if kind == "pdf" and not url.startswith("pdf://"):
            continue
        if kind in {"web", "document"} and not url.startswith(("http://", "https://")):
            continue
        key = (url, quote)
        if key in seen:
            continue
        seen.add(key)
        evidence.append(
            Evidence(
                url=url,
                quote=quote,
                source_type=kind,
                page=str(raw.get("page", "")).strip(),
            )
        )
    return tuple(evidence)


def _claim_usable(
    document: ResearchDocument, claim: ResearchClaim
) -> tuple[Evidence, ...] | None:
    if claim.judgment not in _JUDGMENT_RANK:
        return None
    if claim.confidence not in {"high", "medium"}:
        return None
    evidence = _evidence(document, claim)
    if not evidence:
        return None
    return evidence


def _aggregate(
    document: ResearchDocument, claims: list[ResearchClaim]
) -> tuple[str, str, tuple[Evidence, ...], tuple[str, ...]] | None:
    usable: list[tuple[ResearchClaim, tuple[Evidence, ...]]] = []
    for claim in claims:
        claim_evidence = _claim_usable(document, claim)
        if claim_evidence is not None:
            usable.append((claim, claim_evidence))
    if not usable:
        return None

    # A negative claim dominates a positive one; this is intentional for a
    # veto input.  The confidence is the weakest confidence among the claims
    # that contributed to the chosen judgement.
    chosen_judgment = min(
        (claim.judgment for claim, _ in usable),
        key=lambda value: _JUDGMENT_RANK[value],
    )
    chosen = [
        (claim, claim_evidence)
        for claim, claim_evidence in usable
        if claim.judgment == chosen_judgment
    ]
    confidence = max(
        (claim.confidence for claim, _ in chosen),
        key=lambda value: _CONFIDENCE_RANK[value],
    )
    selected_evidence: list[Evidence] = []
    seen: set[tuple[str, str]] = set()
    for _, items in chosen:
        for item in items:
            key = (item.url, item.quote)
            if key not in seen:
                seen.add(key)
                selected_evidence.append(item)
    ids = tuple(claim.claim_id for claim, _ in chosen)
    return chosen_judgment, confidence, tuple(selected_evidence), ids


def bridge(
    document: ResearchDocument | None,
    base: Qualitative | None = None,
) -> tuple[Qualitative | None, tuple[str, ...]]:
    """Return an effective qualitative object and the bridged module names."""
    if document is None:
        return base, ()
    if base is not None and base.source == "research_bridge":
        # A prior bridge result is derived data, not a human override. Rebuild it
        # from the current research document so filter/semantic fixes take effect.
        base = None

    items = dict(base.items) if base is not None else {}
    added: list[str] = []
    for dimension, module in DIMENSION_MODULES.items():
        existing = items.get(module)
        if existing is not None and existing.judgment != "unknown":
            continue
        claims = [
            claim
            for claim in document.claims
            if claim.dimension == dimension
            and _claim_in_scope(dimension, claim.claim_id)
        ]
        result = _aggregate(document, claims)
        if result is None:
            continue
        judgment, confidence, evidence, claim_ids = result
        items[module] = Judgment(
            module=module,
            judgment=judgment,
            confidence=confidence,
            evidence=evidence,
            notes=f"research bridge {dimension}: " + ", ".join(claim_ids),
        )
        added.append(module)

    if not added:
        return base, ()

    base_source = base.source if base is not None and base.source else ""
    source = f"{base_source}+research_bridge" if base_source else "research_bridge"
    discrepancies = base.discrepancies if base is not None else ()
    return (
        Qualitative(
            items=items,
            discrepancies=discrepancies,
            source=source,
        ),
        tuple(added),
    )

