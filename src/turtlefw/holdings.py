"""Sell discipline and a minimal portfolio layer (C6).

The framework is good at producing a daily verdict and bad at saying when to
leave: a position is re-decided every day from scratch, so a holding can stay
"买入" for months while the reason it was bought disappears, or flip to "排除"
for a reason that has nothing to do with the thesis.  This module adds explicit,
deterministic exit rules over the same artifacts the report already publishes.

Rules (each is a separate signal, so the reason is auditable):

- ``verdict_downgrade``: entry verdict was 买入 and today it is 观察/排除/减持.
- ``margin_lost``: safety margin < 0 (GG below the hurdle).
- ``value_trap``: two or more value-trap checks failed.
- ``stop_loss``: price fell past the position's stop-loss from entry price.
- ``floor_break``: price is below the computed floor (watch, not a forced sell).

Everything is read-only: the module never mutates the run directory and never
calls a data provider, so it can replay any archived day.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

_VERDICT_RE = re.compile(r"^\*\*(买入|观察|排除|减持)\*\*", re.MULTILINE)
_TRAP_RE = re.compile(r"\|\s*价值陷阱\s*\|\s*(\d+)\s*项")

SELL = "sell"
WATCH = "watch"

RULE_LABELS = {
    "verdict_downgrade": "结论降级",
    "margin_lost": "安全边际失守",
    "value_trap": "价值陷阱",
    "stop_loss": "止损",
    "floor_break": "跌破底价",
}


@dataclass(slots=True)
class Holding:
    code: str
    entry_date: str
    entry_price: Decimal | None = None
    entry_verdict: str = "买入"
    entry_margin: Decimal | None = None
    stop_loss: Decimal = Decimal("0.25")


@dataclass(slots=True)
class Snapshot:
    date: str
    verdict: str
    margin: Decimal | None
    price: Decimal | None
    floor: Decimal | None
    traps: int = 0
    evidence_hash: str = ""


@dataclass(slots=True)
class SellSignal:
    code: str
    rule: str
    severity: str
    reason: str

    @property
    def label(self) -> str:
        return RULE_LABELS.get(self.rule, self.rule)


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"none", "nan"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _metric(metrics: Mapping[str, Any], key: str) -> Decimal | None:
    point = metrics.get(key)
    if isinstance(point, Mapping):
        return _decimal(point.get("value"))
    return _decimal(point)


def load_holdings(path: Path | str) -> list[Holding]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise ValueError(f"cannot read holdings file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"holdings file is not valid JSON: {exc}") from exc
    rows = payload.get("holdings") if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        raise ValueError("holdings file must contain a 'holdings' list")
    holdings: list[Holding] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping) or not row.get("code"):
            raise ValueError(f"holding #{index} is missing a code")
        stop_loss = _decimal(row.get("stop_loss"))
        if stop_loss is None:
            stop_loss = Decimal("0.25")
        elif stop_loss > 1:
            raise ValueError(f"holding #{index} stop_loss must be a fraction (0-1)")
        holdings.append(
            Holding(
                code=str(row["code"]).upper(),
                entry_date=str(row.get("entry_date") or ""),
                entry_price=_decimal(row.get("entry_price")),
                entry_verdict=str(row.get("entry_verdict") or "买入"),
                entry_margin=_decimal(row.get("entry_margin")),
                stop_loss=stop_loss,
            )
        )
    return holdings


def snapshot_from_run(day_dir: Path | str, code: str) -> Snapshot | None:
    """Read one stock's published artifacts for one archived run day."""

    root = Path(day_dir) / code
    metrics_path = root / "snapshot" / "metrics.json"
    report_path = root / "analysis_report.md"
    if not metrics_path.is_file() or not report_path.is_file():
        return None
    metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    report = report_path.read_text(encoding="utf-8-sig")
    match = _VERDICT_RE.search(report)
    if match is None:
        return None
    traps_match = _TRAP_RE.search(report)
    evidence = ""
    record = root / "snapshot" / "verdict.json"
    if record.is_file():
        try:
            evidence = str(json.loads(record.read_text(encoding="utf-8-sig")).get("evidence_hash") or "")
        except (OSError, ValueError):
            evidence = ""
    return Snapshot(
        date=Path(day_dir).name,
        verdict=match.group(1),
        margin=_metric(metrics, "margin"),
        price=_metric(metrics, "price"),
        floor=_metric(metrics, "floor"),
        traps=int(traps_match.group(1)) if traps_match else 0,
        evidence_hash=evidence,
    )


def evaluate(holding: Holding, snapshot: Snapshot) -> tuple[SellSignal, ...]:
    signals: list[SellSignal] = []

    def add(rule: str, severity: str, reason: str) -> None:
        signals.append(SellSignal(holding.code, rule, severity, reason))

    if holding.entry_verdict == "买入" and snapshot.verdict in {"观察", "排除", "减持"}:
        add(
            "verdict_downgrade",
            SELL,
            f"买入 → {snapshot.verdict}（{snapshot.date}）",
        )
    if snapshot.margin is not None and snapshot.margin < 0:
        add("margin_lost", SELL, f"安全边际 {snapshot.margin:.2f}% < 0")
    if snapshot.traps >= 2:
        add("value_trap", SELL, f"价值陷阱 {snapshot.traps} 项")
    if (
        holding.entry_price is not None
        and snapshot.price is not None
        and snapshot.price <= holding.entry_price * (1 - holding.stop_loss)
    ):
        add(
            "stop_loss",
            SELL,
            f"现价 {snapshot.price} ≤ 买入价 {holding.entry_price} × (1 - {holding.stop_loss})",
        )
    if (
        snapshot.price is not None
        and snapshot.floor is not None
        and snapshot.price < snapshot.floor
    ):
        add("floor_break", WATCH, f"现价 {snapshot.price} < 底价 {snapshot.floor}")
    return tuple(signals)


def check(
    holdings: Sequence[Holding],
    day_dir: Path | str,
) -> list[tuple[Holding, Snapshot | None, tuple[SellSignal, ...]]]:
    results: list[tuple[Holding, Snapshot | None, tuple[SellSignal, ...]]] = []
    for holding in holdings:
        snapshot = snapshot_from_run(day_dir, holding.code)
        if snapshot is None:
            results.append((holding, None, ()))
            continue
        results.append((holding, snapshot, evaluate(holding, snapshot)))
    return results


SOFT_RULES = frozenset({"verdict_downgrade"})


def check_window(
    holdings: Sequence[Holding],
    day_dirs: Sequence[Path | str],
    *,
    confirm: int = 2,
) -> list[tuple[Holding, Snapshot | None, tuple[SellSignal, ...]]]:
    """Like :func:`check`, but soft rules must persist for ``confirm`` days.

    The archive shows the 1A/understandability veto flips verdicts back and forth
    on noise (00270: 买入→排除→买入→排除 within four days).  Selling on a single
    flip would have round-tripped four times, so ``verdict_downgrade`` is only
    escalated when it holds on every day of the window.  Hard rules (margin lost,
    value trap, stop loss) remain immediate because they are deterministic.
    """

    if not day_dirs:
        return []
    per_day = [check(holdings, day_dir) for day_dir in day_dirs]
    latest = per_day[-1]
    window = max(1, confirm)
    if len(per_day) < window:
        return latest
    results: list[tuple[Holding, Snapshot | None, tuple[SellSignal, ...]]] = []
    for index, (holding, snapshot, signals) in enumerate(latest):
        kept: list[SellSignal] = []
        for signal in signals:
            if signal.rule not in SOFT_RULES:
                kept.append(signal)
                continue
            streak = 0
            for day_result in reversed(per_day[-window:]):
                day_signals = day_result[index][2]
                if any(item.rule == signal.rule for item in day_signals):
                    streak += 1
                else:
                    break
            if streak >= window:
                kept.append(signal)
        results.append((holding, snapshot, tuple(kept)))
    return results


def _fmt(value: Decimal | None) -> str:
    return "—" if value is None else f"{value:.2f}"


def render(results: Sequence[tuple[Holding, Snapshot | None, tuple[SellSignal, ...]]]) -> str:
    lines = ["持仓检查"]
    sells = 0
    for holding, snapshot, signals in results:
        if snapshot is None:
            lines.append(f"- {holding.code}：当日无报告（跳过）")
            continue
        head = (
            f"- {holding.code}：{snapshot.verdict} ｜ margin {_fmt(snapshot.margin)} ｜ "
            f"价 {_fmt(snapshot.price)} / 底价 {_fmt(snapshot.floor)}"
        )
        if not signals:
            lines.append(head + " ｜ 无卖出信号")
            continue
        lines.append(head)
        for signal in signals:
            sells += int(signal.severity == SELL)
            lines.append(f"    - [{signal.severity}] {signal.label}：{signal.reason}")
    lines.append(f"合计：{sells} 条卖出信号")
    return "\n".join(lines)
