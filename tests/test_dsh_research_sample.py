from pathlib import Path

from turtlefw.research import audit, load, quality

SAMPLE = Path(__file__).parent / "fixtures" / "dsh_research_sample.json"


def test_dsh_research_sample_passes_gate():
    document = load(SAMPLE)
    result = audit(
        document,
        metrics={
            "r": "3.36%",
            "payout.mean": "80.01%",
            "pledge_pct": "6.3%",
            "buyback_ratio": "0.3%",
            "parent_cash_ratio": "130.3%",
        },
        facts={},
    )
    assert result["status"] == "pass"
    assert result["quality"]["unknown"] == 0
    assert quality(document)["covered_dimensions"] == [
        "D1",
        "D2",
        "D3",
        "D4",
        "D5",
        "D6",
    ]
    assert quality(document)["evidence_ratio"] == 1.0
