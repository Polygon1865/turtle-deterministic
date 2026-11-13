"""Evidence grading for the research layer.

The 2026-11-04 replay showed verdicts flipping on research judgments that had
no external source behind them.  Across ``.runs/daily`` the same corpus held
15,813 evidence items and only 84 http URLs: almost every claim rested on a
restatement of the data pack, which makes "evidence-backed" look stronger than
it is.  This module grades each source so QA and readers can tell a filing or a
named outlet from a data-pack echo.

Grades
------
``A`` filings / regulators (HKEXnews, cninfo, SEC, ministry sites), PDF reports
``B`` named financial media with editorial review (Reuters, AASTOCKS, 证券时报…)
``C`` anything else with an http URL
``data`` internal data-pack fact, no independent source
``unknown`` no URL and no PDF provenance
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

GRADE_A_HOSTS: tuple[str, ...] = (
    "hkexnews.hk",
    "hkex.com.hk",
    "cninfo.com.cn",
    "sse.com.cn",
    "szse.cn",
    "sec.gov",
    "csrc.gov.cn",
    "samr.gov.cn",
    "gov.cn",
)

GRADE_B_HOSTS: tuple[str, ...] = (
    "reuters.com",
    "bloomberg.com",
    "aastocks.com",
    "eastmoney.com",
    "stcn.com",
    "zhitongcaijing.com",
    "hexun.com",
    "stockstar.com",
    "10jqka.com.cn",
    "sina.com.cn",
    "sohu.com",
    "huxiu.com",
    "caixin.com",
    "cls.cn",
    "wallstreetcn.com",
    "yahoo.com",
)

EXTERNAL_GRADES = frozenset({"A", "B"})


def host_of(url: str) -> str:
    """Return the lower-cased host of ``url`` (empty for non-absolute URLs)."""

    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return ""
    return host.lower()


def _matches(host: str, suffixes: Sequence[str]) -> bool:
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in suffixes)


def grade_url(url: str) -> str:
    """Grade a single URL as ``A``, ``B``, ``C`` or ``unknown``."""

    host = host_of(url)
    if not host:
        return "unknown"
    if _matches(host, GRADE_A_HOSTS):
        return "A"
    if _matches(host, GRADE_B_HOSTS):
        return "B"
    return "C"


def grade_evidence(evidence: Mapping[str, Any]) -> str:
    """Grade one evidence item (``source_type``/``url``/``page``)."""

    if str(evidence.get("source_type") or "").strip() == "data":
        return "data"
    url = str(evidence.get("url") or "").strip()
    if url:
        return grade_url(url)
    if evidence.get("page") not in (None, ""):
        return "A"
    return "unknown"


@dataclass(frozen=True, slots=True)
class EvidenceGrades:
    counts: dict[str, int] = field(default_factory=dict)
    external: int = 0
    high_without_external: tuple[str, ...] = ()

    def summary(self) -> str:
        parts = [f"{grade} {count}" for grade, count in sorted(self.counts.items())]
        return "、".join(parts) if parts else "无证据"


def grade_document(
    claims: Sequence[Any],
    evidence: Mapping[str, Mapping[str, Any]],
) -> EvidenceGrades:
    """Grade all evidence and list high-confidence claims with no A/B source.

    ``claims`` only needs ``claim_id``, ``confidence`` and ``evidence_ids`` so
    this module does not depend on the research schema.
    """

    counts: dict[str, int] = {}
    grades_by_id: dict[str, str] = {}
    for item_id, item in evidence.items():
        grade = grade_evidence(item)
        grades_by_id[str(item_id)] = grade
        counts[grade] = counts.get(grade, 0) + 1
    external = sum(counts.get(grade, 0) for grade in EXTERNAL_GRADES)
    unsupported: list[str] = []
    for claim in claims:
        if str(getattr(claim, "confidence", "") or "") != "high":
            continue
        ids = tuple(getattr(claim, "evidence_ids", ()) or ())
        if not any(grades_by_id.get(str(item_id)) in EXTERNAL_GRADES for item_id in ids):
            unsupported.append(str(getattr(claim, "claim_id", "")))
    return EvidenceGrades(
        counts=counts,
        external=external,
        high_without_external=tuple(unsupported),
    )
