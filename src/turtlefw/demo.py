"""A tiny synthetic dataset so the pipeline can be exercised without a token.

Numbers are fabricated for a fictional consumer company and must not be read
as investment data.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from .data.protocol import StatementRow
from .types import Currency, DividendEvent, StockCode

DEMO_CODE = StockCode.parse("600887")
DEMO_NAME = "示例食品（虚构）"
DEMO_RF = Decimal("1.80")
DEMO_MARKET_CAP = Decimal("180000000000")  # 1800 亿
DEMO_SHARES = Decimal("6360000000")

# year -> {item: yuan}
_INCOME = {
    2020: {"revenue": "96886000000", "n_income_attr_p": "7322000000", "operate_profit": "9200000000"},
    2021: {"revenue": "110600000000", "n_income_attr_p": "8710000000", "operate_profit": "10800000000"},
    2022: {"revenue": "123100000000", "n_income_attr_p": "9430000000", "operate_profit": "11900000000"},
    2023: {"revenue": "126100000000", "n_income_attr_p": "10400000000", "operate_profit": "13100000000"},
    2024: {"revenue": "115800000000", "n_income_attr_p": "8450000000", "operate_profit": "10800000000"},
}
_BALANCE = {
    2020: {"money_cap": "18000000000", "trad_asset": "2000000000", "st_borr": "5000000000",
           "lt_borr": "3000000000", "total_assets": "90000000000",
           "total_hldr_eqy_exc_min_int": "45000000000"},
    2021: {"money_cap": "21000000000", "trad_asset": "2500000000", "st_borr": "6000000000",
           "lt_borr": "3000000000", "total_assets": "100000000000",
           "total_hldr_eqy_exc_min_int": "50000000000"},
    2022: {"money_cap": "24000000000", "trad_asset": "3000000000", "st_borr": "7000000000",
           "lt_borr": "3500000000", "total_assets": "110000000000",
           "total_hldr_eqy_exc_min_int": "55000000000"},
    2023: {"money_cap": "26000000000", "trad_asset": "3500000000", "st_borr": "7500000000",
           "lt_borr": "3500000000", "total_assets": "118000000000",
           "total_hldr_eqy_exc_min_int": "60000000000"},
    2024: {"money_cap": "27000000000", "trad_asset": "4000000000", "st_borr": "8000000000",
           "lt_borr": "4000000000", "total_assets": "120000000000",
           "total_hldr_eqy_exc_min_int": "62000000000"},
}
_CASHFLOW = {
    2020: {"n_cashflow_act": "13000000000", "c_pay_acq_const_fiolta": "4000000000",
           "depr_fa_coga_dpba": "3500000000"},
    2021: {"n_cashflow_act": "14500000000", "c_pay_acq_const_fiolta": "4500000000",
           "depr_fa_coga_dpba": "3800000000"},
    2022: {"n_cashflow_act": "15200000000", "c_pay_acq_const_fiolta": "5000000000",
           "depr_fa_coga_dpba": "4000000000"},
    2023: {"n_cashflow_act": "16000000000", "c_pay_acq_const_fiolta": "5200000000",
           "depr_fa_coga_dpba": "4200000000"},
    2024: {"n_cashflow_act": "13800000000", "c_pay_acq_const_fiolta": "4800000000",
           "depr_fa_coga_dpba": "4400000000"},
}

# Fiscal year -> (per-share dividend, total cash paid)
_DIVIDENDS = {
    2021: ("1.20", "7632000000"),
    2022: ("1.30", "8268000000"),
    2023: ("1.40", "8904000000"),
    2024: ("1.35", "8586000000"),
}


def demo_rows() -> list[StatementRow]:
    rows: list[StatementRow] = []
    for year, items in _INCOME.items():
        for item, raw in items.items():
            rows.append(_row(year, "income", item, raw))
    for year, items in _BALANCE.items():
        for item, raw in items.items():
            rows.append(_row(year, "balance", item, raw))
    for year, items in _CASHFLOW.items():
        for item, raw in items.items():
            rows.append(_row(year, "cashflow", item, raw))
    return rows


def _row(year: int, statement: str, item: str, raw: str) -> StatementRow:
    return StatementRow(
        code=str(DEMO_CODE),
        period_end=date(year, 12, 31),
        period_type="annual",
        statement=statement,
        item=item,
        value=Decimal(raw),
        currency=Currency.CNY,
        source="demo",
        ann_date=date(year + 1, 4, 20),
    )


def demo_dividends() -> list[DividendEvent]:
    return [
        DividendEvent(
            fiscal_year=year,
            event_id=f"{year}-final",
            dps=Decimal(dps),
            currency=Currency.CNY,
            total=Decimal(total),
        )
        for year, (dps, total) in _DIVIDENDS.items()
    ]


def demo_closes() -> list[Decimal]:
    # 10 years of weekly closes, gently oscillating between 20 and 45.
    values: list[Decimal] = []
    for i in range(520):
        price = 30 + 8 * ((i % 104) / 104) - 4 * ((i % 260) / 260)
        values.append(Decimal(str(round(price, 2))))
    return values
