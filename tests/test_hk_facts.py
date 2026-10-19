from decimal import Decimal

from turtlefw.pdf.hk_facts import extract, extract_segments, extract_shareholders


P4 = """
INTERESTS OF SUBSTANTIAL SHAREHOLDERS
MIH Internet Holdings B.V. Long position Corporate (Note 1) 2,079,512,000 22.80%
Advance Data Services Long position Corporate (Note 2) 804,859,700 8.82%
Limited
Note:
1. controlled by Naspers.
"""

MDA = """
The following table sets forth revenues of the Group and its segments.
Revenues % of total revenues
VAS 369,281 319,168 16% 49% 49%
Marketing Services 144,973 121,374 19% 19% 18%
FinTech and Business Services 229,435 211,956 8% 31% 32%
Others 8,077 7,759 4% 1% 1%
The Group 751,766 660,257 14% 100% 100%
Gross profit rose by 21%.
"""


def test_shareholders_and_segments():
    holders = extract_shareholders(P4)
    assert len(holders) == 2
    assert holders[0]["holder_name"] == "MIH Internet Holdings B.V."
    assert holders[0]["hold_amount"] == Decimal("2079512000")
    assert holders[0]["hold_ratio"] == Decimal("22.80")
    assert holders[1]["holder_name"] == "Advance Data Services Limited"

    segments, total, segment_sum = extract_segments(MDA)
    assert len(segments) == 4
    assert total == Decimal("751766")
    assert segment_sum == Decimal("751766")
    facts = extract({"P4": P4, "MDA": MDA})
    assert facts.segment_balanced is True
    assert facts.segments[0]["bz_sales"] == Decimal("369281000000")


def test_segment_mismatch_is_flagged():
    facts = extract({"P4": P4, "MDA": MDA.replace("Others 8,077", "Others 8,000")})
    assert facts.segment_balanced is False
    assert facts.notes
