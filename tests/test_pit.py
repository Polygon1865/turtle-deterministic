from datetime import date
from decimal import Decimal

import pytest

from turtlefw.data.protocol import StatementRow
from turtlefw.pit import PitError, PitStore
from turtlefw.types import Currency


def _row(value: str, ann: date) -> StatementRow:
    return StatementRow(
        code="600887.SH",
        period_end=date(2024, 12, 31),
        period_type="annual",
        statement="income",
        item="revenue",
        value=Decimal(value),
        currency=Currency.CNY,
        source="test",
        ann_date=ann,
    )


def test_pit_restatement_selection(tmp_path):
    store = PitStore(tmp_path)
    store.write("600887.SH", [_row("100", date(2025, 3, 30))], "2025-06-30")
    store.write("600887.SH", [_row("110", date(2026, 3, 30))], "2026-06-30")

    old = store.load("600887.SH", "2025-12-31")
    assert old.rows[0].value == Decimal("100")
    assert old.snapshot.knowledge_date == "2025-06-30"

    new = store.load("600887.SH", "2026-12-31")
    assert new.rows[0].value == Decimal("110")
    assert new.snapshot.knowledge_date == "2026-06-30"


def test_backfill_by_announcement_date(tmp_path):
    store = PitStore(tmp_path)
    snapshots = store.freeze_backfill(
        "600887.SH",
        [_row("100", date(2025, 3, 30)), _row("110", date(2026, 3, 30))],
    )
    assert [item.knowledge_date for item in snapshots] == ["2025-03-30", "2026-03-30"]
    earlier = store.load("600887.SH", "2025-06-30")
    assert earlier.rows[0].value == Decimal("100")
    later = store.load("600887.SH", "2026-06-30")
    assert later.rows[0].value == Decimal("110")


def test_missing_snapshot_raises(tmp_path):
    store = PitStore(tmp_path)
    with pytest.raises(PitError):
        store.load("600887.SH", "2025-01-01")


def test_prune_keeps_newest(tmp_path):
    store = PitStore(tmp_path)
    for day, value in (("2025-03-30", "100"), ("2025-06-30", "105"), ("2025-09-30", "110")):
        store.write("600887.SH", [_row(value, date.fromisoformat(day))], day)
    assert store.prune("600887.SH", keep=2) == 1
    assert len(store.list("600887.SH")) == 2
    assert store.load("600887.SH", "2025-12-31").rows[0].value == Decimal("110")
