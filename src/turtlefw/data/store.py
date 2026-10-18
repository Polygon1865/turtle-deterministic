"""Parquet-backed point-in-time storage for canonical statement rows."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Iterable

import pandas as pd

from ..types import Currency
from .normalize import rows_to_frame
from .protocol import StatementRow

_KEY = ["code", "period_end", "period_type", "statement", "item", "source"]


class StatementStore:
    """One Parquet file per ticker; de-duplicates on the natural key."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, code: str) -> Path:
        return self.root / f"{code}.parquet"

    def append(self, rows: Iterable[StatementRow]) -> int:
        frame = rows_to_frame(rows)
        if frame.empty:
            return 0
        by_code = {code: group for code, group in frame.groupby("code")}
        written = 0
        for code, group in by_code.items():
            path = self._path(code)
            if path.is_file():
                existing = pd.read_parquet(path)
                frame = pd.concat([existing, group], ignore_index=True)
            else:
                frame = group
            frame = frame.drop_duplicates(subset=_KEY, keep="last")
            frame = frame.sort_values(["period_end", "statement", "item"]).reset_index(drop=True)
            frame.to_parquet(path, index=False)
            written += len(group)
        return written

    def read(self, code: str) -> list[StatementRow]:
        path = self._path(code)
        if not path.is_file():
            return []
        frame = pd.read_parquet(path)
        rows: list[StatementRow] = []
        for record in frame.to_dict("records"):
            rows.append(
                StatementRow(
                    code=str(record["code"]),
                    period_end=date.fromisoformat(str(record["period_end"])),
                    period_type=str(record["period_type"]),
                    statement=str(record["statement"]),
                    item=str(record["item"]),
                    value=pd_decimal(record["value"]),
                    currency=Currency(str(record["currency"])),
                    source=str(record["source"]),
                    ann_date=(
                        date.fromisoformat(str(record["ann_date"]))
                        if record.get("ann_date")
                        else None
                    ),
                )
            )
        return rows

    def snapshot_id(self, code: str) -> str:
        """Stable hash of the stored rows, used to make reports reproducible."""
        rows = self.read(code)
        payload = "\n".join(
            f"{r.code}|{r.period_end}|{r.period_type}|{r.statement}|{r.item}|{r.value}|{r.source}"
            for r in sorted(
                rows,
                key=lambda r: (r.period_end, r.statement, r.item, r.source),
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def pd_decimal(raw: object):
    from decimal import Decimal

    return Decimal(str(raw))
