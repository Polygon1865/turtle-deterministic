import json

from turtlefw.numeric_audit import audit
from turtlefw.research import ResearchDocument, _clip_quote, evidence_markdown


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
