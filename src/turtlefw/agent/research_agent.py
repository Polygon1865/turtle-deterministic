"""Optional research agent with a narrow, fake-LLM-testable contract.

The LLM is not allowed to write report numbers. It returns a research payload;
the deterministic validator in :mod:`turtlefw.research` either accepts it or
raises before any report is rendered.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from ..research import ResearchDocument, load_payload


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
    SYSTEM = (
        "You write only D1-D6 claims, params and decisions. Never write report numbers; "
        "use {{metric:id}} or {{fact:id}} placeholders. Return JSON matching the research "
        "schema with evidence for every non-unknown claim. Decisions may only select "
        "one of the supplied candidates; never invent a value."
    )

    def __init__(self, llm: LLM) -> None:
        self.llm = llm

    def run(self, context: Mapping[str, Any]) -> ResearchDocument:
        payload = self.llm.complete(self.SYSTEM, context)
        try:
            return load_payload(payload)
        except (ValueError, TypeError, KeyError) as exc:
            raise AgentError(f"invalid research output: {exc}") from exc
