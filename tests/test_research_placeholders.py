from turtlefw.facts import ResearchClaim, ResearchParam
from turtlefw.research import (
    ResearchDocument,
    canonical_metric_id,
    normalize_document_placeholders,
    normalize_placeholders,
)


def test_canonical_metric_resolves_known_alias() -> None:
    allowed = ("policy.payout_spread", "floor.divergence")
    assert canonical_metric_id("payout_spread", allowed) == "policy.payout_spread"
    assert canonical_metric_id("floor_divergence", allowed) == "floor.divergence"


def test_normalize_placeholders_handles_question_mark() -> None:
    text = "底价偏离 {{metric:floor_divergence?}}。"
    assert normalize_placeholders(text, ("floor.divergence",)) == (
        "底价偏离 {{metric:floor.divergence}}。"
    )


def test_normalize_document_reports_unresolved_ids() -> None:
    document = ResearchDocument(
        claims=(
            ResearchClaim(
                claim_id="D1.one",
                dimension="D1",
                statement="分红差 {{metric:payout_spread}}，未知 {{metric:not_registered}}。",
                judgment="neutral",
                confidence="medium",
                evidence_ids=(),
            ),
        ),
        evidence={},
        params=(
            ResearchParam(
                param_id="p1",
                label="底价偏离",
                value="{{metric:floor_divergence?}}",
                dimension="D1",
                evidence_ids=(),
                confidence="medium",
            ),
        ),
    )
    normalized, unresolved = normalize_document_placeholders(
        document, ("policy.payout_spread", "floor.divergence")
    )
    assert normalized.claims[0].statement.startswith("分红差 {{metric:policy.payout_spread}}")
    assert normalized.params[0].value == "{{metric:floor.divergence}}"
    assert unresolved == ("not_registered",)
