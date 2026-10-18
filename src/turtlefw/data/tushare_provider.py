"""Tushare Pro provider.

Design notes:

* Values are never scaled here; the store keeps the reporting currency base unit.
* Every call goes through a content-addressed cache keyed on endpoint + params + schema.
* Failures are recorded as :class:`FetchIssue` and surfaced in the report instead of
  being silently swallowed.
"""

from __future__ import annotations

import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from ..types import Currency, DividendEvent, FetchIssue, Market, StockCode
from .cache import FileCache
from .normalize import (
    dividend_events,
    hk_dividend_events,
    rows_from_hk_line_items,
    rows_from_wide,
)
from .protocol import ProviderError, StatementRow
from .tushare_maps import (
    CN_BALANCE_FIELDS,
    CN_BALANCE_MAP,
    CN_CASHFLOW_FIELDS,
    CN_CASHFLOW_MAP,
    CN_INCOME_FIELDS,
    CN_INCOME_MAP,
    HK_BALANCE_MAP,
    HK_CASHFLOW_MAP,
    HK_INCOME_MAP,
    HK_LINE_ITEM_FIELDS,
)

INCOME_FIELDS = f"ts_code,end_date,ann_date,report_type,{CN_INCOME_FIELDS}"
BALANCE_FIELDS = f"ts_code,end_date,ann_date,report_type,{CN_BALANCE_FIELDS}"
CASHFLOW_FIELDS = f"ts_code,end_date,ann_date,report_type,{CN_CASHFLOW_FIELDS}"
DIVIDEND_FIELDS = "ts_code,end_date,ann_date,cash_div_tax,base_share,div_proc"
HK_DIVIDEND_FIELDS = "ts_code,end_date,dps_hkd,divi_ratio"
DAILY_BASIC_FIELDS = (
    "ts_code,trade_date,close,pe_ttm,pb,total_mv,circ_mv,dv_ttm,turnover_rate,total_share"
)
STOCK_BASIC_FIELDS = "ts_code,name,industry,area,market,exchange,list_date"


class TushareProvider:
    name = "tushare"
    SCHEMA_VERSION = "turtle-1"

    def __init__(
        self,
        token: str,
        *,
        cache_dir: Path | None = None,
        ttl_seconds: int = 7 * 86400,
        min_interval: float = 0.35,
        max_retries: int = 3,
    ) -> None:
        if not token:
            raise ProviderError("TUSHARE_TOKEN is empty")
        import tushare as ts  # imported lazily so unit tests need no token

        self._ts = ts
        self._pro = self._new_client(token)
        self._cache = FileCache(cache_dir or Path.cwd() / "output" / ".cache", ttl_seconds)
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._last_call = 0.0
        self._issues: list[FetchIssue] = []
        self._hk_daily: dict[str, list[dict]] = {}
        self._hk_failed: set[str] = set()

    def _new_client(self, token: str):
        try:
            return self._ts.pro_api(token=token, timeout=30)
        except TypeError:  # older tushare releases only accept positional args
            self._ts.set_token(token)
            return self._ts.pro_api(timeout=30)

    # -- plumbing ----------------------------------------------------------
    @property
    def issues(self) -> tuple[FetchIssue, ...]:
        return tuple(self._issues)

    def _throttle(self) -> None:
        wait = self._min_interval - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        self._last_call = time.monotonic()

    def _call(self, endpoint: str, **params: Any) -> pd.DataFrame:
        key = FileCache.make_key(endpoint, params, self.SCHEMA_VERSION)
        cached = self._cache.get(key)
        if cached is not None:
            return pd.DataFrame(cached)

        last_error: Exception | None = None
        for attempt in range(1, self._max_retries + 1):
            self._throttle()
            try:
                frame = getattr(self._pro, endpoint)(**params)
                if frame is None:
                    frame = pd.DataFrame()
                self._cache.put(key, frame.to_dict("records"))
                return frame
            except Exception as exc:  # noqa: BLE001 - provider raises vendor exceptions
                last_error = exc
                message = str(exc)
                if "没有接口" in message or "权限" in message:
                    raise ProviderError(f"{endpoint} permission denied: {message}") from exc
                if "频率超限" in message:
                    # e.g. hk_daily is limited to once per hour; retrying is futile.
                    raise ProviderError(f"{endpoint} rate limited: {message}") from exc
                if attempt < self._max_retries:
                    time.sleep(min(2.0 * attempt, 8.0))
        raise ProviderError(
            f"{endpoint} failed after {self._max_retries} attempts: {last_error}"
        )

    def _safe(self, endpoint: str, **params: Any) -> pd.DataFrame:
        try:
            return self._call(endpoint, **params)
        except ProviderError as exc:
            self._issues.append(
                FetchIssue(
                    endpoint=endpoint,
                    code=str(params.get("ts_code", "*")),
                    message=str(exc),
                    retryable=True,
                )
            )
            return pd.DataFrame()

    @staticmethod
    def _default_currency(code: StockCode) -> Currency:
        if code.market is Market.HK:
            return Currency.HKD
        if code.market is Market.US:
            return Currency.USD
        return Currency.CNY

    # -- reference data ----------------------------------------------------
    def stock_basic(self, code: StockCode | None = None) -> list[dict]:
        params: dict[str, Any] = {"fields": STOCK_BASIC_FIELDS}
        if code is not None:
            params["ts_code"] = str(code)
        return self._safe("stock_basic", **params).to_dict("records")

    def _hk_history(self, code: StockCode, years: int = 10) -> list[dict]:
        """Fetch HK daily bars once per session.

        ``hk_daily`` is limited to 1 request/minute, and both the quote and the
        price history need it, so a single 10-year pull serves both.
        """
        key = str(code)
        if key in self._hk_daily:
            return self._hk_daily[key]
        if key in self._hk_failed:
            return []
        end = date.today()
        start = end - timedelta(days=365 * max(years, 10))
        frame = self._safe(
            "hk_daily",
            ts_code=key,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            fields="ts_code,trade_date,close,high,low,vol",
        )
        if frame.empty:
            self._hk_failed.add(key)
            return []
        records = frame.to_dict("records")
        for record in records:
            record["trade_date"] = str(record["trade_date"])
        records.sort(key=lambda r: r["trade_date"])
        self._hk_daily[key] = records
        return records

    def daily_basic(
        self, code: StockCode | None = None, trade_date: str | None = None
    ) -> list[dict]:
        if code is not None and code.market is Market.HK:
            history = self._hk_history(code, years=1)
            return [history[-1]] if history else []

        params: dict[str, Any] = {"fields": DAILY_BASIC_FIELDS}
        if code is not None:
            params["ts_code"] = str(code)
        if trade_date is not None:
            params["trade_date"] = trade_date
        return self._safe("daily_basic", **params).to_dict("records")

    def latest_trade_date(self) -> str:
        today = date.today()
        frame = self._safe(
            "trade_cal",
            exchange="SSE",
            start_date=(today - timedelta(days=10)).strftime("%Y%m%d"),
            end_date=today.strftime("%Y%m%d"),
            fields="cal_date,is_open",
        )
        if frame.empty:
            return today.strftime("%Y%m%d")
        open_days = frame[frame["is_open"] == 1].sort_values("cal_date", ascending=False)
        return str(open_days.iloc[0]["cal_date"]) if not open_days.empty else today.strftime("%Y%m%d")

    # -- statements --------------------------------------------------------
    def statements(
        self,
        code: StockCode,
        *,
        report_type: str = "1",
        currency: Currency | None = None,
        years: int = 6,
    ) -> list[StatementRow]:
        unit = currency or self._default_currency(code)
        start = date.today() - timedelta(days=365 * (years + 1))
        start_str = start.strftime("%Y%m%d")

        if code.is_a_share:
            rows: list[StatementRow] = []
            rows += rows_from_wide(
                self._safe(
                    "income",
                    ts_code=str(code),
                    report_type=report_type,
                    start_date=start_str,
                    fields=INCOME_FIELDS,
                ),
                statement="income",
                item_map=CN_INCOME_MAP,
                currency=unit,
            )
            rows += rows_from_wide(
                self._safe(
                    "balancesheet",
                    ts_code=str(code),
                    report_type=report_type,
                    start_date=start_str,
                    fields=BALANCE_FIELDS,
                ),
                statement="balance",
                item_map=CN_BALANCE_MAP,
                currency=unit,
            )
            rows += rows_from_wide(
                self._safe(
                    "cashflow",
                    ts_code=str(code),
                    report_type=report_type,
                    start_date=start_str,
                    fields=CASHFLOW_FIELDS,
                ),
                statement="cashflow",
                item_map=CN_CASHFLOW_MAP,
                currency=unit,
            )
            return rows

        if code.market is Market.HK:
            rows = []
            rows += rows_from_hk_line_items(
                self._safe("hk_income", ts_code=str(code), fields=HK_LINE_ITEM_FIELDS),
                statement="income",
                item_map=HK_INCOME_MAP,
                currency=unit,
            )
            rows += rows_from_hk_line_items(
                self._safe("hk_balancesheet", ts_code=str(code), fields=HK_LINE_ITEM_FIELDS),
                statement="balance",
                item_map=HK_BALANCE_MAP,
                currency=unit,
            )
            rows += rows_from_hk_line_items(
                self._safe("hk_cashflow", ts_code=str(code), fields=HK_LINE_ITEM_FIELDS),
                statement="cashflow",
                item_map=HK_CASHFLOW_MAP,
                currency=unit,
            )
            return [row for row in rows if row.period_end.year >= start.year]

        raise NotImplementedError("US statements are not supported yet")

    # -- dividends ---------------------------------------------------------
    def dividends(
        self, code: StockCode, *, currency: Currency | None = None, years: int = 6
    ) -> list[DividendEvent]:
        unit = currency or self._default_currency(code)
        if code.is_a_share:
            frame = self._safe("dividend", ts_code=str(code), fields=DIVIDEND_FIELDS)
            events = dividend_events(frame, currency=unit)
        elif code.market is Market.HK:
            frame = self._safe("hk_fina_indicator", ts_code=str(code), fields=HK_DIVIDEND_FIELDS)
            events = hk_dividend_events(frame, currency=unit)
        else:
            return []
        cutoff = date.today().year - years
        return [event for event in events if event.fiscal_year >= cutoff]

    # -- market data -------------------------------------------------------
    def weekly(self, code: StockCode, *, years: int = 10) -> list[dict]:
        end = date.today()
        start = end - timedelta(days=365 * years)
        start_str, end_str = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

        if code.market is Market.HK:
            # No hk_weekly endpoint: daily closes are used as the price history.
            return self._hk_history(code, years=years)

        if not code.is_a_share:
            self._issues.append(
                FetchIssue("weekly", str(code), "price history is A-share/HK only for now")
            )
            return []

        frame = self._safe(
            "weekly",
            ts_code=str(code),
            start_date=start_str,
            end_date=end_str,
            fields="ts_code,trade_date,open,high,low,close,vol,amount",
        )
        if frame.empty:
            return []
        records = frame.to_dict("records")
        for record in records:
            record["trade_date"] = str(record["trade_date"])
        return sorted(records, key=lambda r: r["trade_date"])

    def risk_free_rate(self, code: StockCode) -> Decimal | None:
        end = date.today()
        start = end - timedelta(days=45)
        frame = self._safe(
            "yc_cb",
            ts_code="1001.CB",
            curve_type="0",
            curve_term="10",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            fields="trade_date,yield",
        )
        if frame.empty:
            return None
        latest = frame.sort_values("trade_date").iloc[-1]
        try:
            return Decimal(str(latest["yield"]))
        except Exception:  # noqa: BLE001 - payload shape is vendor-controlled
            return None
