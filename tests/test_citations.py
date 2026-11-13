from __future__ import annotations

import json
from pathlib import Path

import pytest

from turtlefw import citations
from turtlefw.qa import _citation_audit_check


def _research(day_dir: Path, code: str, urls: list[str]) -> None:
    path = day_dir / code / "snapshot" / "research.json"
    path.parent.mkdir(parents=True)
    payload = {
        "evidence": [
            {"id": f"ev-{index}", "url": url, "quote": "q", "source_type": "web"}
            for index, url in enumerate(urls)
        ]
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_check_url_rejects_non_http() -> None:
    result = citations.check_url("data:pack", fetcher=lambda url, timeout: 200)
    assert result.ok is False
    assert "http" in result.reason


def test_check_url_ok_and_not_found() -> None:
    ok = citations.check_url("https://example.com/a", fetcher=lambda url, timeout: 200)
    missing = citations.check_url("https://example.com/b", fetcher=lambda url, timeout: 404)
    assert ok.ok is True and ok.status == 200
    assert missing.ok is False and "404" in missing.reason


def test_check_url_handles_exception() -> None:
    def boom(url: str, timeout: float) -> int:
        raise TimeoutError("slow")

    result = citations.check_url("https://example.com", fetcher=boom)
    assert result.ok is False
    assert "请求失败" in result.reason


def test_audit_day_writes_cache_and_reuses_it(tmp_path: Path) -> None:
    _research(tmp_path, "000001.SZ", ["https://example.com/a"])
    calls: list[str] = []

    def fetcher(url: str, timeout: float) -> int:
        calls.append(url)
        return 200

    first = citations.audit_day(tmp_path, fetcher=fetcher)
    assert len(calls) == 1 and first[0].ok
    cache = json.loads((tmp_path / "citations.json").read_text(encoding="utf-8"))
    assert cache["urls"]["https://example.com/a"]["ok"] is True
    assert cache["urls"]["https://example.com/a"]["code"] == "000001.SZ"

    second = citations.audit_day(tmp_path, fetcher=fetcher)
    assert len(calls) == 1, "fresh cache must not re-fetch"
    assert second[0].cached is True


def test_audit_day_respects_limit(tmp_path: Path) -> None:
    _research(tmp_path, "000001.SZ", [f"https://example.com/{i}" for i in range(5)])
    calls: list[str] = []

    def fetcher(url: str, timeout: float) -> int:
        calls.append(url)
        return 200

    results = citations.audit_day(tmp_path, fetcher=fetcher, limit=2)
    assert len(calls) == 2
    assert len(results) == 2


def test_summarize_reports_failures() -> None:
    ok, detail = citations.summarize(
        [
            citations.CitationResult("https://a", True, 200, "HTTP 200"),
            citations.CitationResult("https://b", False, 404, "HTTP 404"),
        ]
    )
    assert ok is False
    assert "1/2" in detail


def test_citation_audit_row_missing_file_is_pass(tmp_path: Path) -> None:
    code_dir = tmp_path / "000001.SZ"
    code_dir.mkdir()
    ok, detail = _citation_audit_check(code_dir)
    assert ok is True
    assert "未运行" in detail


def test_citation_audit_row_flags_unreachable(tmp_path: Path) -> None:
    code_dir = tmp_path / "000001.SZ"
    code_dir.mkdir()
    (tmp_path / "citations.json").write_text(
        json.dumps(
            {
                "urls": {
                    "https://gone": {
                        "ok": False,
                        "status": 404,
                        "reason": "HTTP 404",
                        "code": "000001.SZ",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    ok, detail = _citation_audit_check(code_dir)
    assert ok is False
    assert "1/1" in detail


@pytest.mark.parametrize("url", ["ftp://x", ""])
def test_check_url_rejects_other_schemes(url: str) -> None:
    assert citations.check_url(url, fetcher=lambda u, t: 200).ok is False
