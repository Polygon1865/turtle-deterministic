"""Normalised owner earnings.

A single year's net income is noisy for cyclicals and working-capital swings.
This module averages a 5-year owner-earnings series:

    OE_t = NI_t + D&A_t - maintenance capex_t - Δworking capital_t

where ``maintenance capex_t = D&A_t * G`` and working capital is
``ΔAR + ΔInventory - ΔAP``. Missing working-capital components are treated as
zero, and a year without NI/D&A is skipped.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from ..data.protocol import StatementRow
from . import statements


def normalized_owner_earnings(
    rows: Sequence[StatementRow],
    *,
    g: Decimal,
    years: int = 5,
) -> Decimal | None:
    income = statements.annual_series(rows, "income", "n_income_attr_p")
    da = statements.da_series(rows)
    ar = statements.annual_series(rows, "balance", "accounts_receiv")
    inventory = statements.annual_series(rows, "balance", "inventories")
    payable = statements.annual_series(rows, "balance", "acct_payable")

    values: list[Decimal] = []
    for year in sorted(set(income) & set(da))[-years:]:
        net_income = income.get(year)
        depreciation = da.get(year)
        if net_income is None or depreciation is None:
            continue
        wc_change = Decimal("0")
        if year - 1 in ar and year in ar:
            wc_change += ar[year] - ar[year - 1]
        if year - 1 in inventory and year in inventory:
            wc_change += inventory[year] - inventory[year - 1]
        if year - 1 in payable and year in payable:
            wc_change -= payable[year] - payable[year - 1]
        values.append(net_income + depreciation - depreciation * g - wc_change)
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def series(
    rows: Sequence[StatementRow],
    *,
    g: Decimal,
) -> dict[int, Decimal]:
    """Per-year owner earnings (used by tests/diagnostics)."""
    income = statements.annual_series(rows, "income", "n_income_attr_p")
    da = statements.da_series(rows)
    result: dict[int, Decimal] = {}
    for year in sorted(set(income) & set(da)):
        net_income = income.get(year)
        depreciation = da.get(year)
        if net_income is None or depreciation is None:
            continue
        result[year] = net_income + depreciation - depreciation * g
    return result
