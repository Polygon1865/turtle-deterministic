"""Deterministic number audit: CLI values vs document-reported values.

The agent extracts numbers from an annual report (with source and page) into a
small JSON file; this module compares them with the canonical CLI values and
emits discrepancy records for the qualitative layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping

LABELS = {
    "revenue": "营业收入",
    "net_income": "归母净利润",
    "ocf": "经营现金流",
    "capex": "资本开支",
    "equity": "归母权益",
    "total_assets": "总资产",
}


@dataclass(frozen=True, slots=True)
class DocNumber:
    item: str
    value: Decimal
    source: str = ""
    page: str = ""
    source_rank: int = 1


def parse_doc_items(raw: Iterable[dict[str, Any]]) -> list[DocNumber]:
    items: list[DocNumber] = []
    for entry in raw:
        item = str(entry.get("item", "")).strip()
        if item not in LABELS:
            raise ValueError(f"unknown audit item: {item!r}")
        try:
            value = Decimal(str(entry.get("value", "")).replace(",", "").strip())
        except InvalidOperation as exc:
            raise ValueError(f"{item}: invalid value {entry.get('value')!r}") from exc
        if not value.is_finite():
            raise ValueError(f"{item}: value is not finite")
        items.append(
            DocNumber(
                item=item,
                value=value,
                source=str(entry.get("source", "")).strip(),
                page=str(entry.get("page", "")).strip(),
                source_rank=int(entry.get("source_rank", 1)),
            )
        )
    return items


def compare(
    cli: Mapping[str, Decimal],
    documents: Iterable[DocNumber],
    *,
    threshold_pct: Decimal = Decimal("1"),
) -> list[dict[str, str]]:
    """Return discrepancy records for values whose relative gap exceeds the threshold."""
    rows: list[dict[str, str]] = []
    for doc in documents:
        base = cli.get(doc.item)
        if base is None or base == 0:
            continue
        diff = abs(doc.value - base) / abs(base) * Decimal("100")
        if diff <= threshold_pct:
            continue
        rows.append(
            {
                "item": LABELS[doc.item],
                "cli_value": f"{base / Decimal('1000000'):,.2f}",
                "doc_value": f"{doc.value / Decimal('1000000'):,.2f}",
                "source": " ".join(part for part in (doc.source, doc.page) if part),
                "source_rank": str(doc.source_rank),
                "note": f"差异 {diff:.2f}%（单位：百万元）",
            }
        )
    return rows
