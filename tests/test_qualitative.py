import json

import pytest

from turtlefw import demo
from turtlefw.config import load_settings
from turtlefw.factors.engine import FactorContext, final_verdict, run
from turtlefw.qualitative import Judgment, Qualitative, load, write_template
from turtlefw.types import Currency, Money, TurtleError


def write(tmp_path, payload):
    path = tmp_path / "q.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def module(judgment="positive", confidence="high", evidence=None, notes=""):
    return {
        "judgment": judgment,
        "confidence": confidence,
        "evidence": evidence if evidence is not None else [
            {"url": "https://example.com/a", "quote": "示例引文"}
        ],
        "notes": notes,
    }


class TestLoad:
    def test_template_roundtrip(self, tmp_path):
        path = write_template(tmp_path / "q.json")
        qualitative = load(path)
        assert set(qualitative.items) == {
            "moat", "management", "policy", "fraud", "understandability", "controller"
        }
        assert all(item.judgment == "unknown" for item in qualitative.items.values())

    def test_missing_evidence_downgrades(self, tmp_path):
        path = write(tmp_path, {"modules": {"moat": module(evidence=[])}})
        item = load(path).get("moat")
        assert item.judgment == "unknown"
        assert "降级" in item.notes

    def test_invalid_judgment(self, tmp_path):
        path = write(tmp_path, {"modules": {"moat": module(judgment="great")}})
        with pytest.raises(TurtleError):
            load(path)

    def test_invalid_url(self, tmp_path):
        path = write(
            tmp_path,
            {"modules": {"moat": module(evidence=[{"url": "ftp://x", "quote": "q"}])}},
        )
        with pytest.raises(TurtleError):
            load(path)


def context(qualitative=None) -> FactorContext:
    from turtlefw.metrics.valuation import build_valuation
    from decimal import Decimal

    snapshot = build_valuation(
        market_cap=demo.DEMO_MARKET_CAP, cash=Decimal("27000000000"),
        debt=Decimal("12000000000"), equity=Decimal("62000000000"),
        net_income=Decimal("8450000000"), revenue=Decimal("115800000000"),
        operate_profit=Decimal("10800000000"), finance_exp=Decimal("500000000"),
        da=Decimal("4400000000"), fcf=Decimal("11300000000"),
        goodwill=Decimal("2000000000"), total_assets=Decimal("120000000000"),
        dps=Decimal("1.3"), price=Decimal("28.3"),
    )
    return FactorContext(
        code=demo.DEMO_CODE, rows=demo.demo_rows(), dividends=demo.demo_dividends(),
        market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY), shares=demo.DEMO_SHARES,
        price=Decimal("28.3"), rf_pct=Decimal("1.8"), tax_pct=Decimal("0"),
        settings=load_settings(), snapshot=snapshot, closes=demo.demo_closes(),
        qualitative=qualitative,
    )


class TestEngineIntegration:
    def test_fraud_negative_vetoes_1a(self):
        qualitative = Qualitative(items={
            "fraud": Judgment("fraud", "negative", "high", (), "有处罚记录"),
        })
        results = run(context(qualitative))
        assert results["1A"].passed is False
        assert final_verdict(results)[0] == "排除"

    def test_management_negative_vetoes_1b(self):
        qualitative = Qualitative(items={
            "management": Judgment("management", "negative", "medium", (), "治理问题"),
        })
        results = run(context(qualitative))
        assert results["1B"].passed is False
        assert final_verdict(results)[1].startswith("因子1B")

    def test_positive_moat_is_informational(self):
        qualitative = Qualitative(items={
            "moat": Judgment("moat", "positive", "high", (), ""),
        })
        results = run(context(qualitative))
        check = {c.name: c for c in results["1B"].checks}["护城河与竞争格局"]
        assert check.status == "info"
