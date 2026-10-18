"""Deliverability gate for one analysis run.

Aggregates the artifacts and deterministic checks into PASS/FAIL rows so the
agent cannot claim completion while a required artifact is missing or a
narrative number is untraceable.
"""

from __future__ import annotations

from pathlib import Path

from . import narrative
from .qualitative import load as load_qualitative


def run_qa(code: str, root: Path | str = "output") -> list[tuple[str, str, str]]:
    base = Path(root) / str(code)
    rows: list[tuple[str, str, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        rows.append((name, "PASS" if ok else "FAIL", detail))

    state = base / "run_state.json"
    add("run_state", state.is_file(), "" if state.is_file() else "缺少 run_state.json")
    add("report", (base / "analysis_report.md").is_file())

    qpath = base / "qualitative.json"
    unknown = 0
    loaded = None
    if not qpath.is_file():
        add("qualitative", False, "缺少 qualitative.json")
    else:
        try:
            loaded = load_qualitative(qpath)
            items = loaded.items
            unknown = sum(1 for item in items.values() if item.judgment == "unknown")
            add("qualitative", True, f"{len(items)} 模块，{unknown} 个 unknown")
            add(
                "discrepancies",
                True,
                f"{len(loaded.discrepancies)} 条数字冲突已记录",
            )
        except Exception as exc:  # schema errors must fail the gate
            add("qualitative", False, str(exc))

    npath = base / "narrative.md"
    if npath.is_file():
        bad = narrative.check(str(code), npath, root=root)
        add("narrative", not bad, ", ".join(bad) if bad else "数字全部可追溯")
    else:
        add("narrative", True, "未提供（可选）")

    if loaded is not None and unknown and unknown == len(loaded.items):
        add("unknown_ratio", False, "全部模块 unknown，定性分析未完成")
    return rows


def failed(rows: list[tuple[str, str, str]]) -> list[str]:
    return [name for name, status, _ in rows if status == "FAIL"]
