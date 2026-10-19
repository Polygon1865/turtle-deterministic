"""No-LLM phase runner.

Commands are supplied explicitly by the caller and executed inside the
analysis directory. The runner never invents research prose and never marks a
phase complete unless the artifact contract passes afterwards. Shell commands
are intentional here: they are local, user-supplied workflow commands.
"""

from __future__ import annotations

import json
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from .orchestrator import PHASES, PhaseResult, validate

STATE_FILE = "agent_state.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class PhaseRun:
    phase: str
    status: str
    command: str = ""
    returncode: int | None = None
    missing: tuple[str, ...] = ()
    message: str = ""
    attempts: int = 0
    started_at: str = ""
    finished_at: str = ""


@dataclass
class AgentRun:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    phases: list[PhaseRun] = field(default_factory=list)
    started_at: str = field(default_factory=_now)
    finished_at: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "phases": [phase.__dict__ for phase in self.phases],
        }


def _run_command(
    root: Path,
    phase: str,
    command: str,
    timeout: int,
    log_dir: Path,
    attempt: int,
) -> tuple[int, str, str]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=root,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    elapsed = time.monotonic() - started
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{phase}.log"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n=== attempt {attempt} ===\n"
            f"$ {command}\n"
            f"exit={completed.returncode} elapsed={elapsed:.2f}s\n"
            f"--- stdout ---\n{completed.stdout}\n"
            f"--- stderr ---\n{completed.stderr}\n"
        )
    return completed.returncode, completed.stdout, completed.stderr


def _prior_passed(root: Path) -> set[str]:
    path = root / STATE_FILE
    if not path.is_file():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {
        str(item.get("phase"))
        for item in payload.get("phases", [])
        if isinstance(item, dict) and item.get("status") == "pass"
    }


def run_commands(
    root: Path | str,
    commands: Mapping[str, str],
    *,
    phases: Sequence[str] = PHASES,
    timeout: int = 300,
    retries: int = 0,
    resume: bool = False,
) -> list[PhaseResult]:
    directory = Path(root)
    if not directory.is_dir():
        return [PhaseResult("data", "failed", message=f"not a directory: {directory}")]
    unknown = sorted(set(commands) - set(PHASES))
    if unknown:
        return [PhaseResult("data", "failed", message=f"unknown phases: {unknown}")]

    run = AgentRun()
    results: list[PhaseResult] = []
    log_dir = directory / ".agent"
    prior_passed = _prior_passed(directory) if resume else set()
    for phase in phases:
        if phase in prior_passed:
            validated = validate(directory, phase)
            if validated.status == "pass":
                run.phases.append(
                    PhaseRun(
                        phase=phase,
                        status="pass",
                        message="resumed",
                        started_at=_now(),
                        finished_at=_now(),
                    )
                )
                results.append(PhaseResult(phase, "pass", message="resumed"))
                continue
        phase_run = PhaseRun(phase=phase, status="blocked", started_at=_now())
        command = commands.get(phase, "")
        if command:
            phase_run.command = command
            returncode = 0
            for attempt in range(1, max(1, retries + 1) + 1):
                phase_run.attempts = attempt
                try:
                    returncode, _stdout, _stderr = _run_command(
                        directory, phase, command, timeout, log_dir, attempt
                    )
                except (OSError, subprocess.TimeoutExpired) as exc:
                    phase_run.status = "failed"
                    phase_run.message = str(exc)
                    phase_run.finished_at = _now()
                    run.phases.append(phase_run)
                    results.append(
                        PhaseResult(phase, "failed", message=phase_run.message)
                    )
                    break
                if returncode == 0:
                    break
            if phase_run.status == "failed":
                break
            phase_run.returncode = returncode
            if returncode != 0:
                phase_run.status = "failed"
                phase_run.message = f"command exited {returncode}; see .agent/{phase}.log"
                phase_run.finished_at = _now()
                run.phases.append(phase_run)
                results.append(
                    PhaseResult(phase, "failed", message=phase_run.message)
                )
                break

        validated = validate(directory, phase)
        phase_run.status = validated.status
        phase_run.missing = validated.missing
        phase_run.message = validated.message
        phase_run.finished_at = _now()
        run.phases.append(phase_run)
        results.append(validated)
        if validated.status != "pass":
            break

    run.finished_at = _now()
    (directory / STATE_FILE).write_text(
        json.dumps(run.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return results
