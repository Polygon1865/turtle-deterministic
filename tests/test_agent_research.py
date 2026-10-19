import pytest

from turtlefw.agent import AgentError, FakeLLM, ResearchAgent
from turtlefw.research import load_payload, render_markdown


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


def test_research_agent_accepts_schema():
    document = ResearchAgent(FakeLLM(_valid_payload())).run({"code": "600887"})
    assert len(document.claims) == 1
    assert document.claims[0].claim_id == "D2.1"


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
