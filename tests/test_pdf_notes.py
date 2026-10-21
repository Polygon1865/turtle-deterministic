from __future__ import annotations

import json
from pathlib import Path

from turtlefw.pdf.notes import extract_note_tables, notes_payload, write_notes


def test_extract_note_table_keeps_citation_and_rows():
    pages = [
        (
            7,
            (
                "第三节 管理层讨论与分析\n营业收入构成\n"
                "[TABLE]\n| 分产品 | 收入 |\n| --- | --- |\n| A | 100 |\n"
            ),
        )
    ]
    notes = extract_note_tables(pages, document_hash="a" * 64)
    assert len(notes) == 1
    note = notes[0]
    assert note.group == "revenue"
    assert note.page == 7
    assert note.citation == "pdf://" + "a" * 16 + "/p7"
    assert note.headers == ("分产品", "收入")
    assert note.rows == (("A", "100"),)


def test_extract_note_table_respects_row_budget():
    rows = "\n".join(f"| A{i} | {i} |" for i in range(5))
    page = "研发投入\n[TABLE]\n| 项目 | 金额 |\n| --- | --- |\n" + rows
    notes = extract_note_tables([(3, page)], max_rows=2)
    assert len(notes) == 1
    assert len(notes[0].rows) == 2


def test_extract_note_tables_ignores_unrelated_tables():
    page = "第三节 管理层讨论与分析\n[TABLE]\n| 项目 | 金额 |\n| --- | --- |\n| A | 1 |"
    assert extract_note_tables([(1, page)]) == []


def test_notes_payload_and_write(tmp_path: Path):
    page = "存货构成\n[TABLE]\n| 类别 | 金额 |\n| --- | --- |\n| 原材料 | 10 |"
    notes = extract_note_tables([(2, page)])
    path = tmp_path / "pdf_notes.json"
    write_notes(notes, path, source="annual.pdf")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["source"] == "annual.pdf"
    assert payload["count"] == 1
    assert payload["notes"][0]["group"] == "inventory"
    assert notes_payload(notes)["notes"][0]["page"] == 2
