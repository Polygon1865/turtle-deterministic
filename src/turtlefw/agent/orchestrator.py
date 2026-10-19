"""Phase-state contract for optional Agent automation.

No LLM is called here. A caller supplies a ``runner`` (or uses the default
no-op) and the orchestrator enforces the artifact contract between phases.
That keeps the deterministic path usable without any model.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

Runner = Callable[[str, Path], None]

PHASES = ("data", "document", "research", "compose", "audit")

REQUIRED: dict[str, tuple[str, ...]] = {
    "data": ("data_pack.md",),
    "document": ("pdf_sections.json", "reported_numbers.json"),
    "research": ("research.json",),
    "compose": ("analysis_report.md",),
    "audit": ("qa.json",),
}


@dataclass(frozen=True, slots=True)
class PhaseResult:
    phase: str
    status: str  # pass | blocked | failed
    missing: tuple[str, ...] = ()
    message: str = ""


def validate(root: Path | str, phase: str) -> PhaseResult:
    directory = Path(root)
    if phase not in REQUIRED:
        return PhaseResult(phase, "failed", message=f"unknown phase {phase}")
    missing = tuple(name for name in REQUIRED[phase] if not (directory / name).is_file())
    if missing:
        return PhaseResult(phase, "blocked", missing=missing, message="missing artifacts")
    return PhaseResult(phase, "pass")


def run(
    root: Path | str,
    *,
    runner: Runner | None = None,
    phases: Sequence[str] = PHASES,
) -> list[PhaseResult]:
    results: list[PhaseResult] = []
    for phase in phases:
        before = validate(root, phase)
        if before.status != "pass":
            results.append(before)
            break
        if runner is not None:
            try:
                runner(phase, Path(root))
            except Exception as exc:  # noqa: BLE001 - runner is user code
                results.append(PhaseResult(phase, "failed", message=str(exc)))
                break
        after = validate(root, phase)
        results.append(after)
        if after.status != "pass":
            break
    return results
