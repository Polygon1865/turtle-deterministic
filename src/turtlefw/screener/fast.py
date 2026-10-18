"""Stage-1 fast screen: market-wide coarse metrics from batch endpoints.

Instead of six calls per stock, this pulls every company's statements for the
last five fiscal years (15 calls), one indicator snapshot (1 call) and computes
R / GG / EV-EBITDA / FCF yield for the whole market in memory.

Payout is approximated with ``dv_ttm * pe_ttm / 100`` (dividend yield x PE),
which avoids a per-stock dividend call.
"""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from ..config import Settings
from ..metrics import returns
from ..types import StockCode

PERIODS = 5


def _periods(count: int = PERIODS) -> list[str]:
    year = pd.Timestamp.now().year - 1
    return [f"{year - i}1231" for i in range(count)]


def _indexed(frame: pd.DataFrame | None) -> pd.DataFrame | None:
    if frame is None or frame.empty:
        return None
    return frame.drop_duplicates("ts_code").set_index("ts_code")


def _col(frame: pd.DataFrame | None, name: str) -> pd.Series | None:
    if frame is None or name not in frame.columns:
        return None
    return pd.to_numeric(frame[name], errors="coerce")


def _fcf(income: pd.DataFrame | None, cash: pd.DataFrame | None) -> pd.Series | None:
    ocf = _col(cash, "n_cashflow_act")
    capex = _col(cash, "c_pay_acq_const_fiolta")
    if ocf is None or capex is None:
        return None
    return ocf - capex.abs()


def fast_screen(
    frame: pd.DataFrame,
    provider,
    settings: Settings,
    rf_pct: Decimal,
    limit: int = 50,
) -> pd.DataFrame:
    periods = _periods()
    income = {p: _indexed(provider.market_statements(p, "income")) for p in periods}
    balance = {p: _indexed(provider.market_statements(p, "balance")) for p in periods}
    cash = {p: _indexed(provider.market_statements(p, "cashflow")) for p in periods}
    quality = _indexed(provider.market_fina_indicator(periods[0]))

    latest = periods[0]
    inc = income[latest]
    if inc is None:
        return pd.DataFrame()

    out = pd.DataFrame(index=inc.index)
    out["net_income"] = _col(inc, "n_income_attr_p")
    out["revenue"] = _col(inc, "revenue")
    out["oper_profit"] = _col(inc, "operate_profit")
    out["fin_exp"] = _col(inc, "finance_exp")

    bs = balance[latest]
    cf = cash[latest]
    out["cash"] = _col(bs, "money_cap")
    out["equity"] = _col(bs, "total_hldr_eqy_exc_min_int")
    debt_parts = [
        series
        for column in ("st_borr", "lt_borr", "bond_payable", "non_cur_liab_due_1y")
        if (series := _col(bs, column)) is not None
    ]
    out["debt"] = (
        sum(debt_parts, start=pd.Series(0.0, index=out.index))
        if debt_parts
        else pd.Series(0.0, index=out.index)
    )
    out["da"] = _col(cf, "depr_fa_coga_dpba")
    out["ocf"] = _col(cf, "n_cashflow_act")
    out["capex"] = _col(cf, "c_pay_acq_const_fiolta")
    out["fcf"] = _fcf(inc, cf)
    prev_fcf = _fcf(income[periods[1]], cash[periods[1]])

    if quality is not None:
        out["roe"] = _col(quality, "roe_waa")
        out["gross_margin"] = _col(quality, "grossprofit_margin")
        out["debt_ratio"] = _col(quality, "debt_to_assets")

    merged = frame.set_index("ts_code").join(out, how="inner")
    merged = merged[merged["total_mv"].notna() & merged["pe_ttm"].notna()]

    mktcap = pd.to_numeric(merged["total_mv"], errors="coerce") * 10000
    payout_raw = (
        pd.to_numeric(merged["dv_ttm"], errors="coerce")
        * pd.to_numeric(merged["pe_ttm"], errors="coerce")
    )
    # dv_ttm x pe_ttm is an approximation; values outside (0, 100] mean the two
    # snapshots disagree, so the payout is unknown rather than clipped to 100.
    payout = payout_raw.where((payout_raw > 0) & (payout_raw <= 100))
    merged["payout"] = payout
    merged["payout_ok"] = payout.notna()
    ni = merged["net_income"]
    aa = (
        merged["fcf"].fillna(prev_fcf)
        if "fcf" in merged
        else pd.Series(float("nan"), index=merged.index)
    )
    if prev_fcf is not None and "fcf" in merged:
        aa = (merged["fcf"].fillna(0) + prev_fcf.reindex(merged.index).fillna(0)) / 2

    ii = float(settings.returns.threshold(Decimal("0"), StockCode.parse("600887")))
    merged["payout"] = payout
    merged["R%"] = ni * payout / 100 / mktcap * 100
    merged["GG%"] = aa * payout / 100 / mktcap * 100
    merged["II%"] = float(
        settings.returns.threshold(rf_pct, StockCode.parse("600887"))
    )
    merged["margin"] = merged["GG%"] - merged["II%"]
    ebitda = merged["oper_profit"].fillna(0) + merged["fin_exp"].fillna(0) + merged["da"].fillna(0)
    merged["EV/EBITDA"] = (mktcap + merged["debt"].fillna(0) - merged["cash"].fillna(0)) / ebitda.where(
        ebitda > 0
    )
    merged["FCF yield%"] = merged["fcf"] / mktcap * 100

    # Quality gates mirror Tier-2, but missing values do not drop the row.
    mask = pd.Series(True, index=merged.index)
    for column, threshold, op in (
        ("roe", settings.screening.min_roe, ">="),
        ("gross_margin", settings.screening.min_gross_margin, ">="),
        ("debt_ratio", settings.screening.max_debt_ratio, "<="),
    ):
        if column in merged.columns:
            values = merged[column]
            ok = values >= float(threshold) if op == ">=" else values <= float(threshold)
            # fail-closed: a missing quality metric is not evidence of quality
            mask &= values.notna() & ok
    merged = merged[mask]

    merged = merged.sort_values("margin", ascending=False)
    columns = [
        "name", "channel", "roe", "payout", "payout_ok", "R%", "GG%", "II%", "margin",
        "EV/EBITDA", "FCF yield%",
    ]
    available = [c for c in columns if c in merged.columns]
    result = merged.head(limit)[available].reset_index()
    return result
