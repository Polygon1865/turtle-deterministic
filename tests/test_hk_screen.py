from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from turtlefw.config import load_settings
from turtlefw.screener.hk import HkScreenError, screen_hk, write_ranking
from turtlefw.types import Currency

SETTINGS = load_settings()
RF = Decimal("1.8")
# HK hurdle = max(hk_floor 5.0, Rf 1.8 + hk_spread 3.0)
HURDLE = Decimal("5.0")


@dataclass(frozen=True)
class _Row:
    statement: str
    period_end: date
    item: str
    value: Decimal


def _cash(period: str, ocf: float, capex: float, *, statement: str = "cashflow") -> list[_Row]:
    year, month, day = int(period[:4]), int(period[4:6]), int(period[6:])
    return [
        _Row(statement, date(year, month, day), "n_cashflow_act", Decimal(str(ocf))),
        _Row(statement, date(year, month, day), "c_pay_acq_const_fiolta", Decimal(str(capex))),
    ]


class _FakeProvider:
    def __init__(self) -> None:
        self.universe = [
            {
                "ts_code": "00700.HK",
                "name": "腾讯",
                "market": "主板",
                "list_date": "20040616",
            },
            {
                "ts_code": "09988.HK",
                "name": "阿里",
                "market": "主板",
                "list_date": "20191126",
            },
            {
                "ts_code": "03690.HK",
                "name": "美团",
                "market": "创业板",
                "list_date": "20180920",
            },
            {
                "ts_code": "01234.HK",
                "name": "新股",
                "market": "主板",
                "list_date": "20250101",
            },
            {
                "ts_code": "00005.HK",
                "name": "汇丰",
                "market": "主板",
                "list_date": "19800102",
            },
            {
                "ts_code": "01299.HK",
                "name": "友邦",
                "market": "主板",
                "list_date": "20101201",
            },
        ]
        self.snapshot = [
            {"ts_code": "00700.HK", "close": 600, "amount": 5_000_000_000},
            {"ts_code": "09988.HK", "close": 120, "amount": 2_000_000_000},
            {"ts_code": "03690.HK", "close": 100, "amount": 1_000_000_000},
            {"ts_code": "01234.HK", "close": 20, "amount": 900_000_000},
            {"ts_code": "00005.HK", "close": 60, "amount": 1_000_000},
            {"ts_code": "01299.HK", "close": 70, "amount": 9_000_000_000},
        ]
        self.indicators = {
            "00700.HK": self._indicator(
                roe=21.13,
                gross=56.21,
                debt=39.13,
                profit=20_000_000_000,
                market_cap=400_000_000_000,
                divi=0.1942,
                eps=24.75,
            ),
            "09988.HK": self._indicator(
                roe=12.0,
                gross=35.0,
                debt=50.0,
                profit=10_000_000_000,
                market_cap=200_000_000_000,
                divi=0.928,
                eps=5.0,
            ),
        }
        self.cashflows = {
            "00700.HK": _cash("20251231", 30_300_000_000, 11_300_000_000)
            + _cash("20241231", 25_000_000_000, 10_000_000_000),
            "09988.HK": _cash("20251231", 12_000_000_000, 2_000_000_000)
            + _cash("20241231", 10_000_000_000, 2_000_000_000),
        }

    @staticmethod
    def _indicator(
        *,
        roe: float,
        gross: float | None,
        debt: float | None,
        profit: float,
        market_cap: float,
        divi: float | None,
        eps: float,
        end: str = "20251231",
        currency: str = "HKD",
        report_type: str = "2025年年报",
    ) -> dict:
        return {
            "end_date": end,
            "report_type": report_type,
            "currency": currency,
            "roe_avg": roe,
            "net_profit_ratio": 25.0,
            "gross_profit_ratio": gross,
            "debt_asset_ratio": debt,
            "operate_income_yoy": 15.0,
            "operate_income": 100_000_000_000,
            "holder_profit": profit,
            "basic_eps": eps,
            "dps_hkd": divi,
            "divi_ratio": divi,
            "bps": 100,
            "pe_ttm": None,
            "pb_ttm": None,
            "total_market_cap": market_cap,
        }

    def hk_universe(self):
        return self.universe

    def hk_market_snapshot(self, trade_date):
        return self.snapshot if trade_date == "20261023" else []

    def hk_indicator(self, code, *, period=None):
        return self.indicators.get(str(code))

    def hk_cashflow_rows(self, code, *, currency=None):
        return self.cashflows.get(str(code), [])


def _screen(provider=None, **kwargs):
    provider = provider or _FakeProvider()
    kwargs.setdefault("trade_date", "20261023")
    kwargs.setdefault("limit", 10)
    return screen_hk(
        provider,
        settings=SETTINGS,
        rf_pct=RF,
        **kwargs,
    )


def test_screen_hk_ranks_by_margin_not_by_roe() -> None:
    """09988 has lower ROE but a far higher payout/FCF spread, so it ranks first."""

    rows = _screen()

    assert [row.code for row in rows] == ["09988.HK", "00700.HK"]
    assert rows[0].rank == 1
    assert rows[0].name == "阿里"
    # GG = avg FCF 9e9 x 92.8% / 2e11 = 4.176%
    assert rows[0].gg == pytest.approx(Decimal("4.176"), abs=Decimal("0.001"))
    # R = 1e10 x 92.8% / 2e11 = 4.64%
    assert rows[0].r == pytest.approx(Decimal("4.64"), abs=Decimal("0.001"))
    assert rows[0].ii == HURDLE
    assert rows[0].margin == pytest.approx(Decimal("-0.824"), abs=Decimal("0.001"))
    # 00700: payout 19.42%, FCF avg 1.7e10, cap 4e11 -> GG 0.825%, R 0.971%
    assert rows[1].gg == pytest.approx(Decimal("0.825351"), abs=Decimal("0.0005"))
    assert rows[1].r == pytest.approx(Decimal("0.971"), abs=Decimal("0.001"))
    assert rows[0].margin > rows[1].margin


def test_screen_hk_payout_falls_back_to_dps_over_eps() -> None:
    provider = _FakeProvider()
    provider.indicators["09988.HK"]["divi_ratio"] = None
    provider.indicators["09988.HK"]["dps_hkd"] = 4.0
    provider.indicators["09988.HK"]["basic_eps"] = 5.0

    rows = _screen(provider)

    alibaba = next(row for row in rows if row.code == "09988.HK")
    assert alibaba.payout == pytest.approx(Decimal("80"), abs=Decimal("0.001"))
    assert alibaba.payout_ok is True


def test_screen_hk_clips_special_dividend_payout() -> None:
    provider = _FakeProvider()
    provider.indicators["09988.HK"]["divi_ratio"] = 1.4084  # >100%: special dividend

    rows = _screen(provider)

    alibaba = next(row for row in rows if row.code == "09988.HK")
    assert alibaba.payout == Decimal("100")
    assert alibaba.payout_ok is False


def test_screen_hk_converts_cny_reporter_to_hkd() -> None:
    provider = _FakeProvider()
    provider.indicators["09988.HK"]["currency"] = "CNY"
    provider.indicators["09988.HK"]["holder_profit"] = 9_200_000_000
    provider.cashflows["09988.HK"] = _cash("20251231", 11_040_000_000, 1_840_000_000) + _cash(
        "20241231", 9_200_000_000, 1_840_000_000
    )

    rows = _screen(provider)

    alibaba = next(row for row in rows if row.code == "09988.HK")
    fx = SETTINGS.fx.cny_per_hkd
    assert alibaba.currency == "CNY"
    # R = (9.2e9 / 0.92) x 92.8% / 2e11 = 4.64%
    expected_r = (Decimal("9200000000") / fx) * Decimal("0.928") / Decimal("200000000000") * 100
    assert alibaba.r == pytest.approx(expected_r, abs=Decimal("0.0005"))


def test_screen_hk_drops_rows_without_cashflow() -> None:
    provider = _FakeProvider()
    provider.cashflows["09988.HK"] = []
    stats: dict[str, int] = {}

    rows = _screen(provider, stats=stats)

    assert [row.code for row in rows] == ["00700.HK"]
    assert stats["drop_no_cashflow"] == 1


def test_screen_hk_quality_gates() -> None:
    provider = _FakeProvider()
    provider.indicators["00700.HK"]["roe_avg"] = 5.0  # below min_roe 8
    provider.indicators["09988.HK"]["debt_asset_ratio"] = 90.0  # above max 70

    stats: dict[str, int] = {}
    with pytest.raises(HkScreenError, match="produced no rows"):
        _screen(provider, stats=stats)

    assert stats["drop_quality"] == 2


def test_screen_hk_tolerates_missing_gross_margin() -> None:
    provider = _FakeProvider()
    provider.indicators["00700.HK"]["gross_profit_ratio"] = None

    rows = _screen(provider)

    assert [row.code for row in rows] == ["09988.HK", "00700.HK"]
    assert rows[1].gross_margin is None


def test_screen_hk_reports_funnel_stats() -> None:
    stats: dict[str, int] = {}
    _screen(stats=stats)

    assert stats["universe"] == 6
    assert stats["drop_gem"] == 1
    assert stats["drop_recent_ipo"] == 1
    assert stats["drop_usd"] == 2  # 00005.HK and 01299.HK are in USD_REPORTING_CODES
    assert stats["candidates"] == 2
    assert stats["rows"] == 2


def test_screen_hk_counts_market_cap_drops() -> None:
    stats: dict[str, int] = {}
    with pytest.raises(HkScreenError, match="produced no rows"):
        _screen(min_market_cap=Decimal("1000000000000"), stats=stats)

    assert stats["drop_market_cap"] == 2


def test_screen_hk_keeps_small_cap_above_threshold() -> None:
    provider = _FakeProvider()
    provider.indicators["09988.HK"]["total_market_cap"] = 3_000_000_000  # 30亿

    rows = _screen(provider)

    assert [row.code for row in rows] == ["00700.HK"]


def test_screen_hk_drops_missing_market_cap() -> None:
    provider = _FakeProvider()
    del provider.indicators["00700.HK"]["total_market_cap"]

    stats: dict[str, int] = {}
    rows = _screen(provider, stats=stats)

    assert [row.code for row in rows] == ["09988.HK"]
    assert stats["drop_no_market_cap"] == 1


def test_screen_hk_limit_and_missing_snapshot() -> None:
    rows = _screen(limit=1)
    assert len(rows) == 1
    with pytest.raises(HkScreenError, match="no HK quote snapshot"):
        _screen(trade_date="20261024")


def test_screen_hk_uses_documented_indicator_fields() -> None:
    from turtlefw.data.tushare_provider import HK_INDICATOR_FIELDS

    fields = set(HK_INDICATOR_FIELDS.split(","))
    assert "report_type" in fields
    assert "currency" in fields
    assert "pe_ttm" in fields
    assert "divi_ratio" in fields
    # hk_fina_indicator does not document ann_date; an unknown field makes
    # Tushare reject the whole request.
    assert "ann_date" not in fields


def test_screen_hk_accepts_annual_report_type_variants() -> None:
    provider = _FakeProvider()
    provider.indicators["00700.HK"]["report_type"] = "2025年年报"
    provider.indicators["09988.HK"]["report_type"] = "Q4"

    rows = _screen(provider)

    assert [row.code for row in rows] == ["09988.HK", "00700.HK"]


def test_screen_hk_records_market_source() -> None:
    provider = _FakeProvider()
    provider.hk_market_source = "yfinance:hk_daily"

    rows = _screen(provider, limit=1)

    assert rows[0].source.startswith("yfinance:hk_daily")


def test_screen_hk_does_not_fall_back_to_interim_indicator() -> None:
    class _NonDecemberProvider(_FakeProvider):
        def hk_indicator(self, code, *, period=None):
            if period:
                return None
            return self._indicator(
                roe=20,
                gross=30,
                debt=50,
                profit=1_000_000_000,
                market_cap=10_000_000_000,
                divi=0.5,
                eps=1.0,
                end="20250630",
                report_type="2025年中报",
            )

    with pytest.raises(HkScreenError, match="produced no rows"):
        _screen(_NonDecemberProvider(), limit=5)


class _UsdProvider(_FakeProvider):
    def reporting_currency(self, code):  # noqa: ANN001
        return Currency.USD if str(code) == "09988.HK" else Currency.HKD


def test_screen_hk_skips_usd_reporting_listing() -> None:
    provider = _UsdProvider()
    provider.indicators["09988.HK"]["currency"] = ""  # unknown -> yfinance check

    rows = _screen(provider)

    assert [row.code for row in rows] == ["00700.HK"]


def test_screen_hk_drops_rmb_counter_duplicate() -> None:
    provider = _FakeProvider()
    provider.universe.append(
        {
            "ts_code": "82333.HK",
            "name": "长城汽车-R",
            "market": "主板",
            "list_date": "20031215",
        }
    )
    provider.snapshot.append(
        {"ts_code": "82333.HK", "close": 12, "amount": 5_000_000_000}
    )
    provider.indicators["82333.HK"] = dict(provider.indicators["00700.HK"])
    provider.cashflows["82333.HK"] = provider.cashflows["00700.HK"]

    stats: dict[str, int] = {}
    rows = _screen(provider, stats=stats)

    assert stats["drop_rmb_counter"] == 1
    assert "82333.HK" not in [row.code for row in rows]


def test_write_ranking_exports_return_columns(tmp_path) -> None:
    rows = _screen()
    path = tmp_path / "ranking_hk.csv"
    write_ranking(path, rows)

    header = path.read_text(encoding="utf-8-sig").splitlines()[0].split(",")
    for column in ("R%", "GG%", "II%", "margin", "payout", "FCF yield%"):
        assert column in header
    assert "score" not in header
