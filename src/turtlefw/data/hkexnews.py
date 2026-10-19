"""HKEXnews announcement search (buyback/disclosure evidence).

This is an evidence adapter, not a statement provider: it returns announcement
metadata and links; it never mutates StatementRow or computes numbers.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol

ACTIVE_STOCK_URL = "https://www.hkexnews.hk/ncms/script/eds/activestock_sehk_e.json"
TITLE_SEARCH_URL = "https://www1.hkexnews.hk/search/titleSearchServlet.do"
FILE_BASE = "https://www1.hkexnews.hk"


class HkexNewsError(Exception):
    pass


class Transport(Protocol):
    def get(self, url: str, params: Mapping[str, str] | None = None) -> Any: ...


class UrllibTransport:
    def get(self, url: str, params: Mapping[str, str] | None = None) -> Any:
        target = f"{url}?{urllib.parse.urlencode(params)}" if params else url
        request = urllib.request.Request(
            target,
            headers={
                "User-Agent": "turtle-deterministic/0.1 research@example.com",
                "Referer": "https://www1.hkexnews.hk/",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)


@dataclass(frozen=True, slots=True)
class Announcement:
    stock_code: str
    title: str
    release_date: str
    file_link: str
    news_id: str


def stock_id_map(payload: Any) -> dict[str, str]:
    if not isinstance(payload, list):
        raise HkexNewsError("invalid HKEX active stock payload")
    result: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("c") or "").strip()
        stock_id = str(item.get("i") or "").strip()
        if code and stock_id:
            result[code] = stock_id
    return result


def _release_date(raw: str) -> str:
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw.strip(), fmt).date().isoformat()
        except ValueError:
            continue
    return raw.strip()[:10]


def search_announcements(
    stock_id: str,
    *,
    from_date: str,
    to_date: str,
    title_keyword: str = "",
    transport: Transport | None = None,
) -> list[Announcement]:
    payload = (transport or UrllibTransport()).get(
        TITLE_SEARCH_URL,
        {
            "sortDir": "0",
            "sortByOptions": "DateTime",
            "category": "0",
            "market": "SEHK",
            "stockId": stock_id,
            "documentType": "-1",
            "fromDate": from_date,
            "toDate": to_date,
            "title": title_keyword,
            "searchType": "0",
            "rowRange": "100",
            "lang": "E",
        },
    )
    if not isinstance(payload, Mapping):
        raise HkexNewsError("invalid HKEXnews response")
    raw = payload.get("result") or "[]"
    rows = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(rows, list):
        raise HkexNewsError("invalid HKEXnews result")
    result: list[Announcement] = []
    for item in rows:
        if not isinstance(item, Mapping):
            continue
        title = str(item.get("TITLE") or "").strip()
        if not title:
            continue
        link = str(item.get("FILE_LINK") or "")
        if link and not link.startswith("http"):
            link = FILE_BASE + link
        result.append(
            Announcement(
                stock_code=str(item.get("STOCK_CODE") or ""),
                title=title,
                release_date=_release_date(str(item.get("DATE_TIME") or "")),
                file_link=link,
                news_id=str(item.get("NEWS_ID") or ""),
            )
        )
    return result


def is_buyback_title(title: str) -> bool:
    lowered = title.lower()
    return any(
        token in lowered
        for token in ("buyback", "repurchase", "回購", "回购")
    )


def buyback_evidence(
    announcements: list[Announcement],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in announcements:
        if not is_buyback_title(item.title):
            continue
        rows.append(
            {
                "id": f"hkexnews:{item.news_id or item.release_date}",
                "page": "",
                "section": "HKEXnews",
                "label": item.title,
                "value": None,
                "unit": "",
                "quote": f"HKEXnews {item.release_date}: {item.title}",
                "confidence": "high",
                "source_rank": 2,
                "source_url": item.file_link,
            }
        )
    return rows
