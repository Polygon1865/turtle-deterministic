"""Evidence-backed qualitative input.

The deterministic pipeline refuses to guess. Qualitative judgments arrive as a
small JSON file; any judgment without evidence is downgraded to ``unknown`` so
the report cannot present an unsupported opinion as a finding.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import TurtleError

MODULES: dict[str, str] = {
    "moat": "护城河与竞争格局",
    "management": "管理层与治理",
    "policy": "监管与政策",
    "fraud": "财务造假/违规前科",
    "understandability": "商业模式可理解性",
    "controller": "控股股东信号",
}

JUDGMENTS = {"positive", "neutral", "negative", "unknown"}
CONFIDENCE = {"high", "medium", "low"}


@dataclass(frozen=True, slots=True)
class Evidence:
    url: str
    quote: str


@dataclass(frozen=True, slots=True)
class Judgment:
    module: str
    judgment: str
    confidence: str
    evidence: tuple[Evidence, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class Qualitative:
    items: dict[str, Judgment] = field(default_factory=dict)

    def get(self, module: str) -> Judgment | None:
        return self.items.get(module)


def template() -> dict[str, Any]:
    return {
        "modules": {
            key: {
                "judgment": "unknown",
                "confidence": "low",
                "evidence": [],
                "notes": "",
            }
            for key in MODULES
        }
    }


def write_template(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(template(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load(path: Path) -> Qualitative:
    if not path.is_file():
        raise TurtleError(f"qualitative file not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TurtleError(f"invalid JSON in {path}: {exc}") from exc

    modules = payload.get("modules")
    if not isinstance(modules, dict):
        raise TurtleError("qualitative JSON must contain a 'modules' object")

    items: dict[str, Judgment] = {}
    for module, raw in modules.items():
        if module not in MODULES:
            raise TurtleError(f"unknown qualitative module: {module}")
        if not isinstance(raw, dict):
            raise TurtleError(f"module {module} must be an object")

        judgment = str(raw.get("judgment", "unknown")).lower()
        confidence = str(raw.get("confidence", "low")).lower()
        if judgment not in JUDGMENTS:
            raise TurtleError(f"{module}: invalid judgment {judgment!r}")
        if confidence not in CONFIDENCE:
            raise TurtleError(f"{module}: invalid confidence {confidence!r}")

        evidence: list[Evidence] = []
        for item in raw.get("evidence", []):
            url = str(item.get("url", "")).strip()
            quote = str(item.get("quote", "")).strip()
            if not url.startswith(("http://", "https://")):
                raise TurtleError(f"{module}: evidence url must start with http(s)")
            if not quote:
                raise TurtleError(f"{module}: evidence quote is empty")
            evidence.append(Evidence(url=url, quote=quote))

        notes = str(raw.get("notes", "")).strip()
        if judgment != "unknown" and not evidence:
            judgment = "unknown"
            notes = (notes + " " if notes else "") + "（无证据，已降级为 unknown）"

        items[module] = Judgment(
            module=module,
            judgment=judgment,
            confidence=confidence,
            evidence=tuple(evidence),
            notes=notes,
        )
    return Qualitative(items=items)


def summary(q: Qualitative) -> list[tuple[str, str, str, int]]:
    """``(label, judgment, confidence, evidence_count)`` for display."""
    rows = []
    for key, label in MODULES.items():
        item = q.get(key)
        if item is None:
            continue
        rows.append((label, item.judgment, item.confidence, len(item.evidence)))
    return rows


def all_evidence(q: Qualitative) -> list[tuple[str, str, str]]:
    """``(module_label, url, quote)`` for the report appendix."""
    rows = []
    for key, label in MODULES.items():
        item = q.get(key)
        if item is None:
            continue
        for evidence in item.evidence:
            rows.append((label, evidence.url, evidence.quote))
    return rows
