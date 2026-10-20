"""Apply selected PDF document facts to statement rows for one pilot field."""

from __future__ import annotations

from decimal import Decimal

from ..data.protocol import StatementRow
from ..types import Currency

PDF_OVERRIDE_ITEMS = {"accounts_receiv"}


def apply_document_facts(
    rows: list[StatementRow],
    document_facts: list[dict[str, object]] | None,
) -> list[StatementRow]:
    if not document_facts or not rows:
        return rows
    target = next((fact for fact in document_facts if fact.get("label") in PDF_OVERRIDE_ITEMS), None)
    if target is None:
        return rows
    item = str(target.get("label"))
    try:
        value = Decimal(str(target.get("value")))
    except Exception:
        return rows
    annual = [
        row
        for row in rows
        if row.statement == "balance" and row.item == item and row.period_type == "annual"
    ]
    if annual:
        anchor = max(annual, key=lambda row: row.period_end)
    else:
        return rows
    replacement = StatementRow(
        code=anchor.code,
        period_end=anchor.period_end,
        period_type=anchor.period_type,
        statement="balance",
        item=item,
        value=value,
        currency=Currency(anchor.currency.value),
        source=f"pdf:{item}:{target.get('page', '')}",
        ann_date=anchor.ann_date,
    )
    result: list[StatementRow] = []
    replaced = False
    for row in rows:
        if (
            row.period_end == anchor.period_end
            and row.statement == "balance"
            and row.item == item
            and row.period_type == "annual"
        ):
            result.append(replacement)
            replaced = True
        else:
            result.append(row)
    if not replaced:
        result.append(replacement)
    return result
