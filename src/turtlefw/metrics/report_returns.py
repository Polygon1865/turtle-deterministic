"""Canonical owner-earnings and return calculations.

Both the factor engine and the data pack call this module so R/GG/OE/AA cannot
drift between report paths.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping, Sequence

from ..data.protocol import StatementRow
from ..types import Currency, Money
from . import cashflow, grids, owner_earnings, returns, statements


@dataclass(frozen=True)
class ReportReturns:
    oe: Decimal | None
    oe_years: int
    oe_normalized: bool
    aa: Decimal | None
    aa_net: Decimal | None
    aa_variants: tuple[grids.AAVariant, ...]
    aa_source: str
    bridge: dict[int, cashflow.CashBridgeYear]
    surplus: dict[int, Decimal]
    r: Decimal | None
    gg: Decimal | None


def compute(
    rows: Sequence[StatementRow],
    *,
    g: Decimal,
    mean_payout: Decimal | None,
    market_cap: Money,
    currency: Currency,
    tax_pct: Decimal,
    buyback: Money | None,
    sbc: Money | None,
    pdf_bridge: Mapping[int, Mapping[str, str | None]] | None = None,
    aa_label: str | None = None,
) -> ReportReturns:
    net_income = statements.net_income(rows)
    da = statements.da_series(rows)
    latest = max(net_income) if net_income else None
    latest_ni = net_income.get(latest) if latest is not None else None
    latest_da = da.get(latest) if latest is not None else None
    oe = (
        latest_ni + latest_da - latest_da * g
        if latest_ni is not None and latest_da is not None
        else latest_ni
    )
    oe_normalized, oe_years = owner_earnings.normalized_owner_earnings_detail(rows, g=g)
    oe_used = oe_normalized if oe_normalized is not None else oe

    bridge = cashflow.build_cash_bridge(rows, pdf_bridge=pdf_bridge)
    surplus = cashflow.surplus_series(bridge)
    fcf = statements.fcf_series(rows)
    aa_all = tuple(grids.aa_variants(surplus) if surplus else grids.aa_variants(fcf))
    aa = aa_all[0].value if aa_all else None
    source_base = cashflow.bridge_label(bridge)
    aa_source = f"{aa_all[0].label}（{source_base}）" if aa_all else "不可用"
    if aa_label:
        selected = next((row for row in aa_all if row.label == aa_label), None)
        if selected is None:
            raise ValueError(f"AA label is not available: {aa_label}")
        aa = selected.value
        aa_source = f"{selected.label}（{source_base}）"
    sbc_amount = sbc.amount if sbc is not None else Decimal("0")
    aa_net = (aa - sbc_amount) if aa is not None else None

    def return_at(value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return returns.penetration_return(
            Money(value, currency),
            mean_payout or Decimal("0"),
            tax_pct,
            buyback or Money.zero(currency),
            market_cap,
            Decimal("1"),
        )

    return ReportReturns(
        oe=oe_used,
        oe_years=len(oe_years),
        oe_normalized=oe_normalized is not None,
        aa=aa,
        aa_net=aa_net,
        aa_variants=aa_all,
        aa_source=aa_source,
        bridge=bridge,
        surplus=surplus,
        r=return_at(oe_used),
        gg=return_at(aa_net),
    )
