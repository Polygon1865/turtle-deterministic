from __future__ import annotations

import json
from pathlib import Path

import pytest

from turtlefw.site import build_site, collect_reports, qa_status


def _make_code(
    day_dir: Path,
    code: str,
    *,
    qa: str = "PASS",
    name: str = "",
    verdict: str = "",
    metrics: dict[str, object] | None = None,
    inputs: dict[str, object] | None = None,
    research: dict[str, object] | None = None,
) -> None:
    code_dir = day_dir / code
    code_dir.mkdir(parents=True, exist_ok=True)
    (code_dir / "qa.json").write_text(
        json.dumps({"status": qa.lower(), "rows": []}), encoding="utf-8"
    )
    snapshot = code_dir / "snapshot"
    snapshot.mkdir(exist_ok=True)
    (snapshot / "manifest.json").write_text(
        json.dumps({"snapshot_id": f"snap-{code}", "numeric_coverage": "1.0"}),
        encoding="utf-8",
    )
    if metrics is not None:
        (snapshot / "metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False), encoding="utf-8"
        )
    if inputs is not None:
        (snapshot / "inputs.json").write_text(
            json.dumps(inputs, ensure_ascii=False), encoding="utf-8"
        )
    if research is not None:
        (snapshot / "research.json").write_text(
            json.dumps(research, ensure_ascii=False), encoding="utf-8"
        )
    (code_dir / "analysis_report.html").write_text(
        '<html><body><a href="/">返回</a><div class="qr-verdict">'
        f"{verdict}</div><p>{name or code}</p></body></html>",
        encoding="utf-8",
    )
    if verdict:
        (code_dir / "analysis_report.md").write_text(
            f"# {code}\n\n**{verdict}** — 测试结论\n", encoding="utf-8"
        )


def _metrics(**values: str) -> dict[str, object]:
    return {key: {"display": value} for key, value in values.items()}


def _status(day_dir: Path, stocks: list[dict[str, object]], **extra: object) -> None:
    payload = {"stocks": stocks, **extra}
    (day_dir / "status.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
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


def test_build_site_writes_flat_page_layout(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-21"
    _make_code(
        day_dir,
        "600887.SH",
        name="伊利",
        verdict="观察",
        metrics=_metrics(
            floor="4.34", price="12.44", premium="186.85%", margin="5.33%"
        ),
    )
    _status(
        day_dir,
        [
            {
                "code": "600887.SH",
                "name": "伊利",
                "rank": 1,
                "status": "ok",
                "qa": "PASS",
                "research": "off",
                "numeric_coverage": "1.0",
            }
        ],
    )
    release = build_site(day_dir, tmp_path / "site", base_url="https://example.com")

    for relative in (
        "index.html",
        "screener.html",
        "method.html",
        "archive/index.html",
        "archive/2026-10-21/index.html",
        "report/600887.SH.html",
        "stock/600887.SH.html",
        "assets/site.css",
        "assets/site.js",
        "assets/favicon.svg",
        "health.txt",
    ):
        assert (release / relative).is_file(), relative

    # root only holds the three top-level pages: no per-stock orphan copies.
    assert sorted(path.name for path in release.glob("*.html")) == [
        "index.html",
        "method.html",
        "screener.html",
    ]

    home = (release / "index.html").read_text(encoding="utf-8")
    assert '<link rel="canonical" href="https://example.com/">' in home
    assert 'property="og:title"' in home
    assert 'rel="icon"' in home
    assert "<style" not in home
    assert "600887.SH" in home and "伊利" in home and "5.33%" in home
    assert home.count("<table") == 1
    assert "观察" in home

    health = (release / "health.txt").read_text(encoding="utf-8")
    assert "status=ok" in health
    assert "qa_pass=1" in health
    assert "days=1" in health


def test_screener_splits_a_share_and_hk(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-23"
    _make_code(day_dir, "600887.SH", name="伊利")
    _make_code(day_dir, "00700.HK", name="腾讯控股")
    (day_dir / "ranking.csv").write_text(
        "code,name,channel,R%,GG%,II%,margin,pe,pb\n"
        "600887.SH,伊利,main,3.10,5.33,3.80,1.53,18.2,4.1\n",
        encoding="utf-8",
    )
    (day_dir / "ranking_deep.csv").write_text(
        "code,name,verdict,margin\n600887.SH,伊利,观察,1.53\n", encoding="utf-8"
    )
    (day_dir / "ranking_hk.csv").write_text(
        "code,name,R%,GG%,II%,margin,pe,pb,payout\n"
        "00700.HK,腾讯控股,0.97,0.83,5.00,-4.17,18.2,4.1,19.42%\n",
        encoding="utf-8",
    )
    release = build_site(day_dir, tmp_path / "site")
    screener = (release / "screener.html").read_text(encoding="utf-8")

    assert 'data-market-panel="A"' in screener
    assert 'data-market-panel="HK"' in screener
    a_panel, hk_panel = screener.split('data-market-panel="HK"', 1)
    assert "600887.SH" in a_panel
    assert "00700.HK" not in a_panel
    assert "00700.HK" in hk_panel
    assert "安全边际" in screener
    assert "ranking_hk.csv" in screener
    assert "观察" in screener
    assert (release / "ranking.csv").is_file()
    assert (release / "archive" / "2026-10-23" / "ranking_hk.csv").is_file()


def test_failed_status_is_flagged_but_not_counted_as_pass(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-22"
    _make_code(day_dir, "601877.SH", name="正泰电器")
    _make_code(day_dir, "600887.SH", name="伊利")
    _status(
        day_dir,
        [
            {
                "code": "601877.SH",
                "rank": 1,
                "status": "failed",
                "qa": "PASS",
                "error": "strict numeric gate",
            },
            {"code": "600887.SH", "rank": 2, "status": "ok", "qa": "PASS"},
        ],
    )

    release = build_site(day_dir, tmp_path / "site")
    health = (release / "health.txt").read_text(encoding="utf-8")
    assert "status=partial" in health
    assert "qa_pass=1" in health
    assert "qa_fail=1" in health

    home = (release / "index.html").read_text(encoding="utf-8")
    assert "失败" in home
    assert "strict numeric gate" in home


def test_home_reports_llm_fallback_reason(tmp_path: Path) -> None:
    day_dir = tmp_path / "2026-10-26"
    _make_code(day_dir, "600729.SH", qa="pass", name="重百集团")
    _status(
        day_dir,
        [
            {
                "code": "600729.SH",
                "name": "重百集团",
                "rank": 1,
                "status": "ok",
                "qa": "PASS",
                "research": "fallback",
                "research_reason": "LLM 研究未采用（json_invalid），已回退确定性报告",
                "numeric_coverage": "1.0",
            }
        ],
        screen_source="tushare:hk_daily",
    )
    release = build_site(day_dir, tmp_path / "site")
    health = (release / "health.txt").read_text(encoding="utf-8")
    assert "llm_on=0" in health
    assert "llm_fallback=1" in health
    assert "llm_off=0" in health
    assert "screen_source=tushare:hk_daily" in health

    home = (release / "index.html").read_text(encoding="utf-8")
    assert "LLM 研究回退" in home
    assert "json_invalid" in home
    assert "未启用 LLM 研究" not in home


def test_archive_keeps_prior_days_and_links_them(tmp_path: Path) -> None:
    site = tmp_path / "site"
    first = tmp_path / "2026-10-21"
    _make_code(first, "600887.SH", name="伊利", verdict="观察")
    _status(first, [{"code": "600887.SH", "rank": 1, "status": "ok", "qa": "PASS"}])
    build_site(first, site)

    second = tmp_path / "2026-10-22"
    _make_code(second, "00700.HK", name="腾讯", verdict="排除")
    _status(second, [{"code": "00700.HK", "rank": 1, "status": "ok", "qa": "PASS"}])
    release = build_site(second, site)

    archived = release / "archive" / "2026-10-21" / "600887.SH.html"
    assert archived.is_file()
    assert 'href="../../archive/2026-10-21/index.html"' in archived.read_text(
        encoding="utf-8"
    )

    day_page = (release / "archive" / "2026-10-21" / "index.html").read_text(
        encoding="utf-8"
    )
    assert "600887.SH" in day_page
    assert 'href="600887.SH.html"' in day_page
    assert "全部存档" in day_page

    archive = (release / "archive" / "index.html").read_text(encoding="utf-8")
    assert "2026-10-21" in archive
    assert "2026-10-22" in archive
    assert 'href="2026-10-21/index.html"' in archive

    home = (release / "index.html").read_text(encoding="utf-8")
    assert "00700.HK" in home
    assert "相对上一数据日 2026-10-21" in home
    assert "days=2" in (release / "health.txt").read_text(encoding="utf-8")


def test_stock_page_collects_history(tmp_path: Path) -> None:
    site = tmp_path / "site"
    first = tmp_path / "2026-10-21"
    _make_code(first, "600887.SH", name="伊利", verdict="观察")
    _status(first, [{"code": "600887.SH", "rank": 1, "status": "ok", "qa": "PASS"}])
    build_site(first, site)

    second = tmp_path / "2026-10-22"
    _make_code(second, "600887.SH", name="伊利", verdict="排除")
    _status(second, [{"code": "600887.SH", "rank": 1, "status": "ok", "qa": "PASS"}])
    release = build_site(second, site)

    stock = (release / "stock" / "600887.SH.html").read_text(encoding="utf-8")
    assert "2026-10-21" in stock
    assert "2026-10-22" in stock
    assert 'href="../archive/2026-10-21/600887.SH.html"' in stock
    assert 'href="../report/600887.SH.html"' in stock

    report = (release / "report" / "600887.SH.html").read_text(encoding="utf-8")
    assert 'href="../stock/600887.SH.html"' in report


def test_stock_lede_uses_metrics_not_research_claims(tmp_path: Path) -> None:
    day = tmp_path / "2026-10-21"
    _make_code(
        day,
        "06862.HK",
        name="海底捞",
        verdict="观察",
        metrics=_metrics(
            r="4.23%",
            gg="7.64%",
            ii="5.00%",
            margin="2.64%",
            floor="1.85",
            price="8.45",
            premium="355.66%",
        ),
        inputs={"name": "海底捞", "industry_label": "餐饮 / Restaurants"},
        research={
            "evidence": [{"id": "e1", "url": "https://x.test", "quote": "q"}],
            "claims": [
                {
                    "claim_id": "D1.1",
                    "dimension": "D1",
                    "statement": "公司以物业管理及相关服务为主业",
                    "judgment": "positive",
                    "confidence": "high",
                    "evidence_ids": ["e1"],
                }
            ],
        },
    )
    release = build_site(day, tmp_path / "site")
    stock = (release / "stock" / "06862.HK.html").read_text(encoding="utf-8")
    assert "结论 观察" in stock
    assert "餐饮 / Restaurants" in stock
    assert "4.23%" in stock
    assert "物业管理" not in stock


def test_site_data_carries_history(tmp_path: Path) -> None:
    site = tmp_path / "site"
    first = tmp_path / "2026-10-21"
    _make_code(first, "600887.SH", name="伊利")
    build_site(first, site)

    second = tmp_path / "2026-10-22"
    _make_code(second, "00700.HK", name="腾讯")
    release = build_site(second, site)

    payload = json.loads((release / "site_data.json").read_text(encoding="utf-8"))
    assert payload["date"] == "2026-10-22"
    assert [item["date"] for item in payload["history"]] == ["2026-10-21"]


def test_build_site_rejects_empty_day(tmp_path: Path) -> None:
    day_dir = tmp_path / "empty"
    day_dir.mkdir()
    with pytest.raises(ValueError, match="no reports"):
        build_site(day_dir, tmp_path / "site")
