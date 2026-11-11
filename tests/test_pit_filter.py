"""Point-in-time ingestion guard: rows announced after ``as_of`` never enter."""

from __future__ import annotations

import json
from pathlib import Path

from turtlefw.backtest import lookahead_audit
from turtlefw.report.snapshot import filter_as_of_rows


def _row(item: str, ann: str | None) -> dict:
    row = {"statement": "income", "item": item, "value": "1"}
    if ann is not None:
        row["ann_date"] = ann
    return row


class TestFilterAsOfRows:
    def test_future_announcement_is_dropped(self):
        rows = [_row("revenue", "20261015"), _row("net_income", "20261029")]
        kept, dropped = filter_as_of_rows(rows, "20261021")
        assert dropped == 1
        assert [row["item"] for row in kept] == ["revenue"]

    def test_iso_dates_are_normalised(self):
        rows = [_row("revenue", "2026-10-29"), _row("net_income", "2026/10/20")]
        kept, dropped = filter_as_of_rows(rows, "2026-10-21")
        assert dropped == 1
        assert [row["item"] for row in kept] == ["net_income"]

    def test_rows_without_announcement_date_are_kept(self):
        rows = [_row("revenue", None), _row("net_income", "")]
        kept, dropped = filter_as_of_rows(rows, "20261021")
        assert dropped == 0
        assert len(kept) == 2

    def test_missing_as_of_keeps_everything(self):
        rows = [_row("revenue", "20261029")]
        kept, dropped = filter_as_of_rows(rows, "")
        assert dropped == 0
        assert len(kept) == 1

    def test_input_rows_are_not_mutated(self):
        rows = [_row("revenue", "20261029")]
        filter_as_of_rows(rows, "20261021")
        assert len(rows) == 1  # the caller's list is untouched

    def test_statement_row_objects_are_supported(self):
        from datetime import date
        from decimal import Decimal

        from turtlefw.data.protocol import StatementRow
        from turtlefw.types import Currency

        row = StatementRow(
            code="KO.US",
            period_end=date(2025, 12, 31),
            period_type="annual",
            statement="income",
            item="revenue",
            value=Decimal("1"),
            currency=Currency.USD,
            source="sec",
            ann_date=date(2026, 1, 10),
        )
        kept, dropped = filter_as_of_rows([row], "20260101")
        assert dropped == 1
        assert kept == []

    def test_archived_violation_cleans_up(self, tmp_path: Path):
        snapshot = tmp_path / "snapshot"
        snapshot.mkdir()
        rows = [
            {"code": "600729.SH", "statement": "balance", "item": "accounts_receiv",
             "value": "1", "ann_date": "20261029"},
            {"code": "600729.SH", "statement": "income", "item": "revenue",
             "value": "1", "ann_date": "20261020"},
        ]
        before = {"as_of": "20261021", "rows": rows}
        (snapshot / "inputs.json").write_text(json.dumps(before), encoding="utf-8")
        assert not lookahead_audit(snapshot).clean

        kept, dropped = filter_as_of_rows(rows, "20261021")
        assert dropped == 1
        (snapshot / "inputs.json").write_text(
            json.dumps({"as_of": "20261021", "rows": kept}), encoding="utf-8"
        )
        assert lookahead_audit(snapshot).clean
