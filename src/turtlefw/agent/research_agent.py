"""Optional research agent with a narrow, fake-LLM-testable contract.

The LLM is not allowed to write report numbers. It returns a research payload;
the deterministic validator in :mod:`turtlefw.research` either accepts it or
raises before any report is rendered.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ..research import (
    ResearchDocument,
    load_payload,
    normalize_document_placeholders,
)
from .research_prompt import SYSTEM_PROMPT

_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")


def _looks_english(text: str) -> bool:
    """True for prose that is effectively English, allowing ticker/company names."""
    latin = len(_LATIN.findall(text))
    cjk = len(_CJK.findall(text))
    return latin >= 60 and cjk < 8


def _language_error(document: ResearchDocument) -> str | None:
    for claim in document.claims:
        if _looks_english(claim.statement) or any(
            _looks_english(item) for item in claim.unknowns
        ):
            return f"research text is not Simplified Chinese: {claim.claim_id}"
    for param in document.params:
        if len(param.value) >= 40 and _looks_english(param.value):
            return f"research text is not Simplified Chinese: {param.param_id}"
    for decision in document.decisions:
        if _looks_english(decision.reason):
            return f"research text is not Simplified Chinese: {decision.decision_id}"
    return None


class AgentError(Exception):
    pass


class LLM(Protocol):
    def complete(self, system: str, payload: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(slots=True)
class FakeLLM:
    """Deterministic response queue for contract tests."""

    response: Mapping[str, Any]

    def complete(self, system: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        return dict(self.response)


class ResearchAgent:
    SYSTEM = SYSTEM_PROMPT

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def run(
        self,
        context: Mapping[str, Any],
        *,
        retries: int = 0,
        min_claims: int = 0,
        min_dimensions: int = 0,
    ) -> ResearchDocument:
        from ..research import quality

        last_error: Exception | None = None
        current = dict(context)
        for _attempt in range(max(0, retries) + 1):
            payload = self.llm.complete(self.SYSTEM, current)
            try:
                document = load_payload(payload)
            except (ValueError, TypeError, KeyError) as exc:
                last_error = exc
                current = {
                    **current,
                    "quality_feedback": f"invalid research output: {exc}",
                }
                continue
            metrics = current.get("metrics")
            allowed = tuple(metrics) if isinstance(metrics, Mapping) else ()
            document, unresolved = normalize_document_placeholders(document, allowed)
            if unresolved:
                last_error = AgentError(
                    "unresolved metric placeholders: " + ", ".join(unresolved)
                )
                current = {
                    **current,
                    "quality_feedback": (
                        f"{last_error}. Use only metric ids present in the "
                        "provided metrics object, e.g. {{metric:policy.payout_spread}}."
                    ),
                }
                continue
            stats = quality(document)
            language_error = _language_error(document)
            if language_error:
                last_error = AgentError(language_error)
                current = {
                    **current,
                    "quality_feedback": (
                        f"{language_error}. Rewrite all natural-language research "
                        "fields in Simplified Chinese (zh-CN); keep only company "
                        "names, tickers and proper nouns in English."
                    ),
                }
                continue
            dimensions = len(stats["covered_dimensions"])
            if stats["claims"] >= min_claims and dimensions >= min_dimensions:
                return document
            last_error = AgentError(
                f"research quality insufficient: claims={stats['claims']} "
                f"dimensions={dimensions}"
            )
            current = {
                **current,
                "quality_feedback": (
                    f"{last_error}. Fill at least {min_claims} claims and "
                    f"{min_dimensions} D1-D6 dimensions with evidence."
                ),
            }
        raise AgentError(f"invalid research output: {last_error}") from last_error
