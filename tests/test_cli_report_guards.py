"""Guard tests for ``turtle report`` flag combinations (T2 regression)."""

from __future__ import annotations

from pathlib import Path

from turtlefw.cli import main


def test_snapshot_and_save_snapshot_are_rejected(tmp_path: Path) -> None:
    """Rendering a frozen snapshot must not try to freeze a second one.

    Before this guard the combination crashed with ``UnboundLocalError:
    metrics_out`` instead of telling the user what was wrong.
    """

    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    code = main(
        [
            "report",
            "00270.HK",
            "--snapshot",
            str(snapshot),
            "--save-snapshot",
            str(tmp_path / "new"),
        ]
    )
    assert code == 2
