import pytest

from turtlefw.agent import AgentError, FakeLLM, ResearchAgent


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
