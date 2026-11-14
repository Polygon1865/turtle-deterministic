"""W2.4 formula registry contract tests.

Every ``formula_id`` the codebase emits must resolve to a definition in
``turtlefw.metrics.formulas``.  When this test fails after adding a metric, the
fix is to register the formula (or extend a prefix rule), not to delete the
assertion.
"""

from __future__ import annotations

import re
from pathlib import Path

from turtlefw.metrics.formulas import EXPLICIT, PREFIXES, describe, resolve, unknown

SRC = Path(__file__).resolve().parents[1] / "src" / "turtlefw"
LITERAL = re.compile(r'formula_id="([^"]+)"')
PREFIX_EMIT = re.compile(r'formula_id=f"([^"{]*)\{')


def _source_files() -> list[Path]:
    return sorted(path for path in SRC.rglob("*.py") if "__pycache__" not in path.parts)


def test_every_literal_formula_id_resolves() -> None:
    missing: list[str] = []
    for path in _source_files():
        for match in LITERAL.finditer(path.read_text(encoding="utf-8")):
            formula_id = match.group(1)
            if resolve(formula_id) is None:
                missing.append(f"{path.relative_to(SRC)}: {formula_id}")
    assert missing == []


def test_dynamic_prefixes_are_registered() -> None:
    prefixes = {prefix for prefix, _, _ in PREFIXES}
    assert prefixes >= {"statement.", "balance.", "factor.", "policy."}
    emitted: set[str] = set()
    leading_placeholder: list[tuple[str, str]] = []
    for path in _source_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if 'formula_id=f"' not in line:
                continue
            for match in PREFIX_EMIT.finditer(line):
                prefix = match.group(1)
                if prefix:
                    emitted.add(prefix)
                else:
                    leading_placeholder.append((f"{path.name}:{number}", line.strip()))
    unregistered = sorted(prefix for prefix in emitted if prefix not in prefixes)
    assert unregistered == [], f"dynamic formula prefixes without a rule: {unregistered}"
    # ``f"{row_item}.pdf"`` starts with a placeholder; those ids are covered by
    # the suffix rule (".pdf"), which resolve() checks with endswith().
    for where, line in leading_placeholder:
        assert ".pdf" in prefixes and '.pdf"' in line, f"{where}: {line}"


def test_resolve_generated_ids() -> None:
    for formula_id in (
        "statement.income.revenue",
        "statement.cashflow.ocf",
        "balance.cash",
        "factor.r",
        "factor.gg",
        "policy.max_debt_ratio",
        "tax.hk_direct",
        "scenario.revenue_minus_10",
        "extras.fy_revenue",
        "dividends.events.pdf",
    ):
        formula = resolve(formula_id)
        assert formula is not None, formula_id
        assert formula.formula_id == formula_id


def test_unknown_ids_are_reported_sorted() -> None:
    assert resolve("nope.what") is None
    assert unknown(["z.unknown", "a.unknown", "returns.safety_margin"]) == [
        "a.unknown",
        "z.unknown",
    ]


def test_explicit_entries_are_complete() -> None:
    assert len(EXPLICIT) >= 19
    for formula_id, formula in EXPLICIT.items():
        assert formula.formula_id == formula_id
        assert formula.expression.strip()
        assert formula.owner.strip()
        assert "/" in formula.owner or "." in formula.owner


def test_describe_mentions_the_expression() -> None:
    assert "=" in describe("returns.safety_margin")
    assert "未登记" in describe("nope.what")
