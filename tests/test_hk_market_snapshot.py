"""HK quote snapshot: trade-date assertion and stale-cache labelling (W1.2)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from turtlefw.data.tushare_provider import TushareProvider

CACHE = Path("tmp") / "cache-hk-snapshot"


def _provider() -> TushareProvider:
    return TushareProvider("test-token", cache_dir=CACHE, min_interval=0.0)


def test_wrong_trade_date_rows_are_dropped_and_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider()
    frame = pd.DataFrame(
        [
            {"ts_code": "00700.HK", "trade_date": "20261028", "close": 380.0},
            {"ts_code": "00700.HK", "trade_date": "20261029", "close": 381.0},
        ]
    )
    monkeypatch.setattr(provider, "_safe", lambda *args, **kwargs: frame)

    rows = provider.hk_market_snapshot("20261029", allow_yfinance=False)

    assert [row["trade_date"] for row in rows] == ["20261029"]
    messages = [issue.message for issue in provider.issues]
    assert any("丢弃 1 行非 20261029 交易日数据" in message for message in messages)


def test_matching_trade_date_rows_are_kept(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider()
    frame = pd.DataFrame(
        [{"ts_code": "00700.HK", "trade_date": "20261029", "close": 381.0}]
    )
    monkeypatch.setattr(provider, "_safe", lambda *args, **kwargs: frame)

    rows = provider.hk_market_snapshot("20261029", allow_yfinance=False)

    assert len(rows) == 1
    assert provider.hk_market_source == "tushare:hk_daily"
    assert provider.stale_endpoints == ()


def test_stale_cache_is_labelled_in_source(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider()
    provider._stale_endpoints.add("hk_daily")  # type: ignore[attr-defined]
    frame = pd.DataFrame(
        [{"ts_code": "00700.HK", "trade_date": "20261029", "close": 381.0}]
    )
    monkeypatch.setattr(provider, "_safe", lambda *args, **kwargs: frame)

    provider.hk_market_snapshot("20261029", allow_yfinance=False)

    assert provider.hk_market_source == "stale-cache:hk_daily"
    assert provider.stale_endpoints == ("hk_daily",)
