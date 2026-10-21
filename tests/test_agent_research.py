import pytest

from turtlefw.agent import AgentError, FakeLLM, ResearchAgent
from turtlefw.research import audit, load_payload, quality, render_markdown, thesis_markdown


def _valid_payload():
    return {
        "evidence": [{"id": "ev1", "url": "https://example.com/a", "quote": "原文"}],
        "claims": [
            {
                "claim_id": "D2.1",
                "dimension": "D2",
                "statement": "品牌护城河，R={{metric:r}}",
                "judgment": "positive",
                "confidence": "high",
                "evidence_ids": ["ev1"],
            }
        ],
    }


def test_research_prompt_covers_d1_to_d6():
    from turtlefw.agent import ResearchAgent

    for dimension in ("D1", "D2", "D3", "D4", "D5", "D6"):
        assert dimension in ResearchAgent.SYSTEM
    assert "pdf_deep" in ResearchAgent.SYSTEM
    assert "pdf_notes" in ResearchAgent.SYSTEM
    assert "pdf://" in ResearchAgent.SYSTEM
    assert "Never write a raw number" in ResearchAgent.SYSTEM
    assert "final report" not in ResearchAgent.SYSTEM.lower()


def test_research_agent_accepts_schema():
    document = ResearchAgent(FakeLLM(_valid_payload())).run({"code": "600887"})
    assert len(document.claims) == 1
    assert document.claims[0].claim_id == "D2.1"


def test_research_agent_retries_invalid_schema():
    class Flaky:
        def __init__(self):
            self.calls = 0

        def complete(self, system, payload):
            self.calls += 1
            if self.calls == 1:
                return {"claims": [{"claim_id": "bad"}]}
            return _valid_payload()

    llm = Flaky()
    document = ResearchAgent(llm).run({"code": "600887"}, retries=1)
    assert document.claims[0].claim_id == "D2.1"
    assert llm.calls == 2


def test_research_agent_retries_insufficient_quality():
    class Flaky:
        def __init__(self):
            self.calls = 0

        def complete(self, system, payload):
            self.calls += 1
            data = _valid_payload()
            if self.calls == 1:
                return data
            data["claims"].append(
                {
                    "claim_id": "D1.1",
                    "dimension": "D1",
                    "statement": "资本强度{{metric:r}}",
                    "judgment": "neutral",
                    "confidence": "medium",
                    "evidence_ids": ["ev1"],
                }
            )
            return data

    llm = Flaky()
    document = ResearchAgent(llm).run(
        {"code": "600887"}, retries=1, min_claims=2, min_dimensions=2
    )
    assert len(document.claims) == 2
    assert llm.calls == 2


def test_research_agent_rejects_raw_numbers():
    payload = _valid_payload()
    payload["claims"][0]["statement"] = "市场份额 30%"
    with pytest.raises(AgentError):
        ResearchAgent(FakeLLM(payload)).run({"code": "600887"})


def test_research_agent_rejects_unknown_evidence():
    payload = _valid_payload()
    payload["claims"][0]["evidence_ids"] = ["missing"]
    with pytest.raises(AgentError):
        ResearchAgent(FakeLLM(payload)).run({"code": "600887"})


def test_research_params_and_decisions():
    payload = _valid_payload()
    payload["params"] = [
        {
            "param_id": "d2.moat_rating",
            "label": "护城河评级",
            "value": "neutral",
            "dimension": "D2",
            "evidence_ids": ["ev1"],
        }
    ]
    payload["decisions"] = [
        {
            "decision_id": "g",
            "metric_id": "g",
            "selected": "1.15",
            "candidates": ["0.85", "1.15", "1.50"],
            "reason": "Capex/D&A 处于中等区间",
        }
    ]
    document = load_payload(payload)
    assert document.params[0].param_id == "d2.moat_rating"
    assert document.decisions[0].selected == "1.15"
    rendered = render_markdown(document, {"r": "3.36%"})
    assert "护城河评级" in rendered
    assert "1.15" in rendered
    assert "0.85, 1.15, 1.50" in rendered


def test_research_rejects_invalid_decision_candidate():
    payload = _valid_payload()
    payload["decisions"] = [
        {
            "decision_id": "g",
            "metric_id": "g",
            "selected": "9.99",
            "candidates": ["0.85", "1.15", "1.50"],
        }
    ]
    with pytest.raises(ValueError, match="selected must be one of candidates"):
        load_payload(payload)


def test_research_audit_reports_unresolved_refs():
    document = load_payload(_valid_payload())
    result = audit(document, metrics={}, facts={})
    assert result["status"] == "review"
    assert any("unresolved metric" in error for error in result["errors"])
    passed = audit(document, metrics={"r": "3.36%"}, facts={})
    assert passed["status"] == "pass"
    assert passed["quality"]["covered_dimensions"] == ["D2"]


def test_research_quality_ratio():
    document = load_payload(_valid_payload())
    result = quality(document)
    assert result["claims"] == 1
    assert result["dimensions"]["D1"] == 0
    assert result["evidence_ratio"] == 1.0


def test_research_thesis_params_render():
    payload = _valid_payload()
    payload["params"] = [
        {
            "param_id": "thesis.core",
            "label": "核心论点",
            "value": "R={{metric:r}} 且护城河稳定",
            "dimension": "D2",
            "evidence_ids": ["ev1"],
        }
    ]
    document = load_payload(payload)
    text = thesis_markdown(document, {"r": "3.36%"})
    assert "3.36%" in text
    assert "护城河稳定" in text
