"""Multi-row PDF facts for main business and capex breakdowns.

A single scalar is insufficient for rows such as revenue by product/region or
capex by asset class. A FactRow keeps the dimension, period and source page so
the report can cite it without flattening the table into a misleading total.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

_NUMBER = re.compile(r"[-−]?\(?\d[\d,]*(?:\.\d+)?\)?")


@dataclass(frozen=True, slots=True)
class FactRow:
    fact_id: str
    item: str
    dimension: str
    label: str
    period: str
    value: Decimal
    unit: str
    page: int
    currency: str = ""
    source: str = "pdf"
    confidence: str = "medium"
    quote: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def fact_hash(self) -> str:
        payload = "|".join(
            (
                self.fact_id,
                self.item,
                self.dimension,
                self.label,
                self.period,
                str(self.value),
                self.unit,
                self.currency,
                str(self.page),
                self.source,
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "fact_id": self.fact_id,
            "item": self.item,
            "dimension": self.dimension,
            "label": self.label,
            "period": self.period,
            "value": f"{self.value:.2f}",
            "unit": self.unit,
            "currency": self.currency,
            "page": self.page,
            "source": self.source,
            "confidence": self.confidence,
            "quote": self.quote,
            "fact_hash": self.fact_hash,
        }
        payload.update(self.extra)
        return payload


def make_fact_id(*parts: object) -> str:
    raw = "|".join(str(part).strip() for part in parts)
    return "pdf:row:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _number(text: str) -> Decimal | None:
    match = _NUMBER.search(text)
    if not match:
        return None
    raw = match.group(0).replace(",", "").replace("−", "-")
    negative = raw.startswith("(") and raw.endswith(")")
    raw = raw.strip("()")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    return -value if negative else value


def rows_to_facts(
    tables: list[list[list[str | None]]],
    *,
    item: str,
    dimension: str,
    page: int,
    year: int,
    unit: str,
    currency: str = "",
    source: str = "pdf",
    scale: Decimal = Decimal("1"),
) -> list[FactRow]:
    """Convert main-business/capex table rows into multi-row facts.

    The first non-empty cell is the label; the first parseable numeric cell is
    the current-period value. Header rows without a numeric value are skipped.
    """
    facts: list[FactRow] = []
    for table in tables:
        current_column: int | None = None
        for row in table:
            header = [str(cell).strip() if cell is not None else "" for cell in row]
            if str(year) in header:
                current_column = header.index(str(year))
                break
        for row in table:
            cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
            if len(cells) < 2:
                continue
            label = cells[0]
            if label in {"产品", "项目", "合计", "总计", "分部", "行业", "地区"}:
                continue
            if any(cell.strip() in {str(year), str(year - 1)} for cell in cells):
                continue
            if current_column is not None:
                value = _number(cells[current_column]) if current_column < len(cells) else None
            else:
                value = None
                for cell in cells[1:]:
                    value = _number(cell)
                    if value is not None:
                        break
            if value is None:
                continue
            facts.append(
                FactRow(
                    fact_id=make_fact_id(page, item, dimension, label, year),
                    item=item,
                    dimension=dimension,
                    label=label,
                    period=f"{year}A",
                    value=value * scale,
                    unit=unit,
                    page=page,
                    currency=currency,
                    source=source,
                    confidence="medium",
                    quote=" | ".join(cells[:4]),
                )
            )
    return facts
