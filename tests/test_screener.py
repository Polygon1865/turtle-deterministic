from datetime import date

import numpy as np
import pandas as pd

from turtlefw.config import ScreeningConfig
from turtlefw.screener import tier1


def universe() -> pd.DataFrame:
    base = {
        "industry": "食品",
        "list_date": "20100101",
        "total_mv": 500000.0,  # 万元 -> 50 亿
        "turnover_rate": 1.0,
        "pb": 2.0,
        "pe_ttm": 15.0,
        "dv_ttm": 3.0,
    }

    def row(code: str, name: str, **overrides) -> dict:
        return {**base, "ts_code": code, "name": name, **overrides}

    return pd.DataFrame(
        [
            row("600001.SH", "正常公司"),
            row("600002.SH", "*ST某某"),
            row("600003.SH", "某银行", industry="银行"),
            row("600004.SH", "新股", list_date="20250101"),
            row("600005.SH", "小市值", total_mv=1000.0),
            row("600006.SH", "亏损公司", pe_ttm=np.nan, dv_ttm=0.0),
            row("600007.SH", "不分红", dv_ttm=0.0),
        ]
    )


class TestFilters:
    def test_removes_st_bank_young_and_small(self):
        filtered = tier1.apply_filters(universe(), ScreeningConfig(), today=date(2026, 1, 1))
        assert set(filtered["ts_code"]) == {"600001.SH", "600006.SH", "600007.SH"}

    def test_empty_input(self):
        empty = pd.DataFrame()
        assert tier1.apply_filters(empty, ScreeningConfig()).empty


class TestChannels:
    def test_main_needs_dividend_and_observation_takes_missing_pe(self):
        filtered = tier1.apply_filters(universe(), ScreeningConfig(), today=date(2026, 1, 1))
        channels = tier1.split_channels(filtered, ScreeningConfig())
        main = set(channels[channels["channel"] == "main"]["ts_code"])
        obs = set(channels[channels["channel"] == "observation"]["ts_code"])
        assert main == {"600001.SH"}
        assert obs == {"600006.SH"}

    def test_observation_is_capped(self):
        cfg = ScreeningConfig(obs_channel_limit=1)
        frame = pd.DataFrame(
            [
                {"ts_code": "A", "pe_ttm": np.nan, "total_mv": 10.0, "dv_ttm": 0.0},
                {"ts_code": "B", "pe_ttm": np.nan, "total_mv": 20.0, "dv_ttm": 0.0},
            ]
        )
        channels = tier1.split_channels(frame, cfg)
        assert list(channels["ts_code"]) == ["B"]


class TestRankMain:
    def test_scores_are_sorted_and_observation_kept(self):
        filtered = tier1.apply_filters(universe(), ScreeningConfig(), today=date(2026, 1, 1))
        channels = tier1.split_channels(filtered, ScreeningConfig())
        ranked = tier1.rank_main(channels, ScreeningConfig())
        assert set(ranked["channel"]) == {"main", "observation"}
        main_scores = ranked[ranked["channel"] == "main"]["tier1_score"].tolist()
        assert main_scores == sorted(main_scores, reverse=True)
