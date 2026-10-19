from turtlefw.data.universe import listed_as_of


def test_listed_as_of_excludes_future_and_delisted():
    universe = [
        {"ts_code": "OLD", "list_date": "20100101", "delist_date": "20200101"},
        {"ts_code": "LIVE", "list_date": "20100101", "delist_date": None},
        {"ts_code": "FUTURE", "list_date": "20270101", "delist_date": None},
    ]
    assert [row["ts_code"] for row in listed_as_of(universe, "2025-06-30")] == ["LIVE"]


def test_nan_delist_date_is_treated_as_live():
    universe = [{"ts_code": "LIVE", "list_date": "20100101", "delist_date": float("nan")}]
    assert len(listed_as_of(universe, "20250630")) == 1
