"""Apply selected PDF document facts to statement rows."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from ..data.protocol import StatementRow
from ..types import Currency

PDF_OVERRIDE_ITEMS = {"accounts_receiv", "inventory", "contract_liab"}
PDF_OVERRIDE_TOLERANCE = Decimal("0.01")


def _replacement(
    rows: list[StatementRow],
    item: str,
    value: Decimal,
    page: object,
    fact_period: object = None,
    fact_currency: object = None,
) -> tuple[StatementRow, date] | None:
    annual = [
        row
        for row in rows
        if row.statement == "balance" and row.item == item and row.period_type == "annual"
    ]
    if not annual:
        return None
    anchor = max(annual, key=lambda row: row.period_end)
    period = str(fact_period) if fact_period is not None else ""
    if period and str(anchor.period_end.year) not in period:
        return None
    if fact_currency and fact_currency != anchor.currency.value:
        return None
    if anchor.value != 0:
        diff = abs(value - anchor.value) / abs(anchor.value)
        if diff > PDF_OVERRIDE_TOLERANCE:
            return None
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


def merge_main_business(
    provider_rows: list[dict[str, object]] | None,
    pdf_rows: list[dict[str, object]] | None,
) -> list[dict[str, object]]:
    """PDF rows win on duplicate labels; provider rows fill the remainder."""
    merged: list[dict[str, object]] = list(pdf_rows or [])
    seen = {str(row.get("bz_item", "")).strip() for row in merged}
    for row in provider_rows or []:
        label = str(row.get("bz_item", "")).strip()
        if label and label in seen:
            continue
        merged.append(row)
    return merged


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
        applied = _replacement(
            result,
            item,
            value,
            fact.get("page", ""),
            fact.get("period"),
            fact.get("currency"),
        )
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
