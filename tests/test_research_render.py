import json

from turtlefw.facts import ResearchClaim
from turtlefw.numeric_audit import audit
from turtlefw.research import (
    ResearchDocument,
    _clip_quote,
    evidence_markdown,
    render_markdown,
)


def test_evidence_markdown_flattens_tables_and_hides_internal_ids() -> None:
    document = ResearchDocument(
        claims=(
            ResearchClaim(
                claim_id="D1.business_model",
                dimension="D1",
                statement="业务由超市与百货构成",
                judgment="neutral",
                confidence="high",
                evidence_ids=("ev",),
            ),
        ),
        evidence={
            "ev": {
                "source_type": "data",
                "title": "数据包 §2 分部收入",
                "quote": "| 超市 | 3,365.90 |\n| 百货 | 1,114.23 |",
            }
        },
    )
    text = evidence_markdown(document)
    assert "internal:" not in text
    assert "| 超市 |" not in text
    assert "超市 · 3,365.90" in text
    assert "数据包 §2 分部收入" in text

    claim_text = render_markdown(document, {})
    assert "| 超市 |" not in claim_text
    assert "> 超市 · 3,365.90" in claim_text


def test_clip_quote_does_not_leave_partial_number() -> None:
    text = "x " * 198 + "10,882.00 tail"
    clipped = _clip_quote(text, limit=400)
    assert "10," not in clipped
    assert clipped.endswith("…")


def test_evidence_markdown_keeps_complete_numbers(tmp_path) -> None:
    quote = (
        "| 2026-09-30 | 机构 | 2026Q4 | 10,882.00 | 510.00 | 1.27 | 18.05 | 买入 |"
        + " "
        + "补充说明 " * 80
    )
    document = ResearchDocument(
        claims=(),
        evidence={"ev": {"source_type": "data", "quote": quote}},
    )
    report = evidence_markdown(document)
    assert "10,882.00" in report

    report_path = tmp_path / "report.md"
    report_path.write_text(report, encoding="utf-8")
    source = tmp_path / "research.json"
    source.write_text(
        json.dumps({"evidence": [{"id": "ev", "source_type": "data", "quote": quote}]}),
        encoding="utf-8",
    )
    result = audit(report_path, [source], strict=True)
    assert result["status"] == "pass", result["unknown"]
