from decimal import Decimal

from turtlefw.cli import build_parser
from turtlefw.metrics.sotp import Segment, compute, parse_segments


def test_sotp_sums_segments_and_net_debt():
    result = compute(
        [
            Segment("云", "EBITDA", Decimal(100), Decimal(2)),
            Segment("广告", "EBITDA", Decimal(50), Decimal(3)),
        ],
        cash=Decimal(20),
        debt=Decimal(70),
        shares=Decimal(10),
    )
    assert result.ev == Decimal(350)
    assert result.net_debt == Decimal(50)
    assert result.equity == Decimal(300)
    assert result.per_share == Decimal(30)
    assert result.skipped == ()


def test_sotp_skips_invalid_segments_instead_of_zero_filling():
    result = compute(
        [
            Segment("有效", "PE", Decimal(10), Decimal(8)),
            Segment("缺倍数", "PE", Decimal(10), None),
            Segment("负基数", "PE", Decimal(-1), Decimal(8)),
        ],
        cash=None,
        debt=None,
        shares=Decimal(4),
    )
    assert result.ev == Decimal(80)
    assert result.per_share == Decimal(20)
    assert result.skipped == ("缺倍数", "负基数")


def test_sotp_with_no_valid_segment_is_none():
    result = compute([Segment("空", "PE", None, None)], cash=None, debt=None, shares=None)
    assert result.ev is None
    assert result.equity is None
    assert result.per_share is None


def test_sotp_parser_takes_explicit_base_units_and_multiple():
    segments = parse_segments(
        [{"name": "云", "metric": "EBITDA", "base": 100, "multiple": 2}]
    )
    assert segments[0].base == Decimal(100)
    assert segments[0].multiple == Decimal(2)


def test_valuation_parser_accepts_sotp():
    args = build_parser().parse_args(["valuation", "600887.SH", "--sotp", "sotp.json"])
    assert args.sotp == "sotp.json"
