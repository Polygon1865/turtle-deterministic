from pathlib import Path

from turtlefw.cli import build_parser
from turtlefw.data.tushare_provider import TushareProvider, set_refresh_market


def test_refresh_market_flag_sets_zero_ttl(tmp_path: Path):
    set_refresh_market(True)
    try:
        provider = TushareProvider("test-token", cache_dir=tmp_path)
        assert provider._cache.ttl_seconds == 0
    finally:
        set_refresh_market(False)


def test_default_provider_uses_seven_day_ttl(tmp_path: Path):
    provider = TushareProvider("test-token", cache_dir=tmp_path)
    assert provider._cache.ttl_seconds == 7 * 86400


def test_cli_accepts_global_refresh_market():
    args = build_parser().parse_args(["--refresh-market", "coverage", "600887"])
    assert args.refresh_market is True
    assert args.command == "coverage"
