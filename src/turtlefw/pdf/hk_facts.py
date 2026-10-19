"""Semantic facts from HK annual-report sections.

The generic PDF extractor returns text/table blobs. HK reports put substantial
shareholders and segment revenue in prose tables, so this module extracts only
the two high-value facts and keeps a source page/text marker for audit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

_SHAREHOLDER = re.compile(
    r"(?P<name>[A-Z][A-Za-z0-9&.,'()\- ]{2,80}?)\s+Long position\s+"
    r".*?(?P<shares>\d[\d,]{5,})\s+(?P<pct>\d+(?:\.\d+)?)%",
    re.S,
)
_SEGMENT = re.compile(
    r"(?m)^(?P<name>[A-Z][A-Za-z][A-Za-z0-9 &/\-]{1,60}?)\s+"
    r"(?P<cur>\d[\d,]{2,})\s+(?P<prior>\d[\d,]{2,})\s+"
    r"(?P<yoy>-?\d+%)\s+(?P<share>\d+%)\s+(?P<share_prior>\d+%)\s*$"
)


@dataclass(frozen=True, slots=True)
class HKFacts:
    holders: list[dict[str, Any]] = field(default_factory=list)
    segments: list[dict[str, Any]] = field(default_factory=list)
    segment_total: Decimal | None = None
    segment_sum: Decimal | None = None
    segment_balanced: bool | None = None
    notes: list[str] = field(default_factory=list)


def _number(text: str) -> Decimal:
    try:
        return Decimal(text.replace(",", "").replace("%", ""))
    except InvalidOperation:
        return Decimal("0")


def extract_shareholders(text: str) -> list[dict[str, Any]]:
    start = text.upper().find("SUBSTANTIAL SHAREHOLDERS")
    if start < 0:
        return []
    block = text[start:]
    stop = block.find("Note:")
    if stop >= 0:
        block = block[:stop]
    holders: list[dict[str, Any]] = []
    for match in _SHAREHOLDER.finditer(block):
        name = " ".join(match.group("name").split())
        tail = block[match.end("name") : match.end("name") + 40]
        after_lines = block[match.end() :].splitlines()
        next_line = after_lines[1].strip() if len(after_lines) > 1 else ""
        if re.match(r"\s*Limited\b", tail, re.IGNORECASE) or next_line.lower().startswith(
            "limited"
        ):
            name = f"{name} Limited"
        holders.append(
            {
                "holder_name": name,
                "hold_amount": _number(match.group("shares")),
                "hold_ratio": _number(match.group("pct")),
                "source": "annual_report",
            }
        )
    return holders


def extract_segments(text: str) -> tuple[list[dict[str, Any]], Decimal | None, Decimal | None]:
    marker = "revenues of the Group and its segments"
    start = text.lower().find(marker.lower())
    if start < 0:
        return [], None, None
    block = text[start:]
    for end_marker in ("\nGross profit.", "\nGross profit ", "\n– Gross profit"):
        end = block.find(end_marker)
        if end >= 0:
            block = block[:end]
            break
    rows: list[dict[str, Any]] = []
    total: Decimal | None = None
    segment_sum = Decimal("0")
    for match in _SEGMENT.finditer(block):
        name = " ".join(match.group("name").split())
        current = _number(match.group("cur"))
        if name.lower() == "the group":
            total = current
            continue
        rows.append(
            {
                "bz_item": name,
                "bz_sales": current * Decimal("1000000"),
                "bz_sales_prior": _number(match.group("prior")) * Decimal("1000000"),
                "share_pct": _number(match.group("share")),
                "source": "annual_report",
            }
        )
        segment_sum += current
    return rows, total, segment_sum


def extract(sections: Mapping[str, Any]) -> HKFacts:
    p4 = sections.get("P4")
    mda = sections.get("MDA")
    holders = extract_shareholders(p4) if isinstance(p4, str) else []
    segments, total, segment_sum = extract_segments(mda) if isinstance(mda, str) else ([], None, None)
    notes: list[str] = []
    balanced: bool | None = None
    if total is not None and segment_sum is not None:
        balanced = segment_sum == total
        if not balanced:
            notes.append(f"segment sum {segment_sum} != total {total}")
    return HKFacts(
        holders=holders,
        segments=segments,
        segment_total=total,
        segment_sum=segment_sum,
        segment_balanced=balanced,
        notes=notes,
    )
