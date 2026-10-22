from __future__ import annotations

import json
from pathlib import Path

import pytest

from turtlefw.site import build_site, collect_reports, qa_status


def _make_code(day_dir: Path, code: str, *, qa: str, name: str = "") -> None:
    code_dir = day_dir / code
    code_dir.mkdir(parents=True)
    (code_dir / "qa.json").write_text(
        f'{{"status":"{qa}","rows":[]}}', encoding="utf-8"
    )
    snapshot = code_dir / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text(
        f'{{"snapshot_id":"snap-{code}","numeric_coverage":"1.0"}}',
        encoding="utf-8",
    )
    (code_dir / "analysis_report.html").write_text(
        f"<html>{name or code}</html>", encoding="utf-8"
    )


def test_qa_status_uses_top_level_status() -> None:
    assert qa_status(Path("missing.json")) == "UNKNOWN"


def test_collect_reports_scans_code_directories(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-21"
    _make_code(day_dir, "600887.SH", qa="pass", name="伊利")
    _make_code(day_dir, "000858.SZ", qa="fail")
    reports = collect_reports(day_dir)
    assert [report.code for report in reports] == ["000858.SZ", "600887.SH"]
    assert reports[1].qa == "PASS"
    assert reports[1].numeric_coverage == "1.0"


def test_build_site_copies_reports_and_writes_health(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-21"
    _make_code(day_dir, "600887.SH", qa="pass", name="伊利")
    (day_dir / "status.json").write_text(
        '{"stocks":[{"code":"600887.SH","name":"伊利","rank":1,"status":"ok",'
        '"qa":"PASS","research":"off","numeric_coverage":"1.0"}]}',
        encoding="utf-8",
    )
    release = build_site(day_dir, tmp_path / "site")
    assert (release / "index.html").is_file()
    assert (release / "600887.SH.html").read_text(encoding="utf-8") == "<html>伊利</html>"
    health = (release / "health.txt").read_text(encoding="utf-8")
    assert "status=ok" in health
    assert "qa_pass=1" in health
    index = (release / "index.html").read_text(encoding="utf-8")
    assert "600887.SH" in index
    assert "伊利" in index


def test_build_site_publishes_candidate_rankings(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-21"
    _make_code(day_dir, "600887.SH", qa="pass", name="伊利")
    (day_dir / "ranking.csv").write_text("code,name\n600887.SH,伊利\n", encoding="utf-8")
    (day_dir / "ranking_deep.csv").write_text(
        "code,name\n600887.SH,伊利\n", encoding="utf-8"
    )
    release = build_site(day_dir, tmp_path / "site")
    assert (release / "ranking.csv").is_file()
    assert (release / "ranking_deep.csv").is_file()


def test_build_site_renders_candidate_pool_and_report_enrichment(
    tmp_path: Path,
) -> None:
    day_dir = tmp_path / "2026-10-21"
    _make_code(day_dir, "600887.SH", qa="pass", name="伊利")
    snapshot = day_dir / "600887.SH" / "snapshot"
    (snapshot / "metrics.json").write_text(
        '{"floor":{"display":"4.34"},"price":{"display":"12.44"},'
        '"premium":{"display":"186.85%"},"margin":{"display":"5.33%"}}',
        encoding="utf-8",
    )
    (snapshot / "inputs.json").write_text(
        '{"industry_name":"食品饮料"}', encoding="utf-8"
    )
    (snapshot / "research.json").write_text(
        '{"claims":[{"statement":"底价为 {{metric:floor}}。"}]}', encoding="utf-8"
    )
    (day_dir / "ranking.csv").write_text(
        "ts_code,name,channel,roe,margin\n"
        "600887.SH,伊利,main,18.0,5.33\n"
        "000858.SZ,五粮液,main,20.0,4.00\n",
        encoding="utf-8",
    )
    (day_dir / "ranking_deep.csv").write_text(
        "ts_code,name,verdict,margin\n600887.SH,伊利,通过,5.33\n",
        encoding="utf-8",
    )
    release = build_site(day_dir, tmp_path / "site")
    index = (release / "index.html").read_text(encoding="utf-8")
    assert "候选池 2" in index
    assert "食品饮料" in index
    assert "底价为 4.34" in index
    assert "600887.SH" in index and "000858.SZ" in index
    assert "5.33%" in index
    assert "只看深度" in index


def test_build_site_does_not_call_failed_status_a_qa_pass(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-22"
    _make_code(day_dir, "601877.SH", qa="pass", name="姝ｆ嘲鐢靛櫒")
    _make_code(day_dir, "600887.SH", qa="pass", name="浼婂埄")
    (day_dir / "status.json").write_text(
        json.dumps(
            {
                "stocks": [
                    {
                        "code": "601877.SH",
                        "rank": 1,
                        "status": "failed",
                        "qa": "PASS",
                        "error": "strict numeric gate",
                    },
                    {
                        "code": "600887.SH",
                        "rank": 2,
                        "status": "ok",
                        "qa": "PASS",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    release = build_site(day_dir, tmp_path / "site")

    health = (release / "health.txt").read_text(encoding="utf-8")
    assert "status=partial" in health
    assert "qa_pass=1" in health
    assert "qa_fail=1" in health
    index = (release / "index.html").read_text(encoding="utf-8")
    assert "FAILED" in index
    assert "strict numeric gate" in index


def test_build_site_archives_prior_dates(tmp_path: Path) -> None:
    site = tmp_path / "site"
    first = tmp_path / "2026-10-21"
    _make_code(first, "600887.SH", qa="pass", name="伊利")
    (first / "status.json").write_text(
        json.dumps({"date": "2026-10-21", "trade_date": "20261021", "stocks": []}),
        encoding="utf-8",
    )
    build_site(first, site)

    second = tmp_path / "2026-10-22"
    _make_code(second, "00700.HK", qa="pass", name="腾讯")
    (second / "status.json").write_text(
        json.dumps(
            {
                "date": "2026-10-22",
                "trade_date": "20261022",
                "stocks": [{"code": "00700.HK", "rank": 1, "qa": "PASS"}],
            }
        ),
        encoding="utf-8",
    )
    release = build_site(second, site)

    assert (release / "archive" / "2026-10-21" / "600887.SH.html").is_file()
    historical = (release / "day" / "2026-10-21" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "600887.SH" in historical
    assert "../../archive/2026-10-21/600887.SH.html" in historical
    assert "2026-10-22" in historical
    latest = (release / "index.html").read_text(encoding="utf-8")
    assert "2026-10-21" in latest
    assert "day/2026-10-21/index.html" in latest
    assert "2026-10-22" in latest
    assert "00700.HK" in latest
    assert "market-chip hk" in latest
    assert 'data-market-tab="A"' in latest
    assert 'data-market-tab="HK"' in latest
    assert 'data-market="HK"' in latest
    assert "days=2" in (release / "health.txt").read_text(encoding="utf-8")


def test_build_site_rejects_empty_day(tmp_path: Path) -> None:
    day_dir = tmp_path / "empty"
    day_dir.mkdir()
    with pytest.raises(ValueError, match="no reports"):
        build_site(day_dir, tmp_path / "site")
