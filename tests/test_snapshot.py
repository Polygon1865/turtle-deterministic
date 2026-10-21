import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from turtlefw import demo
from turtlefw.config import load_settings
from turtlefw.facts import (
    ReportManifest,
    config_payload,
    content_hash,
    file_hash,
    statement_payload,
    template_hash,
)
from turtlefw.pdf.fact_hash import pdf_facts_hash
from turtlefw.report.finalize import FinalizeError, finalize_research
from turtlefw.report.manifest import build_manifest
from turtlefw.report.pdf_facts import apply_document_facts
from turtlefw.report.snapshot import ReportInputs, freeze, load, render, verify_manifest


def _root() -> Path:
    path = Path(tempfile.gettempdir()) / f"turtle-snapshot-test-{os.getpid()}"
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _inputs() -> ReportInputs:
    return ReportInputs(
        code="600887.SH",
        currency="CNY",
        as_of="2026-10-16",
        rows=demo.demo_rows(),
        dividends=demo.demo_dividends(),
        quote={"trade_date": "20261016", "close": 28.2},
        history=[{"trade_date": "20261016", "close": 28.2, "high": 30.0, "low": 27.0}],
        market_cap=str(demo.DEMO_MARKET_CAP),
        shares=str(demo.DEMO_SHARES),
        price="28.2",
        rf_pct=str(demo.DEMO_RF),
        rf_source="test",
    )


def test_inputs_carry_pdf_facts_and_semantic_hash():
    root = _root()
    try:
        inputs = replace(
            _inputs(),
            document_facts=[
                {
                    "id": "pdf:accounts_receiv:132",
                    "label": "accounts_receiv",
                    "value": "40450097000.00",
                    "page": "132",
                    "fact_hash": "abc",
                }
            ],
            fact_rows=[
                {
                    "fact_id": "pdf:row:main_business",
                    "item": "main_business",
                    "label": "液体乳",
                    "value": "80000.00",
                    "page": 88,
                }
            ],
            dps_fact={"dps": "1.2345", "page": "12"},
        )
        settings = load_settings()
        freeze(inputs, settings, root)
        loaded, _ = load(root)
        assert loaded.document_facts[0]["id"] == "pdf:accounts_receiv:132"
        assert loaded.fact_rows[0]["label"] == "液体乳"
        assert loaded.dps_fact["dps"] == "1.2345"
        assert pdf_facts_hash(
            {
                "document_facts": loaded.document_facts,
                "fact_rows": loaded.fact_rows,
                "dps": loaded.dps_fact,
            }
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_metric_registry_points_to_pdf_fact():
    rows = [
        replace(row, item="accounts_receiv")
        if row.statement == "balance" and row.item == "total_assets"
        else row
        for row in demo.demo_rows()
    ]
    inputs = replace(
        _inputs(),
        rows=rows,
        document_facts=[
            {
                "id": "pdf:accounts_receiv:132",
                "label": "accounts_receiv",
                "value": "120500000000.00",
                "page": "132",
            }
        ],
    )
    metrics: dict[str, object] = {}
    render(inputs, load_settings(), metrics_out=metrics)
    point = metrics["accounts_receiv"]
    assert isinstance(point, dict)
    assert point["source_fact_ids"] == ["pdf:accounts_receiv:132"]


def test_report_shows_pdf_accounts_receivable_fact():
    inputs = replace(
        _inputs(),
        document_facts=[
            {
                "id": "pdf:accounts_receiv:132",
                "label": "accounts_receiv",
                "value": "123456789.00",
                "page": "132",
            }
        ],
    )
    markdown, _ = render(inputs, load_settings())
    assert "## PDF 证据" in markdown
    assert "123.46" in markdown


def test_metric_registry_points_to_pdf_balance_facts():
    rows = [
        replace(row, item="inventory", value=Decimal("64628834000"))
        if row.statement == "balance" and row.item == "total_assets"
        else row
        for row in demo.demo_rows()
    ]
    inputs = replace(
        _inputs(),
        rows=rows,
        document_facts=[
            {
                "id": "pdf:inventory:132",
                "label": "inventory",
                "value": "64628834000.00",
                "page": "132",
            }
        ],
    )
    metrics: dict[str, object] = {}
    render(inputs, load_settings(), metrics_out=metrics)
    point = metrics["inventory"]
    assert isinstance(point, dict)
    assert point["source_fact_ids"] == ["pdf:inventory:132"]


def test_dps_pdf_fact_reaches_report_and_metrics():
    fact = {
        "id": "pdf:dps:12",
        "label": "dps",
        "value": "1.2345",
        "unit": "CNY/股",
        "page": "12",
    }
    inputs = replace(
        _inputs(),
        document_facts=[fact],
        dps_fact={"dps": "1.2345", "currency": "CNY", "page": "12"},
    )
    metrics: dict[str, object] = {}
    markdown, _ = render(inputs, load_settings(), metrics_out=metrics)
    point = metrics["dps.pdf"]
    assert isinstance(point, dict)
    assert point["source_fact_ids"] == ["pdf:dps:12"]
    assert "PDF 证据" in markdown
    assert "1.2345" in markdown
    assert "DPS 核对" in markdown


def test_report_shows_main_business_fact_row():
    inputs = replace(
        _inputs(),
        fact_rows=[
            {
                "fact_id": "pdf:row:1",
                "item": "main_business",
                "label": "液体乳",
                "value": "80000.00",
                "page": 88,
            }
        ],
    )
    markdown, _ = render(inputs, load_settings())
    assert "main_business:液体乳" in markdown
    assert "0.08" in markdown


def test_metric_registry_points_to_main_business_fact_row():
    inputs = replace(
        _inputs(),
        fact_rows=[
            {
                "fact_id": "pdf:row:1",
                "item": "main_business",
                "label": "液体乳",
                "value": "80000.00",
                "period": "2025A",
                "page": 88,
            }
        ],
    )
    metrics: dict[str, object] = {}
    render(inputs, load_settings(), metrics_out=metrics)
    point = metrics["main_business.液体乳"]
    assert isinstance(point, dict)
    assert point["source_fact_ids"] == ["pdf:row:1"]


def test_metric_registry_points_to_capex_detail_fact():
    inputs = replace(
        _inputs(),
        fact_rows=[
            {
                "fact_id": "pdf:row:capex",
                "item": "capex_detail",
                "label": "设备购置",
                "value": "12000.00",
                "period": "2025A",
                "page": 99,
            }
        ],
    )
    metrics: dict[str, object] = {}
    render(inputs, load_settings(), metrics_out=metrics)
    point = metrics["capex_detail.设备购置"]
    assert isinstance(point, dict)
    assert point["source_fact_ids"] == ["pdf:row:capex"]


def test_report_contains_industry_template():
    markdown, _ = render(_inputs(), load_settings())
    assert "## 行业模板：食品饮料" in markdown
    assert "Peer 组" in markdown


def test_manifest_facts_hash_uses_effective_pdf_rows():
    rows = [
        replace(row, item="accounts_receiv")
        if row.statement == "balance" and row.item == "total_assets"
        else row
        for row in demo.demo_rows()
    ]
    fact = {
        "id": "pdf:accounts_receiv:132",
        "label": "accounts_receiv",
        "value": "120500000000.00",
        "page": "132",
    }
    inputs = replace(_inputs(), rows=rows, document_facts=[fact])
    manifest = build_manifest(inputs, load_settings(), _root())
    effective = apply_document_facts(list(rows), [fact])
    assert manifest.facts_hash == content_hash(statement_payload(effective))
    assert manifest.pdf_fact_hash_version == 1


def test_old_pdf_fact_hash_uses_file_fallback():
    root = _root()
    try:
        settings = load_settings()
        freeze(_inputs(), settings, root)
        reported = root / "reported_numbers.json"
        reported.write_text("{}", encoding="utf-8")
        inputs, _ = load(root)
        markdown, _ = render(inputs, settings, snapshot_dir=root)
        manifest = build_manifest(
            inputs,
            settings,
            root,
            report_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            pdf_fact_hash=file_hash(reported),
        )
        manifest = replace(manifest, pdf_fact_hash_version=0)
        errors = verify_manifest(inputs, settings, markdown, manifest, root)
        assert "pdf_fact_hash mismatch" not in errors
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_report_contains_peer_financials():
    inputs = replace(
        _inputs(),
        industry_peers=[
            {
                "name": "伊利股份",
                "code": "600887.SH",
                "revenue_cagr": "8.00%",
                "net_margin": "9.00%",
                "roe": "18.00%",
            }
        ],
    )
    markdown, _ = render(inputs, load_settings())
    assert "Peer 财务对比" in markdown
    assert "18.00%" in markdown


def test_snapshot_roundtrip_and_byte_identity():
    root = _root()
    try:
        settings = load_settings()
        freeze(_inputs(), settings, root)
        inputs, loaded_settings = load(root)
        a, _ = render(inputs, loaded_settings, snapshot_dir=root)
        b, _ = render(inputs, loaded_settings, snapshot_dir=root)
        assert a == b
        assert "数据截至：2026-10-16" in a
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_research_section_is_rendered():
    root = _root()
    try:
        research = {
            "evidence": [{"id": "ev1", "url": "https://example.com/a", "quote": "原文"}],
            "claims": [
                {
                    "claim_id": "D2.1",
                    "dimension": "D2",
                    "statement": "品牌护城河，R={{metric:r}}",
                    "judgment": "positive",
                    "confidence": "high",
                    "evidence_ids": ["ev1"],
                }
            ],
        }
        research_path = root / "research.json"
        research_path.write_text(json.dumps(research, ensure_ascii=False), encoding="utf-8")
        settings = load_settings()
        freeze(_inputs(), settings, root, research_source=research_path)
        inputs, loaded_settings = load(root)
        text, _ = render(inputs, loaded_settings, snapshot_dir=root)
        assert "D2.1" in text
        assert "{{metric:r}}" not in text
        assert "https://example.com/a" in text
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_manifest_verification():
    root = _root()
    try:
        settings = load_settings()
        freeze(_inputs(), settings, root)
        inputs, loaded_settings = load(root)
        markdown, _ = render(inputs, loaded_settings, snapshot_dir=root)
        manifest = ReportManifest(
            code=inputs.code,
            as_of=inputs.as_of,
            currency=inputs.currency,
            facts_hash=content_hash(statement_payload(inputs.rows)),
            config_hash=content_hash(config_payload(loaded_settings)),
            template_hash=template_hash(Path(__file__).parents[1] / "src/turtlefw/report/templates"),
            report_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        )
        assert verify_manifest(inputs, loaded_settings, markdown, manifest, root) == []
        bad = replace(manifest, report_hash="deadbeef")
        assert "report_hash mismatch" in verify_manifest(inputs, loaded_settings, markdown, bad, root)
        metrics = root / "metrics.json"
        metrics.write_text('{"r": "1.00"}', encoding="utf-8")
        with_metrics = replace(manifest, metrics_hash=file_hash(metrics))
        assert verify_manifest(inputs, loaded_settings, markdown, with_metrics, root) == []
        metrics.write_text('{"r": "2.00"}', encoding="utf-8")
        assert "metrics_hash mismatch" in verify_manifest(
            inputs, loaded_settings, markdown, with_metrics, root
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_finalize_attaches_research_without_mutating_old_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("TURTLE_OUTPUT_DIR", str(tmp_path / "out"))
    settings = load_settings()
    old = tmp_path / "snapshot"
    freeze(_inputs(), settings, old)
    research = tmp_path / "research.json"
    research.write_text(
        json.dumps(
            {
                "evidence": [
                    {"id": "ev1", "url": "https://example.com/a", "quote": "原文"}
                ],
                "claims": [
                    {
                        "claim_id": "D2.1",
                        "dimension": "D2",
                        "statement": "品牌护城河，R={{metric:r}}",
                        "judgment": "positive",
                        "confidence": "high",
                        "evidence_ids": ["ev1"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = tmp_path / "analysis_report.md"
    target = finalize_research(
        old,
        research,
        tmp_path / "final",
        report_path=report,
        min_claims=1,
        min_dimensions=1,
    )
    assert target.is_dir()
    assert (target / "research.json").is_file()
    assert (target / "research_audit.json").is_file()
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["research_audit_hash"]
    assert not (old / "research.json").exists()
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "D2.1" in text
    assert "**研究摘要**" not in text
    assert manifest["snapshot_id"] in text
    state_path = tmp_path / "out" / "600887.SH" / "run_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["snapshot_id"] == manifest["snapshot_id"]
    assert "snapshot" in state["artifacts"]
    assert "research_audit" in state["artifacts"]


def test_finalize_decision_rebuilds_data_pack(tmp_path, monkeypatch):
    monkeypatch.setenv("TURTLE_OUTPUT_DIR", str(tmp_path / "out"))
    settings = load_settings()
    old = tmp_path / "snapshot"
    freeze(_inputs(), settings, old)
    research = tmp_path / "research.json"
    research.write_text(
        json.dumps(
            {
                "evidence": [
                    {"id": "ev1", "url": "https://example.com/a", "quote": "原文"}
                ],
                "claims": [
                    {
                        "claim_id": "D2.1",
                        "dimension": "D2",
                        "statement": "护城河 R={{metric:r}}",
                        "judgment": "positive",
                        "confidence": "high",
                        "evidence_ids": ["ev1"],
                    }
                ],
                "decisions": [
                    {
                        "decision_id": "g",
                        "metric_id": "g",
                        "selected": "1.50",
                        "candidates": ["0.85", "1.15", "1.50"],
                        "evidence_ids": ["ev1"],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    target = finalize_research(
        old,
        research,
        tmp_path / "final",
        report_path=tmp_path / "report.md",
        min_claims=1,
        min_dimensions=1,
        allow_research_decisions=True,
    )
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    pack = (target / "data_pack.md").read_text(encoding="utf-8")
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert manifest["snapshot_id"] in pack
    assert "research decisions" in report


def test_snapshot_carries_extras_and_manifest_hash(tmp_path):
    settings = load_settings()
    extras = {
        "market": "A",
        "financial_indicators": [{"period_end": "2024-12-31", "roe": "20.5"}],
        "industry": {"level1": "食品饮料"},
        "sources": ["tushare:fina_indicator", "tushare:index_member_all"],
    }
    market = {
        "market": "A",
        "research": [{"report_date": "2026-08-20", "org": "示例证券"}],
        "sources": ["tushare:report_rc"],
        "missing": ["news"],
    }
    inputs = replace(
        _inputs(),
        fundamental_extras=extras,
        industry_name="食品饮料",
        market_extras=market,
        industry_peers=[
            {
                "code": "600519.SH",
                "name": "贵州茅台",
                "revenue_cagr_pct": "12.29",
            }
        ],
    )
    freeze(inputs, settings, tmp_path)
    loaded, _ = load(tmp_path)
    assert loaded.fundamental_extras == extras
    assert loaded.industry_name == "食品饮料"
    assert loaded.market_extras == market
    assert loaded.industry_peers == inputs.industry_peers

    manifest = build_manifest(inputs, settings, tmp_path)
    assert manifest.extras_hash == content_hash(extras)
    assert manifest.market_hash == content_hash(market)
    assert manifest.peers_hash == content_hash(inputs.industry_peers)
    no_peers = build_manifest(replace(inputs, industry_peers=[]), settings, tmp_path)
    assert no_peers.snapshot_id != manifest.snapshot_id
    assert verify_manifest(inputs, settings, "", manifest, tmp_path) == []
    bad = replace(manifest, extras_hash="bad")
    assert "extras_hash mismatch" in verify_manifest(
        inputs, settings, "", bad, tmp_path
    )
    bad_market = replace(manifest, market_hash="bad")
    assert "market_hash mismatch" in verify_manifest(
        inputs, settings, "", bad_market, tmp_path
    )
    bad_peers = replace(manifest, peers_hash="bad")
    assert "peers_hash mismatch" in verify_manifest(
        inputs, settings, "", bad_peers, tmp_path
    )


def test_finalize_refuses_existing_target(tmp_path):
    settings = load_settings()
    old = tmp_path / "snapshot"
    freeze(_inputs(), settings, old)
    research = tmp_path / "research.json"
    research.write_text("{}", encoding="utf-8")
    target = tmp_path / "final"
    target.mkdir()
    try:
        finalize_research(old, research, target)
    except FinalizeError:
        pass
    else:
        raise AssertionError("expected FinalizeError")
