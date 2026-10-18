"""Statement series and derived cash-flow metrics.

All functions take ``StatementRow`` lists and return plain ``Decimal`` values
in the reporting currency's base unit.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from ..data.protocol import StatementRow
from ..types import Currency, Money

DEBT_ITEMS = ("st_borr", "lt_borr", "bond_payable", "non_cur_liab_due_1y")
DA_ITEMS = ("depr_fa_coga_dpba", "amort_intang_assets", "lt_amort_deferred_exp")


def annual_index(rows: Iterable[StatementRow]) -> dict[int, dict[tuple[str, str], Decimal]]:
    """``{year: {(statement, item): value}}`` for annual periods only."""
    index: dict[int, dict[tuple[str, str], Decimal]] = defaultdict(dict)
    for row in rows:
        if row.period_type != "annual":
            continue
        index[row.period_end.year][(row.statement, row.item)] = row.value
    return dict(index)


def annual_series(rows: Iterable[StatementRow], statement: str, item: str) -> dict[int, Decimal]:
    return {
        year: values[(statement, item)]
        for year, values in annual_index(rows).items()
        if (statement, item) in values
    }


def latest_value(series: Mapping[int, Decimal]) -> Decimal | None:
    if not series:
        return None
    return series[max(series)]


def _sum_items(values: Mapping[tuple[str, str], Decimal], statement: str, items: Sequence[str]) -> Decimal | None:
    present = [values[(statement, item)] for item in items if (statement, item) in values]
    if not present:
        return None
    return sum(present, Decimal("0"))


def fcf_series(rows: Iterable[StatementRow]) -> dict[int, Decimal]:
    """FCF = operating cash flow - |capex|."""
    index = annual_index(rows)
    result: dict[int, Decimal] = {}
    for year, values in index.items():
        ocf = values.get(("cashflow", "n_cashflow_act"))
        if ocf is None:
            continue
        capex = values.get(("cashflow", "c_pay_acq_const_fiolta")) or Decimal("0")
        result[year] = ocf - abs(capex)
    return result


def da_series(rows: Iterable[StatementRow]) -> dict[int, Decimal]:
    index = annual_index(rows)
    result: dict[int, Decimal] = {}
    for year, values in index.items():
        total = _sum_items(values, "cashflow", DA_ITEMS)
        if total is not None:
            result[year] = total
    return result


def interest_bearing_debt(rows: Iterable[StatementRow]) -> dict[int, Decimal]:
    index = annual_index(rows)
    result: dict[int, Decimal] = {}
    for year, values in index.items():
        total = _sum_items(values, "balance", DEBT_ITEMS)
        if total is not None:
            result[year] = total
    return result


def net_cash(rows: Iterable[StatementRow], currency: Currency) -> dict[int, Money]:
    """Cash and equivalents minus interest-bearing debt."""
    index = annual_index(rows)
    result: dict[int, Money] = {}
    for year, values in index.items():
        cash = values.get(("balance", "money_cap"))
        debt = _sum_items(values, "balance", DEBT_ITEMS)
        if cash is None or debt is None:
            continue
        result[year] = Money(cash - debt, currency)
    return result


def equity(rows: Iterable[StatementRow]) -> dict[int, Decimal]:
    return annual_series(rows, "balance", "total_hldr_eqy_exc_min_int")


def cash_and_equivalents(rows: Iterable[StatementRow]) -> dict[int, Decimal]:
    return annual_series(rows, "balance", "money_cap")


def net_income(rows: Iterable[StatementRow]) -> dict[int, Decimal]:
    return annual_series(rows, "income", "n_income_attr_p")


def revenue(rows: Iterable[StatementRow]) -> dict[int, Decimal]:
    return annual_series(rows, "income", "revenue")


def window(series: Mapping[int, Decimal], years: int = 5) -> dict[int, Decimal]:
    """Keep the most recent ``years`` observations."""
    if not series:
        return {}
    keep = sorted(series)[-years:]
    return {year: series[year] for year in keep}


def cagr(series: Mapping[int, Decimal], *, years: int = 5) -> Decimal | None:
    """Compound annual growth rate over the most recent ``years`` observations."""
    series = window(series, years)
    years_sorted = sorted(series)
    if len(years_sorted) < 2:
        return None
    first, last = years_sorted[0], years_sorted[-1]
    start, end = series[first], series[last]
    if start is None or end is None or start <= 0 or end <= 0 or last <= first:
        return None
    periods = Decimal(last - first)
    return (end / start) ** (Decimal("1") / periods) - Decimal("1")


def revenue_cagr(rows: Iterable[StatementRow]) -> Decimal | None:
    return cagr(revenue(rows))


def net_income_cagr(rows: Iterable[StatementRow]) -> Decimal | None:
    return cagr(net_income(rows))
