import json
from pathlib import Path

import pytest

from turtlefw.pdf.extract import extract_pdf

ROOT = Path(__file__).resolve().parents[1]
GOLD = Path(__file__).parent / "fixtures" / "pdf_gold_00700.json"


def test_00700_pdf_gold_set():
    payload = json.loads(GOLD.read_text(encoding="utf-8"))
    pdf = ROOT / payload["source"]
    if not pdf.is_file():
        pytest.skip("real 00700 annual report is not available")
    items = {item["item"]: item for item in extract_pdf(pdf, year=payload["year"])}
    for item, expected in payload["items"].items():
        assert item in items, item
        assert items[item]["value"] == expected["value"], item
        assert items[item]["page"] == expected["page"], item
