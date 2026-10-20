from dataclasses import replace
from decimal import Decimal

from turtlefw import demo
from turtlefw.config import load_settings
from turtlefw.data.protocol import StatementRow
from turtlefw.report.pack import render_data_pack
from turtlefw.types import Currency, Money


def render() -> str:
    return render_data_pack(
        demo.DEMO_CODE,
        demo.demo_rows(),
        demo.demo_dividends(),
        quote={"trade_date": "20261016", "close": 28.2},
        history=[
            {"trade_date": "20261016", "close": 28.2, "high": 30.0, "low": 27.0},
            {"trade_date": "20250101", "close": 20.0, "high": 22.0, "low": 19.0},
        ],
        market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
        shares=demo.DEMO_SHARES,
        rf_pct=demo.DEMO_RF,
        settings=load_settings(),
    )


class TestDataPack:
    def test_sections_present(self):
        text = render()
        for heading in (
            "# 数据包",
            "## 1. 关键指标",
            "## 2. 五年财务趋势",
            "## 3. 分红历史",
            "## 5. 估值指标",
            "## 6. 底价",
        ):
            assert heading in text

    def test_currency_and_snapshot(self):
        text = render()
        assert "CNY" in text
        assert "数据快照" in text

    def test_trend_table_has_five_years(self):
        text = render()
        assert "2020" in text and "2024" in text

    def test_working_capital_and_cash_conversion_rows(self):
        text = render()
        for label in ("应收账款", "存货", "合同负债", "预收款项", "预付款项", "OCF/净利润（%）"):
            assert label in text

    def test_holders_and_main_business_are_rendered(self):
        text = render_data_pack(
            demo.DEMO_CODE,
            demo.demo_rows(),
            demo.demo_dividends(),
            quote={"trade_date": "20261016", "close": 28.2},
            history=[{"trade_date": "20261016", "close": 28.2, "high": 30.0, "low": 27.0}],
            market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
            shares=demo.DEMO_SHARES,
            rf_pct=demo.DEMO_RF,
            settings=load_settings(),
            holders=[{"holder_name": "测试股东", "hold_amount": 1000, "hold_ratio": 1.5}],
            main_business=[{"bz_item": "测试业务", "bz_sales": 100, "bz_profit": 20}],
        )
        assert "前十大股东" in text
        assert "测试股东" in text
        assert "主营/分部" in text
        assert "测试业务" in text

    def test_pdf_accounts_receivable_fact_overrides_pack(self):
        rows = [
            replace(row, item="accounts_receiv")
            if row.statement == "balance" and row.item == "total_assets"
            else row
            for row in demo.demo_rows()
        ]
        text = render_data_pack(
            demo.DEMO_CODE,
            rows,
            demo.demo_dividends(),
            quote={"trade_date": "20261016", "close": 28.2},
            history=[{"trade_date": "20261016", "close": 28.2, "high": 30.0, "low": 27.0}],
            market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
            shares=demo.DEMO_SHARES,
            rf_pct=demo.DEMO_RF,
            settings=load_settings(),
            document_facts=[
                {
                    "id": "pdf:accounts_receiv:132",
                    "label": "accounts_receiv",
                    "value": "120500000000.00",
                    "page": "132",
                }
            ],
        )
        assert "120,500.00" in text

    def test_pdf_inventory_fact_overrides_pack(self):
        rows = [
            replace(row, item="inventory", value=Decimal("64628834000"))
            if row.statement == "balance" and row.item == "total_assets"
            else row
            for row in demo.demo_rows()
        ]
        text = render_data_pack(
            demo.DEMO_CODE,
            rows,
            demo.demo_dividends(),
            quote={"trade_date": "20261016", "close": 28.2},
            history=[{"trade_date": "20261016", "close": 28.2, "high": 30.0, "low": 27.0}],
            market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
            shares=demo.DEMO_SHARES,
            rf_pct=demo.DEMO_RF,
            settings=load_settings(),
            document_facts=[
                {
                    "id": "pdf:inventory:132",
                    "label": "inventory",
                    "value": "64628834000.00",
                    "page": "132",
                }
            ],
        )
        assert "64,628.83" in text

    def test_pdf_evidence_section_renders_dps(self):
        text = render_data_pack(
            demo.DEMO_CODE,
            demo.demo_rows(),
            demo.demo_dividends(),
            quote={"trade_date": "20261016", "close": 28.2},
            history=[{"trade_date": "20261016", "close": 28.2, "high": 30.0, "low": 27.0}],
            market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
            shares=demo.DEMO_SHARES,
            rf_pct=demo.DEMO_RF,
            settings=load_settings(),
            document_facts=[
                {
                    "id": "pdf:dps:12",
                    "label": "dps",
                    "value": "1.2345",
                    "unit": "CNY/股",
                    "page": "12",
                }
            ],
        )
        assert "## PDF 证据" in text
        assert "1.2345" in text

    def test_floor_methods_are_numbered(self):
        text = render()
        assert "## 6. 底价（" in text and "法）" in text

    def test_gg_includes_buyback(self):
        text = render_data_pack(
            demo.DEMO_CODE,
            demo.demo_rows(),
            demo.demo_dividends(),
            quote={"trade_date": "20261016", "close": 28.2},
            history=[
                {"trade_date": "20261016", "close": 28.2, "high": 30.0, "low": 27.0},
            ],
            market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
            shares=demo.DEMO_SHARES,
            rf_pct=demo.DEMO_RF,
            settings=load_settings(),
            buyback=Money(Decimal("1000000000"), Currency.CNY),
        )
        assert "| 精算回报率 GG | 5.60% |" in text

    def test_interim_section_when_available(self):
        from datetime import date

        rows = demo.demo_rows() + [
            StatementRow(
                code="600887.SH",
                period_end=date(2025, 6, 30),
                period_type="interim",
                statement="income",
                item="revenue",
                value=50_000_000_000,
                currency=Currency.CNY,
                source="test",
            )
        ]
        text = render_data_pack(
            demo.DEMO_CODE,
            rows,
            demo.demo_dividends(),
            quote={"trade_date": "20261016", "close": 28.2},
            history=[{"trade_date": "20261016", "close": 28.2, "high": 30.0, "low": 27.0}],
            market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
            shares=demo.DEMO_SHARES,
            rf_pct=demo.DEMO_RF,
            settings=load_settings(),
        )
        assert "### 2.1 最新中报/季报" in text
        assert "年化系数 ×2.00" in text
