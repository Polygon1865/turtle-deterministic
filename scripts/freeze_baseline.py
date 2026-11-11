"""Freeze a full daily run as a diffable baseline (roadmap W0.0).

``scripts/golden.py`` (T1) answers "did the verdict/metrics move since the last
golden?".  This script answers the wider question the roadmap asks before any
口径 change: "what did the whole run look like before we touched it?" — every
stock's verdict, key metrics, claims/params count and artifact hashes.

Artifacts (report / metrics / qa) are copied to ``.runs/baseline/<date>/`` which
is git-ignored; the small files that actually need review live under
``baseline/`` and are safe to commit.

Usage::

    python scripts/freeze_baseline.py freeze --date 2026-11-10
    python scripts/freeze_baseline.py check  --date 2026-11-10
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS = Path(".runs") / "daily"
DEFAULT_OUT = Path("baseline")
DEFAULT_ARTIFACTS = Path(".runs") / "baseline"

VERDICT_RE = re.compile(r"^\*\*(买入|观察|排除|减持)\*\*(?:\s*[—-]\s*(.+))?", re.MULTILINE)
COLUMNS = (
    "code",
    "name",
    "market",
    "verdict",
    "reason",
    "r",
    "gg",
    "ii",
    "margin",
    "floor",
    "price",
    "qa",
    "claims",
    "params",
    "report_sha256",
)
NUMERIC_COLUMNS = ("r", "gg", "ii", "margin", "floor", "price")


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text or text.lower() in {"none", "nan"}:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _metric(metrics: Mapping[str, Any], key: str) -> Decimal | None:
    point = metrics.get(key)
    if isinstance(point, Mapping):
        return _decimal(point.get("value"))
    return _decimal(point)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _date_dir(date: str, runs_root: Path) -> Path:
    key = date.replace("-", "")
    if len(key) != 8:
        raise ValueError(f"invalid date {date!r}; expected YYYY-MM-DD")
    return runs_root / f"{key[:4]}-{key[4:6]}-{key[6:]}"


def collect(day_dir: Path) -> dict[str, Any]:
    status_path = day_dir / "status.json"
    if not status_path.is_file():
        raise ValueError(f"missing status.json under {day_dir}")
    status = json.loads(status_path.read_text(encoding="utf-8-sig"))
    rows: list[dict[str, Any]] = []
    hashes: dict[str, dict[str, str]] = {}
    for stock in status.get("stocks") or []:
        code = str(stock.get("code") or "")
        if not code:
            continue
        code_dir = day_dir / code
        report = code_dir / "analysis_report.md"
        metrics_path = code_dir / "snapshot" / "metrics.json"
        qa_path = code_dir / "qa.json"
        research_path = code_dir / "snapshot" / "research.json"
        text = report.read_text(encoding="utf-8-sig") if report.is_file() else ""
        match = VERDICT_RE.search(text)
        metrics: Mapping[str, Any] = {}
        if metrics_path.is_file():
            metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
        claims = params = 0
        if research_path.is_file():
            payload = json.loads(research_path.read_text(encoding="utf-8-sig"))
            claims = len(payload.get("claims") or [])
            params = len(payload.get("params") or [])
        entry: dict[str, Any] = {
            "code": code,
            "name": stock.get("name") or "",
            "market": stock.get("market") or "",
            "verdict": match.group(1) if match else "",
            "reason": (match.group(2) or "").strip() if match else "",
            "qa": stock.get("qa") or "",
            "claims": claims,
            "params": params,
            "report_sha256": _sha256(report) if report.is_file() else "",
        }
        for column in NUMERIC_COLUMNS:
            value = _metric(metrics, column)
            entry[column] = "" if value is None else f"{value:.4f}"
        rows.append(entry)
        hashes[code] = {
            name: _sha256(path)
            for name, path in (
                ("report", report),
                ("metrics", metrics_path),
                ("qa", qa_path),
            )
            if path.is_file()
        }
    return {
        "date": str(status.get("date") or day_dir.name),
        "trade_date": str(status.get("trade_date") or ""),
        "ok": bool(status.get("ok")),
        "stocks": len(rows),
        "rows": rows,
        "hashes": hashes,
    }


def _write_summary(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in COLUMNS})


def _copy_artifacts(day_dir: Path, target: Path) -> None:
    for code_dir in sorted(path for path in day_dir.iterdir() if path.is_dir()):
        code = code_dir.name
        report = code_dir / "analysis_report.md"
        if not report.is_file():
            continue
        destination = target / code
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(report, destination / "analysis_report.md")
        metrics = code_dir / "snapshot" / "metrics.json"
        if metrics.is_file():
            shutil.copyfile(metrics, destination / "metrics.json")
        qa = code_dir / "qa.json"
        if qa.is_file():
            shutil.copyfile(qa, destination / "qa.json")


def freeze(
    date: str,
    *,
    runs_root: Path = DEFAULT_RUNS,
    out: Path = DEFAULT_OUT,
    artifacts: Path | None = DEFAULT_ARTIFACTS,
) -> dict[str, Any]:
    day_dir = _date_dir(date, runs_root)
    payload = collect(day_dir)
    _write_summary(out / f"summary-{day_dir.name}.csv", payload["rows"])
    (out / f"hashes-{day_dir.name}.json").write_text(
        json.dumps(payload["hashes"], ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    meta = {key: payload[key] for key in ("date", "trade_date", "ok", "stocks")}
    (out / f"meta-{day_dir.name}.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if artifacts is not None:
        _copy_artifacts(day_dir, artifacts / day_dir.name)
    return payload


def _read_summary(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return {row["code"]: row for row in csv.DictReader(handle)}


def check(
    date: str,
    *,
    runs_root: Path = DEFAULT_RUNS,
    out: Path = DEFAULT_OUT,
) -> list[str]:
    day_dir = _date_dir(date, runs_root)
    frozen = _read_summary(out / f"summary-{day_dir.name}.csv")
    current = {row["code"]: row for row in collect(day_dir)["rows"]}
    diffs: list[str] = []
    for code in sorted(set(frozen) | set(current)):
        before = frozen.get(code)
        after = current.get(code)
        if before is None:
            diffs.append(f"{code}: 新增（基线没有）")
            continue
        if after is None:
            diffs.append(f"{code}: 消失（基线有）")
            continue
        for column in ("verdict",) + NUMERIC_COLUMNS:
            old = before.get(column, "")
            new = after.get(column, "")
            if old == new:
                continue
            if column in NUMERIC_COLUMNS and old and new:
                old_value = _decimal(old)
                new_value = _decimal(new)
                if old_value is not None and new_value is not None:
                    diffs.append(f"{code}: {column} {old} → {new}（Δ {new_value - old_value:+.4f}）")
                    continue
            diffs.append(f"{code}: {column} {old!r} → {new!r}")
    return diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="冻结/对比每日运行基线（W0.0）")
    sub = parser.add_subparsers(dest="command", required=True)
    freeze_parser = sub.add_parser("freeze", help="冻结某天为基线")
    freeze_parser.add_argument("--date", required=True)
    freeze_parser.add_argument("--runs-root", default=str(DEFAULT_RUNS))
    freeze_parser.add_argument("--out", default=str(DEFAULT_OUT))
    freeze_parser.add_argument(
        "--artifacts", default=str(DEFAULT_ARTIFACTS), help="报告/指标副本目录（默认 .runs/baseline）"
    )
    freeze_parser.add_argument("--no-artifacts", action="store_true")
    check_parser = sub.add_parser("check", help="与基线对比")
    check_parser.add_argument("--date", required=True)
    check_parser.add_argument("--runs-root", default=str(DEFAULT_RUNS))
    check_parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    if args.command == "freeze":
        payload = freeze(
            args.date,
            runs_root=Path(args.runs_root),
            out=Path(args.out),
            artifacts=None if args.no_artifacts else Path(args.artifacts),
        )
        print(
            f"基线已冻结 {payload['date']}：{payload['stocks']} 只 → "
            f"{(Path(args.out) / f'summary-{_date_dir(args.date, Path(args.runs_root)).name}.csv').resolve()}"
        )
        return 0
    diffs = check(args.date, runs_root=Path(args.runs_root), out=Path(args.out))
    if not diffs:
        print(f"与基线一致：{args.date}")
        return 0
    for line in diffs:
        print(line)
    print(f"共 {len(diffs)} 处差异")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
