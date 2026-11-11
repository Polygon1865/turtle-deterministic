from __future__ import annotations

from turtlefw.facts import ResearchClaim
from turtlefw.qualitative import Evidence, Judgment, Qualitative
from turtlefw.research import ResearchDocument
from turtlefw.research_bridge import bridge


def _doc(*claims: ResearchClaim, evidence: dict[str, dict[str, object]] | None = None):
    return ResearchDocument(claims=claims, evidence=evidence or {})


def _claim(
    claim_id: str,
    dimension: str,
    judgment: str,
    *,
    confidence: str = "high",
    evidence_ids: tuple[str, ...] = ("e1",),
) -> ResearchClaim:
    return ResearchClaim(
        claim_id=claim_id,
        dimension=dimension,
        statement="判断",
        judgment=judgment,
        confidence=confidence,
        evidence_ids=evidence_ids,
    )


def test_bridge_maps_dimensions_and_keeps_pdf_evidence():
    doc = _doc(
        _claim("D2.1", "D2", "positive"),
        _claim("D4.1", "D4", "negative", confidence="medium"),
        evidence={
            "e1": {
                "source_type": "pdf",
                "url": "pdf://abc/p12",
                "quote": "原文",
                "page": "12",
            }
        },
    )
    result, modules = bridge(doc)
    assert result is not None
    assert set(modules) == {"moat", "management"}
    assert result.get("moat").judgment == "positive"  # type: ignore[union-attr]
    assert result.get("management").judgment == "negative"  # type: ignore[union-attr]
    assert result.get("management").evidence[0].source_type == "pdf"  # type: ignore[union-attr]
    assert result.source == "research_bridge"


def test_bridge_negative_wins_and_uses_weakest_confidence():
    doc = _doc(
        _claim("D1.business_model", "D1", "positive", confidence="high"),
        _claim("D1.business_model_mix", "D1", "negative", confidence="medium"),
        evidence={
            "e1": {
                "source_type": "data",
                "quote": "指标",
            }
        },
    )
    result, _ = bridge(doc)
    assert result is not None
    item = result.get("understandability")
    assert item is not None
    assert item.judgment == "negative"
    assert item.confidence == "medium"


def test_revenue_contraction_does_not_make_business_ununderstandable():
    """A falling top line is a performance fact, not a comprehension failure.

    On 2026-11-04 a `D1.revenue_contraction: negative` claim flipped 00270.HK
    from 买入 to 排除 through the 1A "看不懂" veto while every deterministic
    number stayed flat.
    """

    doc = _doc(
        _claim("D1.revenue_contraction", "D1", "negative", confidence="high"),
        evidence={"e1": {"source_type": "data", "quote": "营业收入五年复合增速为负"}},
    )
    result, modules = bridge(doc)
    assert result is None
    assert modules == ()


def test_bridge_ignores_low_confidence_and_unknown():
    doc = _doc(
        _claim("D2.1", "D2", "positive", confidence="low"),
        _claim("D2.2", "D2", "unknown"),
        evidence={"e1": {"source_type": "web", "url": "https://x.test", "quote": "q"}},
    )
    result, modules = bridge(doc)
    assert result is None
    assert modules == ()


def test_payout_claim_does_not_set_management():
    doc = _doc(
        _claim("D4.payout_consistency", "D4", "negative", confidence="medium"),
        evidence={
            "e1": {
                "source_type": "data",
                "quote": "支付率交叉核对：相对差 30.09% > 15%",
            }
        },
    )
    result, modules = bridge(doc)
    assert result is None
    assert modules == ()


def test_management_claim_sets_management():
    doc = _doc(
        _claim("D4.management_tenure", "D4", "negative", confidence="medium"),
        evidence={"e1": {"source_type": "data", "quote": "核心管理层频繁变动"}},
    )
    result, modules = bridge(doc)
    assert result is not None
    assert modules == ("management",)
    assert result.get("management").judgment == "negative"  # type: ignore[union-attr]


def test_bridge_keeps_human_judgement_and_fills_unknown():
    human = Qualitative(
        items={
            "moat": Judgment(
                module="moat",
                judgment="negative",
                confidence="high",
                evidence=(Evidence(url="https://x.test", quote="q", source_type="web"),),
            ),
            "policy": Judgment(
                module="policy",
                judgment="unknown",
                confidence="low",
            ),
        },
        source="qualitative.json",
    )
    doc = _doc(
        _claim("D2.1", "D2", "positive"),
        _claim("D3.1", "D3", "positive"),
        evidence={"e1": {"source_type": "web", "url": "https://x.test", "quote": "q"}},
    )
    result, modules = bridge(doc, human)
    assert result is not None
    assert result.get("moat").judgment == "negative"  # type: ignore[union-attr]
    assert result.get("policy").judgment == "positive"  # type: ignore[union-attr]
    assert modules == ("policy",)
    assert result.source == "qualitative.json+research_bridge"


def test_bridge_skips_claims_without_evidence():
    doc = _doc(_claim("D2.1", "D2", "positive", evidence_ids=()))
    result, modules = bridge(doc)
    assert result is None
    assert modules == ()


def test_bridge_rebuilds_derived_base_instead_of_freezing_old_result():
    doc = _doc(
        _claim("D4.1", "D4", "positive"),
        evidence={"e1": {"source_type": "data", "quote": "指标"}},
    )
    derived = Qualitative(
        items={
            "management": Judgment(
                module="management",
                judgment="negative",
                confidence="high",
                evidence=(Evidence(url="internal:old", quote="旧结论"),),
            )
        },
        source="research_bridge",
    )
    result, modules = bridge(doc, derived)
    assert result is not None
    assert result.get("management") is not None
    assert result.get("management").judgment == "positive"  # type: ignore[union-attr]
    assert modules == ("management",)
    assert result.source == "research_bridge"
