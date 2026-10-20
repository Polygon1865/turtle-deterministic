"""Apply selected PDF document facts to statement rows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..data.protocol import StatementRow
from ..types import Currency

PDF_OVERRIDE_ITEMS = {"accounts_receiv", "inventory", "contract_liab"}


def _replacement(
    rows: list[StatementRow],
    item: str,
    value: Decimal,
    page: object,
) -> tuple[StatementRow, date] | None:
    annual = [
        row
        for row in rows
        if row.statement == "balance" and row.item == item and row.period_type == "annual"
    ]
    if not annual:
        return None
    anchor = max(annual, key=lambda row: row.period_end)
    replacement = StatementRow(
        code=anchor.code,
        period_end=anchor.period_end,
        period_type=anchor.period_type,
        statement="balance",
        item=item,
        value=value,
        currency=Currency(anchor.currency.value),
        source=f"pdf:{item}:{page}",
        ann_date=anchor.ann_date,
    )
    return replacement, anchor.period_end


def main_business_rows(fact_rows: list[dict[str, object]] | None) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for row in fact_rows or []:
        if row.get("item") != "main_business":
            continue
        result.append(
            {
                "bz_item": str(row.get("label", "")),
                "bz_sales": row.get("value"),
                "bz_profit": None,
                "source": "pdf",
            }
        )
    return result


def apply_document_facts(
    rows: list[StatementRow],
    document_facts: list[dict[str, object]] | None,
) -> list[StatementRow]:
    if not document_facts or not rows:
        return rows
    result = list(rows)
    for fact in document_facts:
        item = str(fact.get("label", ""))
        if item not in PDF_OVERRIDE_ITEMS:
            continue
        try:
            value = Decimal(str(fact.get("value")))
        except Exception:
            continue
        applied = _replacement(result, item, value, fact.get("page", ""))
        if applied is None:
            continue
        replacement, period_end = applied
        result = [
            replacement
            if (
                row.period_end == period_end
                and row.statement == "balance"
                and row.item == item
                and row.period_type == "annual"
            )
            else row
            for row in result
        ]
    return result
