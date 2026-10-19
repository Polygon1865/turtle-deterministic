import json

from turtlefw.cli import _research_context


def test_research_context_collects_snapshot_sources(tmp_path):
    (tmp_path / "inputs.json").write_text(
        json.dumps(
            {
                "code": "600887.SH",
                "as_of": "2026-10-16",
                "currency": "CNY",
                "parent_cash": "100",
                "pledge_pct": "0",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "manifest.json").write_text(
        json.dumps({"snapshot_id": "snap-1"}), encoding="utf-8"
    )
    (tmp_path / "metrics.json").write_text('{"r": {"display": "3.36%"}}', encoding="utf-8")
    (tmp_path / "evidence.json").write_text(
        json.dumps([{"id": "pdf:section:MDA", "quote": "MDA text"}]),
        encoding="utf-8",
    )
    (tmp_path / "pdf_sections.json").write_text(
        json.dumps({"metadata": {}, "MDA": "MDA text"}),
        encoding="utf-8",
    )
    context = _research_context(str(tmp_path))
    assert context["code"] == "600887.SH"
    assert context["snapshot_id"] == "snap-1"
    assert context["governance"]["parent_cash"] == "100"
    assert any(row["id"] == "data:governance" for row in context["facts"])
    assert any(row["key"] == "parent_cash" for row in context["coverage"])
    assert context["metrics"]["r"]["display"] == "3.36%"
    assert context["facts"][0]["id"] == "pdf:section:MDA"
    assert context["pdf_sections"]["MDA"] == "MDA text"
