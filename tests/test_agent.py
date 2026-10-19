import os
import shutil
import tempfile
from pathlib import Path

from turtlefw.agent import PHASES, run, validate


def _root() -> Path:
    path = Path(tempfile.gettempdir()) / f"turtle-agent-test-{os.getpid()}"
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def test_missing_phase_blocks():
    root = _root()
    try:
        result = validate(root, "data")
        assert result.status == "blocked"
        assert "data_pack.md" in result.missing
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_runner_fills_artifacts():
    root = _root()
    try:
        for phase, files in {
            "data": ["data_pack.md"],
            "document": ["pdf_sections.json", "reported_numbers.json"],
            "research": ["research.json"],
            "compose": ["analysis_report.md"],
            "audit": ["qa.json"],
        }.items():
            for name in files:
                (root / name).write_text(phase, encoding="utf-8")
        results = run(root, phases=PHASES)
        assert [r.status for r in results] == ["pass"] * len(PHASES)
    finally:
        shutil.rmtree(root, ignore_errors=True)
