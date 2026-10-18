"""Deterministic evidence fact-check.

A judgment is only as good as its quote. This module fetches each evidence URL
(or accepts an injected fetcher for tests), normalizes the page text, and scores
how much of the quote actually appears. The verifier prompt makes the semantic
call; this module makes the mechanical one.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable

from .qualitative import MODULES, Qualitative

Fetcher = Callable[[str], str]

USER_AGENT = "Mozilla/5.0 (compatible; turtle-framework/0.1)"


def fetch_url(url: str, timeout: int = 20) -> str:
    import requests

    response = requests.get(
        url, timeout=timeout, headers={"User-Agent": USER_AGENT}
    )
    response.raise_for_status()
    return response.text


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", "", text)


def quote_score(page: str, quote: str) -> float:
    """Fraction of the quote matched contiguously; 1.0 means exact containment."""
    page_n, quote_n = normalize(page), normalize(quote)
    if not quote_n:
        return 0.0
    if quote_n in page_n:
        return 1.0
    anchor = quote_n[:15]
    best = 0.0
    for match in re.finditer(re.escape(anchor), page_n):
        window = page_n[match.start() : match.start() + len(quote_n) + 60]
        block = SequenceMatcher(None, quote_n, window).find_longest_match(
            0, len(quote_n), 0, len(window)
        )
        best = max(best, block.size / len(quote_n))
    return round(best, 3)


@dataclass(frozen=True, slots=True)
class Check:
    module: str
    url: str
    status: str  # ok | quote_missing | unreachable
    score: float
    detail: str = ""


def check_qualitative(
    qualitative: Qualitative,
    fetch: Fetcher = fetch_url,
    threshold: float = 0.9,
) -> list[Check]:
    cache: dict[str, tuple[str, str]] = {}
    checks: list[Check] = []
    for key in MODULES:
        item = qualitative.get(key)
        if item is None:
            continue
        for evidence in item.evidence:
            if evidence.url not in cache:
                try:
                    cache[evidence.url] = ("ok", fetch(evidence.url))
                except Exception as exc:  # network failures are recorded, not raised
                    cache[evidence.url] = ("unreachable", str(exc)[:160])
            status, payload = cache[evidence.url]
            if status != "ok":
                checks.append(Check(key, evidence.url, "unreachable", 0.0, payload))
                continue
            score = quote_score(payload, evidence.quote)
            checks.append(
                Check(
                    key,
                    evidence.url,
                    "ok" if score >= threshold else "quote_missing",
                    score,
                )
            )
    return checks


def failing_modules(checks: list[Check]) -> set[str]:
    """Modules whose judgments have no verifiable evidence at all."""
    failed: set[str] = set()
    for check in checks:
        if check.status != "ok":
            failed.add(check.module)
    return failed


def downgrade(payload: dict, modules: set[str]) -> dict:
    """Set the given modules to unknown and annotate why (mutates a copy)."""
    import copy

    result = copy.deepcopy(payload)
    for module in modules:
        entry = result.get("modules", {}).get(module)
        if not entry:
            continue
        entry["judgment"] = "unknown"
        note = entry.get("notes", "")
        entry["notes"] = (note + " " if note else "") + "（事实校验未通过，已降级为 unknown）"
    return result
