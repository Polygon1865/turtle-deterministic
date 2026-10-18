from decimal import Decimal

from turtlefw.metrics.dividends import DividendEvent, mean_payout, payout_by_year
from turtlefw.types import Currency


def event(year: int, event_id: str, dps: str, total: str | None = None) -> DividendEvent:
    return DividendEvent(
        fiscal_year=year,
        event_id=event_id,
        dps=Decimal(dps),
        currency=Currency.CNY,
        total=Decimal(total) if total else None,
    )


class TestPayoutByYear:
    def test_interim_and_final_are_summed(self):
        """Regression for the original bug: 75%, not 25%."""
        events = [
            event(2024, "final", "1.0", "1000"),
            event(2024, "interim", "0.5", "500"),
        ]
        payouts = payout_by_year(events, {2024: Decimal("2000")})
        assert payouts[2024] == Decimal("75")

    def test_duplicate_announcements_are_idempotent(self):
        events = [event(2024, "final", "1.0", "1000"), event(2024, "final", "1.0", "1000")]
        assert payout_by_year(events, {2024: Decimal("2000")})[2024] == Decimal("50")

    def test_no_events_means_unknown_not_zero(self):
        payouts = payout_by_year([], {2024: Decimal("2000")})
        assert payouts[2024] is None

    def test_year_without_dividend_is_zero(self):
        events = [event(2023, "final", "1.0", "1000")]
        assert payout_by_year(events, {2024: Decimal("2000")})[2024] == Decimal("0")

    def test_negative_income_is_none(self):
        events = [event(2024, "final", "1.0", "1000")]
        assert payout_by_year(events, {2024: Decimal("-5")})[2024] is None

    def test_hk_event_uses_share_count(self):
        hk = DividendEvent(
            fiscal_year=2024,
            event_id="2024-12-31",
            dps=Decimal("2.0"),
            currency=Currency.HKD,
            total=None,
        )
        payouts = payout_by_year([hk], {2024: Decimal("1000")}, shares=Decimal("500"))
        assert payouts[2024] == Decimal("100")


class TestMeanPayout:
    def test_uses_last_three_years(self):
        payouts = {2020: Decimal("10"), 2021: Decimal("20"), 2022: Decimal("30"),
                   2023: Decimal("40"), 2024: Decimal("50")}
        mean, used = mean_payout(payouts, years=3)
        assert used == 3
        assert mean == Decimal("40")

    def test_skips_missing(self):
        mean, used = mean_payout({2023: None, 2024: Decimal("50")}, years=3)
        assert used == 1
        assert mean == Decimal("50")

    def test_all_missing(self):
        assert mean_payout({2024: None}) == (None, 0)
