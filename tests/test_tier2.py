from decimal import Decimal

import pandas as pd

from turtlefw import demo
from turtlefw.config import load_settings
from turtlefw.screener.tier2 import run_tier2


class FakeProvider:
    issues: list = []

    def statements(self, code):
        return demo.demo_rows()

    def dividends(self, code):
        return demo.demo_dividends()

    def weekly(self, code):
        return [{"trade_date": "20261016", "close": 28.3, "high": 30.0, "low": 27.0}]

    def audit(self, code):
        return [{"end_date": "20251231", "audit_agency": "A", "audit_result": "标准无保留意见"}]


def frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ts_code": "600887.SH",
                "name": "示例",
                "channel": "main",
                "close": 28.3,
                "total_mv": 18_000_000.0,  # 万元
                "total_share": 636_000.0,  # 万股
            }
        ]
    )


class TestTier2:
    def test_produces_one_row(self):
        result = run_tier2(frame(), FakeProvider(), load_settings(), Decimal("1.8"), limit=1)
        assert len(result) == 1
        row = result.iloc[0]
        assert row["ts_code"] == "600887.SH"
        assert row["verdict"] in {"买入", "观察", "排除", "数据缺失"}
        assert row["R%"] is not None
        assert row["EV/EBITDA"] is not None

    def test_limit(self):
        result = run_tier2(frame(), FakeProvider(), load_settings(), Decimal("1.8"), limit=0)
        assert result.empty
