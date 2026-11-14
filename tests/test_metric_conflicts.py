"""MetricRegistry duplicates must be visible instead of silently last-wins."""

from __future__ import annotations

from decimal import Decimal

from turtlefw.facts import MetricPoint, MetricRegistry


def _point(value: str, display: str | None = None, rank: int = 0) -> MetricPoint:
    return MetricPoint(
        id="payout.2025",
        name="支付率",
        value=Decimal(value),
        unit="%",
        display=display or f"{Decimal(value):.2f}%",
        source_rank=rank,
    )


def test_identical_duplicate_is_not_a_conflict() -> None:
    registry = MetricRegistry()
    registry.add(_point("87.78"))
    registry.add(_point("87.78"))
    assert registry.conflicts == []


def test_different_duplicate_is_recorded_and_last_wins() -> None:
    registry = MetricRegistry()
    registry.add(_point("87.78", display="87.78%", rank=3))
    registry.add(_point("66.97", display="66.97%", rank=0))

    assert registry.display("payout.2025") == "66.97%"
    assert len(registry.conflicts) == 1
    conflict = registry.conflicts[0]
    assert conflict["id"] == "payout.2025"
    assert conflict["kept"] == "66.97%"
    assert conflict["dropped"] == "87.78%"
    assert conflict["kept_rank"] == 0
    assert conflict["dropped_rank"] == 3


def test_missing_display_falls_back_to_plain_number() -> None:
    registry = MetricRegistry()
    first = MetricPoint(id="x", name="x", value=Decimal("1.5"), display="", unit="")
    second = MetricPoint(id="x", name="x", value=None, display="", unit="")
    registry.add(first)
    registry.add(second)

    assert registry.conflicts[-1]["kept"] == "—"
    assert registry.conflicts[-1]["dropped"] == "1.50"
