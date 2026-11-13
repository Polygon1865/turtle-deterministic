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
_ISO_DATE = re.compile(r"\b(?:19|20)\d{2}-\d{2}-\d{2}\b")
_COMPACT_DATE = re.compile(r"\b(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\b")
_RESEARCH_COLLECTIONS = ("claims", "params", "decisions", "evidence")

# W5.1: every number in the report should be attributable to a source class, not
# merely "present somewhere".  The classes below are coarse on purpose: they map
# to the four artifacts a reader can be pointed at (frozen metrics, statements,
# research document, PDF/evidence facts) plus the rendered data pack.
_CLASS_BY_NAME = (
    ("metrics.json", "metric"),
    ("inputs.json", "financial"),
    ("data_pack", "pack"),
    ("research", "research"),
    ("qualitative", "qualitative"),
    ("evidence", "pdf"),
    ("pdf", "pdf"),
)


def _source_class(path: Path) -> str:
    name = path.name
    for prefix, label in _CLASS_BY_NAME:
        if name.startswith(prefix):
            return label
    return "other"



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
    # Snapshot IDs and calendar dates are provenance, not report metrics.
    text = re.sub(r"`[0-9a-fA-F]{12,}`", "", text)
    text = _ISO_DATE.sub("", text)
    text = _COMPACT_DATE.sub("", text)
    allowed = set()
    class_tokens: dict[str, set[str]] = {}
    source_paths = [Path(source) for source in sources]
    if strict:
        # Strict mode excludes raw statement rows; evidence/data-pack/PDF facts
        # remain valid, but an arbitrary raw input value is not a metric.
        source_paths = [source for source in source_paths if source.name != "inputs.json"]
    for source_path in source_paths:
        label = _source_class(source_path)
        bucket = class_tokens.setdefault(label, set())
        for source_text in _text_sources([source_path]):
            bucket.update(tokens(source_text))
        allowed.update(bucket)
    for source in source_paths:
        counts = _research_counts(source)
        if counts:
            class_tokens.setdefault("research", set()).update(counts)
        allowed.update(counts)
    unknown = [token for token in unknown_numbers(text, allowed) if not _YEAR.match(token)]
    total = len(tokens(text))

    # Attribute each report token to the authoritative artifacts that back it.
    # ``pack`` is excluded: it is a rendered product of the metrics, so counting
    # it as evidence would make every number look doubly sourced.  A token that
    # only exists in the data pack but not in any source artifact is suspicious
    # and reported separately as ``pack_only``.
    authoritative = ("metric", "financial", "pdf", "research", "qualitative")
    by_class: dict[str, int] = {}
    multi = 0
    pack_only = 0
    for token in tokens(text):
        hits = [
            label
            for label in authoritative
            if label in class_tokens and token in class_tokens[label]
        ]
        if hits:
            by_class[hits[0]] = by_class.get(hits[0], 0) + 1
            if len(hits) > 1:
                multi += 1
        elif "pack" in class_tokens and token in class_tokens["pack"]:
            pack_only += 1
    return {
        "report": str(report),
        "strict": strict,
        "tokens": total,
        "unknown": unknown,
        "coverage": round((total - len(unknown)) / total, 4) if total else 1.0,
        "status": "pass" if not unknown else "review",
        "by_class": {label: count for label, count in sorted(by_class.items()) if count},
        "multi_class": multi,
        "pack_only": pack_only,
        "unattributed": len(unknown),
    }
