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

    def test_floor_methods_are_numbered(self):
        text = render()
        assert "## 6. 底价（" in text and "法）" in text

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
