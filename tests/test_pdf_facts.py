from decimal import Decimal
import json

from turtlefw.pdf.dps import extract_dps_from_pages
from turtlefw.pdf.extract import write_reported_numbers
from turtlefw.pdf.multiline import FactRow, make_fact_id


def test_dps_parses_small_value_and_currency():
    result = extract_dps_from_pages(
        [(12, "每股派息 1.2345 元"), (13, "每股股息 2.50 港元")]
    )
    assert result["dps"] == "1.2345"
    assert result["currency"] == "CNY"
    assert result["page"] == "12"


def test_dps_rejects_large_statement_numbers():
    assert extract_dps_from_pages([(1, "每股派息 1,234,567")]) == {}


def test_multiline_fact_hash_stable():
    kwargs = dict(
        fact_id=make_fact_id("00700", "main_business", "online"),
        item="main_business",
        dimension="product",
        label="online",
        period="2025A",
        value=Decimal("100.00"),
        unit="CNY",
        page=88,
    )
    first = FactRow(**kwargs)
    second = FactRow(**kwargs)
    assert first.fact_hash == second.fact_hash
    assert first.to_dict()["fact_hash"] == first.fact_hash


def test_reported_numbers_carries_dps(tmp_path):
    target = write_reported_numbers(
        [],
        tmp_path / "reported_numbers.json",
        dps={
            "dps": "1.2345",
            "currency": "CNY",
            "page": "12",
            "quote": "每股派息 1.2345 元",
        },
        year=2025,
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["dps"]["dps"] == "1.2345"
    assert payload["document_facts"][0]["label"] == "dps"
    assert payload["document_facts"][0]["fact_hash"]
