import json

from turtlefw import numeric_audit, qa
from turtlefw.facts import file_hash
from turtlefw.research import snapshot_audit


def setup_run(tmp_path, with_all=True):
    base = tmp_path / "600887.SH"
    base.mkdir(parents=True, exist_ok=True)
    (base / "run_state.json").write_text(
        json.dumps({"code": "600887.SH", "run_id": "x", "phase": "report"}),
        encoding="utf-8",
    )
    (base / "analysis_report.md").write_text("结论：买入 ｜ R 7.48%", encoding="utf-8")
    payload = {
        "modules": {
            "moat": {
                "judgment": "positive",
                "confidence": "high",
                "evidence": [
                    {"url": "https://x.test/a", "quote": "营收一百亿", "source_type": "web"}
                ],
                "notes": "",
            }
        },
        "discrepancies": [],
    }
    (base / "qualitative.json").write_text(json.dumps(payload), encoding="utf-8")
    (base / "metrics.json").write_text('{"r": "7.48"}', encoding="utf-8")
    audit = numeric_audit.audit(base / "analysis_report.md", [base / "metrics.json"])
    audit["sources"] = ["metrics.json"]
    (base / "numeric_audit.json").write_text(json.dumps(audit), encoding="utf-8")
    (base / "manifest.json").write_text(
        json.dumps(
            {
                "code": "600887.SH",
                "as_of": "2026-10-16",
                "currency": "CNY",
                "facts_hash": "0" * 64,
                "config_hash": "1" * 64,
                "numeric_coverage": str(audit["coverage"]),
                "numeric_status": str(audit["status"]),
                "numeric_unknown": audit["unknown"],
                "numeric_hash": file_hash(base / "numeric_audit.json"),
                "numeric_sources": ["metrics.json"],
            }
        ),
        encoding="utf-8",
    )
    if with_all:
        (base / "narrative.md").write_text("R 为 7.48%", encoding="utf-8")
    snapshot = base / "snapshot"
    snapshot.mkdir(exist_ok=True)
    (snapshot / "verdict.json").write_text(
        json.dumps({"verdict": "买入", "evidence_hash": "2" * 64}),
        encoding="utf-8",
    )
    return base


def test_all_pass(tmp_path):
    setup_run(tmp_path)
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert qa.failed(rows) == []


def test_missing_report_fails(tmp_path):
    base = setup_run(tmp_path)
    (base / "analysis_report.md").unlink()
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "report" in qa.failed(rows)


def test_verdict_record_must_match_report(tmp_path):
    base = setup_run(tmp_path)
    (base / "analysis_report.md").write_text(
        "结论：**排除** — 因子1A「看不懂」触发否决", encoding="utf-8"
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "verdict_record" in qa.failed(rows)


def test_verdict_record_requires_evidence_hash(tmp_path):
    base = setup_run(tmp_path)
    (base / "snapshot" / "verdict.json").write_text(
        json.dumps({"verdict": "买入"}), encoding="utf-8"
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "verdict_record" in qa.failed(rows)


def test_untraceable_narrative_fails(tmp_path):
    base = setup_run(tmp_path)
    (base / "narrative.md").write_text("R 为 9.99%", encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "narrative" in qa.failed(rows)


def test_research_fallback_rate_warns_above_ten_percent(tmp_path):
    base = setup_run(tmp_path)
    stocks = [
        {"code": f"60000{i}.SH", "research": "fallback" if i < 23 else "on"}
        for i in range(40)
    ]
    (tmp_path / "status.json").write_text(json.dumps({"stocks": stocks}), encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research_fallback_rate" in qa.warned(rows)
    assert qa.failed(rows) == []
    assert qa.payload("600887.SH", rows)["status"] == "warn"


def test_research_fallback_rate_passes_below_ten_percent(tmp_path):
    base = setup_run(tmp_path)
    stocks = [
        {"code": f"60000{i}.SH", "research": "fallback" if i < 2 else "on"}
        for i in range(40)
    ]
    (tmp_path / "status.json").write_text(json.dumps({"stocks": stocks}), encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research_fallback_rate" not in qa.warned(rows)
    detail = {name: text for name, _, text in rows}["research_fallback_rate"]
    assert "研究回退 2/40" in detail


def test_all_unknown_fails(tmp_path):
    base = setup_run(tmp_path)
    payload = {
        "modules": {
            "moat": {
                "judgment": "unknown",
                "confidence": "low",
                "evidence": [],
                "notes": "",
            }
        }
    }
    (base / "qualitative.json").write_text(json.dumps(payload), encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "unknown_ratio" in qa.failed(rows)


def test_numeric_coverage_fails_below_one(tmp_path):
    base = setup_run(tmp_path)
    manifest = json.loads((base / "manifest.json").read_text(encoding="utf-8"))
    manifest["numeric_coverage"] = "0.95"
    manifest["numeric_unknown"] = ["9.99"]
    (base / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "numeric_coverage" in qa.failed(rows)


def test_numeric_audit_hash_tamper_fails(tmp_path):
    base = setup_run(tmp_path)
    (base / "numeric_audit.json").write_text(
        (base / "numeric_audit.json").read_text(encoding="utf-8") + " ",
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "numeric_coverage" in qa.failed(rows)


def test_qa_json_artifact(tmp_path):
    base = setup_run(tmp_path)
    rows = qa.run_qa("600887.SH", root=tmp_path)
    target = qa.write_json("600887.SH", rows, root=tmp_path)
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["status"] == "pass"
    assert any(row["name"] == "numeric_coverage" for row in payload["rows"])
    assert target.parent == base


def test_research_provenance_tamper_fails(tmp_path):
    base = setup_run(tmp_path)
    research = base / "research.json"
    research.write_text('{"claims": []}', encoding="utf-8")
    provenance = {
        "provider": "dsh",
        "research_sha256": file_hash(research),
        "context_sha256": "",
    }
    (base / "research_provenance.json").write_text(
        json.dumps(provenance), encoding="utf-8"
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert ("research_provenance", "PASS",) in [(r[0], r[1]) for r in rows]
    research.write_text('{"claims": [], "tampered": true}', encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research_provenance" in qa.failed(rows)


def test_research_artifact_is_validated(tmp_path):
    base = setup_run(tmp_path)
    (base / "research.json").write_text(
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
                "params": [
                    {
                        "param_id": "d2.rating",
                        "label": "护城河评级",
                        "value": "neutral",
                        "dimension": "D2",
                        "evidence_ids": ["ev1"],
                    }
                ],
                "decisions": [
                    {
                        "decision_id": "g",
                        "metric_id": "g",
                        "selected": "1.15",
                        "candidates": ["0.85", "1.15", "1.50"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research" not in qa.failed(rows)
    assert any(name == "research" and status == "PASS" for name, status, _ in rows)


def test_research_bridge_mismatch_fails(tmp_path):
    base = setup_run(tmp_path)
    (base / "research.json").write_text(
        json.dumps(
            {
                "evidence": [
                    {"id": "ev1", "url": "https://example.com/a", "quote": "原文"}
                ],
                "claims": [
                    {
                        "claim_id": "D1.business_model",
                        "dimension": "D1",
                        "statement": "看不懂",
                        "judgment": "negative",
                        "confidence": "high",
                        "evidence_ids": ["ev1"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research_bridge" in qa.failed(rows)

    payload = json.loads((base / "qualitative.json").read_text(encoding="utf-8"))
    payload["source"] = "research_bridge"
    (base / "qualitative.json").write_text(json.dumps(payload), encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research_bridge" not in qa.failed(rows)


def test_research_bridge_accepts_complete_human_module(tmp_path):
    base = setup_run(tmp_path)
    (base / "research.json").write_text(
        json.dumps(
            {
                "evidence": [
                    {"id": "ev1", "url": "https://example.com/a", "quote": "原文"}
                ],
                "claims": [
                    {
                        "claim_id": "D2.1",
                        "dimension": "D2",
                        "statement": "护城河",
                        "judgment": "positive",
                        "confidence": "high",
                        "evidence_ids": ["ev1"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research_bridge" not in qa.failed(rows)


def test_research_audit_artifact_is_required(tmp_path):
    base = setup_run(tmp_path)
    (base / "research.json").write_text(
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
            }
        ),
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research_audit" in qa.failed(rows)

    (base / "metrics.json").write_text(
        json.dumps({"r": {"display": "7.48"}}), encoding="utf-8"
    )
    audit = snapshot_audit(base)
    (base / "research_audit.json").write_text(
        json.dumps(audit), encoding="utf-8"
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    assert "research_audit" not in qa.failed(rows)


def _research_payload(evidence, confidence="high"):
    return {
        "evidence": evidence,
        "claims": [
            {
                "claim_id": "D1.business_model",
                "dimension": "D1",
                "statement": "主营稳健",
                "judgment": "positive",
                "confidence": confidence,
                "evidence_ids": [item["id"] for item in evidence],
            }
        ],
    }


def test_research_grade_flags_high_claims_without_primary_source(tmp_path):
    base = setup_run(tmp_path)
    (base / "research.json").write_text(
        json.dumps(
            _research_payload(
                [{"id": "ev1", "source_type": "data", "quote": "数据包：主营空调"}]
            )
        ),
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    status = {name: state for name, state, _ in rows}
    assert status["research_grade"] == "warn"
    detail = next(detail for name, _, detail in rows if name == "research_grade")
    assert "无 A/B 来源" in detail


def test_research_grade_accepts_primary_source(tmp_path):
    base = setup_run(tmp_path)
    (base / "research.json").write_text(
        json.dumps(
            _research_payload(
                [
                    {
                        "id": "ev1",
                        "url": "https://www.cninfo.com.cn/new/disclosure/detail",
                        "quote": "公司主营空调",
                    }
                ]
            )
        ),
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    status = {name: state for name, state, _ in rows}
    assert status["research_grade"] == "PASS"


def test_research_grade_warns_when_all_evidence_is_data(tmp_path):
    base = setup_run(tmp_path)
    (base / "research.json").write_text(
        json.dumps(
            _research_payload(
                [{"id": "ev1", "source_type": "data", "quote": "数据包：主营空调"}],
                confidence="medium",
            )
        ),
        encoding="utf-8",
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    status = {name: state for name, state, _ in rows}
    assert status["research_grade"] == "warn"


def _write_metric_conflicts(base, payload):
    (base / "snapshot" / "metric_conflicts.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_metric_conflicts_row_warns_on_duplicate_metric(tmp_path):
    base = setup_run(tmp_path)
    _write_metric_conflicts(
        base,
        [
            {
                "id": "payout.2025",
                "kept": "87.78%",
                "dropped": "66.97%",
                "kept_rank": 3,
                "dropped_rank": 0,
            }
        ],
    )
    rows = qa.run_qa("600887.SH", root=tmp_path)
    status = {name: state for name, state, _ in rows}
    detail = {name: text for name, _, text in rows}
    assert status["metric_conflicts"] == "WARN"
    assert "payout.2025" in detail["metric_conflicts"]
    assert "rank=3" in detail["metric_conflicts"]
    assert "metric_conflicts" in qa.warned(rows)


def test_metric_conflicts_row_passes_without_file(tmp_path):
    setup_run(tmp_path)
    rows = qa.run_qa("600887.SH", root=tmp_path)
    status = {name: state for name, state, _ in rows}
    assert status["metric_conflicts"] == "PASS"


def test_metric_conflicts_row_fails_on_broken_json(tmp_path):
    base = setup_run(tmp_path)
    (base / "snapshot" / "metric_conflicts.json").write_text("{", encoding="utf-8")
    rows = qa.run_qa("600887.SH", root=tmp_path)
    status = {name: state for name, state, _ in rows}
    assert status["metric_conflicts"] == "FAIL"
    assert "metric_conflicts" in qa.failed(rows)


def _verdict_record(verdict, evidence_hash):
    return {
        "code": "600887.SH",
        "verdict": verdict,
        "reason": "test",
        "evidence_hash": evidence_hash,
    }


def _write_previous_day(root, date, record):
    snapshot = root / date / "600887.SH" / "snapshot"
    snapshot.mkdir(parents=True, exist_ok=True)
    (snapshot / "verdict.json").write_text(json.dumps(record), encoding="utf-8")


def test_verdict_drift_fails_when_hash_unchanged_but_verdict_moves(tmp_path):
    today = tmp_path / "2026-11-14"
    setup_run(today)
    _write_previous_day(
        tmp_path, "2026-11-13", _verdict_record("观察", "2" * 64)
    )
    rows = qa.run_qa("600887.SH", root=today)
    status = {name: state for name, state, _ in rows}
    detail = {name: text for name, _, text in rows}
    assert status["verdict_drift"] == "FAIL"
    assert "观察→买入" in detail["verdict_drift"]
    assert "证据哈希未变" in detail["verdict_drift"]


def test_verdict_drift_passes_when_hash_unchanged_and_verdict_same(tmp_path):
    today = tmp_path / "2026-11-14"
    setup_run(today)
    _write_previous_day(
        tmp_path,
        "2026-11-13",
        _verdict_record("买入", "2" * 64),
    )
    _replace_verdict(today / "600887.SH", "买入", "2" * 64)
    rows = qa.run_qa("600887.SH", root=today)
    status = {name: state for name, state, _ in rows}
    assert status["verdict_drift"] == "PASS"


def test_verdict_drift_warns_when_evidence_changed(tmp_path):
    today = tmp_path / "2026-11-14"
    setup_run(today)
    _write_previous_day(
        tmp_path,
        "2026-11-13",
        _verdict_record("买入", "3" * 64),
    )
    _replace_verdict(today / "600887.SH", "观察", "4" * 64)
    rows = qa.run_qa("600887.SH", root=today)
    status = {name: state for name, state, _ in rows}
    detail = {name: text for name, _, text in rows}
    assert status["verdict_drift"] == "WARN"
    assert "买入→观察" in detail["verdict_drift"]
    assert "verdict_drift" in qa.warned(rows)


def _replace_verdict(base, verdict, evidence_hash):
    (base / "snapshot" / "verdict.json").write_text(
        json.dumps(_verdict_record(verdict, evidence_hash)), encoding="utf-8"
    )
