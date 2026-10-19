"""Structure the footnote contexts produced by ``pdf/preprocessor.py``.

The preprocessor already writes Markdown tables (``[TABLE] ...``) and page
markers inside ``pdf_sections.json``. This module turns those blocks into a
machine-readable ``footnotes.json`` without pretending to understand every
accounting table.

Output shape::

    {"P3": {"pages": [117], "tables": [{"page": 117, "rows": [[...]]}],
            "text_excerpt": "..."}}
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SECTION_IDS = ("P2", "P3", "P4", "P6", "P13", "MDA", "SUB")

_PAGE = re.compile(r"---\s*p\.(\d+)\s*---")
_TABLE = re.compile(r"\[TABLE\]\s*(.*?)(?=\n\n|\Z)", re.DOTALL)


def _rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells and all(set(cell) <= set(":- ") for cell in cells):
            continue
        rows.append(cells)
    return rows


def structure_sections(sections: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for section_id in SECTION_IDS:
        text = sections.get(section_id)
        if not isinstance(text, str) or not text.strip():
            continue
        pages: set[int] = set()
        tables: list[dict[str, object]] = []
        current_page: int | None = None
        for page_match in _PAGE.finditer(text):
            pages.add(int(page_match.group(1)))
        # Split by page markers while keeping the page number before each block.
        parts = _PAGE.split(text)
        # parts = [intro, page1, content1, page2, content2, ...]
        for index in range(1, len(parts), 2):
            current_page = int(parts[index])
            content = parts[index + 1] if index + 1 < len(parts) else ""
            for table_match in _TABLE.finditer(content):
                rows = _rows(table_match.group(1))
                if rows:
                    tables.append({"page": current_page, "rows": rows})
        # Tables before the first page marker (rare) are kept without a page.
        intro = parts[0] if parts else ""
        for table_match in _TABLE.finditer(intro):
            rows = _rows(table_match.group(1))
            if rows:
                tables.append({"page": None, "rows": rows})
        plain = _TABLE.sub("", _PAGE.sub("", text))
        plain = re.sub(r"\n{3,}", "\n\n", plain).strip()
        result[section_id] = {
            "pages": sorted(pages),
            "tables": tables,
            "text_excerpt": plain[:2000],
        }
    return result


def structure_file(sections_path: Path | str, output_path: Path | str) -> Path:
    source = Path(sections_path)
    payload = json.loads(source.read_text(encoding="utf-8"))
    structured = structure_sections(payload)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return target
