from pathlib import Path

from turtlefw.cli import _data_pack_targets, _fallback_data_pack


def test_custom_pack_output_still_writes_snapshot_pack(tmp_path: Path) -> None:
    base = tmp_path / "601877.SH"
    snapshot = base / "snapshot"

    targets = _data_pack_targets(str(base / "data_pack.md"), str(snapshot))

    assert base / "data_pack.md" in targets
    assert snapshot / "data_pack.md" in targets


def test_snapshot_pack_target_is_not_duplicated(tmp_path: Path) -> None:
    snapshot = tmp_path / "600887.SH" / "snapshot"

    targets = _data_pack_targets(str(snapshot / "data_pack.md"), str(snapshot))

    assert targets == [snapshot / "data_pack.md"]


def test_snapshot_pack_is_not_overwritten_by_stale_base(tmp_path: Path) -> None:
    base = tmp_path / "00700.HK"
    snapshot = base / "snapshot"
    snapshot.mkdir(parents=True)
    (base / "data_pack.md").write_text("stale pack", encoding="utf-8")
    (snapshot / "data_pack.md").write_text("fresh pack", encoding="utf-8")

    _fallback_data_pack(snapshot, base)

    assert (snapshot / "data_pack.md").read_text(encoding="utf-8") == "fresh pack"


def test_snapshot_pack_falls_back_only_when_missing(tmp_path: Path) -> None:
    base = tmp_path / "600887.SH"
    snapshot = base / "snapshot"
    snapshot.mkdir(parents=True)
    (base / "data_pack.md").write_text("legacy pack", encoding="utf-8")

    _fallback_data_pack(snapshot, base)

    assert (snapshot / "data_pack.md").read_text(encoding="utf-8") == "legacy pack"
