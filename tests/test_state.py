import json

import pytest

from turtlefw import state as st
from turtlefw.types import TurtleError


def test_new_and_roundtrip(tmp_path):
    run = st.new("600887.SH")
    path = st.path_for("600887.SH", root=tmp_path)
    st.save(run, path)
    loaded = st.load(path)
    assert loaded.code == "600887.SH"
    assert loaded.phase == "intake"
    assert loaded.run_id == run.run_id


def test_advance_and_artifacts(tmp_path):
    run = st.new("600887.SH")
    st.advance(run, "data")
    st.add_artifact(run, "data_pack", "output/600887.SH/data_pack.md")
    st.add_warning(run, "D&A 缺失")
    path = tmp_path / "run_state.json"
    st.save(run, path)
    loaded = st.load(path)
    assert loaded.phase == "data"
    assert loaded.artifacts["data_pack"].endswith("data_pack.md")
    assert loaded.warnings == ["D&A 缺失"]


def test_invalid_phase_rejected():
    run = st.new("600887.SH")
    with pytest.raises(TurtleError):
        st.advance(run, "nonsense")


def test_missing_file(tmp_path):
    with pytest.raises(TurtleError):
        st.load(tmp_path / "missing.json")


def test_corrupt_file(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(TurtleError):
        st.load(path)
