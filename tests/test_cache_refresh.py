from pathlib import Path

import pandas as pd

from turtlefw.cli import build_parser
from turtlefw.data.cache import FileCache
from turtlefw.data.tushare_provider import TushareProvider, set_refresh_market


def test_file_cache_get_any_ignores_ttl(tmp_path: Path):
    # The DSH sandbox blocks writes outside the workspace, and this repo keeps
    # scratch data under ./tmp; use that so the test exercises real file IO.
    root = Path(__file__).resolve().parents[1] / "tmp" / "pytest-cache-any"
    root.mkdir(parents=True, exist_ok=True)
    cache = FileCache(root, ttl_seconds=0)
    cache.put("key", {"rows": 1})
    assert cache.get("key") is None
    assert cache.get_any("key") == {"rows": 1}


def test_market_endpoint_falls_back_to_cached_snapshot(tmp_path: Path, monkeypatch):
    provider = TushareProvider("test-token", cache_dir=tmp_path)
    monkeypatch.setattr(provider._cache, "get", lambda key: None)
    monkeypatch.setattr(
        provider._cache,
        "get_any",
        lambda key: [{"ts_code": "00700.HK", "close": 300.0}],
    )
    provider._max_retries = 1

    class _Client:
        def hk_daily(self, **kwargs):
            raise RuntimeError("frequency limited")

    provider._client = lambda: _Client()  # type: ignore[assignment]
    frame = provider._call("hk_daily", trade_date="20261030")
    assert list(frame["ts_code"]) == ["00700.HK"]
    assert any("缓存快照" in issue.message for issue in provider.issues)


def test_refresh_market_flag_sets_zero_ttl(tmp_path: Path):
    set_refresh_market(True)
    try:
        provider = TushareProvider("test-token", cache_dir=tmp_path)
        assert provider._cache.ttl_seconds == 0
        # Financial statements are not daily data: they keep the 7-day tier so a
        # refresh-market run does not refetch ~1.7k HK indicators.
        assert provider._fund_cache.ttl_seconds == 7 * 86400
    finally:
        set_refresh_market(False)


def test_default_provider_uses_seven_day_ttl(tmp_path: Path):
    provider = TushareProvider("test-token", cache_dir=tmp_path)
    assert provider._cache.ttl_seconds == 7 * 86400


def test_cli_accepts_global_refresh_market():
    args = build_parser().parse_args(["--refresh-market", "coverage", "600887"])
    assert args.refresh_market is True
    assert args.command == "coverage"
