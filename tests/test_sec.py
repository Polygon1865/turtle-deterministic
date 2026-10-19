from decimal import Decimal

from turtlefw.data.sec import (
    annual_facts,
    compare_rows,
    evidence_facts,
    filing_evidence,
    statement_rows,
)
from turtlefw.types import StockCode


def _payload():
    return {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            {"form": "10-K", "fy": 2025, "val": 1000},
                            {"form": "10-K", "fy": 2024, "val": 900},
                            {"form": "10-Q", "fy": 2025, "val": 9999},
                        ]
                    }
                },
                "NetIncomeLoss": {
                    "units": {"USD": [{"form": "10-K", "fy": 2025, "val": 100}]}
                },
                "CommonStockDividendsPerShareDeclared": {
                    "units": {
                        "USD/shares": [{"form": "10-K", "fy": 2025, "val": 1.25}]
                    }
                },
                "CommonStockSharesOutstanding": {
                    "units": {
                        "shares": [{"form": "10-K", "fy": 2025, "val": 1000000}]
                    }
                },
            }
        }
    }


def test_annual_facts_filters_10k_and_fy():
    facts = annual_facts(_payload())
    assert facts["revenue"][2025] == Decimal("1000")
    assert facts["revenue"][2024] == Decimal("900")
    assert facts["net_income"][2025] == Decimal("100")


def test_compare_rows_reports_difference_without_mutation():
    rows = [
        {
            "period_type": "annual",
            "period_end": "2025-12-31",
            "item": "revenue",
            "value": "1005",
        },
        {
            "period_type": "annual",
            "period_end": "2025-12-31",
            "item": "net_income",
            "value": "80",
        },
    ]
    result = compare_rows(rows, annual_facts(_payload()))
    revenue = next(item for item in result if item["item"] == "revenue")
    assert revenue["status"] == "agree"
    income = next(item for item in result if item["item"] == "net_income")
    assert income["status"] == "review"
    assert rows[0]["value"] == "1005"


def test_statement_rows_from_sec_facts():
    rows = statement_rows(_payload(), StockCode.parse("AAPL.US"))
    revenue = next(
        row
        for row in rows
        if row.item == "revenue" and row.period_end.year == 2025
    )
    assert revenue.value == Decimal("1000")
    assert revenue.source == "sec"
    assert revenue.statement == "income"


def test_evidence_facts_are_addressable():
    facts = evidence_facts(_payload(), cik=320193)
    revenue = next(item for item in facts if item["id"] == "sec:revenue:2025")
    assert "1000" in str(revenue["quote"])
    assert revenue["source_rank"] == 2
    assert "CIK0000320193" in str(revenue["source_url"])
    dividend = next(item for item in facts if item["id"] == "sec:dividend_per_share:2025")
    assert dividend["unit"] == "USD/shares"
    shares = next(item for item in facts if item["id"] == "sec:shares_outstanding:2025")
    assert shares["unit"] == "shares"


def test_latest_10k_filing_evidence():
    payload = {
        "filings": {
            "recent": {
                "form": ["10-Q", "10-K", "10-K/A"],
                "filingDate": ["2025-08-01", "2025-11-01", "2026-01-10"],
                "accessionNumber": [
                    "0001-25-000001",
                    "0001-25-000002",
                    "0001-26-000003",
                ],
                "primaryDocument": ["q.htm", "k.htm", "ka.htm"],
            }
        }
    }
    facts = filing_evidence(payload, cik=320193)
    assert len(facts) == 1
    assert facts[0]["id"] == "sec:filing:0001-26-000003"
    assert "ka.htm" in str(facts[0]["source_url"])
