"""Shared deterministic formatting helpers for report and data pack."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Sequence

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _m(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value / Decimal('1000000'):,.2f}"


def _pct(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}%"


def _ratio_pct(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return _pct(value * Decimal("100"))


def _num(value: Decimal | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _x(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f}x"


def _table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    aligns: Sequence[str] | None = None,
) -> str:
    aligns = aligns or ["l"] * len(headers)
    sep = "|" + "|".join("---:" if a == "r" else ":---" for a in aligns) + "|"
    lines = ["| " + " | ".join(headers) + " |", sep]
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)
