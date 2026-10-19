import tempfile
from pathlib import Path

from turtlefw import cli, state
from turtlefw.paths import output_path, output_root


def _root() -> Path:
    return Path(tempfile.gettempdir()) / "turtle-path-test"


def test_output_root_env(monkeypatch):
    root = _root()
    monkeypatch.setenv("TURTLE_OUTPUT_DIR", str(root))
    assert output_root() == root
    assert output_path("600887.SH", "analysis_report.md") == root / "600887.SH" / "analysis_report.md"
    assert state.path_for("600887.SH") == root / "600887.SH" / "run_state.json"


def test_output_root_alias(monkeypatch):
    root = _root()
    monkeypatch.delenv("TURTLE_OUTPUT_DIR", raising=False)
    monkeypatch.setenv("TURTLE_OUTPUT_ROOT", str(root))
    assert output_root() == root


def test_global_output_dir_sets_env(monkeypatch):
    monkeypatch.delenv("TURTLE_OUTPUT_DIR", raising=False)
    parser = cli.build_parser()
    args = parser.parse_args(["--output-dir", ".runs", "qa", "600887"])
    assert args.output_dir == ".runs"
    monkeypatch.setenv("TURTLE_OUTPUT_DIR", args.output_dir)
    assert output_root() == Path(".runs")


def test_agent_command_does_not_shadow_dispatch():
    parser = cli.build_parser()
    args = parser.parse_args(
        ["agent", "--dir", ".", "--command", "data=echo x"]
    )
    assert args.command == "agent"
    assert args.phase_commands == ["data=echo x"]


def test_report_html_flag():
    parser = cli.build_parser()
    args = parser.parse_args(["report", "600887", "--html"])
    assert args.command == "report"
    assert args.html is True
