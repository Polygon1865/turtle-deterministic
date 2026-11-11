"""Contract tests for the four-role research pipeline (ADR-05 / ADR-06)."""

from __future__ import annotations

import json
from typing import Any, Mapping

import pytest

from turtlefw.agent.budget import BudgetExceeded, TokenBudget
from turtlefw.agent.pipeline import run_research_roles
from turtlefw.agent.roles import (
    AUDITOR,
    EXTRACTOR,
    RESEARCHER,
    ROLES,
    WRITER,
    RoleError,
    ToolBox,
    ToolNotAllowed,
    assemble_payload,
    estimate_tokens,
    validate_extraction,
    validate_research_draft,
)


class QueueLLM:
    def __init__(self, responses: list[Mapping[str, Any]]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def complete(self, system: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append((system, payload))
        if not self.responses:
            raise AssertionError("LLM queue is empty")
        return dict(self.responses.pop(0))


def _evidence_payload() -> dict[str, Any]:
    return {
        "evidence": [
            {"quote": "公司以奶茶为主业。", "url": "https://example.com/a", "source_type": "web"},
            {"quote": "门店数量一千家。", "url": None, "source_type": "data"},
        ]
    }


def _research_payload() -> dict[str, Any]:
    return {
        "claims": [
            {
                "claim_id": "D1.business_model",
                "dimension": "D1",
                "statement": "公司以奶茶为主业。",
                "judgment": "neutral",
                "confidence": "medium",
                "evidence_ids": ["ev-1"],
            }
        ],
        "params": [
            {
                "param_id": "thesis.core",
                "label": "核心",
                "value": "关注现金流与门店质量。",
                "dimension": "D1",
                "confidence": "medium",
            }
        ],
    }


def _full_document() -> dict[str, Any]:
    payload = _research_payload()
    payload["evidence"] = [
        {
            "id": "ev-1",
            "quote": "公司以奶茶为主业。",
            "url": "https://example.com/a",
            "source_type": "web",
        }
    ]
    return payload


def test_registry_covers_four_roles_with_whitelists() -> None:
    assert set(ROLES) == {"extractor", "researcher", "writer", "auditor"}
    assert EXTRACTOR.tools == ("read_metrics", "read_data_pack")
    assert RESEARCHER.tools == ("read_evidence", "read_metrics")
    assert WRITER.tools == ("read_evidence", "read_claims")
    assert AUDITOR.tools == ("validate_document", "quality", "language")
    assert EXTRACTOR.uses_llm and RESEARCHER.uses_llm
    assert not WRITER.uses_llm and not AUDITOR.uses_llm


def test_toolbox_rejects_tools_outside_the_whitelist() -> None:
    box = ToolBox(EXTRACTOR, {"read_metrics": lambda: {"r": 1}, "read_claims": lambda: []})
    assert box.call("read_metrics") == {"r": 1}
    with pytest.raises(ToolNotAllowed) as err:
        box.call("read_claims")
    assert "read_claims" in str(err.value)


def test_validate_extraction_assigns_ids_and_rejects_bad_url() -> None:
    rows = validate_extraction(_evidence_payload())
    assert [row["id"] for row in rows] == ["ev-1", "ev-2"]
    with pytest.raises(RoleError):
        validate_extraction({"evidence": [{"quote": "x", "url": "file:///tmp/a"}]})
    with pytest.raises(RoleError):
        validate_extraction({"evidence": [{"quote": "  "}]})
    with pytest.raises(RoleError):
        validate_extraction({"evidence": []})


def test_validate_research_draft_requires_claims() -> None:
    claims, params = validate_research_draft(_research_payload())
    assert len(claims) == 1 and len(params) == 1
    with pytest.raises(RoleError):
        validate_research_draft({"claims": []})
    with pytest.raises(RoleError):
        validate_research_draft({"claims": [{"claim_id": "x"}], "params": "nope"})


def test_assemble_payload_and_token_estimate() -> None:
    evidence = validate_extraction(_evidence_payload())
    payload = assemble_payload(evidence, [{"claim_id": "x"}], [])
    assert payload["evidence"][0]["id"] == "ev-1"
    assert estimate_tokens(payload) >= 1


def test_pipeline_happy_path_uses_four_roles() -> None:
    llm = QueueLLM([_evidence_payload(), _research_payload()])
    run = run_research_roles({"metrics": {}, "data_pack": ""}, llm=llm)
    assert run.ok is True
    assert run.document is not None
    assert [output.role for output in run.outputs] == [
        "extractor",
        "researcher",
        "writer",
        "auditor",
    ]
    assert run.tokens > 0
    # researcher must receive the extracted evidence, not the raw context only
    assert llm.calls[1][1]["evidence"][0]["id"] == "ev-1"
    assert llm.calls[0][0] != llm.calls[1][0]


def test_pipeline_falls_back_to_single_role_on_schema_failure() -> None:
    llm = QueueLLM([{"evidence": []}, _full_document()])
    run = run_research_roles({"metrics": {}}, llm=llm)
    assert run.fallback == "single_role"
    assert run.reason.startswith("RoleError")
    assert run.document is not None
    assert run.document.claims[0].claim_id == "D1.business_model"


def test_pipeline_degrades_to_deterministic_only_when_budget_is_exhausted() -> None:
    llm = QueueLLM([_evidence_payload()])
    exhausted = TokenBudget(limit=1, used=1)
    run = run_research_roles({"metrics": {}}, llm=llm, budget=exhausted)
    assert run.fallback == "deterministic_only"
    assert run.document is None
    assert "BudgetExceeded" in run.reason


def test_budget_charges_and_reports() -> None:
    budget = TokenBudget(limit=10)
    budget.charge(4)
    assert budget.remaining == 6
    with pytest.raises(BudgetExceeded):
        budget.charge(7)
    assert json.loads(json.dumps(budget.to_dict()))["used"] == 4
