"""Structured high-value note tables from annual-report PDFs.

The deep index keeps page text; this module extracts a small, deterministic set
of *tables* that matter to an equity researcher: revenue mix, R&D, customers,
restricted assets, debt maturity, related-party transactions, inventory and
receivables.

It only chooses and normalises tables that were already extracted by
``preprocessor.extract_all_pages``.  It does not parse numbers into statements
and does not infer values from prose.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .deep_index import pdf_citation

NOTES_VERSION = 1
MAX_TABLES = 30
MAX_ROWS = 12
_CELL_NUMBER = re.compile(r"^[\s\-+]?[\d,]+(?:\.\d+)?%?$")
_PAGE_MARKER = re.compile(r"^\d+\s*/\s*\d+$")

NOTE_GROUPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("revenue", "营业收入构成", ("营业收入构成", "主营业务分行业", "分产品", "分地区")),
    ("rd", "研发投入", ("研发投入", "研发费用", "研发人员")),
    ("customers", "客户与供应商", ("前五名客户", "前五名供应商", "客户集中度")),
    ("restricted", "受限资产", ("受限资产", "所有权或使用权受到限制", "使用受限")),
    ("debt", "有息负债与到期", ("有息负债", "债务期限", "借款到期", "一年内到期")),
    ("related", "关联交易", ("关联方交易", "关联交易", "关联方往来")),
    ("inventory", "存货", ("存货跌价", "存货构成", "存货明细")),
    ("receivables", "应收账款", ("应收账款账龄", "应收账款构成", "坏账准备")),
)

_GROUP_LIMITS = {
    "revenue": 4,
    "rd": 3,
    "customers": 2,
    "restricted": 2,
    "debt": 2,
    "related": 2,
    "inventory": 2,
    "receivables": 2,
}

_GROUP_SIGNALS = {
    "revenue": ("收入", "产品", "行业", "地区", "销售模式"),
    "rd": ("研发", "费用化", "资本化"),
    "customers": ("客户", "供应商", "采购", "销售"),
    "restricted": ("受限", "限制", "保证金", "冻结"),
    "debt": ("到期", "借款", "负债", "债券", "利率"),
    "related": ("关联", "关系", "交易"),
    "inventory": ("存货", "原材料", "库存", "跌价"),
    "receivables": ("应收", "账龄", "坏账", "信用"),
}



@dataclass(frozen=True, slots=True)
class NoteTable:
    group: str
    title: str
    page: int
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    citation: str

    def to_dict(self) -> dict[str, object]:
        return {
            "group": self.group,
            "title": self.title,
            "page": self.page,
            "headers": list(self.headers),
            "rows": [list(row) for row in self.rows],
            "citation": self.citation,
        }


def _clean_cell(cell: str) -> str:
    return " ".join(str(cell).replace("\n", " ").split())


def _parse_tables(chunk: str) -> tuple[list[list[list[str]]], str]:
    """Return markdown tables in ``chunk`` and the trailing non-table text."""
    lines = chunk.splitlines()
    tables: list[list[list[str]]] = []
    current: list[list[str]] = []
    trailing: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [_clean_cell(cell) for cell in stripped.strip("|").split("|")]
            if all(set(cell) <= {"-", ":", " "} for cell in cells if cell):
                continue
            current.append(cells)
            continue
        if current:
            tables.append(current)
            current = []
            trailing = lines[index:]
            break
    if current:
        tables.append(current)
    return tables, "\n".join(trailing)


def _match_group(prefix: str) -> tuple[str, str] | None:
    for group, label, keywords in NOTE_GROUPS:
        for keyword in keywords:
            if keyword in prefix:
                return group, label
    return None


def _title(prefix: str, label: str) -> str:
    lines = [_clean_cell(line) for line in prefix.splitlines() if _clean_cell(line)]
    for line in reversed(lines[-14:]):
        if len(line) > 60 or line.endswith(("。", "：")) or _PAGE_MARKER.match(line):
            continue
        if any(mark in line for mark in ("√", "□", "适用")):
            continue
        if any(char.isdigit() for char in line):
            continue
        if any(keyword in line for _, _, keywords in NOTE_GROUPS for keyword in keywords):
            return line
    for line in reversed(lines[-8:]):
        if _PAGE_MARKER.match(line) or line.endswith(("。", "：")):
            continue
        if any(mark in line for mark in ("√", "□", "适用")):
            continue
        if not any(char.isdigit() for char in line) and 4 <= len(line) <= 40:
            return line
    return label


def _looks_like_header(row: Sequence[str]) -> bool:
    nonempty = [cell for cell in row if cell]
    if len(nonempty) < 2:
        return False
    return not any(_CELL_NUMBER.match(cell) for cell in nonempty)


def _pick_header(rows: list[list[str]]) -> tuple[tuple[str, ...], tuple[tuple[str, ...], ...]] | None:
    for index, row in enumerate(rows[:4]):
        if not _looks_like_header(row):
            continue
        header = tuple(row)
        body = tuple(tuple(item) for item in rows[index + 1 :] if any(item))
        if body:
            return header, body
    return None


def _has_numeric_row(rows: Sequence[Sequence[str]]) -> bool:
    return any(
        any(any(char.isdigit() for char in cell) for cell in row)
        for row in rows
    )


def _header_title(group: str, headers: Sequence[str]) -> str:
    for cell in headers:
        clean = _clean_cell(cell)
        if clean and len(clean) <= 30 and any(
            term in clean for term in _GROUP_SIGNALS[group]
        ):
            return clean
    return ""


def _needs_header_title(title: str) -> bool:
    if len(title) < 8:
        return True
    if not any("\u4e00" <= char <= "\u9fff" for char in title):
        return True
    if title.endswith(("供", "的", "与", "及")):
        return True
    return title.count("（%）") >= 2


def _signal(group: str, title: str, headers: Sequence[str]) -> bool:
    header_text = " ".join(headers)
    if group == "customers":
        return any(term in header_text for term in ("客户", "供应商", "采购"))
    if group == "receivables":
        return any(term in header_text for term in ("应收", "账龄", "坏账", "信用"))
    if group == "debt":
        return any(term in header_text for term in ("借款", "负债", "到期", "债券", "利率"))
    text = " ".join((title, *headers))
    return any(term in text for term in _GROUP_SIGNALS[group])


def extract_note_tables(
    pages: Iterable[tuple[int, str]],
    *,
    document_hash: str = "",
    max_tables: int = MAX_TABLES,
    max_rows: int = MAX_ROWS,
) -> list[NoteTable]:
    """Extract selected note tables, preserving page citations."""
    notes: list[NoteTable] = []
    seen: set[tuple[int, str, tuple[str, ...]]] = set()
    counts = {group: 0 for group in _GROUP_LIMITS}
    for page, text in pages:
        parts = text.split("[TABLE]")
        prefix = parts[0]
        for chunk in parts[1:]:
            tables, trailing = _parse_tables(chunk)
            for rows in tables:
                parsed = _pick_header(rows)
                if parsed is None:
                    continue
                headers, body = parsed
                if not _has_numeric_row(body):
                    continue
                matched = _match_group(prefix)
                if matched is None:
                    continue
                group, label = matched
                if counts[group] >= _GROUP_LIMITS[group]:
                    continue
                title = _title(prefix, label)
                if (
                    len(title) > 30
                    or title.startswith(("项目 ", "项目名称 "))
                    or _needs_header_title(title)
                    or any(mark in title for mark in ("项目名称", "期末余额", "期初余额"))
                ):
                    title = _header_title(group, headers) or label
                if not _signal(group, title, headers):
                    continue
                key = (page, title, headers)
                if key in seen:
                    continue
                seen.add(key)
                notes.append(
                    NoteTable(
                        group=group,
                        title=title,
                        page=page,
                        headers=headers,
                        rows=body[:max_rows],
                        citation=pdf_citation(document_hash, page),
                    )
                )
                counts[group] += 1
                if len(notes) >= max_tables:
                    return notes
            prefix = trailing or prefix
    return notes


def notes_payload(
    notes: Sequence[NoteTable],
    *,
    source: str = "",
) -> dict[str, object]:
    return {
        "version": NOTES_VERSION,
        "source": source,
        "count": len(notes),
        "notes": [note.to_dict() for note in notes],
    }


def write_notes(notes: Sequence[NoteTable], path: Path | str, *, source: str = "") -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(notes_payload(notes, source=source), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
