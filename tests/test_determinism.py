from decimal import Decimal

import pytest

from turtlefw import demo
from turtlefw.config import load_settings
from turtlefw.facts import (
    ReportManifest,
    canonical_json,
    config_payload,
    content_hash,
)
from turtlefw.report.pack import render_data_pack
from turtlefw.research import load as load_research
from turtlefw.types import Currency, Money


def _pack(as_of: str = "2026-10-16") -> str:
    return render_data_pack(
        demo.DEMO_CODE,
        demo.demo_rows(),
        demo.demo_dividends(),
        quote={"trade_date": as_of, "close": 28.2},
        history=[{"trade_date": "20261016", "close": 28.2, "high": 30.0, "low": 27.0}],
        market_cap=Money(demo.DEMO_MARKET_CAP, Currency.CNY),
        shares=demo.DEMO_SHARES,
        rf_pct=demo.DEMO_RF,
        settings=load_settings(),
        as_of=as_of,
    )


class TestCanonical:
    def test_stable_key_order_and_decimal(self):
        a = canonical_json({"b": Decimal("1.20"), "a": [1, 2]})
        b = canonical_json({"a": [1, 2], "b": Decimal("1.20")})
        assert a == b
        assert '"1.20"' in a

    def test_hash_changes_with_content(self):
        assert content_hash({"a": 1}) != content_hash({"a": 2})


class TestManifest:
    def test_snapshot_id_stable_and_excludes_created_at(self):
        base = dict(
            code="600887.SH",
            as_of="2025-12-31",
            currency="CNY",
            facts_hash="f",
            config_hash="c",
            research_hash="r",
            template_hash="t",
        )
        a = ReportManifest(**base, created_at="2026-01-01")
        b = ReportManifest(**base, created_at="2026-02-02")
        assert a.snapshot_id == b.snapshot_id
        assert a.snapshot_id != ReportManifest(**{**base, "facts_hash": "g"}).snapshot_id

    def test_config_payload_excludes_absolute_path(self):
        payload = config_payload(load_settings())
        assert "config_path" not in payload
        assert "screening" in payload


class TestReportDeterminism:
    def test_same_snapshot_same_bytes(self):
        assert _pack() == _pack()

    def test_as_of_changes_52w_window(self):
        # A fixed as-of must not depend on today's date.
        text = _pack("2026-10-16")
        assert "2026-10-16" in text


class TestResearchValidation:
    def _write(self, payload):
        import json
        import tempfile
        from pathlib import Path

        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        handle.write(json.dumps(payload, ensure_ascii=False))
        handle.close()
        return Path(handle.name)

    def test_valid_claim(self):
        path = self._write(
            {
                "evidence": [
                    {"id": "ev1", "url": "https://example.com/a", "quote": "原文"}
                ],
                "claims": [
                    {
                        "claim_id": "D2.1",
                        "dimension": "D2",
                        "statement": "品牌是护城河，R 为 {{metric:r}}",
                        "judgment": "positive",
                        "confidence": "high",
                        "evidence_ids": ["ev1"],
                    }
                ],
            },
        )
        try:
            assert len(load_research(path).claims) == 1
        finally:
            path.unlink(missing_ok=True)

    def test_raw_number_rejected(self):
        path = self._write(
            {
                "evidence": [
                    {"id": "ev1", "url": "https://example.com/a", "quote": "原文"}
                ],
                "claims": [
                    {
                        "claim_id": "D2.1",
                        "dimension": "D2",
                        "statement": "市场份额 30%",
                        "judgment": "positive",
                        "evidence_ids": ["ev1"],
                    }
                ],
            },
        )
        try:
            with pytest.raises(ValueError, match="raw numbers"):
                load_research(path)
        finally:
            path.unlink(missing_ok=True)

    def test_non_unknown_claims_need_evidence(self):
        path = self._write(
            {
                "evidence": [],
                "claims": [
                    {
                        "claim_id": "D2.1",
                        "dimension": "D2",
                        "statement": "品牌是护城河",
                        "judgment": "positive",
                        "evidence_ids": [],
                    }
                ],
            },
        )
        try:
            with pytest.raises(ValueError, match="requires evidence"):
                load_research(path)
        finally:
            path.unlink(missing_ok=True)
