"""Statement series and derived cash-flow metrics.

All functions take ``StatementRow`` lists and return plain ``Decimal`` values
in the reporting currency's base unit.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
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


def as_of_rows(rows: Iterable[StatementRow], as_of: date | str) -> list[StatementRow]:
    """Approximate PIT: keep rows whose announcement date is not after ``as_of``.

    Falls back to ``period_end <= as_of`` when ``ann_date`` is missing. This
    filters future announcements but cannot undo restatements/vintages.
    """
    cutoff = date.fromisoformat(as_of) if isinstance(as_of, str) else as_of
    return [
        row
        for row in rows
        if (row.ann_date is not None and row.ann_date <= cutoff)
        or (row.ann_date is None and row.period_end <= cutoff)
    ]


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
    """FCF = operating cash flow - |capex|; missing capex is not zero."""
    index = annual_index(rows)
    result: dict[int, Decimal] = {}
    for year, values in index.items():
        ocf = values.get(("cashflow", "n_cashflow_act"))
        capex = values.get(("cashflow", "c_pay_acq_const_fiolta"))
        if ocf is None or capex is None:
            continue
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


def diluted_shares(rows: Iterable[StatementRow]) -> Decimal | None:
    """Weighted diluted shares = attributable net income / diluted EPS."""
    income = annual_series(rows, "income", "n_income_attr_p")
    eps = annual_series(rows, "income", "diluted_eps")
    for year in sorted(set(income) & set(eps), reverse=True):
        if income[year] is not None and eps[year] and eps[year] > 0:
            return income[year] / eps[year]
    return None


@dataclass(frozen=True, slots=True)
class TTMSummary:
    as_of: date
    period_type: str
    values: dict[tuple[str, str], Decimal]
    note: str = ""


@dataclass(frozen=True, slots=True)
class TTMTransform:
    rows: list[StatementRow]
    as_of: date | None = None
    note: str = ""


def apply_ttm(rows: Iterable[StatementRow]) -> TTMTransform:
    """Return annual rows with the latest interim replaced by a TTM annual row.

    Flow items (income/cashflow) become annual + interim - prior interim;
    balance items use the latest interim balance. This lets the existing annual
    engine run on a TTM basis without changing its formulas.
    """
    row_list = list(rows)
    interim = latest_interim(row_list)
    if interim is None:
        return TTMTransform(row_list, note="没有 interim，未应用 TTM")
    period_end, period_type, current = interim
    annual_rows = [
        row
        for row in row_list
        if row.period_type == "annual" and row.period_end < period_end
    ]
    if not annual_rows:
        return TTMTransform(row_list, note="没有早于 interim 的年报，未应用 TTM")
    if any(row.period_type == "annual" and row.period_end.year == period_end.year for row in row_list):
        return TTMTransform(row_list, note="interim 与年报同年，未应用 TTM")
    annual_end = max(row.period_end for row in annual_rows)
    annual = {
        (row.statement, row.item): row.value
        for row in annual_rows
        if row.period_end == annual_end
    }
    prior_end = period_end.replace(year=period_end.year - 1)
    prior = {
        (row.statement, row.item): row.value
        for row in row_list
        if row.period_end == prior_end and row.period_type == period_type
    }
    synthetic: list[StatementRow] = []
    code = row_list[0].code
    currency = row_list[0].currency
    for (statement, item), current_value in current.items():
        key = (statement, item)
        if statement in ("income", "cashflow") and key in annual and key in prior:
            value = annual[key] + current_value - prior[key]
        elif statement == "balance":
            value = current_value
        else:
            continue
        synthetic.append(
            StatementRow(
                code=code,
                period_end=period_end,
                period_type="annual",
                statement=statement,
                item=item,
                value=value,
                currency=currency,
                source="ttm",
                ann_date=next(
                    (row.ann_date for row in row_list if row.period_end == period_end),
                    None,
                ),
            )
        )
    if not synthetic:
        return TTMTransform(row_list, note="没有可计算 TTM 的科目")
    kept = [
        row
        for row in row_list
        if not (row.period_type == "annual" and row.period_end.year == period_end.year)
    ]
    return TTMTransform(
        kept + synthetic,
        as_of=period_end,
        note=f"{annual_end.isoformat()} 年报 + {period_end.isoformat()} {period_type} - {prior_end.isoformat()} {period_type}",
    )


def ttm(rows: Iterable[StatementRow]) -> TTMSummary | None:
    """Latest annual + current interim - prior-year interim for flow items."""
    interim = latest_interim(rows)
    if interim is None:
        return None
    period_end, period_type, current = interim
    prior_end = period_end.replace(year=period_end.year - 1)
    prior = {
        (row.statement, row.item): row.value
        for row in rows
        if row.period_end == prior_end and row.period_type == period_type
    }
    annuals: dict[date, dict[tuple[str, str], Decimal]] = defaultdict(dict)
    for row in rows:
        if row.period_type == "annual" and row.period_end < period_end:
            annuals[row.period_end][(row.statement, row.item)] = row.value
    if not annuals:
        return None
    annual_end = max(annuals)
    annual = annuals[annual_end]
    values: dict[tuple[str, str], Decimal] = {}
    for key, current_value in current.items():
        if key in prior and key in annual:
            values[key] = annual[key] + current_value - prior[key]
    if not values:
        return None
    return TTMSummary(
        as_of=period_end,
        period_type=period_type,
        values=values,
        note=f"{annual_end.isoformat()} 年报 + {period_end.isoformat()} {period_type} - {prior_end.isoformat()} {period_type}",
    )


def latest_interim(    rows: Iterable[StatementRow],
) -> tuple[date, str, dict[tuple[str, str], Decimal]] | None:
    """Latest non-annual period and its raw values, if any."""
    periods: dict[date, str] = {}
    values: dict[date, dict[tuple[str, str], Decimal]] = defaultdict(dict)
    for row in rows:
        if row.period_type == "annual":
            continue
        periods[row.period_end] = row.period_type
        values[row.period_end][(row.statement, row.item)] = row.value
    if not periods:
        return None
    latest = max(periods)
    return latest, periods[latest], values[latest]


def annualise_factor(period_type: str) -> Decimal:
    """Q1×4, H1×2, Q3×4/3; annual/other ×1."""
    return {
        "q1": Decimal("4"),
        "interim": Decimal("2"),
        "q3": Decimal("4") / Decimal("3"),
    }.get(period_type, Decimal("1"))


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
