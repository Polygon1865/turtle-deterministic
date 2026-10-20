"""Annual-report PDF number extraction.

This is the M6 bridge from ``pdf_sections.json`` to ``reported_numbers.json``:
it scans the consolidated statements for the six items the deterministic audit
supports, parses Chinese/English number formats, and keeps the page/source so
every number can be traced back to the PDF.

It is intentionally conservative: a line must contain a known statement alias
and a parseable number. If the current-year column cannot be distinguished,
the first number is used and ``confidence`` is downgraded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable, Sequence

ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("营业收入", "营业总收入", "Revenues", "Revenue", "Total revenue"),
    "net_income": (
        "归属于母公司股东的净利润",
        "归属于母公司所有者的净利润",
        "母公司股东应占溢利",
        "Profit attributable to shareholders",
        "Equity holders of the Company",
    ),
    "ocf": (
        "经营活动产生的现金流量净额",
        "经营活动现金流量净额",
        "Net cash generated from operating activities",
        "Net cash flows generated from operating activities",
        "Net cash from operating activities",
    ),
    "capex": (
        "购建固定资产、无形资产和其他长期资产支付的现金",
        "购建固定资产、无形资产及其他长期资产支付的现金",
        "Purchase of/prepayments for property, plant and equipment",
        "Purchase of property, plant and equipment",
    ),
    "equity": (
        "归属于母公司所有者权益（或股东权益）合计",
        "归属于母公司股东权益（或股东权益）合计",
        "归属于母公司所有者权益合计",
        "归属于母公司股东权益合计",
        "Equity attributable to equity holders of the Company",
        "Total equity attributable to shareholders",
    ),
    "total_assets": ("资产总计", "总资产", "Total assets"),
    "accounts_receiv": (
        "应收账款",
        "应收票据及应收账款",
        "Trade receivables",
        "Accounts receivable",
    ),
    "inventory": ("存货", "Inventories", "Inventory"),
    "contract_liab": ("合同负债", "Contract liabilities"),
    "adv_receipts": (
        "预收款项",
        "预收款",
        "Advances from customers",
        "Receipts in advance",
    ),
    "prepayments": ("预付款项", "预付账款", "Prepayments", "Prepaid expenses"),
}

EXTRA_ALIASES: dict[str, tuple[str, ...]] = {
    "capex_intangibles": (
        "Purchase of/prepayments for intangible assets",
        "Purchase of intangible assets",
    )
}

STATEMENT_TITLES = (
    "合并资产负债表",
    "合并利润表",
    "合并现金流量表",
    "合并所有者权益变动表",
    "Consolidated statement of financial position",
    "Consolidated income statement",
    "Consolidated statement of cash flows",
)

UNIT_SCALES = {
    "元": Decimal("1"),
    "千元": Decimal("1000"),
    "万元": Decimal("10000"),
    "百万元": Decimal("1000000"),
    "亿元": Decimal("100000000"),
    "人民币元": Decimal("1"),
    "人民币千元": Decimal("1000"),
    "人民币万元": Decimal("10000"),
    "人民币百万元": Decimal("1000000"),
    "人民币亿元": Decimal("100000000"),
    "RMB": Decimal("1"),
    "RMB'000": Decimal("1000"),
    "RMB million": Decimal("1000000"),
}

_NUMBER = re.compile(
    r"[-−]?\(?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?"
    r"|[-−]?\(?\d+\.\d+\)?"
)
_PLAIN = re.compile(r"[-−]?\(?\d{4,}\)?")
_UNIT = re.compile(
    r"(人民币)?\s*(百万元|亿元|千元|万元|元|RMB'000|RMB million)",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Candidate:
    item: str
    value: Decimal
    page: int
    source: str
    confidence: str
    score: int


def parse_number(token: str, scale: Decimal = Decimal("1")) -> Decimal | None:
    """Parse ``1,234.5``, ``(1,234)`` and ``−1,234``; reject placeholders."""
    raw = token.strip().replace("，", ",").replace("−", "-")
    if raw in {"", "-", "—", "–", "不适用", "N/A", "n/a"}:
        return None
    negative = raw.startswith("-") or (raw.startswith("(") and raw.endswith(")"))
    raw = raw.strip("-()").replace(",", "")
    try:
        value = Decimal(raw)
    except InvalidOperation:
        return None
    if not value.is_finite():
        return None
    return (-value if negative else value) * scale


def detect_scale(line: str, default: Decimal = Decimal("1")) -> Decimal:
    normalized = line.replace("’", "'").replace("‘", "'")
    # HK reports commonly use RMB'Million / RMB'000.
    if re.search(r"RMB\s*'?\s*(?:Million|M)\b", normalized, re.IGNORECASE):
        return Decimal("1000000")
    if re.search(r"RMB\s*'?\s*000\b", normalized, re.IGNORECASE):
        return Decimal("1000")
    match = _UNIT.search(normalized)
    if not match:
        return default
    unit = match.group(2)
    return UNIT_SCALES.get(unit, default)


def _statement_score(page_text: str) -> int:
    score = 0
    lower = page_text.lower()
    for title in STATEMENT_TITLES:
        if title.lower() in lower:
            score += 3
    if "合并" in page_text or "consolidated" in lower:
        score += 2
    if "母公司" in page_text and "合并" not in page_text:
        score -= 2
    if "审计报告" in page_text or "关键审计事项" in page_text:
        score -= 5
    if "附注" in page_text:
        score -= 1
    return score


def _line_score(line: str, page_score: int, item: str) -> int:
    score = page_score
    tokens = _NUMBER.findall(line) or _PLAIN.findall(line)
    large = 0
    for token in tokens:
        value = parse_number(token)
        if value is not None and abs(value) > 1000:
            large += 1
    if large >= 2:
        score += 4
    if "其中" in line:
        score += 1
    if item == "revenue" and "营业总收入" in line:
        score -= 1
    if any(term in line for term in ("审计", "确认", "关键审计", "亿元", "营业收入是")):
        score -= 5
    return score


def _tokens(line: str) -> list[str]:
    tokens = _NUMBER.findall(line)
    if tokens:
        return tokens
    return _PLAIN.findall(line)


def _matches(alias: str, line: str) -> bool:
    if alias.lower() == "equity holders of the company":
        return line.strip().lower().startswith(alias.lower())
    return alias.lower() in line.lower()


def _scan_following_values(
    lines: list[str], start: int, *, stop_terms: tuple[str, ...], limit: int = 14
) -> tuple[str, str] | None:
    """Return the last numeric pair's line/value before a stop term."""
    found: tuple[str, str] | None = None
    for following in lines[start + 1 : start + 1 + limit]:
        if any(term.lower() in following.lower() for term in stop_terms):
            break
        tokens = _tokens(following)
        if len(tokens) >= 2:
            found = (following, tokens[0])
    return found


def extract_from_pages(
    pages_text: Sequence[tuple[int, str]],
    *,
    year: int,
    report_type: str = "年报",
) -> list[dict[str, str]]:
    """Extract candidates from ``(page_number, text)`` pairs."""
    candidates: list[Candidate] = []
    for page_number, text in pages_text:
        if not text:
            continue
        page_score = _statement_score(text)
        page_scale = detect_scale(text)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for index, line in enumerate(lines):
            for item, aliases in {**ALIASES, **EXTRA_ALIASES}.items():
                if not any(_matches(alias, line) for alias in aliases):
                    continue
                # Some HK statements put the label on one line and the total
                # after a block of segment/subtotal lines.
                stripped_label = line.strip().rstrip(":").lower()
                if item == "revenue" and stripped_label in {"revenue", "revenues"}:
                    followed = _scan_following_values(
                        lines, index, stop_terms=("cost of revenues",)
                    )
                    if followed is not None:
                        line, first = followed
                        value = parse_number(first, detect_scale(line, page_scale))
                        if value is not None:
                            candidates.append(
                                Candidate(
                                    item=item,
                                    value=value,
                                    page=page_number,
                                    source=f"{year}{report_type}",
                                    confidence="high",
                                    score=_line_score(line, page_score, item) + 5,
                                )
                            )
                            break
                if item == "equity" and stripped_label.startswith(
                    "equity attributable to equity holders"
                ):
                    followed = _scan_following_values(
                        lines,
                        index,
                        stop_terms=("non-controlling interests", "total equity"),
                    )
                    if followed is not None:
                        line, first = followed
                        value = parse_number(first, detect_scale(line, page_scale))
                        if value is not None:
                            candidates.append(
                                Candidate(
                                    item=item,
                                    value=value,
                                    page=page_number,
                                    source=f"{year}{report_type}",
                                    confidence="high",
                                    score=_line_score(line, page_score, item) + 5,
                                )
                            )
                            break
                # Prefer a number on the same line; otherwise look one line
                # ahead (PDF extraction often splits label and value).
                numbers = _tokens(line)
                target_line = line
                if not numbers and index + 1 < len(lines):
                    target_line = lines[index + 1]
                    numbers = _tokens(target_line)
                value = None
                for token in numbers:
                    candidate_value = parse_number(token, detect_scale(target_line, page_scale))
                    # A note reference like "五、32" is too small to be a
                    # statement value; also skip obviously malformed values.
                    if candidate_value is not None and abs(candidate_value) > Decimal("1000"):
                        value = (
                            abs(candidate_value)
                            if item in {"capex", "capex_intangibles"}
                            else candidate_value
                        )
                        break
                if value is None:
                    continue
                confidence = "high" if page_score >= 3 else "medium"
                candidates.append(
                    Candidate(
                        item=item,
                        value=value,
                        page=page_number,
                        source=f"{year}{report_type}",
                        confidence=confidence,
                        score=_line_score(line, page_score, item),
                    )
                )
                break  # one item per line

    # Pick the highest-scoring, then earliest-page candidate per item.
    best: dict[str, Candidate] = {}
    for candidate in candidates:
        current = best.get(candidate.item)
        if current is None or (candidate.score, -candidate.page) > (current.score, -current.page):
            best[candidate.item] = candidate

    # HK reports split capex into PPE and intangible assets; the audit item is
    # the sum of the two cash outflows. A-share reports already have a combined
    # line, so the extra alias only fires when that line exists.
    intangible = best.pop("capex_intangibles", None)
    ppe = best.get("capex")
    if intangible is not None and ppe is not None:
        best["capex"] = Candidate(
            item="capex",
            value=ppe.value + intangible.value,
            page=ppe.page,
            source=ppe.source,
            confidence=ppe.confidence,
            score=ppe.score,
        )

    return [
        {
            "item": item,
            "value": f"{candidate.value:.2f}",
            "unit": "元",
            "source": candidate.source,
            "page": str(candidate.page),
            "confidence": candidate.confidence,
        }
        for item, candidate in best.items()
    ]


def extract_cash_bridge_from_pages(
    pages_text: Sequence[tuple[int, str]],
) -> dict[str, str | None]:
    """Extract the HK indirect cash-flow bridge from statement/note pages.

    HK cash-flow statements use the indirect method: no gross receipts/payments
    are disclosed. This captures the reconciliation that *is* disclosed:
    net profit → D&A + working-capital changes → cash generated → tax → OCF,
    plus capex. Values are scaled to yuan using the page's ``RMB'Million`` unit.
    """
    all_lines: list[tuple[int, str]] = []
    page_text: dict[int, str] = {}
    scales: dict[int, Decimal] = {}
    for page_number, text in pages_text:
        page_text[page_number] = text or ""
        scales[page_number] = detect_scale(text or "")
        for line in (text or "").splitlines():
            stripped = line.strip()
            if stripped:
                all_lines.append((page_number, stripped))

    # Prefer the note/page that contains the full indirect reconciliation.
    bridge_pages = [
        page
        for page, text in page_text.items()
        if "cash generated from operations" in text.lower()
        and "changes in working capital" in text.lower()
    ]
    bridge_page = bridge_pages[0] if bridge_pages else None
    if bridge_page is None:
        # A-share cash-flow statements are direct; there is no indirect
        # reconciliation to build this bridge from.
        return {}
    lines = [(page, line) for page, line in all_lines if page == bridge_page]

    def value_after(
        terms: tuple[str, ...],
        *,
        source_lines: Sequence[tuple[int, str]] = all_lines,
        start: int = 0,
    ) -> tuple[Decimal, int] | None:
        for index in range(start, len(source_lines)):
            page, line = source_lines[index]
            if not any(term.lower() in line.lower() for term in terms):
                continue
            tokens = _tokens(line)
            target = line
            if not tokens and index + 1 < len(source_lines):
                next_line = source_lines[index + 1][1]
                next_tokens = _tokens(next_line)
                # Skip the "2025 2024" column header after a section heading.
                if next_tokens and all(
                    len(token.replace(",", "")) == 4 and token.startswith("20")
                    for token in next_tokens
                ):
                    continue
                target = next_line
                tokens = next_tokens
            for token in tokens:
                value = parse_number(token, detect_scale(target, scales.get(page, Decimal("1"))))
                if value is not None and abs(value) > Decimal("1000"):
                    return value, page
        return None

    net_profit = value_after(("Profit for the year", "Profit for the period"), source_lines=lines)
    da_total = Decimal("0")
    da_page: int | None = None
    for term in (
        "Depreciation of property",
        "Amortisation of intangible",
        "Depreciation of right-of-use",
    ):
        found = value_after((term,), source_lines=lines)
        if found is not None:
            da_total += abs(found[0])
            da_page = found[1] if da_page is None else da_page

    working_capital = Decimal("0")
    wc_page: int | None = None
    wc_start = next(
        (i for i, (_, line) in enumerate(lines) if "Changes in working capital" in line),
        None,
    )
    if wc_start is not None:
        for index in range(wc_start + 1, len(lines)):
            page, line = lines[index]
            if "Cash generated from operations" in line:
                break
            tokens = _tokens(line)
            if not tokens:
                continue
            value = parse_number(
                tokens[0], detect_scale(line, scales.get(page, Decimal("1")))
            )
            if value is None or abs(value) < Decimal("1000"):
                continue
            working_capital += value
            wc_page = page if wc_page is None else wc_page

    cash_generated = value_after(("Cash generated from operations",), source_lines=lines)
    tax_paid = value_after(("Income tax paid",))
    ocf = value_after(
        (
            "Net cash flows generated from operating activities",
            "Net cash generated from operating activities",
        )
    )
    capex = Decimal("0")
    capex_page: int | None = None
    for term in (
        "Purchase of/prepayments for property, plant and equipment",
        "Purchase of/prepayments for intangible assets",
    ):
        found = value_after((term,))
        if found is not None:
            capex += abs(found[0])
            capex_page = found[1] if capex_page is None else capex_page

    def fmt(value: Decimal | None) -> str | None:
        return None if value is None else f"{value:.2f}"

    return {
        "net_profit": fmt(net_profit[0] if net_profit else None),
        "depreciation_amortisation": fmt(da_total or None),
        "working_capital_change": fmt(working_capital if wc_page else None),
        "cash_generated_from_operations": fmt(cash_generated[0] if cash_generated else None),
        "income_tax_paid": fmt(tax_paid[0] if tax_paid else None),
        "ocf": fmt(ocf[0] if ocf else None),
        "capex": fmt(capex or None),
        "page": str((ocf or cash_generated or net_profit or (Decimal("0"), 0))[1] or ""),
    }


def extract_sbc_from_pages(
    pages_text: Sequence[tuple[int, str]],
) -> dict[str, str]:
    """Extract share-based compensation (prefer equity-settled SBC)."""
    preferred = (
        "Equity-settled share-based compensation",
        "股份支付费用",
        "股权激励费用",
    )
    fallback = ("Share-based compensation expenses",)

    def scan(aliases: tuple[str, ...]) -> tuple[int, Decimal] | None:
        best: tuple[int, Decimal] | None = None
        for page, text in pages_text:
            scale = detect_scale(text)
            for line in (text or "").splitlines():
                if not any(alias.lower() in line.lower() for alias in aliases):
                    continue
                tokens = _tokens(line)
                if not tokens:
                    continue
                for token in tokens:
                    value = parse_number(token, detect_scale(line, scale))
                    if value is not None and abs(value) > Decimal("1000"):
                        if best is None or abs(value) > abs(best[1]):
                            best = (page, value)
                        break
        return best

    best = scan(preferred) or scan(fallback)
    if best is None:
        return {}
    return {"sbc": f"{abs(best[1]):.2f}", "page": str(best[0])}


def _read_pages(pdf_path: Path | str, max_pages: int | None = None) -> list[tuple[int, str]]:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency error
        raise RuntimeError("pdfplumber is not installed; install .[pdf]") from exc
    pages: list[tuple[int, str]] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        selected = pdf.pages[:max_pages] if max_pages else pdf.pages
        for number, page in enumerate(selected, start=1):
            pages.append((number, page.extract_text() or ""))
    return pages


def extract_pdf(
    pdf_path: Path | str,
    *,
    year: int,
    report_type: str = "年报",
    max_pages: int | None = None,
) -> list[dict[str, str]]:
    """Read a PDF with pdfplumber and extract the six audit items."""
    return extract_from_pages(
        _read_pages(pdf_path, max_pages), year=year, report_type=report_type
    )


def extract_pdf_bundle(
    pdf_path: Path | str,
    *,
    year: int,
    report_type: str = "年报",
    max_pages: int | None = None,
) -> tuple[list[dict[str, str]], dict[str, str | None], dict[str, str]]:
    pages = _read_pages(pdf_path, max_pages)
    return (
        extract_from_pages(pages, year=year, report_type=report_type),
        extract_cash_bridge_from_pages(pages),
        extract_sbc_from_pages(pages),
    )


def write_reported_numbers(
    items: Iterable[dict[str, str]],
    output_path: Path | str,
    *,
    pdf_path: str = "",
    cash_bridge: dict[str, str | None] | None = None,
    sbc: dict[str, str] | None = None,
    year: int | None = None,
) -> Path:
    import json

    from ..facts import file_hash

    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    item_list = list(items)
    document_hash = ""
    if pdf_path and Path(pdf_path).is_file():
        document_hash = file_hash(pdf_path)
    facts = [
        {
            "id": f"pdf:{item.get('item', '')}:{item.get('page', '')}",
            "document_hash": document_hash,
            "page": str(item.get("page", "")),
            "section": str(item.get("source", "")),
            "label": str(item.get("item", "")),
            "value": str(item.get("value", "")),
            "unit": str(item.get("unit", "")),
            "extraction_method": "pdfplumber",
            "confidence": str(item.get("confidence", "")),
            "source_url": pdf_path,
            "source_rank": 1,
        }
        for item in item_list
    ]
    payload: dict[str, object] = {
        "source_pdf": pdf_path,
        "document_hash": document_hash,
        "items": item_list,
        "document_facts": facts,
    }
    if year is not None:
        payload["year"] = year
    if cash_bridge is not None:
        payload["cash_bridge"] = cash_bridge
    if sbc:
        payload["sbc"] = sbc
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target
