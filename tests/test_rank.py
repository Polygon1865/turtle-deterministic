import numpy as np
import pandas as pd

from turtlefw.config import ScreeningConfig
from turtlefw.screener.rank import coverage, percentile_scores, rank


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts_code": ["NODATA", "GOOD", "OK"],
            "roe_waa": [np.nan, 20.0, 10.0],
            "fcf_yield": [np.nan, 10.0, 5.0],
            "penetration_r": [np.nan, 8.0, 4.0],
            "ev_ebitda": [np.nan, 5.0, 10.0],
            "floor_premium": [np.nan, 0.0, 50.0],
        }
    )


class TestPercentileScores:
    def test_missing_scores_zero_not_best(self):
        scores = percentile_scores(frame())
        assert scores.loc[0].sum() == 0.0

    def test_lower_is_better_is_inverted(self):
        scores = percentile_scores(frame())
        # GOOD has the lowest EV/EBITDA, so it must score highest on that column
        assert scores.loc[1, "ev_ebitda"] > scores.loc[2, "ev_ebitda"]


class TestRank:
    def test_missing_data_row_is_excluded(self):
        cfg = ScreeningConfig(min_coverage=0.75)
        ranked = rank(frame(), cfg)
        assert ranked.loc[ranked["ts_code"] == "NODATA", "composite_score"].isna().all()
        assert coverage(frame()).loc[0] == 0.0

    def test_good_row_ranks_first(self):
        cfg = ScreeningConfig(min_coverage=0.5)
        ranked = rank(frame(), cfg)
        assert ranked.iloc[0]["ts_code"] == "GOOD"

    def test_ineligible_rows_go_last(self):
        cfg = ScreeningConfig(min_coverage=0.75)
        ranked = rank(frame(), cfg)
        assert ranked.iloc[-1]["ts_code"] == "NODATA"

    def test_empty_frame(self):
        cfg = ScreeningConfig()
        result = rank(pd.DataFrame(), cfg)
        assert result.empty
        assert "composite_score" in result.columns
