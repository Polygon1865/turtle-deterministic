"""Citation audit (roadmap W5.2): every web evidence URL must still resolve.

The research layer cites URLs.  A 404, a removed article or a typo turns a claim
into an unsupported one, and nothing in the numeric audit notices because the
quote itself is present.  This module checks reachability, caches results for a
week so the daily run does not re-hit the same pages, and records the outcome in
``<day>/citations.json`` where QA can read it without doing network I/O.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlparse

TIMEOUT_SECONDS = 10.0
MAX_AGE_DAYS = 7
CACHE_VERSION = 1

Fetcher = Callable[[str, float], int]


@dataclass(frozen=True)
class CitationResult:
    url: str
    ok: bool
    status: int
    reason: str
    cached: bool = False

    def line(self) -> str:
        mark = "OK  " if self.ok else "FAIL"
        note = self.reason or (f"HTTP {self.status}" if self.status else "")
        suffix = "（缓存）" if self.cached else ""
        return f"{mark} {self.url} ｜ {note}{suffix}"


def _default_fetch(url: str, timeout: float) -> int:
    import requests

    response = requests.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        headers={"User-Agent": "turtle-framework-citation-audit/1.0"},
    )
    return int(response.status_code)


def check_url(
    url: str,
    *,
    fetcher: Fetcher | None = None,
    timeout: float = TIMEOUT_SECONDS,
) -> CitationResult:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return CitationResult(url=url, ok=False, status=0, reason="不是 http(s) URL")
    fetch = fetcher or _default_fetch
    try:
        status = fetch(url, timeout)
    except Exception as exc:  # noqa: BLE001 - network failures are the point
        return CitationResult(url=url, ok=False, status=0, reason=f"请求失败：{type(exc).__name__}")
    if 200 <= status < 400:
        return CitationResult(url=url, ok=True, status=status, reason=f"HTTP {status}")
    return CitationResult(url=url, ok=False, status=status, reason=f"HTTP {status}")


def _cache_path(day_dir: Path) -> Path:
    return day_dir / "citations.json"


def load_cache(day_dir: Path) -> dict[str, Any]:
    path = _cache_path(day_dir)
    if not path.is_file():
        return {"version": CACHE_VERSION, "urls": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return {"version": CACHE_VERSION, "urls": {}}
    if not isinstance(payload, dict) or not isinstance(payload.get("urls"), dict):
        return {"version": CACHE_VERSION, "urls": {}}
    payload.setdefault("version", CACHE_VERSION)
    return payload


def _is_fresh(entry: Mapping[str, Any], now: datetime, max_age_days: int) -> bool:
    stamp = entry.get("checked_at")
    if not isinstance(stamp, str):
        return False
    try:
        checked = datetime.fromisoformat(stamp)
    except ValueError:
        return False
    return now - checked <= timedelta(days=max_age_days)


def evidence_urls(research: Iterable[Mapping[str, Any]]) -> list[str]:
    urls: list[str] = []
    for item in research:
        url = str(item.get("url") or "").strip()
        if url.startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
    return urls


def audit_day(
    day_dir: Path,
    *,
    fetcher: Fetcher | None = None,
    timeout: float = TIMEOUT_SECONDS,
    max_age_days: int = MAX_AGE_DAYS,
    limit: int = 30,
) -> list[CitationResult]:
    """Audit every cited URL in ``<day>/<code>/snapshot/research.json``."""
    cache = load_cache(day_dir)
    urls_by_code: dict[str, list[str]] = {}
    for research_path in sorted(day_dir.glob("*/snapshot/research.json")):
        code = research_path.parent.parent.name
        try:
            payload = json.loads(research_path.read_text(encoding="utf-8-sig"))
        except ValueError:
            continue
        evidence = payload.get("evidence") if isinstance(payload, dict) else None
        if not isinstance(evidence, list):
            continue
        urls = evidence_urls(item for item in evidence if isinstance(item, dict))
        if urls:
            urls_by_code[code] = urls

    now = datetime.now()
    results: list[CitationResult] = []
    checked = 0
    for code, urls in urls_by_code.items():
        for url in urls:
            if checked >= limit:
                break
            entry = cache["urls"].get(url)
            if isinstance(entry, dict) and _is_fresh(entry, now, max_age_days):
                results.append(
                    CitationResult(
                        url=url,
                        ok=bool(entry.get("ok")),
                        status=int(entry.get("status") or 0),
                        reason=str(entry.get("reason") or ""),
                        cached=True,
                    )
                )
                cache["urls"][url]["code"] = code
                continue
            result = check_url(url, fetcher=fetcher, timeout=timeout)
            results.append(result)
            cache["urls"][url] = {
                "ok": result.ok,
                "status": result.status,
                "reason": result.reason,
                "checked_at": now.isoformat(timespec="seconds"),
                "code": code,
            }
            checked += 1
        if checked >= limit:
            break
    cache["checked_at"] = now.isoformat(timespec="seconds")
    cache["results"] = len(results)
    _cache_path(day_dir).write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return results


def summarize(results: Sequence[CitationResult]) -> tuple[bool, str]:
    if not results:
        return True, "没有可审计的 http(s) 引用"
    failed = [item for item in results if not item.ok]
    if failed:
        sample = "、".join(item.url for item in failed[:3])
        return False, f"{len(failed)}/{len(results)} 条引用不可达：{sample}"
    cached = sum(1 for item in results if item.cached)
    detail = f"{len(results)} 条引用全部可达"
    if cached:
        detail += f"（缓存 {cached}）"
    return True, detail
