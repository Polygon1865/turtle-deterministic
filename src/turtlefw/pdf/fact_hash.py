"""Semantic hash for PDF facts, independent of file path/order."""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def pdf_facts_hash(payload: Mapping[str, Any] | None) -> str:
    if not payload:
        return ""
    facts = list(payload.get("document_facts", []))
    rows = list(payload.get("fact_rows", []))
    dps = payload.get("dps") or payload.get("dps_fact") or None
    canonical = {
        "document_facts": sorted(facts, key=lambda item: str(item.get("id", ""))),
        "fact_rows": sorted(rows, key=lambda item: str(item.get("fact_id", ""))),
        "dps": dps,
    }
    text = json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
