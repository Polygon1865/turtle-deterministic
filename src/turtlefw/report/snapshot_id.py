"""Source-row snapshot identifier shared by pack, report and CLI."""

from __future__ import annotations

import hashlib
from typing import Sequence

from ..data.protocol import StatementRow


def source_snapshot_id(rows: Sequence[StatementRow]) -> str:
    payload = "\n".join(
        f"{r.code}|{r.period_end}|{r.period_type}|{r.statement}|{r.item}|{r.value}|{r.source}"
        for r in sorted(rows, key=lambda r: (r.period_end, r.statement, r.item))
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
