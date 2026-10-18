from decimal import Decimal

import pytest

from turtlefw.metrics.audit import compare, parse_doc_items


def test_matching_numbers_produce_nothing():
    rows = compare(
        {"revenue": Decimal("1000000000")},
        parse_doc_items([{"item": "revenue", "value": "1000000000"}]),
    )
    assert rows == []


def test_divergence_over_threshold_is_reported():
    rows = compare(
        {"revenue": Decimal("1000000000")},
        parse_doc_items([{"item": "revenue", "value": "1020000000", "source": "年报", "page": "p.12"}]),
    )
    assert len(rows) == 1
    assert rows[0]["item"] == "营业收入"
    assert "2.00%" in rows[0]["note"]
    assert rows[0]["source"] == "年报 p.12"


def test_small_divergence_is_ignored():
    rows = compare(
        {"revenue": Decimal("1000000000")},
        parse_doc_items([{"item": "revenue", "value": "1005000000"}]),
        threshold_pct=Decimal("1"),
    )
    assert rows == []


def test_unknown_item_rejected():
    with pytest.raises(ValueError):
        parse_doc_items([{"item": "ebitda", "value": "1"}])
