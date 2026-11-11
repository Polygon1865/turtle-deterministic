"""Shared deterministic formatting helpers for report and data pack."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Sequence

from ..types import Market

TEMPLATE_DIR = Path(__file__).parent / "templates"


def data_source_label(market: Market) -> str:
    """Human label for the vendor that produced the numbers.

    US statements come from SEC companyfacts with yfinance as the fallback, so
    claiming "Tushare Pro" (as the 2026-11-11 KO.US smoke found) is false.
    """

    return "Tushare Pro" if market is not Market.US else "yfinance + SEC（实验）"



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


def _cell(value: object) -> str:
    """Render one table cell without letting its text break the table.

    A literal ``|`` inside a cell starts a new column in every Markdown
    dialect, so it must be escaped before it reaches the template.  Newlines
    are folded into spaces for the same reason.
    """

    text = " ".join(str(value).split())
    return text.replace("|", "\\|")


def _table(
    headers: Sequence[str],
    rows: Sequence[Sequence[str]],
    aligns: Sequence[str] | None = None,
) -> str:
    aligns = aligns or ["l"] * len(headers)
    sep = "|" + "|".join("---:" if a == "r" else ":---" for a in aligns) + "|"
    lines = [
        "| " + " | ".join(_cell(header) for header in headers) + " |",
        sep,
    ]
    for row in rows:
        lines.append("| " + " | ".join(_cell(cell) for cell in row) + " |")
    return "\n".join(lines)
