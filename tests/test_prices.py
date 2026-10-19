from decimal import Decimal

from turtlefw.metrics.prices import adjust_ohlc, factor_map


def test_adjust_ohlc_backward():
    history = [
        {"trade_date": "20240101", "open": "10", "high": "12", "low": "9", "close": "11"},
        {"trade_date": "20250101", "open": "20", "high": "22", "low": "19", "close": "21"},
    ]
    factors = {"20240101": Decimal("2"), "20250101": Decimal("4")}
    adjusted = adjust_ohlc(history, factors)
    assert Decimal(adjusted[0]["close"]) == Decimal("11") * Decimal("0.5")
    assert Decimal(adjusted[1]["close"]) == Decimal("21")


def test_factor_map_skips_bad_rows():
    rows = [
        {"trade_date": "20240101", "adj_factor": "2.0"},
        {"trade_date": "20240102", "adj_factor": None},
        {"trade_date": "", "adj_factor": "3"},
    ]
    assert factor_map(rows) == {"20240101": Decimal("2.0")}
