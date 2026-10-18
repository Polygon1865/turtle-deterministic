"""Tier-1 filters and the dual-channel split, as pure DataFrame functions."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from ..config import ScreeningConfig

_NAME_FILTER = r"^\*?ST|^PT|退市"


def apply_filters(df: pd.DataFrame, cfg: ScreeningConfig, *, today: date | None = None) -> pd.DataFrame:
    if df.empty:
        return df.copy()

    today = today or date.today()
    frame = df.copy()

    if "name" in frame.columns:
        frame = frame[~frame["name"].astype(str).str.contains(_NAME_FILTER, regex=True, na=False)]

    if "industry" in frame.columns and cfg.excluded_industries:
        frame = frame[~frame["industry"].astype(str).isin(cfg.excluded_industries)]

    if "list_date" in frame.columns:
        cutoff = (today - timedelta(days=cfg.min_listing_years * 365)).strftime("%Y%m%d")
        frame = frame[frame["list_date"].astype(str) <= cutoff]

    if "total_mv" in frame.columns:
        frame = frame[frame["total_mv"].notna()]
        frame = frame[frame["total_mv"] / 10000 >= float(cfg.min_market_cap_yi)]

    if "turnover_rate" in frame.columns:
        frame = frame[frame["turnover_rate"].notna()]
        frame = frame[frame["turnover_rate"] >= float(cfg.min_turnover_pct)]

    if "pb" in frame.columns:
        frame = frame[frame["pb"].notna()]
        frame = frame[(frame["pb"] > 0) & (frame["pb"] <= float(cfg.max_pb))]

    return frame


def split_channels(df: pd.DataFrame, cfg: ScreeningConfig) -> pd.DataFrame:
    """Main channel: profitable + dividend. Observation: missing PE, top N by cap."""
    if df.empty:
        result = df.copy()
        result["channel"] = pd.Series(dtype="object")
        return result

    pe = df["pe_ttm"] if "pe_ttm" in df.columns else pd.Series(float("nan"), index=df.index)
    main_mask = pe.notna() & (pe > 0) & (pe <= float(cfg.max_pe))
    obs_mask = pe.isna()

    main = df[main_mask].copy()
    if "dv_ttm" in main.columns:
        main = main[main["dv_ttm"].notna() & (main["dv_ttm"] > 0)]
    main["channel"] = "main"

    obs = df[obs_mask].copy()
    if "total_mv" in obs.columns:
        obs = obs.sort_values("total_mv", ascending=False)
    obs = obs.head(cfg.obs_channel_limit).copy()
    obs["channel"] = "observation"

    return pd.concat([main, obs], ignore_index=True)


def rank_main(df: pd.DataFrame, cfg: ScreeningConfig) -> pd.DataFrame:
    """Composite score 0.4*dv + 0.3/PE + 0.3/PB, normalised to the max."""
    if df.empty:
        return df.copy()

    main = df[df["channel"] == "main"].copy()
    obs = df[df["channel"] == "observation"].copy()

    if not main.empty:
        dv = main["dv_ttm"] if "dv_ttm" in main.columns else pd.Series(0.0, index=main.index)
        pe = main["pe_ttm"] if "pe_ttm" in main.columns else pd.Series(float("nan"), index=main.index)
        pb = main["pb"] if "pb" in main.columns else pd.Series(float("nan"), index=main.index)

        def _norm(series: pd.Series) -> pd.Series:
            peak = series.max()
            if peak is None or pd.isna(peak) or peak <= 0:
                return pd.Series(0.0, index=series.index)
            return series / peak

        main["tier1_score"] = (
            0.4 * _norm(dv) + 0.3 * _norm(1.0 / pe) + 0.3 * _norm(1.0 / pb)
        )
        main = main.sort_values("tier1_score", ascending=False).head(cfg.tier2_main_limit)

    obs["tier1_score"] = 0.0
    return pd.concat([main, obs], ignore_index=True)
