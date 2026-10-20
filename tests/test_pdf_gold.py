import json
from pathlib import Path

import pytest

from turtlefw.pdf.extract import extract_pdf

ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = Path(__file__).parent / "fixtures"
GOLD_FILES = sorted(GOLD_DIR.glob("pdf_gold_*.json"))


@pytest.mark.parametrize("gold", GOLD_FILES, ids=[path.stem for path in GOLD_FILES])
def test_real_pdf_gold_set(gold: Path):
    payload = json.loads(gold.read_text(encoding="utf-8"))
    pdf = ROOT / payload["source"]
    if not pdf.is_file():
        pytest.skip(f"real annual report is not available: {pdf}")
    items = {item["item"]: item for item in extract_pdf(pdf, year=payload["year"])}
    for item, expected in payload["items"].items():
        assert item in items, f"{gold.name}: {item}"
        assert items[item]["value"] == expected["value"], f"{gold.name}: {item}"
        if expected.get("page"):
            assert items[item]["page"] == expected["page"], f"{gold.name}: {item}"
