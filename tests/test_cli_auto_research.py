from __future__ import annotations

import json
from pathlib import Path

import turtlefw.cli as cli
from turtlefw import state as st


def _valid_research() -> dict:
    return {
        "evidence": [
            {
                "id": "ev1",
                "url": "https://example.com/a",
                "quote": "公司业务稳定。",
            }
        ],
        "claims": [
            {
                "claim_id": "D1.1",
                "dimension": "D1",
                "statement": "公司业务稳定。",
                "judgment": "neutral",
                "confidence": "medium",
                "evidence_ids": ["ev1"],
            }
        ],
    }


def test_run_parser_accepts_with_research():
    args = cli.build_parser().parse_args(
        [
            "run",
            "600887",
            "--with-research",
            "--research-response",
            "replay.json",
            "--pdf-index",
            "pdf_index.json",
        ]
    )
    assert args.with_research is True
    assert args.research_response == "replay.json"
    assert args.pdf_index == "pdf_index.json"


def test_run_with_research_requires_existing_file(monkeypatch):
    assert (
        cli._run_cmd(
            "600887",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            "missing.json",
            None,
            False,
            False,
            False,
            False,
            False,
            with_research=True,
        )
        == 2
    )


def test_run_auto_research_chains_snapshot_agent_and_finalize(
    tmp_path: Path, monkeypatch
):
    root = tmp_path / "runs"
    replay = tmp_path / "replay.json"
    replay.write_text(json.dumps(_valid_research()), encoding="utf-8")
    monkeypatch.setattr(cli, "output_root", lambda: root)
    monkeypatch.setattr(cli, "_state_cmd", lambda *args, **kwargs: 0)

    calls: dict[str, object] = {}

    def fake_report(*args, **kwargs):
        save_snapshot = Path(args[7])
        data_pack = Path(args[17])
        save_snapshot.mkdir(parents=True, exist_ok=True)
        (save_snapshot / "data_pack.md").write_text("snapshot pack", encoding="utf-8")
        data_pack.parent.mkdir(parents=True, exist_ok=True)
        data_pack.write_text("base pack", encoding="utf-8")
        calls["report"] = (save_snapshot, data_pack)
        return 0

    def fake_context(snapshot, data_pack=None, **_kwargs):
        calls["context"] = (snapshot, data_pack)
        return {"code": "600887.SH", "snapshot_id": "snap"}

    def fake_agent(snapshot, out, *_args, **_kwargs):
        snapshot_path = Path(snapshot)
        out_path = Path(out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(_valid_research()), encoding="utf-8")
        (snapshot_path / "research_context.json").write_text("{}", encoding="utf-8")
        calls["agent"] = (snapshot, out)
        return 0

    def fake_provenance(research, snapshot, provider, model, out, *_args, **_kwargs):
        calls["provenance"] = (research, snapshot, provider, model, out)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text("{}", encoding="utf-8")
        return 0

    def fake_finalize(source, research, out, **kwargs):
        out_path = Path(out)
        out_path.mkdir(parents=True)
        (out_path / "data_pack.md").write_text("final pack", encoding="utf-8")
        (out_path / "research.json").write_text(
            Path(research).read_text(encoding="utf-8"), encoding="utf-8"
        )
        (out_path / "research_audit.json").write_text("{}", encoding="utf-8")
        (out_path / "research_provenance.json").write_text("{}", encoding="utf-8")
        base = Path(source).parent
        run = st.new("600887.SH")
        st.add_artifact(run, "snapshot", str(out_path))
        st.save(run, base / "run_state.json")
        calls["finalize"] = (Path(source), Path(research), out_path, kwargs)
        return out_path

    monkeypatch.setattr(cli, "_report", fake_report)
    monkeypatch.setattr(cli, "_research_context", fake_context)
    monkeypatch.setattr(cli, "_research_agent_cmd", fake_agent)
    monkeypatch.setattr(cli, "_research_provenance_cmd", fake_provenance)
    monkeypatch.setattr(
        "turtlefw.report.finalize.finalize_research", fake_finalize
    )

    rc = cli._run_cmd(
        "600887",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        False,
        False,
        False,
        False,
        False,
        with_research=True,
        research_response=str(replay),
    )

    assert rc == 0
    base = root / "600887.SH"
    assert (base / "snapshot").is_dir()
    assert (base / "research.json").is_file()
    assert (base / "data_pack.md").read_text(encoding="utf-8") == "final pack"
    assert not (base / ".research-snapshot-base").exists()
    assert not (base / ".research-snapshot-final").exists()
    assert calls["agent"][0] == str(base / ".research-snapshot-base")
    assert calls["finalize"][0] == base / ".research-snapshot-base"
    state = json.loads((base / "run_state.json").read_text(encoding="utf-8"))
    assert state["artifacts"]["snapshot"] == str((base / "snapshot").resolve())
    assert state["artifacts"]["data_pack"] == str((base / "data_pack.md").resolve())


def test_research_agent_rejects_over_budget_context(tmp_path: Path, monkeypatch):
    replay = tmp_path / "replay.json"
    replay.write_text(json.dumps(_valid_research()), encoding="utf-8")
    monkeypatch.setattr(cli, "_research_context", lambda *args, **kwargs: {"x": "a" * 1000})
    out = tmp_path / "research.json"
    rc = cli._research_agent_cmd(
        str(tmp_path),
        str(out),
        None,
        None,
        None,
        response=str(replay),
        max_input_tokens=10,
    )
    assert rc == 2
    assert not out.exists()


def test_research_agent_writes_usage_sidecar(tmp_path: Path, monkeypatch):
    replay = tmp_path / "replay.json"
    replay.write_text(json.dumps(_valid_research()), encoding="utf-8")
    monkeypatch.setattr(cli, "_research_context", lambda *args, **kwargs: {"x": "a" * 40})
    out = tmp_path / "research.json"
    rc = cli._research_agent_cmd(
        str(tmp_path),
        str(out),
        None,
        None,
        None,
        response=str(replay),
        max_input_tokens=100,
    )
    assert rc == 0
    usage = json.loads((tmp_path / "research.usage.json").read_text(encoding="utf-8"))
    assert usage["mode"] == "replay"
    assert usage["input_chars"] > 0
    assert usage["estimated_input_tokens"] > 0
    assert usage["max_input_tokens"] == 100


def test_run_auto_research_failure_cleans_staging(tmp_path: Path, monkeypatch):
    root = tmp_path / "runs"
    replay = tmp_path / "replay.json"
    replay.write_text(json.dumps(_valid_research()), encoding="utf-8")
    monkeypatch.setattr(cli, "output_root", lambda: root)
    monkeypatch.setattr(cli, "_state_cmd", lambda *args, **kwargs: 0)

    def fake_report(*args, **kwargs):
        staging = Path(args[7])
        staging.mkdir(parents=True, exist_ok=True)
        (staging / "data_pack.md").write_text("pack", encoding="utf-8")
        return 0

    def fake_context(snapshot, data_pack=None, **_kwargs):
        return {"code": "600887.SH"}

    def fake_agent(*_args, **_kwargs):
        return 2

    monkeypatch.setattr(cli, "_report", fake_report)
    monkeypatch.setattr(cli, "_research_context", fake_context)
    monkeypatch.setattr(cli, "_research_agent_cmd", fake_agent)

    rc = cli._run_cmd(
        "600887",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        False,
        False,
        False,
        False,
        False,
        with_research=True,
        research_response=str(replay),
    )

    base = root / "600887.SH"
    assert rc == 2
    assert not (base / ".research-snapshot-base").exists()
    assert not (base / ".research-snapshot-final").exists()
    assert not (base / "snapshot").exists()
