"""Structural lint for a rendered ``analysis_report.md``.

The numeric gate (``qa``) only proves that numbers can be traced; it cannot see
that a heading lost its number, that a table is one cell short, or that a raw
``20261027`` leaked into the prose.  This module parses the Markdown that will
actually ship and reports those defects as structured findings so the QA gate
can fail on them instead of discovering them by eye.

The lint is deliberately markdown-only: it never imports the renderer, so it can
also be pointed at a historical report to quantify regressions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_DIGITS: dict[str, int] = {
    "零": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}

_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_NUMBERED = re.compile(r"^([一二三四五六七八九十]+)、\s*(.*\S)\s*$")
_RAW_DATE = re.compile(r"(?<!\d)(?:19|20)\d{6}(?!\d)")
_TEMPLATE_LEFT = re.compile(r"\{\{|\}\}")
_GLUED = re.compile(r"。；|；。|，。|。。")
_SEPARATOR = re.compile(r"^\|?[\s:|-]+\|?$")
_RULE = re.compile(r"^\s*(?:---+|\*\*\*+|___+)\s*$")
_FENCE = re.compile(r"^\s*```")

MAX_FINDINGS = 200


@dataclass(frozen=True, slots=True)
class Finding:
    """One structural defect, addressed by 1-based source line."""

    code: str
    line: int
    message: str


def numeral_value(text: str) -> int | None:
    """Return the integer value of a Chinese section numeral (``十一`` -> 11)."""

    if not text or any(ch not in "零一二三四五六七八九十" for ch in text):
        return None
    if "十" not in text:
        return _DIGITS.get(text) if len(text) == 1 else None
    head, _, tail = text.partition("十")
    tens = _DIGITS[head] if head else 1
    ones = _DIGITS[tail] if tail else 0
    return tens * 10 + ones


def _split_cells(row: str) -> list[str]:
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        if char == "\\" and index + 1 < len(body) and body[index + 1] == "|":
            current.append("|")
            index += 2
            continue
        if char == "|":
            cells.append("".join(current).strip())
            current = []
            index += 1
            continue
        current.append(char)
        index += 1
    cells.append("".join(current).strip())
    return cells


def _is_blockquote(line: str) -> bool:
    return line.lstrip().startswith(">")


def lint_report(markdown: str) -> list[Finding]:
    """Return every structural defect found in ``markdown`` (empty when clean)."""

    lines = markdown.splitlines()
    findings: list[Finding] = []
    in_fence = False

    def add(code: str, line: int, message: str) -> None:
        if len(findings) < MAX_FINDINGS:
            findings.append(Finding(code, line, message))

    # --- headings ---------------------------------------------------------
    headings: list[tuple[int, int, str]] = []  # (line, level, raw text)
    for number, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING.match(line)
        if match:
            headings.append((number, len(match.group(1)), match.group(2).strip()))
    if in_fence:
        add("fence.unbalanced", len(lines), "代码围栏未闭合（``` 出现在奇数个位置）")

    seen: dict[tuple[int, str], int] = {}
    numbered: list[tuple[int, int, str]] = []
    for number, level, text in headings:
        match = _NUMBERED.match(text)
        title = match.group(2) if match else text
        key = (level, title)
        if key in seen:
            add(
                "heading.duplicate",
                number,
                f"重复标题（首次出现在第 {seen[key]} 行）：{text}",
            )
        else:
            seen[key] = number
        if level == 2:
            if not match:
                add("heading.unnumbered", number, f"二级标题缺少中文序号：{text}")
            else:
                value = numeral_value(match.group(1))
                if value is not None:
                    numbered.append((number, value, title))

    expected = 1
    for number, value, title in numbered:
        if value != expected:
            add(
                "heading.order",
                number,
                f"二级标题序号应为第 {expected} 节，实际为「{title}」",
            )
        expected = value + 1

    # --- empty sections ---------------------------------------------------
    for position, (number, level, text) in enumerate(headings):
        end = len(lines) + 1
        for later_line, later_level, _ in headings[position + 1 :]:
            if later_level <= level:
                end = later_line
                break
        has_content = False
        for body in lines[number:end - 1]:
            stripped = body.strip()
            if not stripped or _RULE.match(stripped):
                continue
            has_content = True
            break
        if not has_content:
            add("section.empty", number, f"空节：「{text}」下面没有任何内容")

    # --- tables -----------------------------------------------------------
    index = 0
    while index < len(lines):
        line = lines[index]
        if _FENCE.match(line):
            in_fence = not in_fence
            index += 1
            continue
        if in_fence or not line.lstrip().startswith("|"):
            index += 1
            continue
        header_line = index + 1
        header = _split_cells(line)
        index += 1
        if index >= len(lines) or not _SEPARATOR.match(lines[index].strip()):
            add(
                "table.header",
                header_line,
                f"表格缺少分隔行（表头 {len(header)} 列）",
            )
        else:
            index += 1
        while index < len(lines) and lines[index].lstrip().startswith("|"):
            cells = _split_cells(lines[index])
            if len(cells) != len(header):
                add(
                    "table.ragged",
                    index + 1,
                    f"表格行列数 {len(cells)} 与表头 {len(header)} 不一致",
                )
            index += 1

    # --- inline leaks -----------------------------------------------------
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            continue
        if _TEMPLATE_LEFT.search(line):
            add("template.unresolved", number, "残留模板占位符 {{ }}")
        if _is_blockquote(line):
            continue
        if _RAW_DATE.search(line):
            add("date.raw", number, "裸 8 位日期（应为 YYYY-MM-DD）")
        if _GLUED.search(line):
            add("punct.glued", number, "句读粘连（。；）")

    findings.sort(key=lambda item: (item.line, item.code))
    return findings


def summary(findings: list[Finding]) -> str:
    """One-line summary for the QA gate detail column."""

    if not findings:
        return ""
    head = "、".join(f"{item.code}@L{item.line}" for item in findings[:5])
    if len(findings) > 5:
        return f"{head} 等 {len(findings)} 项结构问题"
    return head
