from datetime import date
from decimal import Decimal

from turtlefw.data.protocol import StatementRow
from turtlefw.metrics import source_resolver
from turtlefw.types import Currency


def _rows() -> list[StatementRow]:
    return [
        StatementRow(
            "600887.SH",
            date(2025, 12, 31),
            "annual",
            "income",
            "revenue",
            Decimal("100"),
            Currency.CNY,
            "tushare",
            date(2026, 3, 30),
        )
    ]


def _items(value: str = "102") -> list[dict]:
    return [{"item": "revenue", "value": value, "page": "10", "confidence": "high"}]


def test_record_only_keeps_engine_value():
    candidates = source_resolver.collect(_rows(), _items())
    facts = source_resolver.solve(candidates, policy="record-only")
    assert facts[0].status == "conflict"
    assert facts[0].selected_for_display is None
    assert facts[0].selected_for_engine is None
    assert source_resolver.apply_engine(_rows(), facts)[0].value == Decimal("100")


def test_display_primary_does_not_change_engine():
    facts = source_resolver.solve(
        source_resolver.collect(_rows(), _items()), policy="display-primary"
    )
    assert facts[0].selected_for_display is not None
    assert facts[0].selected_for_engine is None


def test_engine_primary_replaces_row():
    facts = source_resolver.solve(
        source_resolver.collect(_rows(), _items()), policy="engine-primary"
    )
    rows = source_resolver.apply_engine(_rows(), facts)
    assert rows[0].value == Decimal("102")
    assert rows[0].source == "resolved:pdf"
