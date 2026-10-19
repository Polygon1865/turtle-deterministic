"""SEC companyfacts cross-check (US data coverage).

This is an independent source audit, not a replacement for the primary
provider. It never mutates statement rows: differences are reported with SEC
tag/year/value and the local value.
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol, Sequence

from ..types import Currency, StockCode
from .protocol import StatementRow

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
ARCHIVE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{document}"
TAGS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ),
    "net_income": ("NetIncomeLoss",),
    "operate_profit": ("OperatingIncomeLoss",),
    "total_assets": ("Assets",),
    "equity": ("StockholdersEquity",),
    "cash": ("CashAndCashEquivalentsAtCarryingValue",),
    "debt": ("LongTermDebtNoncurrent", "LongTermDebt", "DebtCurrent"),
    "goodwill": ("Goodwill",),
    "ocf": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
    "da": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
    ),
    "sbc": ("ShareBasedCompensation",),
    "dividend_per_share": ("CommonStockDividendsPerShareDeclared",),
    "dividends_paid": ("PaymentsOfDividendsCommonStock",),
    "shares_outstanding": ("CommonStockSharesOutstanding",),
}
STATEMENT_ITEMS = {
    "income": ("revenue", "net_income", "operate_profit"),
    "balance": ("total_assets", "equity", "cash", "debt", "goodwill"),
    "cashflow": ("ocf", "capex", "da", "sbc"),
}


class SecError(Exception):
    pass


class Transport(Protocol):
    def get(self, url: str, headers: Mapping[str, str]) -> Mapping[str, Any]: ...


class UrllibTransport:
    def get(self, url: str, headers: Mapping[str, str]) -> Mapping[str, Any]:
        request = urllib.request.Request(url, headers=dict(headers))
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - network errors become audit errors
            raise SecError(f"SEC request failed: {exc}") from exc
        if not isinstance(payload, dict):
            raise SecError("SEC response must be an object")
        return payload


def _headers() -> dict[str, str]:
    user_agent = os.environ.get(
        "SEC_USER_AGENT", "turtle-deterministic/0.1 research@example.com"
    )
    return {"User-Agent": user_agent, "Accept": "application/json"}


def cik_for_ticker(ticker: str, transport: Transport | None = None) -> int:
    payload = (transport or UrllibTransport()).get(TICKERS_URL, _headers())
    want = ticker.upper().removeprefix("US").removesuffix(".US")
    for item in payload.values():
        if not isinstance(item, Mapping):
            continue
        if str(item.get("ticker", "")).upper() == want:
            try:
                return int(item["cik_str"])
            except (KeyError, TypeError, ValueError) as exc:
                raise SecError("invalid SEC ticker mapping") from exc
    raise SecError(f"ticker not found in SEC mapping: {ticker}")


def _units(fact: Mapping[str, Any]) -> Mapping[str, Any]:
    units = fact.get("units", {})
    return units if isinstance(units, Mapping) else {}


def annual_facts(payload: Mapping[str, Any]) -> dict[str, dict[int, Decimal]]:
    """Map the supported items to fiscal-year values (10-K, USD only)."""
    facts = payload.get("facts", {}).get("us-gaap", {})
    if not isinstance(facts, Mapping):
        return {}
    result: dict[str, dict[int, Decimal]] = {}
    for item, tags in TAGS.items():
        values: dict[int, Decimal] = {}
        for tag in tags:
            fact = facts.get(tag)
            if not isinstance(fact, Mapping):
                continue
            for unit, rows in _units(fact).items():
                if str(unit).upper() not in {"USD", "USD/SHARES", "SHARES"}:
                    continue
                for row in rows if isinstance(rows, list) else []:
                    if not isinstance(row, Mapping):
                        continue
                    if row.get("form") not in {"10-K", "10-K/A"}:
                        continue
                    year = row.get("fy")
                    value = row.get("val")
                    if year is None or value is None:
                        continue
                    try:
                        values[int(year)] = Decimal(str(value))
                    except (InvalidOperation, ValueError):
                        continue
            if values:
                break
        if values:
            result[item] = values
    return result


def statement_rows(
    payload: Mapping[str, Any],
    code: StockCode,
) -> list[StatementRow]:
    """Build annual StatementRows from SEC companyfacts.

    The SEC facts do not contain every provider field; missing items are omitted
    rather than filled with zero. Period end uses the fiscal year end (Dec 31)
    because companyfacts exposes ``fy`` but not a uniform fiscal calendar.
    """
    facts = annual_facts(payload)
    years = sorted(
        {
            year
            for values in facts.values()
            for year in values
        }
    )[-5:]
    rows: list[StatementRow] = []
    for year in years:
        for statement, items in STATEMENT_ITEMS.items():
            for item in items:
                value = facts.get(item, {}).get(year)
                if value is None:
                    continue
                canonical = {
                    "net_income": "n_income_attr_p",
                    "equity": "total_hldr_eqy_exc_min_int",
                    "cash": "money_cap",
                    "debt": "st_borr",
                    "da": "depr_fa_coga_dpba",
                    "capex": "c_pay_acq_const_fiolta",
                }.get(item, item)
                if item == "capex":
                    value = abs(value)
                rows.append(
                    StatementRow(
                        code=str(code),
                        period_end=date(year, 12, 31),
                        period_type="annual",
                        statement=statement,
                        item=canonical,
                        value=value,
                        currency=Currency.USD,
                        source="sec",
                    )
                )
    return rows


def fetch_companyfacts(
    cik: int,
    transport: Transport | None = None,
) -> Mapping[str, Any]:
    return (transport or UrllibTransport()).get(
        FACTS_URL.format(cik=cik), _headers()
    )


def evidence_facts(
    payload: Mapping[str, Any],
    *,
    cik: int | None = None,
) -> list[dict[str, object]]:
    """Turn annual SEC facts into report-addressable evidence rows."""
    facts = annual_facts(payload)
    source_url = FACTS_URL.format(cik=cik) if cik is not None else ""
    rows: list[dict[str, object]] = []
    units = {
        "dividend_per_share": "USD/shares",
        "shares_outstanding": "shares",
        "dividends_paid": "USD",
    }
    for item, values in sorted(facts.items()):
        for year, value in sorted(values.items()):
            rows.append(
                {
                    "id": f"sec:{item}:{year}",
                    "page": "",
                    "section": "SEC",
                    "label": f"SEC {item} FY{year}",
                    "value": str(value),
                    "unit": units.get(item, "USD"),
                    "quote": f"SEC companyfacts {item} FY{year} = {value}",
                    "confidence": "high",
                    "source_rank": 2,
                    "source_url": source_url,
                }
            )
    return rows


def fetch_submissions(
    cik: int,
    transport: Transport | None = None,
) -> Mapping[str, Any]:
    return (transport or UrllibTransport()).get(
        SUBMISSIONS_URL.format(cik=cik), _headers()
    )


def filing_evidence(
    payload: Mapping[str, Any],
    *,
    cik: int,
    forms: tuple[str, ...] = ("10-K", "10-K/A"),
) -> list[dict[str, object]]:
    """Latest annual filing as a research evidence row."""
    filings = payload.get("filings", {})
    recent = filings.get("recent", {}) if isinstance(filings, Mapping) else {}
    if not isinstance(recent, Mapping):
        return []
    forms_list = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    documents = recent.get("primaryDocument", [])
    latest: int | None = None
    for index, form in enumerate(forms_list if isinstance(forms_list, list) else []):
        if str(form) in forms and (latest is None or str(dates[index]) > str(dates[latest])):
            latest = index
    if latest is None:
        return []
    accession = str(accessions[latest])
    document = str(documents[latest])
    url = ARCHIVE_URL.format(
        cik=cik, accession=accession.replace("-", ""), document=document
    )
    return [
        {
            "id": f"sec:filing:{accession}",
            "page": "",
            "section": "SEC 10-K",
            "label": f"{forms_list[latest]} {dates[latest]}",
            "value": None,
            "unit": "",
            "quote": (
                f"SEC {forms_list[latest]} filed {dates[latest]} "
                f"(accession {accession})"
            ),
            "confidence": "high",
            "source_rank": 2,
            "source_url": url,
        }
    ]


def compare_rows(
    rows: Sequence[Mapping[str, Any]],
    facts: Mapping[str, Mapping[int, Decimal]],
    *,
    tolerance_pct: Decimal = Decimal("1"),
) -> list[dict[str, object]]:
    annual = [
        row
        for row in rows
        if row.get("period_type") == "annual"
        and row.get("period_end")
        and row.get("value") not in (None, "")
    ]
    if not annual:
        return []
    latest_year = max(int(str(row["period_end"])[:4]) for row in annual)
    results: list[dict[str, object]] = []
    for item in TAGS:
        local = next(
            (
                row
                for row in sorted(
                    annual, key=lambda row: str(row.get("period_end", ""))
                )
                if row.get("item") == item
                and int(str(row["period_end"])[:4]) == latest_year
            ),
            None,
        )
        sec_values = facts.get(item, {})
        sec_value = sec_values.get(latest_year)
        if local is None or sec_value is None:
            continue
        try:
            local_value = Decimal(str(local["value"]))
        except (InvalidOperation, KeyError):
            continue
        diff = (
            abs(local_value - sec_value) / abs(sec_value) * Decimal("100")
            if sec_value != 0
            else Decimal("0")
        )
        results.append(
            {
                "item": item,
                "year": latest_year,
                "sec_value": str(sec_value),
                "local_value": str(local_value),
                "diff_pct": str(diff.quantize(Decimal("0.01"))),
                "status": "agree" if diff <= tolerance_pct else "review",
            }
        )
    return results
