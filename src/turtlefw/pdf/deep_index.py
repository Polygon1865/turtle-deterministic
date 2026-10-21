"""Page-level index and retrieval for annual-report PDFs.

The legacy ``pdf_sections.json`` keeps seven short contexts.  This module keeps
the *whole* document index (every page, its section and a stable citation) and
selects a bounded, page-addressable context for an LLM.  It never rewrites
numbers and never acts as a financial parser.

The index is deliberately plain JSON so it can live next to a snapshot and be
reproduced without a vector database::

    {"version": 1, "document": {...}, "sections": [...],
     "pages": [{"page": 3, "section_id": "sec-003", "text": "...",
                "citation": "pdf://<hash>/p3", "chars": 1234}]}

Selection is lexical (no network/model dependency) so the same PDF and the same
focus terms produce the same context.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

INDEX_VERSION = 1
DEFAULT_MAX_CHARS = 160_000
MAX_QUOTE = 400

_CN_HEADING = re.compile(r"^\s*(第[一二三四五六七八九十百]+节\s*[^\n]{0,80})$")
_TERM = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9&.'-]{2,}")

_KNOWN_HEADINGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("mda", ("管理层讨论与分析", "董事会报告", "MD&A", "MANAGEMENT DISCUSSION AND ANALYSIS")),
    ("governance", ("公司治理", "企业管治报告", "CORPORATE GOVERNANCE REPORT")),
    ("auditor", ("审计报告", "核数师报告", "INDEPENDENT AUDITOR'S REPORT")),
    ("notes", ("财务报表附注", "财务报告附注", "NOTES TO THE FINANCIAL STATEMENTS")),
    ("related_party", ("关联方交易", "关联交易", "RELATED PARTY TRANSACTIONS")),
    ("risk", ("风险管理", "风险因素", "RISK MANAGEMENT", "RISK FACTORS")),
    ("business", ("经营情况讨论", "业务回顾", "BUSINESS REVIEW", "OPERATING REVIEW")),
    ("esg", ("环境、社会及管治报告", "环境、社会及管治", "ENVIRONMENTAL, SOCIAL AND GOVERNANCE")),
    ("directors", ("董事报告", "董事会报告", "DIRECTORS' REPORT")),
    ("shares", ("股份变动", "股本变动", "SHARE CAPITAL")),
    ("subsidiaries", ("主要控股参股公司", "主要附属公司", "PRINCIPAL SUBSIDIARIES")),
    ("summary", ("会计数据和财务指标", "财务摘要", "FINANCIAL HIGHLIGHTS")),
    ("important", ("重要提示", "IMPORTANT NOTICE")),
    ("financial", ("财务报告", "财务报表", "FINANCIAL STATEMENTS")),
)

_KIND_PRIORITY = {
    "mda": 14,
    "business": 11,
    "risk": 10,
    "governance": 9,
    "auditor": 9,
    "related_party": 8,
    "notes": 8,
    "subsidiaries": 6,
    "directors": 5,
    "financial": 5,
    "esg": 4,
    "shares": 4,
    "summary": 3,
    "important": 2,
    "front": 1,
}

_DEFAULT_FOCUS = (
    "管理层讨论与分析",
    "经营情况",
    "主营业务",
    "营业收入",
    "毛利率",
    "现金流",
    "研发",
    "风险",
    "公司治理",
    "关联交易",
    "审计报告",
    "财务报表附注",
    "分部",
    "股东",
    "分红",
    "资本开支",
)


def _clean_text(text: str) -> str:
    text = text.replace("\u3000", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    blank = False
    for line in lines:
        if not line:
            if not blank:
                cleaned.append("")
            blank = True
        else:
            cleaned.append(line)
            blank = False
    return "\n".join(cleaned).strip()


def _quote(text: str, limit: int = MAX_QUOTE) -> str:
    return " ".join(text.split())[:limit]


def _short_hash(document_hash: str) -> str:
    return document_hash[:16] if document_hash else "local"


def _citation(document_hash: str, page: int) -> str:
    return f"pdf://{_short_hash(document_hash)}/p{page}"


def pdf_citation(document_hash: str, page: int) -> str:
    """Public citation helper shared with structured-note extraction."""
    return _citation(document_hash, page)


def _kind_for(title: str) -> str:
    lowered = title.lower()
    for kind, terms in _KNOWN_HEADINGS:
        if any(term.lower() in lowered for term in terms):
            return kind
    if "管理层讨论" in title or "经营情况" in title:
        return "mda"
    if "财务报告" in title or "财务报表" in title:
        return "financial"
    return "section"


def _looks_like_toc(lines: Sequence[str]) -> bool:
    joined = "\n".join(lines[:30])
    upper = joined.upper()
    return ("目录" in joined or "CONTENTS" in upper) and joined.count("...") >= 3


def _heading_for_page(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    head = lines[:15]
    if _looks_like_toc(head):
        return ""
    for line in head:
        if len(line) < 4 or len(line) > 90:
            continue
        if re.fullmatch(r"[\d\s.\-—]+", line):
            continue
        match = _CN_HEADING.match(line)
        if match:
            return line
        upper = line.upper()
        for _kind, terms in _KNOWN_HEADINGS:
            if any(upper.startswith(term.upper()) for term in terms):
                return line
    return ""


def _front_section(page_count: int, first_heading: int | None) -> dict[str, Any]:
    end = (first_heading - 1) if first_heading and first_heading > 1 else page_count
    return {
        "id": "sec-000",
        "title": "封面/前置信息",
        "kind": "front",
        "start_page": 1,
        "end_page": max(1, end),
    }


def build_index(
    pages: Iterable[tuple[int, str]],
    *,
    document_hash: str = "",
    source_name: str = "",
) -> dict[str, Any]:
    """Build a deterministic page/section index from extracted page text."""
    by_page: dict[int, str] = {}
    for page, text in pages:
        by_page[int(page)] = _clean_text(str(text))
    if not by_page:
        return {
            "version": INDEX_VERSION,
            "document": {
                "sha256": document_hash,
                "source_name": source_name,
                "page_count": 0,
                "chars": 0,
            },
            "sections": [],
            "pages": [],
        }

    records: list[dict[str, Any]] = []
    for page in sorted(by_page):
        text = by_page[page]
        records.append(
            {
                "page": page,
                "text": text,
                "chars": len(text),
                "citation": _citation(document_hash, page),
                "section_id": "front",
            }
        )

    sections: list[dict[str, Any]] = []
    headings: list[tuple[int, str, str]] = []
    for record in records:
        title = _heading_for_page(str(record["text"]))
        if not title:
            continue
        kind = _kind_for(title)
        if (
            headings
            and kind in {"financial", "notes"}
            and kind == headings[-1][2]
            and not _CN_HEADING.match(title)
        ):
            # Financial statements contain many bold sub-headings that are not
            # chapters; keep them inside the enclosing financial section.
            continue
        headings.append((int(record["page"]), title, kind))

    first_heading = headings[0][0] if headings else None
    if first_heading is None or first_heading > 1:
        sections.append(_front_section(len(records), first_heading))

    for index, (start, title, kind) in enumerate(headings, start=1):
        end = headings[index][0] - 1 if index < len(headings) else records[-1]["page"]
        sections.append(
            {
                "id": f"sec-{len(sections):03d}",
                "title": title,
                "kind": kind,
                "start_page": start,
                "end_page": max(start, end),
            }
        )

    section_by_page: dict[int, str] = {}
    for section in sections:
        for page in range(int(section["start_page"]), int(section["end_page"]) + 1):
            section_by_page[page] = str(section["id"])
    for record in records:
        record["section_id"] = section_by_page.get(int(record["page"]), "front")

    return {
        "version": INDEX_VERSION,
        "document": {
            "sha256": document_hash,
            "source_name": source_name,
            "page_count": len(records),
            "chars": sum(int(record["chars"]) for record in records),
        },
        "sections": sections,
        "pages": records,
    }


def build_from_pdf(path: Path | str, *, max_pages: int | None = None) -> dict[str, Any]:
    """Extract all pages from a PDF (pdfplumber/PyMuPDF fallback)."""
    source = Path(path)
    from .preprocessor import extract_all_pages

    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    pages = extract_all_pages(str(source))
    if max_pages is not None:
        pages = pages[: max(0, int(max_pages))]
    return build_index(pages, document_hash=digest, source_name=source.name)


def write_index(index: Mapping[str, Any], path: Path | str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (json.dumps(index, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    return target


def load_index(path: Path | str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list):
        raise TypeError(f"invalid PDF index: {path}")
    return payload


def _section_map(index: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    sections = index.get("sections", [])
    if not isinstance(sections, list):
        return {}
    return {
        str(section.get("id")): section
        for section in sections
        if isinstance(section, Mapping) and section.get("id")
    }


def search(index: Mapping[str, Any], query: str, *, limit: int = 10) -> list[dict[str, Any]]:
    """Return page hits ranked by title/body term frequency."""
    terms = _TERM.findall(query)
    if not terms:
        return []
    sections = _section_map(index)
    hits: list[tuple[int, dict[str, Any]]] = []
    pages = index.get("pages", [])
    if not isinstance(pages, list):
        return []
    for page in pages:
        if not isinstance(page, Mapping):
            continue
        text = str(page.get("text", ""))
        section = sections.get(str(page.get("section_id")), {})
        title = f"{section.get('title', '')} {text[:200]}"
        score = 0
        first = -1
        for term in terms:
            in_title = title.count(term)
            in_text = text.count(term)
            if in_title:
                score += 5 + in_title
            if in_text:
                score += min(6, in_text)
            if first < 0:
                first = text.find(term)
        if score <= 0:
            continue
        snippet = text[max(0, first - 120) : first + 220] if first >= 0 else text[:300]
        hits.append(
            (
                score,
                {
                    "page": int(page.get("page", 0)),
                    "citation": str(page.get("citation", "")),
                    "section_id": str(page.get("section_id", "")),
                    "section_title": str(section.get("title", "")),
                    "score": score,
                    "snippet": " ".join(snippet.split()),
                },
            )
        )
    hits.sort(key=lambda item: (-item[0], item[1]["page"]))
    return [hit for _score, hit in hits[: max(1, int(limit))]]


def deep_context(
    index: Mapping[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    focus_terms: Sequence[str] | None = None,
    max_pages: int = 60,
) -> dict[str, Any]:
    """Select a bounded page set with sections, text and stable citations."""
    budget = max(2_000, int(max_chars))
    page_limit = max(1, int(max_pages))
    focus = tuple(focus_terms or _DEFAULT_FOCUS)
    document = index.get("document", {})
    if not isinstance(document, Mapping):
        document = {}
    sections = index.get("sections", [])
    if not isinstance(sections, list):
        sections = []
    section_map = _section_map(index)
    pages = index.get("pages", [])
    if not isinstance(pages, list):
        pages = []

    scored: list[tuple[int, int, Mapping[str, Any]]] = []
    for page in pages:
        if not isinstance(page, Mapping):
            continue
        text = str(page.get("text", ""))
        if not text.strip():
            continue
        section = section_map.get(str(page.get("section_id")), {})
        kind = str(section.get("kind", "section"))
        title = str(section.get("title", ""))
        score = _KIND_PRIORITY.get(kind, 0)
        page_no = int(page.get("page", 0))
        if page_no == int(section.get("start_page", -1)):
            score += 12
        if page_no <= 2:
            score += 6
        for term in focus:
            if term in title:
                score += 10
            count = text.count(term)
            if count:
                score += min(8, count)
        scored.append((score, page_no, page))

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected: list[dict[str, Any]] = []
    citations: dict[str, dict[str, Any]] = {}
    used = 0
    truncated_pages = 0
    for score, page_no, page in scored:
        if len(selected) >= page_limit or used >= budget:
            break
        remaining = budget - used
        if remaining < 200:
            break
        full_text = str(page.get("text", ""))
        text = full_text[:remaining]
        truncated = len(full_text) > len(text)
        if truncated:
            truncated_pages += 1
        section = section_map.get(str(page.get("section_id")), {})
        citation = str(page.get("citation", "")) or _citation(
            str(document.get("sha256", "")), page_no
        )
        record = {
            "page": page_no,
            "citation": citation,
            "section_id": str(page.get("section_id", "")),
            "section_title": str(section.get("title", "")),
            "section_kind": str(section.get("kind", "section")),
            "score": score,
            "text": text,
            "truncated": truncated,
        }
        selected.append(record)
        citations[citation] = {
            "page": page_no,
            "section": str(section.get("title", "")),
            "quote": _quote(full_text),
        }
        used += len(text)

    selected.sort(key=lambda item: int(item["page"]))
    return {
        "version": INDEX_VERSION,
        "document": {
            "sha256": str(document.get("sha256", "")),
            "source_name": str(document.get("source_name", "")),
            "page_count": int(document.get("page_count", len(pages))),
            "chars": int(document.get("chars", 0)),
        },
        "sections": sections,
        "pages": selected,
        "citations": citations,
        "stats": {
            "pages_total": len(pages),
            "pages_selected": len(selected),
            "chars_selected": used,
            "max_chars": budget,
            "max_pages": page_limit,
            "truncated_pages": truncated_pages,
            "focus_terms": list(focus),
        },
    }
