"""SEC companyfacts cross-check (US data coverage).

This is an independent source audit, not a replacement for the primary
provider. It never mutates statement rows: differences are reported with SEC
tag/year/value and the local value.
"""

from __future__ import annotations

import json
import os
import urllib.request
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Protocol, Sequence

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
TAGS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
    ),
    "net_income": ("NetIncomeLoss",),
    "total_assets": ("Assets",),
    "equity": ("StockholdersEquity",),
    "ocf": ("NetCashProvidedByUsedInOperatingActivities",),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment",),
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
                if str(unit).upper() not in {"USD", "USD/SHARES"}:
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
