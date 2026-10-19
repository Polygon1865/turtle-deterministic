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

    def run(self, context: Mapping[str, Any], *, retries: int = 0) -> ResearchDocument:
        last_error: Exception | None = None
        for _attempt in range(max(0, retries) + 1):
            payload = self.llm.complete(self.SYSTEM, context)
            try:
                return load_payload(payload)
            except (ValueError, TypeError, KeyError) as exc:
                last_error = exc
        raise AgentError(f"invalid research output: {last_error}") from last_error
