"""Cash-bridge metrics (true cash income → operating outflows → surplus).

This is the local counterpart of the upstream v2 factor-3 cash bridge. It
uses the cash-flow statement where available and falls back to OCF − capex
when the bridge components are missing (notably HK line-item data).

The output is deliberately explicit: every step is kept so the report can
show where ``AA`` came from, and missing components never become zero.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal
from typing import Mapping, Sequence

from ..data.protocol import StatementRow
from . import statements


@dataclass(frozen=True, slots=True)
class CashBridgeYear:
    year: int
    revenue: Decimal | None
    cash_received: Decimal | None
    ar_change: Decimal | None
    advance_change: Decimal | None
    prepayment_change: Decimal | None
    true_cash_income: Decimal | None
    operating_outflows: Decimal | None
    capex: Decimal | None
    surplus: Decimal | None
    ocf: Decimal | None
    fcf: Decimal | None
    source: str  # cash_bridge | derived_bridge | indirect_bridge | pdf_indirect | ocf_fallback | ocf_no_capex | unavailable
    complete: bool
    net_profit: Decimal | None = None
    depreciation_amortisation: Decimal | None = None
    working_capital_change: Decimal | None = None
    cash_generated: Decimal | None = None
    income_tax_paid: Decimal | None = None


def _series(rows: Sequence[StatementRow], statement: str, item: str) -> dict[int, Decimal]:
    return statements.annual_series(rows, statement, item)


def _positive(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value if value > 0 else Decimal("0")


def build_cash_bridge(
    rows: Sequence[StatementRow],
    *,
    pdf_bridge: Mapping[int, Mapping[str, str | None]] | None = None,
) -> dict[int, CashBridgeYear]:
    revenue = _series(rows, "income", "revenue")
    cash_received = _series(rows, "cashflow", "c_fr_sale_sg")
    inflow_total = _series(rows, "cashflow", "c_inf_fr_operate_a")
    ar = _series(rows, "balance", "accounts_receiv")
    prepayments = _series(rows, "balance", "prepayments")
    advance = _series(rows, "balance", "adv_receipts") or _series(
        rows, "balance", "contract_liab"
    )
    goods = _series(rows, "cashflow", "c_paid_goods_srv")
    employees = _series(rows, "cashflow", "c_paid_to_for_empl")
    taxes = _series(rows, "cashflow", "c_paid_for_taxes")
    other = _series(rows, "cashflow", "c_pay_oth_act")
    ocf = _series(rows, "cashflow", "n_cashflow_act")
    capex = _series(rows, "cashflow", "c_pay_acq_const_fiolta")

    years = sorted(set(revenue) | set(ocf) | set(cash_received) | set(inflow_total))
    result: dict[int, CashBridgeYear] = {}
    for year in years:
        rev = revenue.get(year)
        cash_in = cash_received.get(year)
        ar_change = (
            ar[year] - ar[year - 1] if year in ar and year - 1 in ar else None
        )
        advance_change = (
            advance[year] - advance[year - 1]
            if year in advance and year - 1 in advance
            else None
        )
        prepayment_change = (
            prepayments[year] - prepayments[year - 1]
            if year in prepayments and year - 1 in prepayments
            else None
        )

        true_cash: Decimal | None = cash_in
        if true_cash is None and rev is not None:
            ar_increase = _positive(ar_change)
            advance_decrease = _positive(-advance_change) if advance_change is not None else None
            if ar_increase is not None and advance_decrease is not None:
                prepay_increase = _positive(prepayment_change)
                true_cash = rev - ar_increase - (prepay_increase or Decimal("0")) - advance_decrease
                if advance_change is not None and advance_change > 0:
                    true_cash += advance_change

        outflow_parts = [goods.get(year), employees.get(year), taxes.get(year), other.get(year)]
        present = [value for value in outflow_parts if value is not None]
        outflows = sum(present, Decimal("0")) if len(present) >= 3 else None
        derived_outflows = False
        ocf_value = ocf.get(year)
        if outflows is None and inflow_total.get(year) is not None and ocf_value is not None:
            # Derive total operating outflow from the inflow subtotal and OCF.
            outflows = inflow_total[year] - ocf_value
            derived_outflows = True
        if derived_outflows and cash_in is None and rev is not None and ar_change is not None and advance_change is not None:
            # No sales-receipt line is available. Use the revenue-based proxy
            # only as a clearly-marked partial fallback; do not overwrite an
            # actual c_fr_sale_sg value with an accrual proxy.
            ar_increase = ar_change if ar_change > 0 else Decimal("0")
            prepay_increase = (
                prepayment_change
                if prepayment_change is not None and prepayment_change > 0
                else Decimal("0")
            )
            advance_increase = advance_change if advance_change > 0 else Decimal("0")
            advance_decrease = -advance_change if advance_change < 0 else Decimal("0")
            true_cash = rev - ar_increase - prepay_increase - advance_decrease + advance_increase
        indirect_bridge = False
        if outflows is None and ocf_value is not None and true_cash is not None:
            # HK line items have no gross cash receipts/payments. Derive the
            # implied operating outflow from OCF and mark it as indirect.
            outflows = true_cash - ocf_value
            indirect_bridge = True
        capex_value = abs(capex[year]) if year in capex else None
        fcf = (
            ocf_value - capex_value
            if ocf_value is not None and capex_value is not None
            else ocf_value
        )

        if true_cash is not None and outflows is not None:
            surplus = true_cash - outflows - (capex_value or Decimal("0"))
            if derived_outflows:
                # Total outflow came from inflow subtotal - OCF; the bridge is
                # useful but not a complete gross cash bridge.
                source = "derived_bridge"
                complete = False
            elif indirect_bridge:
                source = "indirect_bridge"
                complete = False
            elif cash_in is None:
                # The cash-income side was derived from revenue, not actual
                # sales receipts.
                source = "derived_bridge"
                complete = False
            else:
                source = "cash_bridge"
                complete = True
        elif ocf_value is not None:
            surplus = ocf_value - (capex_value or Decimal("0"))
            source = "ocf_fallback"
            complete = False
        else:
            surplus = None
            source = "unavailable"
            complete = False

        result[year] = CashBridgeYear(
            year=year,
            revenue=rev,
            cash_received=cash_in,
            ar_change=ar_change,
            advance_change=advance_change,
            prepayment_change=prepayment_change,
            true_cash_income=true_cash,
            operating_outflows=outflows,
            capex=capex_value,
            surplus=surplus,
            ocf=ocf_value,
            fcf=fcf,
            source=source,
            complete=complete,
        )
    if pdf_bridge:
        for year, values in pdf_bridge.items():
            item = result.get(year)
            if item is None:
                continue

            def number(key: str) -> Decimal | None:
                raw = values.get(key)
                try:
                    return Decimal(str(raw)) if raw not in (None, "") else None
                except Exception:  # noqa: BLE001 - PDF JSON is external
                    return None

            ocf_value = number("ocf")
            capex_value = number("capex")
            if ocf_value is None or capex_value is None:
                continue
            surplus = ocf_value - abs(capex_value)
            result[year] = replace(
                item,
                ocf=ocf_value,
                capex=abs(capex_value),
                surplus=surplus,
                fcf=surplus,
                source="pdf_indirect",
                complete=True,
                net_profit=number("net_profit"),
                depreciation_amortisation=number("depreciation_amortisation"),
                working_capital_change=number("working_capital_change"),
                cash_generated=number("cash_generated_from_operations"),
                income_tax_paid=number("income_tax_paid"),
            )
    return result


def surplus_series(bridge: Mapping[int, CashBridgeYear]) -> dict[int, Decimal]:
    return {
        year: item.surplus
        for year, item in bridge.items()
        if item.surplus is not None
    }


def coverage(bridge: Mapping[int, CashBridgeYear]) -> tuple[int, int]:
    """(complete bridge years, total years)."""
    return sum(1 for item in bridge.values() if item.complete), len(bridge)


def bridge_label(bridge: Mapping[int, CashBridgeYear]) -> str:
    """Human-readable source label for AA (never call a fallback a full bridge)."""
    sources = {item.source for item in bridge.values()}
    if not sources:
        return "FCF"
    if sources == {"pdf_indirect"}:
        return "PDF间接现金桥"
    if sources == {"pdf_indirect", "ocf_fallback"}:
        return "PDF间接现金桥+OCF"
    if "pdf_indirect" in sources:
        if "derived_bridge" in sources:
            return "PDF间接现金桥+推导桥（部分）"
        return "PDF间接现金桥+历史口径"
    if sources == {"derived_bridge"}:
        return "推导现金桥（部分）"
    if sources == {"cash_bridge", "derived_bridge"}:
        return "现金桥+推导桥（部分）"
    if "derived_bridge" in sources:
        return "推导现金桥+其他口径（部分）"
    if sources == {"cash_bridge"}:
        return "现金桥"
    if sources == {"indirect_bridge"}:
        return "间接现金桥"
    if sources == {"cash_bridge", "indirect_bridge"}:
        return "现金桥+间接桥"
    if sources == {"indirect_bridge", "ocf_fallback"}:
        return "间接现金桥+OCF"
    if sources == {"cash_bridge", "ocf_fallback"}:
        return "现金桥+OCF"
    if sources & {"cash_bridge", "indirect_bridge"}:
        return "现金桥+间接桥+OCF"
    return "FCF；现金桥不可用"
