"""Deterministic section renumbering for the rendered report.

Section numbers used to be assembled from three places: literals in
``analysis.md.j2``, a ``fundamental_section``/``market_section`` string built in
``analysis.py``, and ``## 行业分类`` emitted by ``industry.py``.  Every new
conditionally-rendered block therefore had a chance to land between two numbers
without one of its own.  ``renumber`` makes the rendered document the single
source of truth: whatever top-level headings survived rendering are numbered
一、二、三… in document order.
"""

from __future__ import annotations

import re

_HEADING = re.compile(r"^(##)\s+(.*\S)\s*$")
_NUMBERED = re.compile(r"^[一二三四五六七八九十]+、\s*")
_FENCE = re.compile(r"^\s*```")
_ONES = ("零", "一", "二", "三", "四", "五", "六", "七", "八", "九")


def numeral(value: int) -> str:
    """Return the Chinese numeral for ``value`` (1 -> 一, 11 -> 十一)."""

    if value < 1:
        raise ValueError(f"section number must be positive, got {value}")
    if value < 10:
        return _ONES[value]
    if value == 10:
        return "十"
    if value < 20:
        return "十" + _ONES[value - 10]
    tens, ones = divmod(value, 10)
    if tens >= 10:
        raise ValueError(f"section number too large: {value}")
    return _ONES[tens] + "十" + (_ONES[ones] if ones else "")


def renumber(markdown: str) -> str:
    """Rewrite every level-2 heading with a consecutive Chinese numeral."""

    lines = markdown.splitlines()
    out: list[str] = []
    in_fence = False
    expected = 1
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        match = _HEADING.match(line)
        if not match:
            out.append(line)
            continue
        title = _NUMBERED.sub("", match.group(2)).strip()
        out.append(f"## {numeral(expected)}、{title}")
        expected += 1
    suffix = "\n" if markdown.endswith("\n") else ""
    return "\n".join(out) + suffix
