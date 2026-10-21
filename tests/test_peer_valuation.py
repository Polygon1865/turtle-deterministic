from decimal import Decimal

from turtlefw.cli import build_parser
from turtlefw.metrics.peer_valuation import compute


def test_peer_comps_uses_median_and_requires_three_peers():
    result = compute(
        eps=Decimal(2),
        bvps=Decimal(10),
        peers=[
            {"pe_ttm": 10, "pb": 1},
            {"pe_ttm": 12, "pb": 2},
            {"pe_ttm": 14, "pb": 3},
            {"pe_ttm": 100, "pb": 4},
        ],
    )
    assert result.peer_count == 4
    assert result.pe_median == Decimal(13)
    assert result.pb_median == Decimal(5) / Decimal(2)
    assert result.pe_value == Decimal(26)
    assert result.pb_value == Decimal(25)


def test_peer_comps_skips_missing_and_non_positive_multiples():
    result = compute(
        eps=Decimal(1),
        bvps=Decimal(5),
        peers=[
            {"pe_ttm": None, "pb": 0},
            {"pe_ttm": -3, "pb": None},
            {"pe_ttm": 8, "pb": 1},
        ],
    )
    assert result.pe_median is None
    assert result.pb_median is None
    assert result.pe_value is None


def test_peer_comps_does_not_value_negative_eps():
    result = compute(
        eps=Decimal(-1),
        bvps=Decimal(5),
        peers=[
            {"pe_ttm": 10, "pb": 1},
            {"pe_ttm": 12, "pb": 2},
            {"pe_ttm": 14, "pb": 3},
        ],
    )
    assert result.pe_median == Decimal(12)
    assert result.pe_value is None
    assert result.pb_value == Decimal(10)


def test_valuation_parser_accepts_wacc_overrides():
    args = build_parser().parse_args(
        ["valuation", "600887", "--beta", "1.1", "--erp", "5.5"]
    )
    assert args.beta == 1.1
    assert args.erp == 5.5


def test_valuation_parser_accepts_pit_and_ttm():
    args = build_parser().parse_args(
        ["valuation", "600887", "--as-of", "2025-06-30", "--pit", "--ttm"]
    )
    assert args.as_of == "2025-06-30"
    assert args.pit is True
    assert args.ttm is True

