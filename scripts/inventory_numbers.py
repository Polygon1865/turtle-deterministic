"""Inventory numbers that reports render without going through MetricRegistry.

Roadmap W2.0: before migrating everything to ``MetricPoint`` we need to know
how many numbers still bypass the ledger, where they live, and who owns them.
The scanner is deliberately dumb and explicable:

* ``fstring``: an f-string with a numeric format spec (``:.2f``, ``,.1f``…)
* ``quantize``: ``Decimal.quantize`` / ``round`` formatting before insertion
* ``format``: ``"{:.2f}".format(...)`` / ``format(value, ".2f")``

It skips lines that already resolve through ``metric_ledger.display`` or
``{{metric:`` placeholders.  Usage::

    python scripts/inventory_numbers.py --out docs/report-numbers.md
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = ROOT / "src" / "turtlefw" / "report"
TARGETS = ("analysis.py", "pack.py", "industry.py", "market.py", "extras.py", "html.py")

# A numeric format spec must have a digit right before the type letter:
# ``:.2f``/``:38%`` yes; CSS pseudo selectors like ``:first-child`` no.
_NUMERIC_SPEC = re.compile(r":\s*[,0-9.]*[0-9][dfx%]")
# CSS declarations inside the inline stylesheet (``width:38%;color:…``) look
# like numeric renders; skip them unless the line is an f-string.
_CSS_DECL = re.compile(r"[a-z-]+\s*:\s*[^;{}]{1,80};")
# Numbers can also bypass the ledger through the shared formatters.
_FORMAT_HELPERS = re.compile(r"\b(?:_pct|_m|_ratio_pct|_num|_x)\(")
_WORD_FMT = re.compile(r"\{:\s*[,0-9.]*[dfx%]\}")
_LEDGER_MARKERS = ("metric_ledger.display", "{{metric:")


@dataclass(frozen=True, slots=True)
class Finding:
    path: str
    function: str
    line: int
    kind: str
    snippet: str


def _function_spans(tree: ast.AST) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            ends = [
                getattr(child, "end_lineno", None) or getattr(child, "lineno", node.lineno)
                for child in ast.walk(node)
            ]
            spans.append((node.lineno, max(ends), node.name))
    return spans


def _function_for(line: int, spans: Sequence[tuple[int, int, str]]) -> str:
    best = ("", -1)
    for start, end, name in spans:
        if start <= line <= end and start >= best[1]:
            best = (name, start)
    return best[0] or "<module>"


_REGISTRY_CALLS = ("add_metric(", "metric_ledger.add(", "registry.add(", "MetricPoint(")


def _paren_delta(line: str) -> int:
    return line.count("(") - line.count(")")


def scan_source(text: str, path: str) -> list[Finding]:
    """Return every numeric render that bypasses the metric ledger."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = ast.Module(body=[], type_ignores=[])
    spans = _function_spans(tree)
    findings: list[Finding] = []
    registry_depth = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if registry_depth > 0:
            # Inside an add_metric(...) call the display string is *meant* to be
            # preformatted — that value is registered, not rendered ad hoc.
            registry_depth += _paren_delta(line)
            continue
        if not line or line.startswith("#"):
            continue
        if any(marker in line for marker in _REGISTRY_CALLS):
            depth = _paren_delta(line)
            if depth > 0:
                registry_depth = depth
            continue
        if any(marker in line for marker in _LEDGER_MARKERS):
            continue
        if _CSS_DECL.search(line) and 'f"' not in line and "f'" not in line:
            continue
        kind = ""
        if ".format(" in line and (_WORD_FMT.search(line) or re.search(r"format\([^)]*[\"']\.[0-9]", line)):
            kind = "format"
        elif _NUMERIC_SPEC.search(line) or _WORD_FMT.search(line):
            kind = "fstring"
        elif ".quantize(" in line:
            kind = "quantize"
        elif _FORMAT_HELPERS.search(line):
            kind = "helper"
        if not kind:
            continue
        findings.append(
            Finding(
                path=path,
                function=_function_for(number, spans),
                line=number,
                kind=kind,
                snippet=line[:120],
            )
        )
    return findings


def scan(targets: Iterable[Path] = ()) -> list[Finding]:
    findings: list[Finding] = []
    for target in targets or [REPORT_DIR / name for name in TARGETS]:
        if not target.is_file():
            continue
        findings.extend(scan_source(target.read_text(encoding="utf-8"), str(target.name)))
    return findings


def render(findings: Sequence[Finding], *, limit: int = 12) -> str:
    by_file: dict[str, list[Finding]] = {}
    for finding in findings:
        by_file.setdefault(finding.path, []).append(finding)
    lines = [
        "# 报告里还没进 MetricRegistry 的数字（W2.0 盘点）",
        "",
        "由 `scripts/inventory_numbers.py` 生成；改动机器可读源，不要手改本文。",
        "口径：f-string 数字格式、`Decimal.quantize`、`format()`、以及 `_pct/_m/_ratio_pct/_num/_x` 等共享格式化函数；",
        "已走 `metric_ledger.display()` 或 `{{metric:…}}` 的行不计入。",
        "",
        f"合计：**{len(findings)}** 处，分布在 {len(by_file)} 个文件。",
        "",
        "| 文件 | 处数 | 最集中的函数 |",
        "| --- | --- | --- |",
    ]
    for name in sorted(by_file, key=lambda key: (-len(by_file[key]), key)):
        items = by_file[name]
        counter: dict[str, int] = {}
        for item in items:
            counter[item.function] = counter.get(item.function, 0) + 1
        top = max(counter.items(), key=lambda pair: (pair[1], pair[0]))
        lines.append(f"| `{name}` | {len(items)} | `{top[0]}` ({top[1]}) |")
    lines.append("")
    for name in sorted(by_file, key=lambda key: (-len(by_file[key]), key)):
        items = by_file[name]
        lines.extend([f"## `{name}`（{len(items)} 处）", "", "| 行 | 函数 | 方式 | 片段 |", "| --- | --- | --- | --- |"])
        for item in items[:limit]:
            snippet = item.snippet.replace("|", "\\|")
            lines.append(f"| {item.line} | `{item.function}` | {item.kind} | `{snippet}` |")
        if len(items) > limit:
            lines.append(f"| … | | | 其余 {len(items) - limit} 处 |")
        lines.append("")
    lines.extend(
        [
            "## 归属建议",
            "",
            "- `analysis.py` 的汇总表/因子表：应迁到 `MetricPoint`，数字由 registry 提供。",
            "- `pack.py` 的数据包行：多为原始行值，保留但标注 `source_fact_ids`。",
            "- `html.py`：只应格式化已解析的字符串，出现数字格式说明解析层漏了。",
            "- 每次迁移后重跑本脚本，数字应单调下降；W2.1 的验收是降到 0。",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/report-numbers.md")
    parser.add_argument("--limit", type=int, default=12)
    args = parser.parse_args(argv)
    findings = scan()
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(findings, limit=args.limit), encoding="utf-8")
    print(f"盘点 {len(findings)} 处 → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
