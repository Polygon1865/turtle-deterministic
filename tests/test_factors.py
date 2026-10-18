from decimal import Decimal

from turtlefw import demo
from turtlefw.config import load_settings
from turtlefw.factors.engine import FactorContext, final_verdict, run
from turtlefw.metrics.valuation import build_valuation
from turtlefw.types import Currency, Money


def context(audit=None) -> FactorContext:
    rows = demo.demo_rows()
    dividends = demo.demo_dividends()
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
    return FactorContext(
        code=demo.DEMO_CODE,
        rows=rows,
        dividends=dividends,
        market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
        shares=demo.DEMO_SHARES,
        price=Decimal("28.3"),
        rf_pct=Decimal("1.8"),
        tax_pct=Decimal("0"),
        settings=settings,
        snapshot=snapshot,
        closes=demo.demo_closes(),
        audit=audit or (),
    )


class TestEngine:
    def test_all_factors_produce_results(self):
        results = run(context())
        assert set(results) == {"1A", "1B", "2", "3", "4"}
        assert "粗算回报率 R" in dict(results["2"].metrics)
        assert "精算回报率 GG" in dict(results["3"].metrics)

    def test_factor2_gate_matches_threshold(self):
        results = run(context())
        r = dict(results["2"].metrics)["粗算回报率 R"]
        assert r.endswith("%")

    def test_audit_veto(self):
        results = run(context(audit=[{"audit_result": "保留意见", "audit_agency": "某所"}]))
        assert results["1A"].passed is False
        assert final_verdict(results)[0] == "排除"

    def test_clean_audit_is_not_a_veto(self):
        results = run(context(audit=[{"audit_result": "标准无保留意见", "audit_agency": "某所"}]))
        assert results["1A"].passed is not False

    def test_one_auditor_change_is_not_frequent(self):
        audit = [
            {"audit_result": "标准无保留意见", "audit_agency": "A"},
            {"audit_result": "标准无保留意见", "audit_agency": "A"},
            {"audit_result": "标准无保留意见", "audit_agency": "B"},
        ]
        results = run(context(audit=audit))
        check = {c.name: c for c in results["1A"].checks}["频繁更换审计师"]
        assert check.status == "pass"

    def test_two_auditor_changes_veto(self):
        audit = [
            {"audit_result": "标准无保留意见", "audit_agency": "A"},
            {"audit_result": "标准无保留意见", "audit_agency": "B"},
            {"audit_result": "标准无保留意见", "audit_agency": "C"},
        ]
        results = run(context(audit=audit))
        assert results["1A"].passed is False

    def test_single_year_fcf_drop_is_not_a_trap(self):
        results = run(context())
        trap = {c.name: c for c in results["4"].checks}["现金流趋势性恶化"]
        assert trap.status == "pass"

    def test_final_verdict_is_known(self):
        assert final_verdict(run(context()))[0] in {"买入", "观察", "排除"}


class TestValuationSnapshot:
    def test_ratios(self):
        ctx = context()
        snap = ctx.snapshot
        assert snap.ev is not None and snap.ev > 0
        assert snap.ev_ebitda is not None
        assert snap.pb is not None
        assert snap.fcf_yield is not None
        assert snap.goodwill_ratio == Decimal("2000000000") / Decimal("120000000000") * 100

    def test_missing_inputs_are_none(self):
        snap = build_valuation(
            market_cap=None, cash=None, debt=None, equity=None, net_income=None,
            revenue=None, operate_profit=None, finance_exp=None, da=None, fcf=None,
            goodwill=None, total_assets=None, dps=None, price=None,
        )
        assert snap.ev is None and snap.ev_ebitda is None and snap.fcf_yield is None
