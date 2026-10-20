"""Phase-2 readiness gate for PDF fact coverage."""

from __future__ import annotations

from dataclasses import dataclass

REQUIRED_FIELDS = (
    "accounts_receiv",
    "inventory",
    "contract_liab",
    "dps",
    "main_business",
    "capex_detail",
)


@dataclass(frozen=True)
class CoverageGate:
    statuses: dict[str, str]

    def missing(self) -> tuple[str, ...]:
        return tuple(
            field
            for field in REQUIRED_FIELDS
            if self.statuses.get(field) not in {"complete", "not_applicable"}
        )

    def phase2_ready(self) -> bool:
        return not self.missing()
