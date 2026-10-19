"""Append-only point-in-time (PIT) snapshot library.

Each snapshot is the full statement set known at a ``knowledge_date``. A query
for ``as_of`` selects the latest snapshot whose knowledge date is not after
``as_of`` and then keeps facts announced by that date. Restatements are
represented by writing a newer snapshot with the corrected row.

The library cannot invent vintages that were never captured. ``backfill``
seeds cumulative snapshots by announcement date from the currently available
data; that is useful for historical filtering but is not a substitute for a
real vendor vintage history.
"""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Iterator

from .data.protocol import StatementRow
from .facts import content_hash, file_hash
from .paths import output_root
from .types import Currency


class PitError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class PitSnapshot:
    code: str
    knowledge_date: str
    rows: tuple[StatementRow, ...]
    source: str = "tushare"
    backfill: bool = False
    snapshot_id: str = ""
    created_at: str = ""


@dataclass(frozen=True, slots=True)
class PitSelection:
    code: str
    as_of: str
    snapshot: PitSnapshot
    rows: tuple[StatementRow, ...]


def _row_payload(row: StatementRow) -> dict[str, Any]:
    return {
        "code": row.code,
        "period_end": row.period_end.isoformat(),
        "period_type": row.period_type,
        "statement": row.statement,
        "item": row.item,
        "value": str(row.value),
        "currency": row.currency.value,
        "source": row.source,
        "ann_date": row.ann_date.isoformat() if row.ann_date else None,
    }


def rows_payload(rows: Iterable[StatementRow]) -> list[dict[str, Any]]:
    return [_row_payload(row) for row in rows]


def _row_from(payload: dict[str, Any]) -> StatementRow:
    return StatementRow(
        code=str(payload["code"]),
        period_end=date.fromisoformat(str(payload["period_end"])),
        period_type=str(payload["period_type"]),
        statement=str(payload["statement"]),
        item=str(payload["item"]),
        value=Decimal(str(payload["value"])),
        currency=Currency(str(payload["currency"])),
        source=str(payload["source"]),
        ann_date=date.fromisoformat(str(payload["ann_date"])) if payload.get("ann_date") else None,
    )


def _as_of_date(value: date | str) -> date:
    return date.fromisoformat(value) if isinstance(value, str) else value


class PitStore:
    def __init__(self, root: Path | str | None = None) -> None:
        self.root = Path(root) if root is not None else output_root() / "pit"

    def _code_dir(self, code: str) -> Path:
        return self.root / str(code)

    def _index_path(self, code: str) -> Path:
        return self._code_dir(code) / "index.json"

    def _read_index(self, code: str) -> list[dict[str, Any]]:
        path = self._index_path(code)
        if not path.is_file():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return []
        entries = payload.get("snapshots", [])
        return entries if isinstance(entries, list) else []

    def _write_index(self, code: str, entries: list[dict[str, Any]]) -> None:
        path = self._index_path(code)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": 1, "snapshots": entries}
        temporary = path.with_suffix(".json.tmp")
        temporary.write_bytes(
            (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
                "utf-8"
            )
        )
        temporary.replace(path)

    @contextmanager
    def _lock(self, code: str, timeout: float = 10.0) -> Iterator[None]:
        lock = self._code_dir(code) / ".lock"
        lock.parent.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        handle = None
        while handle is None:
            try:
                handle = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() - started > timeout:
                    raise PitError(f"{code}: PIT store is locked")
                time.sleep(0.05)
        try:
            yield
        finally:
            if handle is not None:
                os.close(handle)
            lock.unlink(missing_ok=True)

    def write(
        self,
        code: str,
        rows: Iterable[StatementRow],
        knowledge_date: date | str,
        *,
        source: str = "tushare",
        backfill: bool = False,
    ) -> PitSnapshot:
        known = _as_of_date(knowledge_date).isoformat()
        row_list = tuple(
            sorted(rows, key=lambda r: (r.period_end, r.statement, r.item, r.source))
        )
        payload = {
            "schema_version": 1,
            "code": str(code),
            "knowledge_date": known,
            "source": source,
            "backfill": backfill,
            "rows": [_row_payload(row) for row in row_list],
        }
        snapshot_id = content_hash(payload)
        target = self._code_dir(code) / f"{known}_{snapshot_id[:12]}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file():
            target.write_bytes(
                (
                    json.dumps(
                        {**payload, "snapshot_id": snapshot_id},
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
            )
        created_at = datetime.now().isoformat(timespec="seconds")
        with self._lock(code):
            entries = [
                entry
                for entry in self._read_index(code)
                if entry.get("snapshot_id") != snapshot_id
            ]
            entries.append(
                {
                    "knowledge_date": known,
                    "snapshot_id": snapshot_id,
                    "row_count": len(row_list),
                    "facts_hash": file_hash(target),
                    "source": source,
                    "backfill": backfill,
                    "sequence": len(entries),
                    "created_at": created_at,
                    "path": target.name,
                }
            )
            self._write_index(code, entries)
        return PitSnapshot(
            code=str(code),
            knowledge_date=known,
            rows=row_list,
            source=source,
            backfill=backfill,
            snapshot_id=snapshot_id,
            created_at=created_at,
        )

    def freeze_backfill(
        self,
        code: str,
        rows: Iterable[StatementRow],
        *,
        source: str = "backfill",
    ) -> list[PitSnapshot]:
        """Create cumulative snapshots at each announcement date."""
        by_date: dict[str, list[StatementRow]] = {}
        undated: list[StatementRow] = []
        for row in rows:
            if row.ann_date is None:
                undated.append(row)
            else:
                by_date.setdefault(row.ann_date.isoformat(), []).append(row)
        if not by_date:
            return [self.write(code, list(undated), date.today(), source=source, backfill=True)]
        snapshots: list[PitSnapshot] = []
        cumulative: list[StatementRow] = list(undated)
        for known in sorted(by_date):
            cumulative.extend(by_date[known])
            snapshots.append(
                self.write(code, cumulative, known, source=source, backfill=True)
            )
        return snapshots

    def prune(self, code: str, keep: int = 5) -> int:
        """Keep the newest ``keep`` snapshots and return removed count."""
        if keep < 1:
            raise PitError("keep must be >= 1")
        with self._lock(code):
            entries = sorted(
                self._read_index(code),
                key=lambda entry: (
                    str(entry.get("knowledge_date", "")),
                    int(entry.get("sequence", 0)),
                ),
            )
            removed = entries[:-keep]
            kept = entries[-keep:]
            for entry in removed:
                (self._code_dir(code) / str(entry.get("path", ""))).unlink(missing_ok=True)
            for sequence, entry in enumerate(kept):
                entry["sequence"] = sequence
            self._write_index(code, kept)
            return len(removed)

    def list(self, code: str) -> list[dict[str, Any]]:        return sorted(
            self._read_index(code),
            key=lambda entry: (str(entry.get("knowledge_date", "")), int(entry.get("sequence", 0))),
        )

    def load(self, code: str, as_of: date | str) -> PitSelection:
        cutoff = _as_of_date(as_of).isoformat()
        candidates = [
            entry for entry in self._read_index(code) if str(entry.get("knowledge_date", "")) <= cutoff
        ]
        if not candidates:
            raise PitError(f"{code}: no PIT snapshot on or before {cutoff}")
        entry = max(
            candidates,
            key=lambda item: (str(item.get("knowledge_date", "")), int(item.get("sequence", 0))),
        )
        path = self._code_dir(code) / str(entry.get("path", ""))
        if not path.is_file():
            raise PitError(f"{code}: snapshot file missing: {path}")
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        rows = tuple(_row_from(row) for row in payload.get("rows", []))
        known = str(payload.get("knowledge_date", cutoff))
        dedup: dict[tuple[date, str, str], StatementRow] = {}
        for row in rows:
            key = (row.period_end, row.statement, row.item)
            current = dedup.get(key)
            if current is None or (row.ann_date or date.min) >= (current.ann_date or date.min):
                dedup[key] = row
        selected = tuple(
            row
            for row in dedup.values()
            if (row.ann_date is None and row.period_end <= _as_of_date(cutoff))
            or (row.ann_date is not None and row.ann_date <= _as_of_date(cutoff))
        )
        snapshot = PitSnapshot(
            code=str(payload.get("code", code)),
            knowledge_date=known,
            rows=rows,
            source=str(payload.get("source", "")),
            backfill=bool(payload.get("backfill", False)),
            snapshot_id=str(payload.get("snapshot_id", "")),
            created_at=str(entry.get("created_at", "")),
        )
        return PitSelection(code=str(code), as_of=cutoff, snapshot=snapshot, rows=selected)
