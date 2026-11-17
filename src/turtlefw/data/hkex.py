"""HKEXnews helpers: issuer ids, disclosure lists and share buy-back parsing.

Official sources
----------------
* ``prefix.do`` maps a stock code to the exchange's internal ``stockId``.
* ``titleSearchServlet.do`` lists filed documents for that issuer.
* "Next Day Disclosure Return" (FF305) filings carry, in Part B or in the
  share buy-back section, the per-date repurchase table:

  ``12). Shares repurchased for cancellation but not yet cancelled 239,000
  0.00263 % HKD 420.9441`` followed by ``Date of changes 09 October 2026``.

  The per-share price in that table is the volume-weighted average price
  (NDR note 4), so ``amount = shares x price`` reproduces the aggregate paid.

The exchange publishes no machine-readable API; this module is a thin,
polite scraper. Callers are expected to cache results (the provider stores
the parsed events in its file cache).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

BASE = "https://www1.hkexnews.hk"
HEADERS = {
    "User-Agent": "turtle-framework/1.0 (+https://daily.polygon1865.com)",
    "Accept": "application/json, text/javascript, */*",
}
TIMEOUT_SECONDS = 30.0


class HkexError(RuntimeError):
    """Raised when HKEXnews cannot be reached or returns unexpected data."""


@dataclass(frozen=True, slots=True)
class BuybackEvent:
    """One repurchase date parsed out of an exchange filing."""

    trade_date: date
    shares: int
    amount: Decimal
    currency: str
    price: Decimal | None = None
    source: str = "hkex"

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date.isoformat(),
            "shares": self.shares,
            "amount": str(self.amount),
            "currency": self.currency,
            "price": None if self.price is None else str(self.price),
            "source": self.source,
        }


_PREFIX_ID = re.compile(r'"stockId"\s*:\s*(\d+)')
_DATE_LINE = re.compile(r"Date of changes\s+(\d{1,2}\s+\w+\s+\d{4})")
_PART_B_ROW = re.compile(
    r"^\s*\d+\)\.\s+Shares repurchased.*?\s(?P<shares>[\d,]+)\s+"
    r"(?P<pct>[\d.]+)\s*%\s+(?P<currency>HKD|RMB|USD)\s+(?P<price>[\d.,]+)\s*$"
)
_TABLE_HEADER = re.compile(r"aggregate price paid|buy-?back date", re.IGNORECASE)
_TABLE_ROW = re.compile(
    r"^\s*(?P<day>\d{2}/\d{2}/\d{4})\s+(?P<shares>[\d,]+)\s+"
    r"(?P<high>[\d.]+)\s+(?P<low>[\d.]+)\s+(?P<amount>[\d,.]+)\s*$"
)
_MONTH_FORMATS = ("%d %B %Y", "%d %b %Y")


def _parse_decimal(text: str) -> Decimal | None:
    cleaned = text.replace(",", "").strip()
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_long_date(text: str) -> date | None:
    cleaned = " ".join(text.split())
    for fmt in _MONTH_FORMATS:
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            continue
    return None


def stock_id(code: str, *, session: requests.Session | None = None) -> str:
    """Return the HKEX internal ``stockId`` for a five-digit stock code."""

    digits = code.split(".")[0].strip().zfill(5)
    caller = session or requests
    try:
        response = caller.get(
            f"{BASE}/search/prefix.do",
            params={"callback": "callback", "lang": "EN", "type": "A", "name": digits, "market": "SEHK"},
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as exc:  # pragma: no cover - network
        raise HkexError(f"HKEXnews prefix lookup failed: {exc}") from exc
    match = _PREFIX_ID.search(response.text)
    if not match:
        raise HkexError(f"HKEXnews returned no stockId for {digits}")
    return match.group(1)


def documents(
    stock: str,
    *,
    from_date: date,
    to_date: date,
    row_range: int = 5000,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """List filings for one issuer, newest first."""

    params = {
        "sortDir": "0",
        "sortByOptions": "DateTime",
        "category": "0",
        "market": "SEHK",
        "stockId": stock,
        "documentType": "-1",
        "fromDate": from_date.strftime("%Y%m%d"),
        "toDate": to_date.strftime("%Y%m%d"),
        "title": "",
        "searchType": "0",
        "t1code": "",
        "t2Gcode": "",
        "t2code": "",
        "rowRange": str(row_range),
        "lang": "EN",
    }
    caller = session or requests
    try:
        response = caller.get(
            f"{BASE}/search/titleSearchServlet.do",
            params=params,
            headers=HEADERS,
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:  # pragma: no cover - network
        raise HkexError(f"HKEXnews document search failed: {exc}") from exc
    result = payload.get("result")
    rows = json.loads(result) if isinstance(result, str) else result or []
    return [row for row in rows if isinstance(row, dict)]


def pdf_text(content: bytes) -> str:
    """Extract text from a filing PDF (pdfplumber is an optional extra)."""

    try:
        import io

        import pdfplumber
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise HkexError("pdfplumber is required to parse HKEXnews PDFs") from exc
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


def parse_buyback_text(text: str) -> list[BuybackEvent]:
    """Parse repurchase rows from a Next Day Disclosure Return.

    Handles both layouts seen in the wild:

    * FF305 Part B rows ("Shares repurchased for cancellation but not yet
      cancelled ... Date of changes ..."), where the amount is derived from
      the disclosed VWAP;
    * the explicit buy-back table ("Buy-back date ... Aggregate price paid"),
      where the amount is already disclosed.
    """

    lines = [line.rstrip() for line in text.splitlines()]
    events: list[BuybackEvent] = []
    pending: tuple[int, Decimal, str, Decimal] | None = None
    table_mode = False

    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if _TABLE_HEADER.search(line):
            table_mode = True
        row = _PART_B_ROW.match(line)
        if row:
            shares = int(row.group("shares").replace(",", ""))
            price = _parse_decimal(row.group("price"))
            if shares > 0 and price is not None and price > 0:
                pending = (shares, price, row.group("currency"), price)
            continue
        if pending is not None:
            date_match = _DATE_LINE.search(line)
            if date_match:
                trade_date = _parse_long_date(date_match.group(1))
                if trade_date is not None:
                    shares, price, currency, _ = pending
                    events.append(
                        BuybackEvent(
                            trade_date=trade_date,
                            shares=shares,
                            amount=(price * shares).quantize(Decimal("0.01")),
                            currency=currency,
                            price=price,
                        )
                    )
                pending = None
                continue
        if table_mode:
            match = _TABLE_ROW.match(line)
            if match:
                shares = int(match.group("shares").replace(",", ""))
                amount = _parse_decimal(match.group("amount"))
                if shares > 0 and amount is not None and amount > 0:
                    try:
                        trade_date = datetime.strptime(match.group("day"), "%d/%m/%Y").date()
                    except ValueError:
                        continue
                    events.append(
                        BuybackEvent(
                            trade_date=trade_date,
                            shares=shares,
                            amount=amount.quantize(Decimal("0.01")),
                            currency="HKD",
                            price=None,
                        )
                    )
    return events


def is_next_day_disclosure(title: str) -> bool:
    return "next day disclosure" in title.lower()
