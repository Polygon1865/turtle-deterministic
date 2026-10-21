"""Tushare Pro provider.

Design notes:

* Values are never scaled here; the store keeps the reporting currency base unit.
* Every call goes through a content-addressed cache keyed on endpoint + params + schema.
* Failures are recorded as :class:`FetchIssue` and surfaced in the report instead of
  being silently swallowed.
"""

from __future__ import annotations

import tempfile
import threading
import time
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

from ..metrics.prices import adjust_ohlc, factor_map
from ..paths import output_root
from ..types import Currency, DividendEvent, FetchIssue, Market, StockCode
from .cache import FileCache
from .extras import (
    normalize_company,
    normalize_disclosures,
    normalize_express,
    normalize_fina_indicator,
    normalize_float_holders,
    normalize_forecast,
    normalize_holder_count,
    normalize_holder_trades,
    normalize_industry,
    normalize_managers,
    normalize_rewards,
    normalize_share_float,
)
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
STOCK_BASIC_FIELDS = "ts_code,name,industry,area,market,exchange,list_date,delist_date"
A_INDICATOR_FIELDS = (
    "ts_code,end_date,ann_date,roe_waa,grossprofit_margin,netprofit_margin,"
    "debt_to_assets,ocf_to_or,eps,bps"
)
HK_INDICATOR_FIELDS = (
    "ts_code,end_date,ann_date,roe_avg,gross_profit_ratio,net_profit_ratio,"
    "debt_asset_ratio,ocf_sales,basic_eps,bps"
)
US_INDICATOR_FIELDS = (
    "ts_code,end_date,roe_avg,gross_profit_ratio,net_profit_ratio,"
    "debt_asset_ratio,basic_eps"
)
FORECAST_FIELDS = (
    "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,"
    "net_profit_max,summary,change_reason"
)
EXPRESS_FIELDS = (
    "ts_code,ann_date,end_date,revenue,n_income,total_assets,"
    "total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe"
)
DISCLOSURE_FIELDS = "ts_code,ann_date,end_date,pre_date,actual_date,modify_date"
COMPANY_FIELDS = (
    "ts_code,com_name,chairman,manager,secretary,reg_capital,setup_date,"
    "province,city,employees,main_business,website"
)
MANAGER_FIELDS = "ts_code,ann_date,name,gender,title,begin_date,end_date"
REWARD_FIELDS = "ts_code,ann_date,name,title,reward,hold_vol"
CLASSIFY_FIELDS = "index_code,industry_name,level,industry_code,is_pub,parent_code"
MEMBER_FIELDS = (
    "l1_code,l1_name,l2_code,l2_name,l3_code,l3_name,ts_code,name,"
    "in_date,out_date,is_new"
)
FLOAT_HOLDER_FIELDS = (
    "ts_code,ann_date,end_date,holder_name,hold_amount,hold_ratio,"
    "hold_float_ratio,hold_change,holder_type"
)
HOLDER_COUNT_FIELDS = "ts_code,ann_date,end_date,holder_num"
HOLDER_TRADE_FIELDS = (
    "ts_code,ann_date,holder_name,holder_type,in_de,change_vol,change_ratio,"
    "after_share,after_ratio,avg_price"
)
SHARE_FLOAT_FIELDS = (
    "ts_code,ann_date,float_date,holder_name,float_share,float_ratio,share_type"
)


class TushareProvider:
    name = "tushare"
    SCHEMA_VERSION = "turtle-8"

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
        self._token = token
        self._local = threading.local()
        self._lock = threading.Lock()
        self._pro = self._new_client(token)
        self._cache = FileCache(cache_dir or output_root() / ".cache", ttl_seconds)
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._last_call = 0.0
        self._issues: list[FetchIssue] = []
        self._hk_daily: dict[str, list[dict]] = {}
        self._hk_failed: set[str] = set()
        self._hk_yf: dict[str, tuple[list[dict], dict]] = {}
        self._us_yf: dict[str, Any] = {}
        self._dividend_map: dict[str, pd.DataFrame] | None = None

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

    def _client(self):
        """One Tushare client per thread; the shared session is not thread-safe."""
        client = getattr(self._local, "pro", None)
        if client is None:
            client = self._new_client(self._token)
            self._local.pro = client
        return client

    def _throttle(self) -> None:
        with self._lock:
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
                frame = getattr(self._client(), endpoint)(**params)
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
            with self._lock:
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

    def reporting_currency(self, code: StockCode) -> Currency | None:
        """Best-effort reporting currency for a listing.

        A-shares report in CNY. HK listings frequently report in CNY even
        though they trade in HKD; Yahoo's ``financialCurrency`` is used as a
        proxy and may be unavailable offline.
        """
        if code.market is Market.HK:
            _, quote = self._yf_hk(code)
            raw = quote.get("reporting_currency")
            if raw in {"CNY", "HKD", "USD"}:
                return Currency(raw)
            return None
        if code.market is Market.US:
            return Currency.USD
        return Currency.CNY

    # -- reference data ----------------------------------------------------
    def stock_basic(self, code: StockCode | None = None, *, list_status: str = "L") -> list[dict]:
        params: dict[str, Any] = {"fields": STOCK_BASIC_FIELDS, "list_status": list_status}
        if code is not None:
            params["ts_code"] = str(code)
        return self._safe("stock_basic", **params).to_dict("records")

    def _yf_hk(self, code: StockCode) -> tuple[list[dict], dict]:
        """Yahoo Finance quote + daily history for HK listings (cached)."""
        key = str(code)
        if key in self._hk_yf:
            return self._hk_yf[key]

        try:
            import yfinance as yf
        except ImportError:
            self._issues.append(FetchIssue("yfinance", key, "yfinance not installed"))
            self._hk_yf[key] = ([], {})
            return self._hk_yf[key]

        # yfinance keeps SQLite caches under the user cache dir, which is not
        # writable in some sandboxes. Point all of its caches at a writable
        # temp directory before the first ticker is created.
        try:
            cache_dir = Path(tempfile.gettempdir()) / "turtle-yf-cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            yf.set_tz_cache_location(str(cache_dir))
        except Exception:  # noqa: BLE001 - cache is an optimisation only
            pass

        symbol = f"{int(code.numeric):04d}.HK"
        history: list[dict] = []
        quote: dict = {}
        try:
            ticker = yf.Ticker(symbol)
            frame = ticker.history(period="10y", interval="1d", auto_adjust=False)
            if frame is not None and not frame.empty:
                for index, row in frame.iterrows():
                    history.append(
                        {
                            "trade_date": index.strftime("%Y%m%d"),
                            "close": float(row["Close"]),
                            "high": float(row["High"]),
                            "low": float(row["Low"]),
                        }
                    )
            fast = ticker.fast_info

            def _fast(*names):
                for name in names:
                    try:
                        value = fast[name]
                    except Exception:  # noqa: BLE001 - FastInfo shape varies
                        value = getattr(fast, name, None)
                    if value:
                        return value
                return None

            price = _fast("lastPrice", "last_price")
            cap = _fast("marketCap", "market_cap")
            shares = _fast("shares")
            if price:
                quote["close"] = float(price)
            if cap:
                quote["total_mv"] = float(cap) / 10000  # 万元
            if shares:
                quote["total_share"] = float(shares) / 10000  # 万股
            if history:
                quote["trade_date"] = history[-1]["trade_date"]
            # Yahoo exposes the currency of the financial statements
            # (``financialCurrency``), not the listing currency. This is the
            # best available proxy for "reporting currency" without a PDF.
            try:
                info = ticker.info or {}
                reporting = str(info.get("financialCurrency") or "").upper()
                if reporting in {"CNY", "RMB"}:
                    quote["reporting_currency"] = "CNY"
                elif reporting in {"HKD", "USD"}:
                    quote["reporting_currency"] = reporting
            except Exception:  # noqa: BLE001 - metadata is optional
                pass
        except Exception as exc:  # noqa: BLE001 - network/vendor errors
            self._issues.append(FetchIssue("yfinance", key, str(exc)))

        self._hk_yf[key] = (history, quote)
        return self._hk_yf[key]

    def _yf_us(self, code: StockCode):
        key = str(code)
        if key not in self._us_yf:
            import yfinance as yf

            symbol = key.removesuffix(".US")
            cache_dir = Path(tempfile.gettempdir()) / "turtle-yf-cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            yf.set_tz_cache_location(str(cache_dir))
            self._us_yf[key] = yf.Ticker(symbol)
        return self._us_yf[key]

    def _yf_us_statements(self, code: StockCode) -> list[StatementRow]:
        try:
            rows = self._yf_us_statements_primary(code)
            if rows:
                return rows
        except (OSError, ValueError, KeyError, ImportError) as exc:
            self._issues.append(FetchIssue("yfinance", str(code), f"US statements failed: {exc}"))
        return self._sec_us_statements(code)

    def _sec_us_statements(self, code: StockCode) -> list[StatementRow]:
        """Independent SEC fallback when yfinance statements are unavailable."""
        try:
            from .sec import cik_for_ticker, fetch_companyfacts, statement_rows

            cik = cik_for_ticker(str(code))
            rows = statement_rows(fetch_companyfacts(cik), code)
            if rows:
                return rows
        except Exception as exc:  # noqa: BLE001 - optional external source
            self._issues.append(FetchIssue("sec", str(code), str(exc)))
        return []

    def _yf_us_statements_primary(self, code: StockCode) -> list[StatementRow]:
        ticker = self._yf_us(code)
        info = ticker.info or {}
        currency = Currency(str(info.get("financialCurrency") or "USD"))
        frames = {
            "income": ticker.financials,
            "balance": ticker.balance_sheet,
            "cashflow": ticker.cashflow,
        }
        mapping: dict[tuple[str, str], tuple[str, ...]] = {
            ("income", "revenue"): ("Total Revenue", "Operating Revenue"),
            ("income", "n_income_attr_p"): ("Net Income Common Stockholders", "Net Income"),
            ("income", "n_income"): ("Net Income",),
            ("income", "operate_profit"): ("Operating Income", "EBIT"),
            ("income", "basic_eps"): ("Basic EPS",),
            ("income", "diluted_eps"): ("Diluted EPS",),
            ("balance", "total_assets"): ("Total Assets",),
            ("balance", "total_hldr_eqy_exc_min_int"): ("Stockholders Equity", "Common Stock Equity"),
            ("balance", "st_borr"): ("Total Debt",),
            ("balance", "goodwill"): ("Goodwill",),
            ("balance", "total_liab"): ("Total Liabilities Net Minority Interest",),
            ("balance", "money_cap"): ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"),
            ("balance", "accounts_receiv"): ("Accounts Receivable", "Gross Accounts Receivable"),
            ("balance", "inventories"): ("Inventory",),
            ("cashflow", "n_cashflow_act"): ("Operating Cash Flow", "Cash Flow From Continuing Operating Activities"),
            ("cashflow", "c_pay_acq_const_fiolta"): ("Capital Expenditure",),
            ("cashflow", "depr_fa_coga_dpba"): ("Depreciation And Amortization", "Reconciled Depreciation"),
            ("cashflow", "sbc"): ("Share Based Compensation", "Stock Based Compensation"),
        }
        rows: list[StatementRow] = []
        for statement, frame in frames.items():
            if frame is None or frame.empty:
                continue
            index = {str(label): label for label in frame.index}
            for column in frame.columns:
                period_end = pd.Timestamp(column).date()
                for (target_statement, canonical), labels in mapping.items():
                    if target_statement != statement:
                        continue
                    label = next((index[name] for name in labels if name in index), None)
                    if label is None:
                        continue
                    raw = frame.at[label, column]
                    if pd.isna(raw):
                        continue
                    value = Decimal(str(raw))
                    if canonical == "c_pay_acq_const_fiolta":
                        value = abs(value)
                    rows.append(
                        StatementRow(
                            code=str(code),
                            period_end=period_end,
                            period_type="annual",
                            statement=statement,
                            item=canonical,
                            value=value,
                            currency=currency,
                            source="yfinance",
                        )
                    )
        return rows

    def _yf_us_history(self, code: StockCode, *, years: int = 10) -> list[dict]:
        frame = self._yf_us(code).history(period=f"{years}y", interval="1d", auto_adjust=True)
        if frame is None or frame.empty:
            return []
        records: list[dict] = []
        for index, row in frame.iterrows():
            records.append(
                {
                    "trade_date": pd.Timestamp(index).strftime("%Y%m%d"),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                }
            )
        return records

    def _yf_us_quote(self, code: StockCode) -> dict[str, Any]:
        ticker = self._yf_us(code)
        info = ticker.info or {}
        history = self._yf_us_history(code, years=1)
        trade_date = history[-1]["trade_date"] if history else date.today().strftime("%Y%m%d")
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        return {
            "ts_code": str(code),
            "trade_date": trade_date,
            "close": price,
            "total_mv": (info.get("marketCap") or 0) / 10000 if info.get("marketCap") else None,
            "total_share": (info.get("sharesOutstanding") or 0) / 10000
            if info.get("sharesOutstanding")
            else None,
        }

    def _yf_us_dividends(self, code: StockCode, *, years: int = 6) -> list[DividendEvent]:
        series = self._yf_us(code).dividends
        if series is None or len(series) == 0:
            return []
        unit = self._default_currency(code)
        cutoff = date.today().year - years
        events: list[DividendEvent] = []
        for index, value in series.items():
            event_date = pd.Timestamp(index).date()
            if event_date.year < cutoff:
                continue
            events.append(
                DividendEvent(
                    fiscal_year=event_date.year,
                    event_id=event_date.isoformat(),
                    dps=Decimal(str(value)),
                    currency=unit,
                )
            )
        return events

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

        yf_history, _ = self._yf_hk(code)
        if yf_history:
            self._hk_daily[key] = yf_history
            return yf_history

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
            _, quote = self._yf_hk(code)
            if quote:
                return [{**quote, "ts_code": str(code)}]
            history = self._hk_history(code, years=1)
            return [history[-1]] if history else []

        if code is not None and code.market is Market.US:
            return [self._yf_us_quote(code)]

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

        if code.market is Market.US:
            return self._yf_us_statements(code)

        raise NotImplementedError("US statements are not supported yet")

    # -- dividends ---------------------------------------------------------
    def prefetch_dividends(self, periods: list[str]) -> None:
        """Load all cash-dividend rows for the given fiscal years (one call each)."""
        frames = [
            self._paginated("dividend", DIVIDEND_FIELDS, end_date=period)
            for period in periods
        ]
        non_empty = [frame for frame in frames if not frame.empty]
        if not non_empty:
            self._dividend_map = {}
            return
        combined = pd.concat(non_empty, ignore_index=True)
        self._dividend_map = {
            code: group for code, group in combined.groupby("ts_code")
        }

    # -- dividends ---------------------------------------------------------
    def dividends(
        self,
        code: StockCode,
        *,
        currency: Currency | None = None,
        years: int = 6,
        dps_fx: Decimal = Decimal("1"),
    ) -> list[DividendEvent]:
        unit = currency or self._default_currency(code)
        if code.is_a_share:
            if self._dividend_map is not None:
                frame = self._dividend_map.get(str(code), pd.DataFrame())
            else:
                frame = self._safe("dividend", ts_code=str(code), fields=DIVIDEND_FIELDS)
            events = dividend_events(frame, currency=unit)
        elif code.market is Market.HK:
            frame = self._safe("hk_fina_indicator", ts_code=str(code), fields=HK_DIVIDEND_FIELDS)
            events = hk_dividend_events(frame, currency=unit, dps_fx=dps_fx)
        elif code.market is Market.US:
            events = self._yf_us_dividends(code, years=years)
        else:
            return []
        cutoff = date.today().year - years
        return [event for event in events if event.fiscal_year >= cutoff]

    # -- market-wide batch (Stage 1) ---------------------------------------
    def _paginated(self, endpoint: str, fields: str, **params: Any) -> pd.DataFrame:
        frames: list[pd.DataFrame] = []
        limit = 5000
        for page in range(4):
            frame = self._safe(
                endpoint, fields=fields, limit=limit, offset=page * limit, **params
            )
            if frame.empty:
                break
            frames.append(frame)
            if len(frame) < limit:
                break
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    def market_statements(self, period: str, statement: str) -> pd.DataFrame:
        """All listed companies' statements for one fiscal period (VIP batch)."""
        endpoint, fields = {
            "income": ("income_vip", INCOME_FIELDS),
            "balance": ("balancesheet_vip", BALANCE_FIELDS),
            "cashflow": ("cashflow_vip", CASHFLOW_FIELDS),
        }[statement]
        return self._paginated(endpoint, fields, period=period, report_type="1")

    def market_fina_indicator(self, period: str) -> pd.DataFrame:
        return self._paginated(
            "fina_indicator_vip",
            "ts_code,end_date,roe_waa,grossprofit_margin,debt_to_assets",
            period=period,
        )

    # -- supplemental fundamentals -----------------------------------------
    def fundamental_extras(self, code: StockCode) -> dict[str, Any]:
        """Fetch non-statement fundamentals for one listing.

        This is deliberately separate from :meth:`statements`: forecast,
        express and indicator data must never be merged into the audited
        statement rows.  Empty responses are reported as ``missing`` rather
        than zero-filled.  Vendor permission failures are captured by
        :meth:`_safe` and surface through ``provider.issues``.
        """
        payload: dict[str, Any] = {
            "code": str(code),
            "market": code.market.value,
            "sources": [],
            "missing": [],
        }
        start = (date.today() - timedelta(days=365 * 6)).strftime("%Y%m%d")

        def records(endpoint: str, fields: str, **params: Any) -> list[dict[str, Any]]:
            frame = self._safe(endpoint, fields=fields, **params)
            return [] if frame.empty else frame.to_dict("records")

        def add(key: str, endpoint: str, value: Any) -> None:
            if value:
                payload[key] = value
                payload["sources"].append(f"tushare:{endpoint}")
            else:
                payload["missing"].append(key)

        if code.is_a_share:
            add(
                "financial_indicators",
                "fina_indicator",
                normalize_fina_indicator(
                    records(
                        "fina_indicator",
                        A_INDICATOR_FIELDS,
                        ts_code=str(code),
                        start_date=start,
                    ),
                    "A",
                ),
            )
            add(
                "forecasts",
                "forecast",
                normalize_forecast(
                    records(
                        "forecast",
                        FORECAST_FIELDS,
                        ts_code=str(code),
                        start_date=start,
                    )
                ),
            )
            add(
                "express",
                "express",
                normalize_express(
                    records(
                        "express",
                        EXPRESS_FIELDS,
                        ts_code=str(code),
                        start_date=start,
                    )
                ),
            )
            add(
                "disclosures",
                "disclosure_date",
                normalize_disclosures(
                    records("disclosure_date", DISCLOSURE_FIELDS, ts_code=str(code))
                ),
            )
            company_rows = records("stock_company", COMPANY_FIELDS, ts_code=str(code))
            add(
                "company",
                "stock_company",
                normalize_company(company_rows[0] if company_rows else None),
            )
            add(
                "managers",
                "stk_managers",
                normalize_managers(
                    records("stk_managers", MANAGER_FIELDS, ts_code=str(code))
                ),
            )
            add(
                "rewards",
                "stk_rewards",
                normalize_rewards(
                    records("stk_rewards", REWARD_FIELDS, ts_code=str(code))
                ),
            )

            memberships = records(
                "index_member_all",
                MEMBER_FIELDS,
                ts_code=str(code),
            )
            classifications = records(
                "index_classify", CLASSIFY_FIELDS, level="L1"
            )
            add(
                "industry",
                "index_member_all",
                normalize_industry(memberships, classifications),
            )
            add(
                "float_holders",
                "top10_floatholders",
                normalize_float_holders(
                    records(
                        "top10_floatholders",
                        FLOAT_HOLDER_FIELDS,
                        ts_code=str(code),
                    )
                ),
            )
            add(
                "holder_count",
                "stk_holdernumber",
                normalize_holder_count(
                    records("stk_holdernumber", HOLDER_COUNT_FIELDS, ts_code=str(code))
                ),
            )
            add(
                "holder_trades",
                "stk_holdertrade",
                normalize_holder_trades(
                    records(
                        "stk_holdertrade",
                        HOLDER_TRADE_FIELDS,
                        ts_code=str(code),
                        start_date=start,
                    )
                ),
            )
            add(
                "share_float",
                "share_float",
                normalize_share_float(
                    records("share_float", SHARE_FLOAT_FIELDS, ts_code=str(code))
                ),
            )
            return payload

        if code.market is Market.HK:
            add(
                "financial_indicators",
                "hk_fina_indicator",
                normalize_fina_indicator(
                    records(
                        "hk_fina_indicator",
                        HK_INDICATOR_FIELDS,
                        ts_code=str(code),
                    ),
                    "HK",
                ),
            )
            return payload

        if code.market is Market.US:
            add(
                "financial_indicators",
                "us_fina_indicator",
                normalize_fina_indicator(
                    records(
                        "us_fina_indicator",
                        US_INDICATOR_FIELDS,
                        ts_code=str(code).removesuffix(".US"),
                    ),
                    "US",
                ),
            )
            return payload

        return payload

    # -- governance / capital actions -------------------------------------
    def pledge(self, code: StockCode, *, years: int = 5) -> list[dict]:
        """A-share pledge statistics, newest first; empty for HK/US or no access."""
        if not code.is_a_share:
            return []
        frame = self._safe(
            "pledge_stat",
            ts_code=str(code),
            fields="ts_code,end_date,pledge_ratio",
        )
        if frame.empty:
            return []
        frame = frame.sort_values("end_date", ascending=False)
        return frame.head(years).to_dict("records")

    def pledge_ratio(self, code: StockCode) -> Decimal | None:
        rows = self.pledge(code)
        if not rows:
            return None
        value = rows[0].get("pledge_ratio")
        try:
            return Decimal(str(value)) if value is not None else None
        except Exception:  # noqa: BLE001 - vendor payload
            return None

    def repurchase(self, code: StockCode, *, years: int = 5) -> list[dict]:
        """A-share buyback rows (amount is 万元 in Tushare); newest first."""
        if not code.is_a_share:
            return []
        frame = self._safe(
            "repurchase",
            ts_code=str(code),
            fields="ts_code,ann_date,end_date,amount,vol,proc",
        )
        if frame.empty:
            return []
        if "ann_date" in frame.columns:
            frame = frame.sort_values("ann_date", ascending=False)
        return frame.head(years * 4).to_dict("records")

    def buyback_amount(self, code: StockCode, *, years: int = 3) -> Decimal | None:
        """Annualised completed/implemented buyback amount in report currency.

        Tushare returns ``amount`` in yuan and often several cumulative
        snapshots of the same programme. Keep the largest amount per calendar
        year, then average over the available years.
        """
        rows = self.repurchase(code)
        if not rows:
            return None
        cutoff = date.today().year - years
        by_year: dict[int, Decimal] = {}
        for row in rows:
            process = str(row.get("proc", "")).strip()
            if process not in {"实施", "完成"}:
                continue
            raw_date = str(row.get("ann_date") or row.get("end_date") or "")[:4]
            try:
                year = int(raw_date)
            except ValueError:
                continue
            if year < cutoff:
                continue
            raw = row.get("amount")
            try:
                amount = Decimal(str(raw)) if raw is not None else None
            except Exception:  # noqa: BLE001 - vendor payload
                amount = None
            if amount is not None and amount > 0:
                by_year[year] = max(by_year.get(year, Decimal("0")), amount)
        if not by_year:
            return None
        total = sum(by_year.values(), Decimal("0"))
        return total / Decimal(max(1, min(years, len(by_year))))

    def holders(self, code: StockCode) -> list[dict]:
        """Latest top-10 shareholder table (A-share only)."""
        if not code.is_a_share:
            return []
        frame = self._safe(
            "top10_holders",
            ts_code=str(code),
            fields="ts_code,end_date,holder_name,hold_amount,hold_ratio",
        )
        if frame.empty:
            return []
        latest = str(frame["end_date"].max())
        return frame[frame["end_date"].astype(str) == latest].to_dict("records")

    def main_business(self, code: StockCode) -> list[dict]:
        """Latest revenue/profit by product/segment (A-share only)."""
        if not code.is_a_share:
            return []
        frame = self._safe(
            "fina_mainbz",
            ts_code=str(code),
            fields="ts_code,end_date,bz_item,bz_sales,bz_profit",
        )
        if frame.empty:
            return []
        latest = str(frame["end_date"].max())
        return frame[frame["end_date"].astype(str) == latest].to_dict("records")

    def audit(self, code: StockCode, *, years: int = 5) -> list[dict]:
        """Latest audit opinions; HK/US are not covered by ``fina_audit``."""
        if not code.is_a_share:
            return []
        frame = self._safe(
            "fina_audit",
            ts_code=str(code),
            fields="ts_code,end_date,audit_agency,audit_result",
        )
        if frame.empty:
            return []
        frame = frame.sort_values("end_date", ascending=False)
        return frame.head(years).to_dict("records")

    # -- market data -------------------------------------------------------
    def weekly(self, code: StockCode, *, years: int = 10) -> list[dict]:
        end = date.today()
        start = end - timedelta(days=365 * years)
        start_str, end_str = start.strftime("%Y%m%d"), end.strftime("%Y%m%d")

        if code.market is Market.HK:
            # No hk_weekly endpoint: daily closes are used as the price history.
            return self._hk_history(code, years=years)

        if code.market is Market.US:
            return self._yf_us_history(code, years=years)

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
        factors_frame = self._safe(
            "adj_factor",
            ts_code=str(code),
            start_date=start_str,
            end_date=end_str,
            fields="ts_code,trade_date,adj_factor",
        )
        factors = factor_map(factors_frame.to_dict("records")) if not factors_frame.empty else {}
        records = adjust_ohlc(records, factors)
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
