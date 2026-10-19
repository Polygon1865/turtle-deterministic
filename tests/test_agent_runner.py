import sys
from pathlib import Path

from turtlefw.agent.runner import run_commands


def _python_write(name: str) -> str:
    script = f"from pathlib import Path; Path({name!r}).write_text('ok', encoding='utf-8')"
    return f'"{sys.executable}" -c "{script}"'


def test_command_fills_artifact(tmp_path):
    results = run_commands(tmp_path, {"data": _python_write("data_pack.md")})
    assert results[0].status == "pass"
    assert (tmp_path / "data_pack.md").is_file()
    assert (tmp_path / "agent_state.json").is_file()
    assert (tmp_path / ".agent" / "data.log").is_file()


def test_missing_command_blocks(tmp_path):
    results = run_commands(tmp_path, {})
    assert results[0].status == "blocked"
    assert "data_pack.md" in results[0].missing


def test_command_failure_stops_runner(tmp_path):
    results = run_commands(tmp_path, {"data": "exit 1"})
    assert results[0].status == "failed"
    assert "exited 1" in results[0].message


def test_resume_skips_passed_phase(tmp_path):
    (tmp_path / "data_pack.md").write_text("ok", encoding="utf-8")
    run_commands(tmp_path, {})
    results = run_commands(
        tmp_path,
        {"data": "exit 1"},
        resume=True,
    )
    assert results[0].status == "pass"
    assert results[0].message == "resumed"


def test_retry_attempts(tmp_path):
    results = run_commands(tmp_path, {"data": "exit 1"}, retries=1)
    assert results[0].status == "failed"
    log = (tmp_path / ".agent" / "data.log").read_text(encoding="utf-8")
    assert "attempt 2" in log
