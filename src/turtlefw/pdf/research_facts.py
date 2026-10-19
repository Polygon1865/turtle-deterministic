"""Turn PDF section text into page-addressable research evidence.

The numeric extraction path (``pdf/extract.py``) owns statement numbers. This
module owns *qualitative* PDF evidence: section id, best page, excerpt and a
stable fact id. Claims can bind ``{{fact:pdf:section:MDA}}`` without copying
raw numeric text into the research document.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

SECTION_LABELS = {
    "P2": "受限现金/资产",
    "P3": "应收账款账龄",
    "P4": "关联方交易",
    "P6": "资本承诺/或有负债",
    "P13": "非经常性损益",
    "MDA": "管理层讨论与分析",
    "SUB": "附属公司/合并范围",
}
MAX_QUOTE = 320


def _document_hash(sections_path: Path | str | None) -> str:
    if sections_path is None:
        return ""
    path = Path(sections_path)
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def section_facts(
    payload: Mapping[str, Any],
    *,
    document_hash: str = "",
) -> list[dict[str, object]]:
    metadata = payload.get("metadata", {})
    section_pages = metadata.get("section_pages", {}) if isinstance(metadata, Mapping) else {}
    facts: list[dict[str, object]] = []
    for section, label in SECTION_LABELS.items():
        text = payload.get(section)
        if not isinstance(text, str) or not text.strip():
            continue
        pages = section_pages.get(section, []) if isinstance(section_pages, Mapping) else []
        page = pages[0] if isinstance(pages, list) and pages else None
        quote = " ".join(text.split())[:MAX_QUOTE]
        facts.append(
            {
                "id": f"pdf:section:{section}",
                "document_hash": document_hash,
                "page": page,
                "section": section,
                "label": label,
                "value": None,
                "unit": "",
                "quote": quote,
                "extraction_method": "section-context",
                "confidence": "medium" if page is not None else "low",
                "source_rank": 1,
            }
        )
    return facts


def load(path: Path | str) -> list[dict[str, object]]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    return section_facts(payload, document_hash=_document_hash(source))


def write(
    sections_path: Path | str,
    out_path: Path | str,
) -> list[dict[str, object]]:
    facts = load(sections_path)
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (json.dumps(facts, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return facts


def fact_map(facts: list[Mapping[str, object]]) -> dict[str, str]:
    return {
        str(fact["id"]): str(fact.get("quote", ""))
        for fact in facts
        if fact.get("id")
    }
