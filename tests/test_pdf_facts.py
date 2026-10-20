from dataclasses import replace
from decimal import Decimal
import json

import pytest

from turtlefw.pdf.dps import extract_dps_from_pages
from turtlefw.pdf.extract import _is_capex_table, write_reported_numbers
from turtlefw.pdf.multiline import FactRow, make_fact_id, rows_to_facts
from turtlefw.metrics.dps_check import crosscheck_dps
from turtlefw.report.facts_coverage import CoverageGate
from turtlefw.report.pdf_facts import apply_document_facts, main_business_rows, merge_main_business
from turtlefw.demo import demo_rows


def test_dps_parses_small_value_and_currency():
    result = extract_dps_from_pages(
        [(12, "每股派息 1.2345 元"), (13, "每股股息 2.50 港元")]
    )
    assert result["dps"] == "1.2345"
    assert result["currency"] == "CNY"
    assert result["page"] == "12"


def test_dps_rejects_large_statement_numbers():
    assert extract_dps_from_pages([(1, "每股派息 1,234,567")]) == {}


def test_document_fact_overrides_accounts_receivable():
    anchor = next(
        row for row in demo_rows() if row.statement == "balance" and row.period_type == "annual"
    )
    rows = [replace(anchor, item="accounts_receiv", value=Decimal("1"))]
    before = rows[0]
    changed = apply_document_facts(
        rows,
        [
            {
                "label": "accounts_receiv",
                "value": "123456789.00",
                "page": "132",
            }
        ],
    )
    after = next(
        row
        for row in changed
        if row.statement == "balance"
        and row.item == "accounts_receiv"
        and row.period_end == before.period_end
    )
    assert after.value == Decimal("123456789.00")
    assert after.source == "pdf:accounts_receiv:132"


@pytest.mark.parametrize("item", ["inventory", "contract_liab"])
def test_document_fact_overrides_other_balance_items(item):
    anchor = next(
        row for row in demo_rows() if row.statement == "balance" and row.period_type == "annual"
    )
    rows = [replace(anchor, item=item, value=Decimal("1"))]
    changed = apply_document_facts(
        rows,
        [{"label": item, "value": "987654321.00", "page": "133"}],
    )
    after = changed[0]
    assert after.value == Decimal("987654321.00")
    assert after.source == f"pdf:{item}:133"


def test_main_business_fact_rows_convert_to_pack_rows():
    rows = main_business_rows(
        [
            {
                "fact_id": "pdf:row:1",
                "item": "main_business",
                "label": "液体乳",
                "value": "80000.00",
                "page": 88,
            }
        ]
    )
    assert rows == [
        {
            "bz_item": "液体乳",
            "bz_sales": "80000.00",
            "bz_profit": None,
            "source": "pdf",
        }
    ]


def test_capex_table_requires_explicit_header():
    assert not _is_capex_table([["资产", "2025"], ["存货", "100"]])
    assert _is_capex_table([["项目", "2025"], ["设备", "100"]])


def test_capex_detail_rows_to_facts():
    facts = rows_to_facts(
        [[["项目", "2025"], ["设备购置", "12,000"], ["在建工程", "8,000"]]],
        item="capex_detail",
        dimension="asset_class",
        page=99,
        year=2025,
        unit="CNY",
    )
    assert [fact.label for fact in facts] == ["设备购置", "在建工程"]
    assert facts[0].value == Decimal("12000")
    assert facts[0].item == "capex_detail"


def test_main_business_pdf_rows_win_on_duplicate():
    merged = merge_main_business(
        [{"bz_item": "液体乳", "bz_sales": 1}, {"bz_item": "奶粉", "bz_sales": 2}],
        [{"bz_item": "液体乳", "bz_sales": 9}],
    )
    assert merged[0]["bz_sales"] == 9
    assert [row["bz_item"] for row in merged] == ["液体乳", "奶粉"]


def test_main_business_uses_current_year_column():
    facts = rows_to_facts(
        [[["产品", "2024", "2025"], ["液体乳", "75,000", "80,000"]]],
        item="main_business",
        dimension="product",
        page=88,
        year=2025,
        unit="CNY",
    )
    assert len(facts) == 1
    assert facts[0].value == Decimal("80000")


def test_main_business_table_rows_to_facts():
    tables = [
        [
            ["产品", "2025", "2024"],
            ["液体乳", "80,000", "75,000"],
            ["奶粉", "20,000", "18,000"],
            ["合计", "100,000", "93,000"],
        ]
    ]
    facts = rows_to_facts(
        tables,
        item="main_business",
        dimension="product",
        page=88,
        year=2025,
        unit="CNY",
    )
    assert [fact.label for fact in facts] == ["液体乳", "奶粉"]
    assert facts[0].value == Decimal("80000")
    assert all(fact.item == "main_business" for fact in facts)
    assert all(fact.page == 88 for fact in facts)


def test_dps_crosscheck_matches_closest_event():
    from turtlefw.types import Currency, DividendEvent

    events = [
        DividendEvent(fiscal_year=2025, event_id="a", dps=Decimal("1.20"), currency=Currency.CNY),
        DividendEvent(fiscal_year=2024, event_id="b", dps=Decimal("1.10"), currency=Currency.CNY),
    ]
    check = crosscheck_dps(Decimal("1.20"), events)
    assert check.status == "match"
    assert check.provider_dps == Decimal("1.20")
    unavailable = crosscheck_dps(Decimal("1.20"), events, fiscal_year=2026)
    assert unavailable.status == "unavailable"


def test_phase2_gate_allows_documented_not_applicable():
    gate = CoverageGate(
        {
            "accounts_receiv": "complete",
            "inventory": "complete",
            "contract_liab": "complete",
            "dps": "complete",
            "main_business": "complete",
            "capex_detail": "not_applicable",
        }
    )
    assert gate.phase2_ready()
    assert gate.missing() == ()


def test_phase2_gate_blocks_unaccepted_not_applicable():
    gate = CoverageGate(
        {
            "accounts_receiv": "not_applicable",
            "inventory": "complete",
            "contract_liab": "complete",
            "dps": "complete",
            "main_business": "complete",
            "capex_detail": "not_applicable",
        }
    )
    assert not gate.phase2_ready()
    assert gate.unaccepted_not_applicable() == ("accounts_receiv",)


def test_pdf_facts_hash_is_path_independent():
    from turtlefw.pdf.fact_hash import pdf_facts_hash

    a = pdf_facts_hash(
        {
            "document_facts": [
                {"id": "pdf:ar:1", "label": "accounts_receiv", "value": "1", "source_url": "/a.pdf"}
            ]
        }
    )
    b = pdf_facts_hash(
        {
            "document_facts": [
                {"id": "pdf:ar:1", "label": "accounts_receiv", "value": "1", "source_url": "/b.pdf"}
            ]
        }
    )
    assert a == b


def test_phase2_gate_blocks_missing_field():
    gate = CoverageGate(
        {
            "accounts_receiv": "complete",
            "inventory": "complete",
            "contract_liab": "complete",
            "dps": "complete",
            "main_business": "complete",
            "capex_detail": "missing",
        }
    )
    assert not gate.phase2_ready()
    assert gate.missing() == ("capex_detail",)


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
    row = FactRow(
        fact_id="pdf:row:test",
        item="main_business",
        dimension="product",
        label="液体乳",
        period="2025A",
        value=Decimal("80000"),
        unit="CNY",
        page=88,
    )
    target = write_reported_numbers(
        [],
        tmp_path / "rows.json",
        fact_rows=[row],
        year=2025,
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["fact_rows"][0]["label"] == "液体乳"
    assert payload["fact_rows"][0]["fact_hash"]
