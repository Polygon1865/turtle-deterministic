"""Synthetic row builder shared by tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from turtlefw.data.protocol import StatementRow
from turtlefw.types import Currency


def make_rows(
    spec: dict[tuple[str, str], dict[int, str]],
    *,
    code: str = "600887.SH",
    currency: Currency = Currency.CNY,
) -> list[StatementRow]:
    rows: list[StatementRow] = []
    for (statement, item), years in spec.items():
        for year, raw in years.items():
            rows.append(
                StatementRow(
                    code=code,
                    period_end=date(int(year), 12, 31),
                    period_type="annual",
                    statement=statement,
                    item=item,
                    value=Decimal(raw),
                    currency=currency,
                    source="test",
                    ann_date=date(int(year) + 1, 4, 20),
                )
            )
    return rows
