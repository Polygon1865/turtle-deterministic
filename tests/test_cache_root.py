"""T5: one HTTP cache across days, so a new day does not cold-start."""

from __future__ import annotations

import os
from pathlib import Path

from turtlefw import paths


def test_runs_root_parent_become_the_shared_cache(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(paths.CACHE_ENV, raising=False)
    runs_root = tmp_path / ".runs" / "daily"
    assert paths.cache_root(runs_root) == runs_root.parent / ".cache"


def test_env_override_wins(monkeypatch, tmp_path: Path) -> None:
    shared = tmp_path / "shared-cache"
    monkeypatch.setenv(paths.CACHE_ENV, str(shared))
    assert paths.cache_root(tmp_path / ".runs" / "daily") == shared


def test_defaults_to_output_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv(paths.CACHE_ENV, raising=False)
    monkeypatch.setenv("TURTLE_OUTPUT_DIR", str(tmp_path / "out"))
    assert paths.cache_root() == tmp_path / "out" / ".cache"


def test_daily_points_every_step_at_the_shared_cache(monkeypatch, tmp_path: Path) -> None:
    """run_daily must export the cache path before spawning any CLI step."""

    from turtlefw.daily import DailyConfig, DailyPaths, run_daily

    monkeypatch.delenv(paths.CACHE_ENV, raising=False)
    runs_root = tmp_path / ".runs" / "daily"
    paths_obj = DailyPaths(
        day=__import__("datetime").date(2026, 11, 10),
        runs_root=runs_root,
        site_root=tmp_path / "site",
        pdf_root=tmp_path / "pdfs",
    )

    def fake_run(command, cwd, timeout):  # noqa: ANN001 - test double
        # Skip every real step: this only asserts the environment is set
        # before the first child process would have started.
        assert os.environ.get("TURTLE_CACHE_DIR") == str(runs_root.parent / ".cache")
        raise RuntimeError("stop")

    try:
        run_daily(
            paths_obj,
            DailyConfig(),
            codes=[],
            skip_screen=True,
            publish=False,
            run_command=fake_run,
        )
    except Exception:  # noqa: BLE001 - the run is aborted on purpose
        pass
    assert os.environ.get("TURTLE_CACHE_DIR") == str(runs_root.parent / ".cache")
