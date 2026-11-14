"""MetricRegistry duplicate handling: authoritative rank wins, ties keep last.

W1.7: when the same id is produced twice we must not silently let whichever
helper ran last decide the number.  A point carrying a higher ``source_rank``
(audited statement row) beats a derived or rounded one; equal ranks stay
last-write-wins so existing renders are unchanged.  Every disagreement is
recorded in ``conflicts`` for the QA/audit to surface.
"""

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


def test_higher_rank_wins_even_when_added_first() -> None:
    registry = MetricRegistry()
    registry.add(_point("87.78", display="87.78%", rank=3))
    registry.add(_point("66.97", display="66.97%", rank=0))

    assert registry.display("payout.2025") == "87.78%"
    conflict = registry.conflicts[-1]
    assert conflict["kept"] == "87.78%"
    assert conflict["dropped"] == "66.97%"
    assert conflict["kept_rank"] == 3
    assert conflict["dropped_rank"] == 0


def test_higher_rank_wins_when_added_last() -> None:
    registry = MetricRegistry()
    registry.add(_point("66.97", display="66.97%", rank=0))
    registry.add(_point("87.78", display="87.78%", rank=3))

    assert registry.display("payout.2025") == "87.78%"
    assert registry.conflicts[-1]["dropped_rank"] == 0


def test_equal_rank_stays_last_write_wins() -> None:
    registry = MetricRegistry()
    registry.add(_point("87.78", display="87.78%", rank=1))
    registry.add(_point("66.97", display="66.97%", rank=1))

    assert registry.display("payout.2025") == "66.97%"
    assert len(registry.conflicts) == 1


def test_missing_display_falls_back_to_plain_number() -> None:
    registry = MetricRegistry()
    first = MetricPoint(id="x", name="x", value=Decimal("1.5"), display="", unit="")
    second = MetricPoint(id="x", name="x", value=None, display="", unit="")
    registry.add(first)
    registry.add(second)

    assert registry.conflicts[-1]["kept"] == "—"
    assert registry.conflicts[-1]["dropped"] == "1.50"
