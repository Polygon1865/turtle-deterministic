import pytest

from turtlefw.facts import ResearchDecision
from turtlefw.research import ResearchDocument, engine_decisions


def document(*, evidence: bool = False) -> ResearchDocument:
    return ResearchDocument(
        claims=(),
        evidence={} if not evidence else {"ev": {"url": "https://x.test", "quote": "q"}},
        decisions=(
            ResearchDecision(
                decision_id="g",
                metric_id="g",
                selected="1.15",
                candidates=("0.85", "1.15", "1.50"),
                reason="maintenance capex",
                evidence_ids=("ev",) if evidence else (),
            ),
        ),
    )


def test_decisions_are_disabled_by_default():
    with pytest.raises(ValueError, match="disabled"):
        engine_decisions(document(), allow=False)


def test_decisions_require_evidence_when_enabled():
    with pytest.raises(ValueError, match="require evidence"):
        engine_decisions(document(), allow=True)


def test_decisions_return_selected_candidate_when_enabled():
    assert engine_decisions(document(evidence=True), allow=True) == {"g": "1.15"}


def test_no_decisions_is_always_allowed():
    empty = ResearchDocument(claims=(), evidence={})
    assert engine_decisions(empty) == {}
    assert engine_decisions(empty, allow=True) == {}
