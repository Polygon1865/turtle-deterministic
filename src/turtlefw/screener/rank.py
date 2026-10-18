"""Coverage-aware cross-sectional ranking.

Two rules make this different from a naive percentile blend:

* a missing metric scores 0, never the best percentile;
* rows whose metric coverage is below ``min_coverage`` get no score at all,
  so they cannot enter the output list.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping

import pandas as pd

from ..config import ScreeningConfig

DIMENSIONS: dict[str, bool] = {
    "roe_waa": True,
    "fcf_yield": True,
    "penetration_r": True,
    "ev_ebitda": False,
    "floor_premium": False,
}


def percentile_scores(
    df: pd.DataFrame, dimensions: Mapping[str, bool] = DIMENSIONS
) -> pd.DataFrame:
    scores = pd.DataFrame(index=df.index)
    for column, higher_is_better in dimensions.items():
        if column not in df.columns:
            scores[column] = 0.0
            continue
        ranks = df[column].rank(pct=True)  # NaN stays NaN
        if not higher_is_better:
            ranks = 1.0 - ranks
        scores[column] = ranks.fillna(0.0)
    return scores


def coverage(
    df: pd.DataFrame, dimensions: Mapping[str, bool] = DIMENSIONS
) -> pd.Series:
    columns = [c for c in dimensions if c in df.columns]
    if not columns:
        return pd.Series(0.0, index=df.index)
    return df[columns].notna().mean(axis=1)


def rank(
    df: pd.DataFrame,
    cfg: ScreeningConfig,
    dimensions: Mapping[str, bool] = DIMENSIONS,
) -> pd.DataFrame:
    """Attach ``coverage`` and ``composite_score``; sort eligible rows first."""
    if df.empty:
        result = df.copy()
        result["coverage"] = pd.Series(dtype=float)
        result["composite_score"] = pd.Series(dtype=float)
        return result

    scores = percentile_scores(df, dimensions)
    weights: dict[str, float] = {k: float(v) for k, v in cfg.score_weights.items()}

    total = pd.Series(0.0, index=df.index)
    for column in scores.columns:
        total = total + scores[column] * weights.get(column, 0.0)

    cov = coverage(df, dimensions)
    result = df.copy()
    result["coverage"] = cov
    result["composite_score"] = total.where(cov >= cfg.min_coverage)

    eligible = result[result["composite_score"].notna()].sort_values(
        "composite_score", ascending=False
    )
    ineligible = result[result["composite_score"].isna()].sort_values(
        "coverage", ascending=False
    )
    return pd.concat([eligible, ineligible])


def to_decimal(value: object) -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))
