"""Run the four research roles with fallback (ADR-05 + ADR-06).

Order: extractor -> researcher -> writer -> auditor.  The writer and auditor are
deterministic; only the first two call the LLM.  Any role error, schema failure
or budget exhaustion downgrades to the single-role agent (if budget remains) or
to deterministic-only, and the reason is recorded so the daily job can surface
it instead of silently producing a thinner report.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from ..research import ResearchDocument, load_payload, quality
from .budget import BudgetExceeded, TokenBudget
from .research_agent import AgentError, ResearchAgent, _language_error
from .roles import (
    AUDITOR,
    EXTRACTOR,
    EXTRACTOR_SYSTEM,
    RESEARCHER,
    RESEARCHER_SYSTEM,
    WRITER,
    RoleError,
    ToolBox,
    assemble_payload,
    estimate_tokens,
    validate_extraction,
    validate_research_draft,
)


@dataclass(slots=True)
class RoleOutput:
    role: str
    payload: dict[str, Any]
    tokens: int


@dataclass(slots=True)
class RoleRun:
    document: ResearchDocument | None
    outputs: tuple[RoleOutput, ...]
    fallback: str
    reason: str
    tokens: int

    @property
    def ok(self) -> bool:
        return self.document is not None and not self.fallback


def _default_tools(state: dict[str, Any]) -> dict[str, Callable[..., Any]]:
    return {
        "read_metrics": lambda: state.get("metrics", {}),
        "read_data_pack": lambda: state.get("data_pack", ""),
        "read_evidence": lambda: list(state.get("evidence", [])),
        "read_claims": lambda: list(state.get("claims", [])),
        "validate_document": lambda payload: load_payload(payload),
        "quality": lambda document: quality(document),
        "language": lambda document: _language_error(document),
    }


def _call_llm(llm: Any, system: str, payload: Mapping[str, Any], budget: TokenBudget) -> Mapping[str, Any]:
    response = llm.complete(system, payload)
    if not isinstance(response, Mapping):
        raise RoleError("LLM response must be a JSON object")
    budget.charge(estimate_tokens(response))
    return response


def run_research_roles(
    context: Mapping[str, Any],
    *,
    llm: Any,
    budget: TokenBudget | None = None,
    min_claims: int = 0,
    min_dimensions: int = 0,
    retries: int = 0,
    fallback_single: bool = True,
    tools: Mapping[str, Callable[..., Any]] | None = None,
) -> RoleRun:
    box_budget = budget or TokenBudget()
    state: dict[str, Any] = {
        "metrics": context.get("metrics", {}),
        "data_pack": context.get("data_pack", ""),
        "evidence": [],
        "claims": [],
    }
    registry = dict(_default_tools(state))
    if tools:
        registry.update(tools)
    outputs: list[RoleOutput] = []

    def _downgrade(reason: str) -> RoleRun:
        if not fallback_single or box_budget.remaining <= 0:
            return RoleRun(None, tuple(outputs), "deterministic_only", reason, box_budget.used)
        try:
            document = ResearchAgent(llm).run(
                dict(context),
                retries=retries,
                min_claims=min_claims,
                min_dimensions=min_dimensions,
            )
        except AgentError as exc:
            return RoleRun(
                None,
                tuple(outputs),
                "deterministic_only",
                f"{reason}; single_role: {exc}",
                box_budget.used,
            )
        return RoleRun(document, tuple(outputs), "single_role", reason, box_budget.used)

    try:
        extractor = ToolBox(EXTRACTOR, registry)
        extractor.call("read_metrics")
        extractor.call("read_data_pack")
        extracted = _call_llm(
            llm,
            EXTRACTOR_SYSTEM,
            {"context": dict(context)},
            box_budget,
        )
        evidence = validate_extraction(extracted)
        state["evidence"] = evidence
        outputs.append(RoleOutput("extractor", dict(extracted), estimate_tokens(extracted)))

        researcher = ToolBox(RESEARCHER, registry)
        researcher.call("read_evidence")
        researched = _call_llm(
            llm,
            RESEARCHER_SYSTEM,
            {"context": dict(context), "evidence": evidence},
            box_budget,
        )
        claims, params = validate_research_draft(researched)
        state["claims"] = claims
        outputs.append(RoleOutput("researcher", dict(researched), estimate_tokens(researched)))

        writer = ToolBox(WRITER, registry)
        payload = assemble_payload(writer.call("read_evidence"), claims, params)
        outputs.append(RoleOutput("writer", payload, 0))

        auditor = ToolBox(AUDITOR, registry)
        document = auditor.call("validate_document", payload)
        stats = auditor.call("quality", document)
        problems: list[str] = []
        language = auditor.call("language", document)
        if language:
            problems.append(str(language))
        if stats["claims"] < min_claims:
            problems.append(f"claims={stats['claims']} < {min_claims}")
        if len(stats["covered_dimensions"]) < min_dimensions:
            problems.append(
                f"dimensions={len(stats['covered_dimensions'])} < {min_dimensions}"
            )
        if problems:
            raise RoleError("audit failed: " + "; ".join(problems))
        outputs.append(
            RoleOutput(
                "auditor",
                {"status": "pass", "claims": stats["claims"], "dimensions": len(stats["covered_dimensions"])},
                0,
            )
        )
    except (RoleError, BudgetExceeded, ValueError, KeyError, TypeError) as exc:
        return _downgrade(f"{type(exc).__name__}: {exc}")
    return RoleRun(document, tuple(outputs), "", "", box_budget.used)
