from datetime import date
from decimal import Decimal

from turtlefw.cli import _governance
from turtlefw.data.protocol import StatementRow
from turtlefw.types import Currency, StockCode


class FakeProvider:
    def __init__(self) -> None:
        self.report_types: list[str] = []

    def statements(self, code, report_type="1"):
        self.report_types.append(report_type)
        if report_type != "6":
            raise AssertionError("governance must use the parent-company statement")
        return [
            StatementRow(
                code=str(code),
                period_end=date(2025, 12, 31),
                period_type="annual",
                statement="balance",
                item="money_cap",
                value=13_406_727_376.75,
                currency=Currency.CNY,
                source="test",
            )
        ]

    def pledge_ratio(self, code):
        return Decimal("1.0")

    def buyback_amount(self, code):
        return None


def test_governance_uses_parent_statement_and_never_consolidated_fallback():
    provider = FakeProvider()
    parent_cash, pledge, buyback = _governance(
        provider, StockCode.parse("600887.SH"), Currency.CNY
    )
    assert provider.report_types == ["6"]
    assert parent_cash == Decimal("13406727376.75")
    assert pledge == Decimal("1.0")
    assert buyback is None


class EmptyProvider(FakeProvider):
    def statements(self, code, report_type="1"):
        self.report_types.append(report_type)
        return []


def test_governance_leaves_parent_cash_unknown_when_parent_statement_is_absent():
    provider = EmptyProvider()
    parent_cash, _pledge, _buyback = _governance(
        provider, StockCode.parse("600941.SH"), Currency.CNY
    )
    assert provider.report_types == ["6"]
    assert parent_cash is None
