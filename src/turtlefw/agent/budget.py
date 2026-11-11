"""Token/call budget shared by the role pipeline (ADR-06).

The daily job already spends ~370k input tokens for 40 stocks; a four-role
pipeline multiplies calls.  Budget must therefore be explicit and enforced at
the boundary, with a deterministic-only degradation when it runs out.
"""

from __future__ import annotations

from dataclasses import dataclass


class BudgetExceeded(RuntimeError):
    """Raised when a call would push usage past the configured limit."""

    def __init__(self, limit: int, requested: int) -> None:
        super().__init__(f"token budget exceeded: requested={requested} limit={limit}")
        self.limit = limit
        self.requested = requested


@dataclass(slots=True)
class TokenBudget:
    limit: int = 500_000
    used: int = 0
    calls: int = 0

    def charge(self, tokens: int) -> None:
        if tokens < 0:
            raise ValueError("tokens must be >= 0")
        if self.used + tokens > self.limit:
            raise BudgetExceeded(self.limit, self.used + tokens)
        self.used += tokens
        self.calls += 1

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.used)

    def to_dict(self) -> dict[str, int]:
        return {"limit": self.limit, "used": self.used, "calls": self.calls}
