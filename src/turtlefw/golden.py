"""Golden-set harness for qualitative agreement.

Labels are human judgments stored as CSV (one row per code+module). The scorer
compares them with the produced qualitative.json files and reports agreement,
coverage and unknown rate. It never writes into the qualitative files.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .qualitative import MODULES, load

JUDGMENTS = ("positive", "neutral", "negative", "unknown")
HEADER = ["code", "module", "human_judgment", "notes"]


@dataclass(frozen=True, slots=True)
class Label:
    code: str
    module: str
    judgment: str
    notes: str = ""


def write_template(path: Path | str, codes: list[str]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for code in codes:
            for module in MODULES:
                writer.writerow([code, module, "", ""])
    return path


def read_labels(path: Path | str) -> list[Label]:
    labels: list[Label] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            code = str(row.get("code", "")).strip()
            module = str(row.get("module", "")).strip()
            judgment = str(row.get("human_judgment", "")).strip().lower()
            if not code or module not in MODULES or judgment not in JUDGMENTS:
                continue
            labels.append(Label(code, module, judgment, str(row.get("notes", "") or "")))
    return labels


def score(labels: list[Label], root: Path | str = "output") -> dict:
    per_module: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    missing: set[str] = set()
    predicted_unknown = 0
    total = 0
    matched = 0
    cache: dict[str, object] = {}

    for label in labels:
        qpath = Path(root) / label.code / "qualitative.json"
        if not qpath.is_file():
            missing.add(label.code)
            continue
        if label.code not in cache:
            cache[label.code] = load(qpath)
        qualitative = cache[label.code]
        item = qualitative.get(label.module)
        actual = item.judgment if item else "unknown"
        total += 1
        if actual == "unknown":
            predicted_unknown += 1
        per_module[label.module][1] += 1
        if actual == label.judgment:
            matched += 1
            per_module[label.module][0] += 1

    return {
        "total": total,
        "matched": matched,
        "agreement": (matched / total) if total else 0.0,
        "missing": sorted(missing),
        "predicted_unknown": predicted_unknown,
        "per_module": {
            module: {
                "matched": counts[0],
                "total": counts[1],
                "agreement": (counts[0] / counts[1]) if counts[1] else 0.0,
            }
            for module, counts in per_module.items()
        },
    }


def format_report(result: dict) -> str:
    lines = [
        f"黄金集一致率：{result['matched']}/{result['total']} "
        f"= {result['agreement'] * 100:.1f}%"
    ]
    for module, counts in result["per_module"].items():
        lines.append(
            f"  {module:<18}{counts['matched']:>3}/{counts['total']:<3}"
            f"{counts['agreement'] * 100:>6.1f}%"
        )
    if result["missing"]:
        lines.append("缺少 qualitative.json：" + ", ".join(result["missing"]))
    if result["total"]:
        lines.append(
            f"模型判为 unknown：{result['predicted_unknown']}/{result['total']}"
        )
    return "\n".join(lines)
