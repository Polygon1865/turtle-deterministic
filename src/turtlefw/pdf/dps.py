"""Independent DPS extraction.

DPS is usually a small number (0–100), so the general statement extractor's
>1000 threshold must not be reused. This module only returns a traceable DPS
candidate; the caller decides whether to use it.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

DPS_ALIASES = (
    "每股派息",
    "每股股息",
    "每股股利",
    "每股现金红利",
    "每股分红",
    "Dividend per share",
    "DPS",
)

_NUMBER = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?")
_CURRENCY = (
    ("港元", "HKD"),
    ("港币", "HKD"),
    ("人民币", "CNY"),
    ("美元", "USD"),
    ("RMB", "CNY"),
    ("HKD", "HKD"),
    ("USD", "USD"),
)


def _number(line: str) -> Decimal | None:
    match = _NUMBER.search(line.replace("，", ","))
    if not match:
        return None
    try:
        value = Decimal(match.group(0).replace(",", ""))
    except InvalidOperation:
        return None
    if value <= 0 or value >= Decimal("1000"):
        return None
    return value


def _currency(line: str, default: str = "CNY") -> str:
    for token, code in _CURRENCY:
        if token in line:
            return code
    return default


def extract_dps_from_pages(
    pages_text: list[tuple[int, str]],
    *,
    default_currency: str = "CNY",
) -> dict[str, str]:
    """Return the first traceable DPS candidate, or an empty dict."""
    for page, text in pages_text:
        for line in (text or "").splitlines():
            if not any(alias.lower() in line.lower() for alias in DPS_ALIASES):
                continue
            value = _number(line)
            if value is None:
                continue
            return {
                "dps": f"{value:.4f}",
                "currency": _currency(line, default_currency),
                "page": str(page),
                "quote": " ".join(line.split())[:200],
            }
    return {}
