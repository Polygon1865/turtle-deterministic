import json

from turtlefw.cli import _research_provenance_cmd


def test_research_provenance_hashes_artifacts(tmp_path):
    research = tmp_path / "research.json"
    research.write_text('{"claims": []}', encoding="utf-8")
    (tmp_path / "research_context.json").write_text('{"code": "600887"}', encoding="utf-8")
    out = tmp_path / "provenance.json"
    assert (
        _research_provenance_cmd(
            str(research),
            str(tmp_path),
            "dsh",
            "deepseek",
            str(out),
            "2026-10-19T22:00:00+08:00",
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["provider"] == "dsh"
    assert payload["mode"] == "dsh"
    assert payload["retries"] == 0
    assert len(payload["research_sha256"]) == 64
    assert len(payload["context_sha256"]) == 64
    assert payload["generated_at"] == "2026-10-19T22:00:00+08:00"


def test_research_provenance_records_replay_telemetry(tmp_path):
    research = tmp_path / "research.json"
    research.write_text('{"claims": []}', encoding="utf-8")
    (tmp_path / "research_context.json").write_text('{"code": "600887"}', encoding="utf-8")
    out = tmp_path / "provenance.json"
    assert (
        _research_provenance_cmd(
            str(research),
            str(tmp_path),
            "turtle-research-agent",
            "replay",
            str(out),
            None,
            elapsed_seconds=12.5,
            mode="replay",
            retries=2,
        )
        == 0
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mode"] == "replay"
    assert payload["retries"] == 2
    assert payload["elapsed_seconds"] == 12.5
