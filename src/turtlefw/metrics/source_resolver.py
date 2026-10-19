"""SourceRank resolution: record-only → display-primary → engine-primary.

A ResolvedFact keeps every candidate. The policy only decides which value is
shown and, explicitly, which value (if any) is allowed to replace the engine
input. It never deletes the conflicting evidence.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence

from ..data.protocol import StatementRow
from ..facts import SourceValue, source_rank

POLICIES = ("record-only", "display-primary", "engine-primary")
ITEM_MAP = {
    "revenue": ("income", "revenue"),
    "net_income": ("income", "n_income_attr_p"),
    "ocf": ("cashflow", "n_cashflow_act"),
    "capex": ("cashflow", "c_pay_acq_const_fiolta"),
    "equity": ("balance", "total_hldr_eqy_exc_min_int"),
    "total_assets": ("balance", "total_assets"),
}


def _dec(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, TypeError):
        return None


def _display(value: Decimal) -> str:
    return f"{value / Decimal('1000000'):,.2f}"


def _candidate(
    key: tuple[str, str, str, str, str],
    value: Decimal,
    source: str,
    rank: int,
    *,
    confidence: str = "",
    ann_date: str = "",
    source_id: str = "",
    page: str = "",
    document_hash: str = "",
) -> SourceValue:
    return SourceValue(
        key=key,
        value=value,
        source=source,
        source_rank=rank,
        confidence=confidence,
        ann_date=ann_date,
        source_id=source_id,
        page=page,
        document_hash=document_hash,
        display=_display(value),
    )


def collect(
    rows: Iterable[StatementRow],
    reported_items: Sequence[Mapping[str, Any]],
    *,
    year: int | None = None,
) -> list[SourceValue]:
    row_list = list(rows)
    annual = [
        row for row in row_list if row.period_type == "annual"
    ]
    latest_by_item: dict[tuple[str, str], StatementRow] = {}
    for annual_row in annual:
        item_key = (annual_row.statement, annual_row.item)
        current_row = latest_by_item.get(item_key)
        if current_row is None or annual_row.period_end > current_row.period_end:
            latest_by_item[item_key] = annual_row
    candidates: list[SourceValue] = []
    for _item, (statement, canonical) in ITEM_MAP.items():
        found = latest_by_item.get((statement, canonical))
        if found is not None and (year is None or found.period_end.year <= year):
            fact_key = (
                found.code,
                found.period_end.isoformat(),
                found.statement,
                found.item,
                found.currency.value,
            )
            candidates.append(
                _candidate(
                    fact_key,
                    found.value,
                    source=found.source or "tushare",
                    rank=source_rank(found.source or "tushare"),
                    ann_date=found.ann_date.isoformat() if found.ann_date else "",
                    source_id=f"statement:{found.period_end.isoformat()}:{found.item}",
                )
            )
    for item in reported_items:
        canonical_pair = ITEM_MAP.get(str(item.get("item", "")))
        value = _dec(item.get("value"))
        if canonical_pair is None or value is None:
            continue
        statement, field = canonical_pair
        found = latest_by_item.get((statement, field))
        if found is None:
            continue
        if year is not None and found.period_end.year != year:
            continue
        fact_key = (
            found.code,
            found.period_end.isoformat(),
            statement,
            field,
            found.currency.value,
        )
        candidates.append(
            _candidate(
                fact_key,
                value,
                source="pdf",
                rank=1,
                confidence=str(item.get("confidence", "")),
                ann_date=found.ann_date.isoformat() if found.ann_date else "",
                source_id=f"pdf:{item.get('item')}:{item.get('page', '')}",
                page=str(item.get("page", "")),
            )
        )
    return candidates


def _sort_key(value: SourceValue) -> tuple[int, int, str, str]:
    confidence = {"high": 0, "medium": 1, "low": 2}.get(value.confidence.lower(), 9)
    return (value.source_rank, confidence, value.ann_date, value.source_id)


def solve(
    candidates: Iterable[SourceValue],
    *,
    policy: str = "record-only",
    tolerance_pct: Decimal = Decimal("1"),
    as_of: str | None = None,
) -> list[Any]:
    from ..facts import ResolvedFact

    if policy not in POLICIES:
        raise ValueError(f"unknown source policy: {policy}")
    grouped: dict[tuple[str, str, str, str, str], list[SourceValue]] = {}
    for candidate in candidates:
        if as_of and candidate.ann_date and candidate.ann_date > as_of:
            continue
        grouped.setdefault(candidate.key, []).append(candidate)
    resolved: list[ResolvedFact] = []
    for key, group in grouped.items():
        ordered = sorted(group, key=_sort_key)
        primary = ordered[0]
        max_diff = Decimal("0")
        for candidate in ordered[1:]:
            if primary.value == 0:
                continue
            diff = abs(candidate.value - primary.value) / abs(primary.value) * Decimal("100")
            max_diff = max(max_diff, diff)
        conflict = max_diff > tolerance_pct
        status = "conflict" if conflict else "agreed"
        display = primary if policy in ("display-primary", "engine-primary") else None
        engine = primary if policy == "engine-primary" else None
        reason = (
            f"rank {primary.source_rank}; max diff {max_diff:.2f}% "
            f"{'>' if conflict else '<='} {tolerance_pct}%"
        )
        resolved.append(
            ResolvedFact(
                key=key,
                primary=primary,
                candidates=tuple(ordered),
                status=status,
                diff_pct=max_diff,
                reason=reason,
                selected_for_display=display,
                selected_for_engine=engine,
            )
        )
    return sorted(resolved, key=lambda item: item.key)


def apply_engine(
    rows: Iterable[StatementRow], resolved: Iterable[Any]
) -> list[StatementRow]:
    replacements = {
        fact.key: fact.selected_for_engine
        for fact in resolved
        if fact.selected_for_engine is not None
    }
    out: list[StatementRow] = []
    for row in rows:
        key = (
            row.code,
            row.period_end.isoformat(),
            row.statement,
            row.item,
            row.currency.value,
        )
        selected = replacements.get(key)
        if selected is None:
            out.append(row)
        else:
            out.append(
                StatementRow(
                    code=row.code,
                    period_end=row.period_end,
                    period_type=row.period_type,
                    statement=row.statement,
                    item=row.item,
                    value=selected.value,
                    currency=row.currency,
                    source=f"resolved:{selected.source}",
                    ann_date=row.ann_date,
                )
            )
    return out


def to_payload(resolved: Iterable[Any]) -> list[dict[str, Any]]:
    def candidate(value: Any) -> dict[str, Any] | None:
        if value is None:
            return None
        return {
            "value": str(value.value),
            "source": value.source,
            "source_rank": value.source_rank,
            "confidence": value.confidence,
            "ann_date": value.ann_date,
            "source_id": value.source_id,
            "page": value.page,
            "display": value.display,
        }

    return [
        {
            "key": list(fact.key),
            "status": fact.status,
            "diff_pct": str(fact.diff_pct),
            "reason": fact.reason,
            "primary": candidate(fact.primary),
            "candidates": [candidate(value) for value in fact.candidates],
            "selected_for_display": candidate(fact.selected_for_display),
            "selected_for_engine": candidate(fact.selected_for_engine),
        }
        for fact in resolved
    ]


def render_markdown(payload: Sequence[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for fact in payload:
        key = fact.get("key", [])
        if not key:
            continue
        label = f"{key[2]}.{key[3]} @ {key[1]}"
        primary = fact.get("primary") or {}
        display = fact.get("selected_for_display") or {}
        lines.append(
            f"- **{label}**：{fact.get('status')}，主源 {primary.get('source')}="
            f"{primary.get('display')}；展示选择 {display.get('source') or '—'}；"
            f"{fact.get('reason')}"
        )
        for candidate in fact.get("candidates", []):
            if candidate is primary or candidate.get("source_id") == primary.get("source_id"):
                continue
            if fact.get("status") != "conflict":
                continue
            lines.append(
                f"  - 冲突：{candidate.get('source')} rank={candidate.get('source_rank')} "
                f"{candidate.get('display')} ({candidate.get('source_id')})"
            )
    return "\n".join(lines)
