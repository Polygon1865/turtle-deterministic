"""Numeric traceability audit for report/data-pack prose.

This is not a numeric guard that can rewrite a report. It extracts numeric
tokens from a rendered report and reports tokens that do not appear in any of
the declared source artifacts (metrics/data pack/qualitative/research).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable

from .narrative import tokens, unknown_numbers

_YEAR = re.compile(r"^(19|20)\d{2}$")
_RESEARCH_COLLECTIONS = ("claims", "params", "decisions", "evidence")


def _text_sources(paths: Iterable[Path | str]) -> list[str]:
    texts: list[str] = []
    for path in paths:
        source = Path(path)
        if not source.is_file():
            continue
        if source.suffix == ".json":
            try:
                payload = json.loads(source.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            texts.append(json.dumps(payload, ensure_ascii=False, default=str))
        else:
            texts.append(source.read_text(encoding="utf-8-sig"))
    return texts


def _research_counts(path: Path | str) -> set[str]:
    """Counts printed by the research coverage/summary blocks.

    ``research.json`` stores the collections themselves while the rendered
    report prints their lengths; those counts are derived by the framework,
    not written by the model, so they count as traceable to the source.
    """
    source = Path(path)
    if source.suffix != ".json" or not source.is_file():
        return set()
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return set()
    if not isinstance(payload, dict):
        return set()
    counts: set[str] = set()
    for key in _RESEARCH_COLLECTIONS:
        value = payload.get(key)
        if isinstance(value, list):
            counts.add(str(len(value)))
    return counts


def audit(
    report: Path | str,
    sources: Iterable[Path | str],
    *,
    strict: bool = False,
) -> dict[str, Any]:
    text = Path(report).read_text(encoding="utf-8-sig")
    # Snapshot IDs are provenance, not report metrics.
    text = re.sub(r"`[0-9a-fA-F]{12,}`", "", text)
    allowed = set()
    source_paths = [Path(source) for source in sources]
    if strict:
        # Strict mode excludes raw statement rows; evidence/data-pack/PDF facts
        # remain valid, but an arbitrary raw input value is not a metric.
        source_paths = [source for source in source_paths if source.name != "inputs.json"]
    for source_text in _text_sources(source_paths):
        allowed.update(tokens(source_text))
    for source in source_paths:
        allowed.update(_research_counts(source))
    unknown = [token for token in unknown_numbers(text, allowed) if not _YEAR.match(token)]
    total = len(tokens(text))
    return {
        "report": str(report),
        "strict": strict,
        "tokens": total,
        "unknown": unknown,
        "coverage": round((total - len(unknown)) / total, 4) if total else 1.0,
        "status": "pass" if not unknown else "review",
    }
