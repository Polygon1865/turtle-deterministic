"""T2 — one payout answer everywhere (roadmap)."""

from __future__ import annotations

from decimal import Decimal

import pandas as pd

from turtlefw.data.normalize import hk_dividend_events
from turtlefw.metrics import payout as payout_metrics
from turtlefw.screener.hk import _payout
from turtlefw.types import Currency


def test_vendor_ratio_fraction_and_percent() -> None:
    assert payout_metrics.vendor_ratio(Decimal("0.928")).pct == Decimal("92.8")
    assert payout_metrics.vendor_ratio(Decimal("92.8")).pct == Decimal("92.8")
    assert payout_metrics.vendor_ratio(None).pct is None


def test_vendor_ratio_clips_special_dividend() -> None:
    result = payout_metrics.vendor_ratio(Decimal("1.4084"))
    assert result.pct == Decimal("100")
    assert result.reliable is False
    assert "clipped" in result.note


def test_dps_ratio_converts_eps_currency() -> None:
    plain = payout_metrics.dps_ratio(Decimal("0.5"), Decimal("1.0"))
    assert plain.pct == Decimal("50")
    converted = payout_metrics.dps_ratio(Decimal("0.4882"), Decimal("0.5548"), eps_fx=Decimal("0.92"))
    assert converted.pct is not None
    assert abs(converted.pct - Decimal("80.95")) < Decimal("0.05")
    assert payout_metrics.dps_ratio(Decimal("0"), Decimal("1")).pct is None
    assert payout_metrics.dps_ratio(Decimal("1"), Decimal("-1")).pct is None


def test_events_ratio_and_resolve() -> None:
    events = payout_metrics.events_ratio(Decimal("87.78"), Decimal("100"))
    assert events.pct == Decimal("87.78")
    ratio = payout_metrics.vendor_ratio(Decimal("0.67"))
    resolved = payout_metrics.resolve(events, ratio, prefer=("divi_ratio", "dps", "events"))
    assert resolved.source == "divi_ratio"
    fallback = payout_metrics.resolve(events, payout_metrics.NONE)
    assert fallback.source == "events"
    assert payout_metrics.resolve().pct is None


def test_agree_tolerance() -> None:
    left = payout_metrics.vendor_ratio(Decimal("0.5"))
    right = payout_metrics.vendor_ratio(Decimal("0.5000001"))
    assert payout_metrics.agree(left, right)
    assert not payout_metrics.agree(left, payout_metrics.vendor_ratio(Decimal("0.6")))
    assert payout_metrics.agree(None, None)
    assert not payout_metrics.agree(left, None)


def test_normaliser_and_screener_agree_on_special_dividend() -> None:
    """Regression for the 01513/02877 bug: 140.84% must not become 1.41%."""

    frame = pd.DataFrame(
        [
            {
                "end_date": "20251231",
                "divi_ratio": Decimal("1.4084"),
                "dps_hkd": Decimal("1.0"),
            }
        ]
    )
    events = hk_dividend_events(frame, currency=Currency.HKD)
    assert len(events) == 1
    assert events[0].payout_pct == Decimal("100")

    screen_value, reliable = _payout(
        {"divi_ratio": Decimal("1.4084")}, currency=Currency.HKD, fx=Decimal("1")
    )
    assert screen_value == Decimal("100")
    assert reliable is False
    assert payout_metrics.agree(
        payout_metrics.vendor_ratio(events[0].payout_pct),
        payout_metrics.Payout(screen_value, "divi_ratio", reliable),
    )


def test_normaliser_and_screener_agree_on_fraction() -> None:
    frame = pd.DataFrame(
        [
            {
                "end_date": "20251231",
                "divi_ratio": Decimal("0.928"),
                "dps_hkd": Decimal("0.5"),
            }
        ]
    )
    events = hk_dividend_events(frame, currency=Currency.HKD)
    screen_value, reliable = _payout(
        {"divi_ratio": Decimal("0.928")}, currency=Currency.HKD, fx=Decimal("1")
    )
    assert events[0].payout_pct == screen_value == Decimal("92.8")
    assert reliable is True
