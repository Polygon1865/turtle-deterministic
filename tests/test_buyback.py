from __future__ import annotations

from datetime import date
from decimal import Decimal

from turtlefw.data.tushare_provider import TushareProvider
from turtlefw.types import StockCode


def test_buyback_amount_ignores_nan_rows() -> None:
    provider = object.__new__(TushareProvider)
    year = date.today().year
    provider.repurchase = lambda code: [  # type: ignore[method-assign]
        {"proc": "完成", "ann_date": f"{year}0101", "amount": "nan"},
        {"proc": "完成", "ann_date": f"{year}0102", "amount": "100"},
        {"proc": "完成", "ann_date": f"{year}0103", "amount": "200"},
    ]

    assert provider.buyback_amount(StockCode.parse("600887.SH"), years=1) == Decimal("200")
