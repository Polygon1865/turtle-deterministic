"""Optional research agent with a narrow, fake-LLM-testable contract.

The LLM is not allowed to write report numbers. It returns a research payload;
the deterministic validator in :mod:`turtlefw.research` either accepts it or
raises before any report is rendered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ..research import ResearchDocument, load_payload
from .research_prompt import SYSTEM_PROMPT


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
            stats = quality(document)
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
