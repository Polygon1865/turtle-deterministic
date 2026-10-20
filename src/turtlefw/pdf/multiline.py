"""Multi-row PDF facts for main business and capex breakdowns.

A single scalar is insufficient for rows such as revenue by product/region or
capex by asset class. A FactRow keeps the dimension, period and source page so
the report can cite it without flattening the table into a misleading total.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal


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
