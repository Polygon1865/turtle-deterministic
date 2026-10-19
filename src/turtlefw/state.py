"""Run state for the multi-phase agent workflow.

The state file is the only source of truth for "where did this analysis stop".
It contains no numbers and no judgments, just phase, artifacts and warnings, so
the deterministic core never depends on it.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import output_root
from .types import TurtleError

PHASES = (
    "intake",
    "data",
    "report_pdf",
    "qualitative",
    "report",
    "qa",
    "done",
    "failed",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class RunState:
    code: str
    run_id: str
    phase: str = "intake"
    snapshot_id: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    started_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def path_for(code: str, root: Path | str | None = None) -> Path:
    base = Path(root) if root is not None else output_root()
    return base / str(code) / "run_state.json"


def new(code: str) -> RunState:
    return RunState(code=str(code), run_id=uuid.uuid4().hex[:12])


def load(path: Path | str) -> RunState:
    path = Path(path)
    if not path.is_file():
        raise TurtleError(f"run_state not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise TurtleError(f"invalid run_state JSON: {exc}") from exc
    known = set(RunState.__dataclass_fields__)
    state = RunState(**{key: value for key, value in data.items() if key in known})
    if state.phase not in PHASES:
        raise TurtleError(f"invalid phase: {state.phase!r}")
    return state


def save(state: RunState, path: Path | str) -> Path:
    state.updated_at = _now()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def advance(state: RunState, phase: str) -> RunState:
    if phase not in PHASES:
        raise TurtleError(f"invalid phase: {phase!r}")
    state.phase = phase
    return state


def add_artifact(state: RunState, key: str, value: str) -> RunState:
    state.artifacts[key] = value
    return state


def add_warning(state: RunState, message: str) -> RunState:
    state.warnings.append(message)
    return state


def ask(state: RunState, question: str) -> RunState:
    state.questions.append(question)
    return state
