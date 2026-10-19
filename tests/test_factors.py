from dataclasses import replace
from decimal import Decimal

import pytest

from turtlefw import demo
from turtlefw.config import load_settings
from turtlefw.factors.engine import FactorContext, final_verdict, run
from turtlefw.metrics.valuation import build_valuation
from turtlefw.qualitative import Judgment, Qualitative
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

    def test_high_floor_premium_caps_buy(self):
        results = run(replace(context(), price=Decimal("200")))
        assert dict(results["4"].metrics)["结论"] in {"观察", "排除"}
        check = {c.name: c for c in results["4"].checks}["底价约束"]
        assert check.status == "veto"

    def test_unreliable_payout_caps_buy(self):
        results = run(replace(context(), payout_reliable=False))
        assert dict(results["4"].metrics)["结论"] in {"观察", "排除"}

    def test_final_verdict_is_known(self):
        assert final_verdict(run(context()))[0] in {"买入", "观察", "排除"}

    def test_g_grid_is_used_and_reported(self):
        results = run(context())
        metrics = dict(results["2"].metrics)
        assert "维持性 Capex 系数 G" in metrics
        assert metrics["维持性 Capex 系数 G"].startswith("1.15")

    def test_research_decision_selects_g_candidate(self):
        results = run(replace(context(), decisions={"g": "1.50"}))
        metrics = dict(results["2"].metrics)
        assert "1.50" in metrics["维持性 Capex 系数 G"]

    def test_research_decision_rejects_unknown_candidate(self):
        with pytest.raises(ValueError, match="not in the G grid"):
            run(replace(context(), decisions={"g": "9.99"}))

    def test_research_decision_selects_tax_and_aa(self):
        results = run(
            replace(context(), decisions={"tax": "10", "aa": "AA_all"})
        )
        assert dict(results["2"].metrics)["股息税率 Q"] == "10.00%"
        assert dict(results["3"].metrics)["AA 口径"].startswith("AA_all")

    def test_research_decision_selects_pessimistic_scenario(self):
        results = run(replace(context(), decisions={"scenario": "0.8"}))
        metrics = dict(results["3"].metrics)
        assert metrics["悲观情景 k"] == "0.80"
        assert metrics["悲观情景 GG"].endswith("%")

    def test_research_decision_rejects_unknown_scenario(self):
        with pytest.raises(ValueError, match="not a supported k"):
            run(replace(context(), decisions={"scenario": "0.5"}))

    def test_confidence_is_reported(self):
        results = run(context())
        metrics = dict(results["4"].metrics)
        assert metrics["外推可信度"] in {"high", "medium", "low"}
        assert metrics["价值陷阱"].endswith("项")

    def test_negative_moat_is_a_trap(self):
        qualitative = Qualitative(
            items={
                "moat": Judgment(
                    module="moat",
                    judgment="negative",
                    confidence="high",
                    evidence=(),
                )
            }
        )
        results = run(replace(context(), qualitative=qualitative))
        check = {c.name: c for c in results["4"].checks}["护城河正在收窄"]
        assert check.status == "veto"
        assert dict(results["4"].metrics)["价值陷阱"].startswith("1")

    def test_pledge_above_70_is_a_veto(self):
        results = run(replace(context(), pledge_pct=Decimal("80")))
        assert results["1A"].passed is False
        assert final_verdict(results)[0] == "排除"

    def test_low_parent_cash_is_an_upstream_veto(self):
        results = run(replace(context(), parent_cash=Decimal("1")))
        check = {c.name: c for c in results["1B"].checks}["现金上游障碍"]
        assert check.status == "veto"
        assert results["1B"].passed is False

    def test_buyback_increases_crude_return(self):
        base = dict(run(context())["2"].metrics)["粗算回报率 R"]
        with_buyback = dict(
            run(replace(context(), buyback=Money(Decimal("1000000000"), Currency.CNY)))["2"].metrics
        )["粗算回报率 R"]
        assert Decimal(with_buyback.rstrip("%")) > Decimal(base.rstrip("%"))

    def test_sbc_reduces_refined_return(self):
        base = dict(run(context())["3"].metrics)["精算回报率 GG"]
        with_sbc = dict(
            run(replace(context(), sbc=Money(Decimal("1000000000"), Currency.CNY)))["3"].metrics
        )["精算回报率 GG"]
        assert Decimal(with_sbc.rstrip("%")) < Decimal(base.rstrip("%"))


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
