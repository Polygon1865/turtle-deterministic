"""Narrative number whitelist.

The agent may write prose, but every number it mentions must already exist in
the CLI outputs. This module extracts numeric tokens and flags anything that
cannot be traced back to the deterministic layer.
"""

from __future__ import annotations

import re
from pathlib import Path

from .paths import output_root

TOKEN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def normalize(token: str) -> str:
    return token.replace(",", "")


def tokens(text: str) -> list[str]:
    return [normalize(match) for match in TOKEN.findall(text or "")]


def whitelist(texts: list[str]) -> set[str]:
    return {
        variant
        for text in texts
        for token in tokens(text)
        for variant in _variants(token)
    }


def _variants(token: str) -> set[str]:
    variants = {token}
    if "." in token:
        trimmed = token.rstrip("0").rstrip(".")
        if trimmed:
            variants.add(trimmed)
        variants.add(token.rstrip("0"))
    else:
        variants.add(f"{token}.0")
    return variants


def unknown_numbers(narrative: str, allowed: set[str]) -> list[str]:
    bad: set[str] = set()
    for token in tokens(narrative):
        if any(variant in allowed for variant in _variants(token)):
            continue
        bad.add(token)
    return sorted(bad)


def check(
    code: str, narrative_path: Path | str, root: Path | str | None = None
) -> list[str]:
    base = (Path(root) if root is not None else output_root()) / str(code)
    sources = [
        base / "analysis_report.md",
        base / "data_pack.md",
        base / "qualitative.json",
    ]
    texts = [path.read_text(encoding="utf-8") for path in sources if path.is_file()]
    allowed = whitelist(texts)
    narrative = Path(narrative_path).read_text(encoding="utf-8")
    return unknown_numbers(narrative, allowed)
