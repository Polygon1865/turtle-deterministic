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

# Accepted by the user on 2026-10-21: the 11 official PDFs contain only total
# capex, not a multi-row breakdown. This is a documented source limitation, not
# a missing parser.
ACCEPTED_NOT_APPLICABLE = {"capex_detail"}


@dataclass(frozen=True)
class CoverageGate:
    statuses: dict[str, str]

    def missing(self) -> tuple[str, ...]:
        return tuple(
            field
            for field in REQUIRED_FIELDS
            if self.statuses.get(field) not in {"complete", "not_applicable"}
        )

    def unaccepted_not_applicable(self) -> tuple[str, ...]:
        return tuple(
            field
            for field in REQUIRED_FIELDS
            if self.statuses.get(field) == "not_applicable"
            and field not in ACCEPTED_NOT_APPLICABLE
        )

    def phase2_ready(self) -> bool:
        return not self.missing() and not self.unaccepted_not_applicable()
