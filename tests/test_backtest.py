"""Archive replay: look-ahead audit, verdict churn, and the QA guard."""

from __future__ import annotations

import json
from pathlib import Path

from turtlefw.backtest import (
    churn_rows,
    load_panel,
    lookahead_audit,
    render_markdown,
    write_report,
)
from turtlefw.qa import _pit_lookahead_check

AS_OF = "20261101"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _code_dir(day: Path, code: str, *, verdict: str, margin: str) -> Path:
    base = day / code
    _write_json(
        base / "snapshot" / "inputs.json",
        {
            "as_of": AS_OF,
            "rows": [
                {"code": code, "statement": "income", "item": "revenue", "ann_date": "20261028"},
                {"code": code, "statement": "income", "item": "net_income", "ann_date": "",},
            ],
        },
    )
    _write_json(
        base / "snapshot" / "metrics.json",
        {
            "r": {"value": "5.0"},
            "gg": {"value": "9.0"},
            "margin": {"value": margin},
            "floor": {"value": "4.6"},
            "price": {"value": "8.0"},
        },
    )
    (base / "analysis_report.md").write_text(
        f"**{verdict}** — 估值或数据仍待确认\n", encoding="utf-8"
    )
    return base


def _day(root: Path, date: str, stocks: list[tuple[str, str, str]]) -> Path:
    day = root / date
    _write_json(
        day / "status.json",
        {
            "date": date,
            "ok": True,
            "stocks": [
                {"code": code, "name": name, "market": market}
                for code, name, market in stocks
            ],
        },
    )
    for code, _name, _market in stocks:
        _code_dir(day, code, verdict="观察", margin="1.00")
    return day


class TestLookaheadAudit:
    def test_future_announcement_is_a_violation(self, tmp_path):
        base = _code_dir(tmp_path, "600000.SH", verdict="买入", margin="1.0")
        _write_json(
            base / "snapshot" / "inputs.json",
            {
                "as_of": AS_OF,
                "rows": [
                    {"code": "600000.SH", "statement": "income", "item": "revenue",
                     "ann_date": "20261028"},
                    {"code": "600000.SH", "statement": "income", "item": "net_income",
                     "ann_date": "20261105"},
                ],
            },
        )
        audit = lookahead_audit(base / "snapshot")
        assert not audit.clean
        assert audit.checked == 2
        assert audit.unknown == 0
        assert "ann_date=20261105" in audit.violations[0]
        assert "公告日晚于" in audit.summary()

    def test_rows_without_announcement_date_are_unknown_not_clean(self, tmp_path):
        base = _code_dir(tmp_path, "00002.HK", verdict="观察", margin="1.0")
        audit = lookahead_audit(base / "snapshot")
        assert audit.clean
        assert audit.checked == 1
        assert audit.unknown == 1
        assert "1 行缺公告日" in audit.summary()

    def test_missing_snapshot_is_reported_by_qa(self, tmp_path):
        ok, detail = _pit_lookahead_check(tmp_path)
        assert ok
        assert "未保存快照" in detail


class TestPanelAndChurn:
    def _archive(self, tmp_path: Path) -> Path:
        root = tmp_path / "daily"
        _day(root, "2026-11-01", [("600000.SH", "浦发银行", "A")])
        day2 = _day(root, "2026-11-02", [("600000.SH", "浦发银行", "A")])
        _code_dir(day2, "600000.SH", verdict="排除", margin="-2.5")
        return root

    def test_panel_reads_verdicts_and_metrics(self, tmp_path):
        report = load_panel(self._archive(tmp_path))
        assert report.dates == ["2026-11-01", "2026-11-02"]
        assert len(report.rows) == 2
        assert report.rows[1].verdict == "排除"
        assert report.rows[1].margin == -2.5

    def test_churn_counts_verdict_flips(self, tmp_path):
        report = load_panel(self._archive(tmp_path))
        assert len(report.churn) == 1
        row = report.churn[0]
        assert row.code == "600000.SH"
        assert row.flips == 1
        assert row.verdicts == ("观察", "排除")
        assert row.margin_span == 3.5

    def test_churn_is_ordered_by_flip_count(self):
        rows = [
            _panel_row("2026-11-01", "A", "买入", 1.0),
            _panel_row("2026-11-02", "A", "排除", 0.0),
            _panel_row("2026-11-01", "B", "观察", 1.0),
            _panel_row("2026-11-02", "B", "观察", 1.2),
        ]
        churn = churn_rows(rows)
        assert [row.code for row in churn] == ["A", "B"]
        assert churn[1].flips == 0

    def test_markdown_and_write(self, tmp_path):
        root = self._archive(tmp_path)
        report = load_panel(root)
        text = render_markdown(report, limit=5)
        assert "前视审计" in text
        assert "结论翻转" in text
        assert "600000.SH" in text
        out = tmp_path / "replay.md"
        path, _ = write_report(root, out, limit=5)
        assert path.read_text(encoding="utf-8") == text


def _panel_row(date: str, code: str, verdict: str, margin: float):
    from turtlefw.backtest import PanelRow

    return PanelRow(
        date=date,
        code=code,
        name=code,
        market="A",
        verdict=verdict,
        r=5.0,
        gg=9.0,
        margin=margin,
        floor=4.6,
        price=8.0,
    )
