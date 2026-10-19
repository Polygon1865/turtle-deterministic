from decimal import Decimal
import hashlib

from turtlefw import demo
from turtlefw.cli import kpi_summary
from turtlefw.config import load_settings
from turtlefw.factors.engine import FactorContext, final_verdict, run
from turtlefw.metrics.valuation import build_valuation
from turtlefw.metrics import registry as metric_registry
from turtlefw.report.analysis import render_analysis
from turtlefw.types import Currency, Money


def make_context() -> tuple[FactorContext, dict]:
    settings = load_settings()
    snapshot = build_valuation(
        market_cap=demo.DEMO_MARKET_CAP,
        cash=Decimal("27000000000"),
        debt=Decimal("12000000000"),
        equity=Decimal("62000000000"),
        net_income=Decimal("8450000000"),
        revenue=Decimal("115800000000"),
        operate_profit=Decimal("10800000000"),
        finance_exp=Decimal("500000000"),
        da=Decimal("4400000000"),
        fcf=Decimal("11300000000"),
        goodwill=Decimal("2000000000"),
        total_assets=Decimal("120000000000"),
        dps=Decimal("1.3"),
        price=Decimal("28.3"),
    )
    ctx = FactorContext(
        code=demo.DEMO_CODE,
        rows=demo.demo_rows(),
        dividends=demo.demo_dividends(),
        market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
        shares=demo.DEMO_SHARES,
        price=Decimal("28.3"),
        rf_pct=Decimal("1.8"),
        tax_pct=Decimal("0"),
        settings=settings,
        snapshot=snapshot,
        closes=demo.demo_closes(),
    )
    return ctx, run(ctx)


def render() -> tuple[str, str]:
    ctx, results = make_context()
    text = render_analysis(
        ctx,
        results,
        settings=load_settings(),
        snapshot_id="test",
        rf_source="test",
    )
    return text, final_verdict(results)[0]


class TestAnalysisReport:
    def test_kpi_and_engine_match(self):
        ctx, results = make_context()
        items = dict(
            kpi_summary(
                demo.DEMO_CODE,
                demo.demo_rows(),
                demo.demo_dividends(),
                market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
                shares=demo.DEMO_SHARES,
                rf_pct=Decimal("1.8"),
                settings=load_settings(),
                closes=demo.demo_closes(),
                price=Decimal("28.3"),
            )
        )
        assert items["穿透回报率 R"] == dict(results["2"].metrics)["粗算回报率 R"]
        assert items["精算回报率 GG"] == dict(results["3"].metrics)["精算回报率 GG"]


class TestMetricRegistry:
    def test_golden_report_hash(self):
        text, verdict = render()
        assert verdict == "观察"
        assert hashlib.sha256(text.encode("utf-8")).hexdigest() == (
            "4ae2ea8c02cf5315acd435a173bf36e2b3d15a7546b1fc4075a4ae9587f0da7c"
        )

    def test_core_metric_ledger(self):
        ctx, results = make_context()
        registry = metric_registry.build(
            ctx, results, composite=Decimal("26.80"), premium=Decimal("5.60")
        )
        assert registry.display("r") == dict(results["2"].metrics)["粗算回报率 R"]
        assert registry.get("r").value == dict(results["2"].values)["r"]
        assert registry.get("gg").value == dict(results["3"].values)["gg"]
        assert registry.display("gg") == dict(results["3"].metrics)["精算回报率 GG"]
        assert registry.display("floor") == "26.80"
        assert registry.resolve("R={{metric:r}}").startswith("R=")
        assert registry.coverage(metric_registry.REQUIRED_FOR_REPORT) == "ok"
        assert registry.get("revenue.latest") is not None

    def test_verdict_and_position_are_consistent(self):
        text, verdict = render()
        assert "最终结论" in text
        if verdict == "观察":
            assert "| 仓位建议 | 观察仓位 |" in text
            assert "| 仓位建议 | 标准仓位 |" not in text
            assert "| 仓位建议 | 50% |" not in text

    def test_thesis_card_present(self):
        text, _ = render()
        assert "投资论点卡" in text
        assert "基本面止损条件" in text
        assert "事件监控清单" in text

    def test_unknown_list_is_dynamic(self):
        text, _ = render()
        assert "护城河与竞争格局" in text
        assert "护城河类型与竞争格局" not in text
        assert "未提供定性输入" in text

    def test_no_stale_disclaimer(self):
        text, _ = render()
        assert "未包含 LLM 定性判断" not in text
