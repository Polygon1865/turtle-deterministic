"""Freeze and verify a daily-run golden baseline (roadmap T1).

The golden file is a small JSON summary of one daily run: per-stock verdict,
key valuation metrics, QA/research state and claim counts.  It intentionally
ignores formatting, so a template change does not fail the baseline; only
conclusions or numbers do.

Usage::

    python scripts/golden.py freeze --date 2026-11-10
    python scripts/golden.py check --date 2026-11-10
    python scripts/golden.py check --date 2026-11-10 --tol 0.05
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_RUNS = Path(".runs") / "daily"
DEFAULT_GOLDEN = Path("tests") / "fixtures"

VERDICT_RE = re.compile(r"^\*\*(买入|观察|排除|减持)\*\* — (.+?)\s*$")
METRIC_KEYS = ("r", "gg", "ii", "margin", "floor", "premium", "payout", "price", "pb", "fcf_yield")
TEXT_FIELDS = ("name", "market", "status", "qa", "research", "verdict", "reason", "coverage")
COUNT_KEYS = ("stocks", "ok", "qa_pass", "research_on")


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, dict):
        value = value.get("value")
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _verdict(report: Path) -> tuple[str, str]:
    try:
        lines = report.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return "", ""
    for line in lines[:30]:
        match = VERDICT_RE.match(line.strip())
        if match:
            return match.group(1), match.group(2)
    return "", ""


def _claims(code_dir: Path) -> int:
    for name in ("research.json", "research_failed/research.json"):
        path = code_dir / "snapshot" / name
        if not path.is_file() and name.startswith("research_failed"):
            path = code_dir / name
        data = _read_json(path)
        claims = data.get("claims") if isinstance(data, dict) else None
        if isinstance(claims, list):
            return len(claims)
    return 0


def collect(day_dir: Path) -> dict:
    """Summarise one daily run directory into the golden shape."""

    status = _read_json(day_dir / "status.json")
    stocks: dict[str, dict] = {}
    for row in status.get("stocks", []):
        code = row.get("code") or ""
        if not code:
            continue
        code_dir = day_dir / code
        metrics = _read_json(code_dir / "snapshot" / "metrics.json")
        qa = _read_json(code_dir / "qa.json")
        verdict, reason = _verdict(code_dir / "analysis_report.md")
        qa_rows = qa.get("rows") if isinstance(qa.get("rows"), list) else []
        structure = next(
            (item for item in qa_rows if item.get("name") == "report_structure"), {}
        )
        stocks[code] = {
            "name": row.get("name", ""),
            "market": row.get("market", ""),
            "status": row.get("status", ""),
            "qa": row.get("qa", ""),
            "research": row.get("research", ""),
            "coverage": row.get("numeric_coverage", ""),
            "verdict": verdict,
            "reason": reason,
            "claims": _claims(code_dir),
            "metrics": {key: _number(metrics.get(key)) for key in METRIC_KEYS},
            "structure": structure.get("status", ""),
            "qa_fail": [item.get("name") for item in qa_rows if item.get("status") != "PASS"],
        }
    rows = list(stocks.values())
    return {
        "date": status.get("date", day_dir.name),
        "trade_date": status.get("trade_date", ""),
        "ok": bool(status.get("ok", False)),
        "counts": {
            "stocks": len(rows),
            "ok": sum(1 for item in rows if item["status"] == "ok"),
            "qa_pass": sum(1 for item in rows if item["qa"] == "PASS"),
            "research_on": sum(1 for item in rows if item["research"] == "on"),
        },
        "stocks": dict(sorted(stocks.items())),
    }


def compare(golden: dict, current: dict, *, tol: float = 0.01) -> list[tuple[str, str, object, object]]:
    """Return human-readable differences ``(code, field, old, new)``."""

    changes: list[tuple[str, str, object, object]] = []
    old_stocks = golden.get("stocks", {})
    new_stocks = current.get("stocks", {})
    for code in sorted(set(old_stocks) | set(new_stocks)):
        old = old_stocks.get(code)
        new = new_stocks.get(code)
        if old is None:
            changes.append((code, "stock", "缺失", "新增"))
            continue
        if new is None:
            changes.append((code, "stock", "存在", "消失"))
            continue
        for field in TEXT_FIELDS:
            if old.get(field) != new.get(field):
                changes.append((code, field, old.get(field), new.get(field)))
        if old.get("claims") != new.get("claims"):
            changes.append((code, "claims", old.get("claims"), new.get("claims")))
        old_metrics = old.get("metrics") or {}
        new_metrics = new.get("metrics") or {}
        for key in METRIC_KEYS:
            left, right = old_metrics.get(key), new_metrics.get(key)
            if left is None or right is None:
                if left != right:
                    changes.append((code, f"metrics.{key}", left, right))
                continue
            if abs(float(left) - float(right)) > tol:
                changes.append((code, f"metrics.{key}", left, right))
    for key in COUNT_KEYS:
        left = (golden.get("counts") or {}).get(key)
        right = (current.get("counts") or {}).get(key)
        if left != right:
            changes.append(("*", f"counts.{key}", left, right))
    return changes


def _format(changes: list[tuple[str, str, object, object]]) -> str:
    lines = []
    for code, field, old, new in changes:
        lines.append(f"  {code:<12} {field:<20} {old!s:<28} -> {new!s}")
    return "\n".join(lines)


def freeze(date: str, *, runs_root: Path, out: Path) -> int:
    day_dir = runs_root / date
    if not day_dir.is_dir():
        print(f"没有找到运行目录：{day_dir}", file=sys.stderr)
        return 1
    payload = collect(day_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    counts = payload["counts"]
    print(f"已冻结 {date} -> {out}")
    print(f"  股票 {counts['stocks']} 只；ok {counts['ok']}；QA PASS {counts['qa_pass']}；研究 on {counts['research_on']}")
    return 0


def check(date: str, *, runs_root: Path, golden_path: Path, tol: float, fail_on_diff: bool) -> int:
    if not golden_path.is_file():
        print(f"没有找到 golden 文件：{golden_path}", file=sys.stderr)
        return 2
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    day_dir = runs_root / date
    if not day_dir.is_dir():
        print(f"没有找到运行目录：{day_dir}", file=sys.stderr)
        return 1
    current = collect(day_dir)
    changes = compare(golden, current, tol=tol)
    if not changes:
        print(f"{date} 与 golden 一致（{current['counts']['stocks']} 只）。")
        return 0
    print(f"{date} 与 golden 有 {len(changes)} 处差异：")
    print(_format(changes))
    return 1 if fail_on_diff else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze/compare a daily-run golden baseline")
    sub = parser.add_subparsers(dest="command", required=True)

    freeze_parser = sub.add_parser("freeze", help="write a golden file for one day")
    freeze_parser.add_argument("--date", required=True)
    freeze_parser.add_argument("--runs-root", default=str(DEFAULT_RUNS))
    freeze_parser.add_argument("--out", default="")

    check_parser = sub.add_parser("check", help="compare a day against its golden file")
    check_parser.add_argument("--date", required=True)
    check_parser.add_argument("--runs-root", default=str(DEFAULT_RUNS))
    check_parser.add_argument("--golden", default="")
    check_parser.add_argument("--tol", type=float, default=0.01)
    check_parser.add_argument("--no-fail", action="store_true")

    args = parser.parse_args(argv)
    runs_root = Path(args.runs_root)
    if args.command == "freeze":
        out = Path(args.out) if args.out else DEFAULT_GOLDEN / f"golden-daily-{args.date}.json"
        return freeze(args.date, runs_root=runs_root, out=out)
    golden_path = Path(args.golden) if args.golden else DEFAULT_GOLDEN / f"golden-daily-{args.date}.json"
    return check(
        args.date,
        runs_root=runs_root,
        golden_path=golden_path,
        tol=args.tol,
        fail_on_diff=not args.no_fail,
    )


if __name__ == "__main__":
    raise SystemExit(main())
