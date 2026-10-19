import json
import os
import shutil
import tempfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from turtlefw import demo
from turtlefw.cleanroom import run
from turtlefw.config import load_settings
from turtlefw.metrics import statements
from turtlefw.report.snapshot import ReportInputs, freeze, load, render
from turtlefw.types import Currency


def _root() -> Path:
    path = Path(tempfile.gettempdir()) / f"turtle-cleanroom-test-{os.getpid()}"
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot(root: Path) -> None:
    inputs = ReportInputs(
        code="600887.SH",
        currency="CNY",
        as_of="2026-10-16",
        rows=demo.demo_rows(),
        dividends=demo.demo_dividends(),
        quote={"trade_date": "20261016", "close": 28.2},
        history=[],
        market_cap=str(demo.DEMO_MARKET_CAP),
        shares=str(demo.DEMO_SHARES),
        price="28.2",
        rf_pct=str(demo.DEMO_RF),
        rf_source="test",
    )
    freeze(inputs, load_settings(), root)


def _numbers(root: Path, multiplier: str = "1") -> Path:
    rows = demo.demo_rows()
    latest = max(r.period_end.year for r in rows if r.period_type == "annual")
    values = {
        "revenue": statements.revenue(rows).get(latest),
        "net_income": statements.net_income(rows).get(latest),
        "ocf": statements.annual_series(rows, "cashflow", "n_cashflow_act").get(latest),
        "capex": statements.annual_series(rows, "cashflow", "c_pay_acq_const_fiolta").get(latest),
        "equity": statements.equity(rows).get(latest),
        "total_assets": statements.annual_series(rows, "balance", "total_assets").get(latest),
    }
    items = [
        {"item": key, "value": str(value * Decimal(multiplier)), "page": "p.1"}
        for key, value in values.items()
        if value is not None
    ]
    path = root / "numbers.json"
    path.write_text(json.dumps({"items": items}), encoding="utf-8")
    return path


def test_cleanroom_matches_snapshot():
    root = _root()
    try:
        _snapshot(root)
        result = run(root, _numbers(root))
        assert result["status"] == "pass"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_cleanroom_flags_mismatch():
    root = _root()
    try:
        _snapshot(root)
        result = run(root, _numbers(root, "2"))
        assert result["status"] == "review"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_cleanroom_runs_independent_formula():
    root = _root()
    try:
        _snapshot(root)
        inputs, settings = load(root)
        metrics: dict[str, object] = {}
        render(inputs, settings, metrics_out=metrics)
        (root / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False), encoding="utf-8"
        )
        result = run(root, _numbers(root))
        independent = result["independent_metrics"]
        assert independent["formula"] == "owner_earnings.cash_bridge"
        assert "r" in independent
        assert "gg" in independent
        assert result["ledger_comparison"]["r"]["status"] == "pass"
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_cleanroom_parity_two_companies():
    for code, currency in (("600887.SH", Currency.CNY), ("00700.HK", Currency.HKD)):
        root = _root()
        try:
            rows = [replace(row, code=code, currency=currency) for row in demo.demo_rows()]
            dividends = [
                replace(event, currency=currency) for event in demo.demo_dividends()
            ]
            inputs = ReportInputs(
                code=code,
                currency=currency.value,
                as_of="2026-10-16",
                rows=rows,
                dividends=dividends,
                quote={"trade_date": "20261016", "close": 28.2},
                history=[],
                market_cap=str(demo.DEMO_MARKET_CAP),
                shares=str(demo.DEMO_SHARES),
                price="28.2",
                rf_pct=str(demo.DEMO_RF),
                rf_source="test",
            )
            freeze(inputs, load_settings(), root)
            loaded, settings = load(root)
            metrics: dict[str, object] = {}
            render(loaded, settings, metrics_out=metrics)
            (root / "metrics.json").write_text(
                json.dumps(metrics, ensure_ascii=False), encoding="utf-8"
            )
            result = run(root, _numbers(root))
            assert result["ledger_comparison"]["r"]["status"] == "pass"
            assert result["ledger_comparison"]["gg"]["status"] == "pass"
        finally:
            shutil.rmtree(root, ignore_errors=True)
