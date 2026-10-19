from decimal import Decimal

from turtlefw.data.sec import annual_facts, compare_rows, statement_rows
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
