import json
from typing import Any, Mapping

from turtlefw.data.hkexnews import (
    buyback_evidence,
    is_buyback_title,
    search_announcements,
    stock_id_map,
)


class FakeTransport:
    def __init__(self, payload: Mapping[str, Any]):
        self.payload = payload

    def get(self, url: str, params: Mapping[str, str] | None = None) -> Any:
        return self.payload


def test_stock_id_map_and_buyback_evidence():
    mapping = stock_id_map([{"c": "00700", "i": 7609, "n": "TENCENT"}])
    assert mapping["00700"] == "7609"

    payload = {
        "result": json.dumps(
            [
                {
                    "STOCK_CODE": "00700",
                    "TITLE": "Next Day Disclosure Return - share buybacks",
                    "DATE_TIME": "09/04/2026 12:00",
                    "FILE_LINK": "/listedco/listconews/sehk/2026/0409/a.pdf",
                    "NEWS_ID": "12100102",
                },
                {
                    "STOCK_CODE": "00700",
                    "TITLE": "Annual Report",
                    "DATE_TIME": "08/04/2025 12:00",
                    "FILE_LINK": "/a.pdf",
                    "NEWS_ID": "x",
                },
            ]
        )
    }
    rows = search_announcements(
        "7609",
        from_date="20240101",
        to_date="20261231",
        transport=FakeTransport(payload),
    )
    assert rows[0].release_date == "2026-04-09"
    assert rows[0].file_link.startswith("https://www1.hkexnews.hk/")
    evidence = buyback_evidence(rows)
    assert len(evidence) == 1
    assert evidence[0]["id"] == "hkexnews:12100102"


def test_buyback_title_filter():
    assert is_buyback_title("Share Buyback Report")
    assert is_buyback_title("回購股份")
    assert not is_buyback_title("Annual Report")
