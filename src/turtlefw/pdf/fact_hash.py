"""Semantic hash for PDF facts, independent of file path/order."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _fact(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("id", "label", "value", "unit", "page", "fact_hash")
    }


def _row(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in (
            "fact_id",
            "item",
            "dimension",
            "label",
            "period",
            "value",
            "unit",
            "page",
            "fact_hash",
        )
    }


def _dps(item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in ("dps", "currency", "page")}


def pdf_facts_hash(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return ""
    facts = [_fact(item) for item in payload.get("document_facts", [])]
    rows = [_row(item) for item in payload.get("fact_rows", [])]
    dps_raw = payload.get("dps") or payload.get("dps_fact") or None
    dps = _dps(dps_raw) if isinstance(dps_raw, Mapping) else dps_raw
    canonical = {
        "document_facts": sorted(facts, key=lambda item: str(item.get("id", ""))),
        "fact_rows": sorted(rows, key=lambda item: str(item.get("fact_id", ""))),
        "dps": dps,
    }
    text = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
