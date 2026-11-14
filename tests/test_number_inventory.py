"""W2.0 number inventory: the scanner must find bypassing renders, not noise."""

from __future__ import annotations

from pathlib import Path

import importlib.util
import sys

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inventory_numbers.py"


def _module():
    spec = importlib.util.spec_from_file_location("inventory_numbers", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses(slots=True) resolves annotations through sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SAMPLE = '''
def render(ledger, value):
    text = f"{value:.2f}%"
    label = ledger.display("r")
    other = f"{payload:,.1f}"
    rounded = value.quantize(Decimal("0.01"))
    return "{:.2f}".format(value)
'''


def test_scanner_counts_three_render_kinds_and_skips_ledger() -> None:
    module = _module()
    findings = module.scan_source(SAMPLE, "analysis.py")
    kinds = {finding.kind for finding in findings}
    assert kinds == {"fstring", "quantize", "format"}
    assert all(finding.function == "render" for finding in findings)
    # the ledger line itself is not a finding
    assert all('ledger.display' not in finding.snippet for finding in findings)


def test_scanner_reports_functions_and_lines() -> None:
    module = _module()
    findings = module.scan_source(SAMPLE, "pack.py")
    lines = [finding.line for finding in findings]
    assert lines == sorted(lines)
    assert findings[0].path == "pack.py"
    assert findings[0].line == 3


def test_repo_scan_is_non_empty_and_grouped() -> None:
    module = _module()
    findings = module.scan()
    assert len(findings) >= 10
    names = {finding.path for finding in findings}
    assert "analysis.py" in names and "pack.py" in names
    markdown = module.render(findings, limit=3)
    assert "合计：**" in markdown
    assert "| 文件 | 处数 | 最集中的函数 |" in markdown
    assert "归属建议" in markdown


def test_css_pseudo_selectors_are_not_counted() -> None:
    module = _module()
    css = "  .table-wrap table.kv td:first-child{width:38%;color:var(--muted)}"
    assert module.scan_source(css, "html.py") == []
