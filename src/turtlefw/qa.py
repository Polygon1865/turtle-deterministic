"""Deliverability gate for one analysis run.

Aggregates the artifacts and deterministic checks into PASS/FAIL rows so the
agent cannot claim completion while a required artifact is missing or a
narrative number is untraceable.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from datetime import datetime

from . import narrative
from .facts import ReportManifest
from .paths import output_root
from .qualitative import load as load_qualitative


def run_qa(code: str, root: Path | str | None = None) -> list[tuple[str, str, str]]:
    base = (Path(root) if root is not None else output_root()) / str(code)
    rows: list[tuple[str, str, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        rows.append((name, "PASS" if ok else "FAIL", detail))

    state = base / "run_state.json"
    add("run_state", state.is_file(), "" if state.is_file() else "缺少 run_state.json")
    add("report", (base / "analysis_report.md").is_file())

    try:
        from .data.coverage import capabilities
        from .types import StockCode

        cap_rows = capabilities(StockCode.parse(str(code)))
        missing = [row.label for row in cap_rows if row.status == "missing"]
        add(
            "data_coverage",
            True,
            "missing: " + ",".join(missing) if missing else "no missing capabilities",
        )
    except Exception as exc:
        add("data_coverage", False, str(exc))

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
            bad_evidence = [
                key
                for key, item in items.items()
                if item.judgment != "unknown" and not item.evidence
            ]
            add(
                "evidence",
                not bad_evidence,
                "" if not bad_evidence else "缺少证据：" + ",".join(bad_evidence),
            )
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

    rpath = base / "research.json"
    if rpath.is_file():
        from .research import load as load_research

        try:
            document = load_research(rpath)
            add(
                "research",
                True,
                f"{len(document.claims)} claims, "
                f"{len(document.params)} params, "
                f"{len(document.decisions)} decisions",
            )
        except Exception as exc:
            add("research", False, str(exc))

    provenance_path = base / "research_provenance.json"
    if provenance_path.is_file():
        try:
            provenance = json.loads(provenance_path.read_text(encoding="utf-8-sig"))
            research_file = base / "research.json"
            actual = (
                hashlib.sha256(research_file.read_bytes()).hexdigest()
                if research_file.is_file()
                else ""
            )
            expected = str(provenance.get("research_sha256", ""))
            add(
                "research_provenance",
                bool(expected) and actual == expected,
                f"provider={provenance.get('provider', '')} "
                f"model={provenance.get('model', '')}",
            )
        except Exception as exc:
            add("research_provenance", False, str(exc))
    else:
        add("research_provenance", True, "未提供（可选）")

    if loaded is not None and unknown and unknown == len(loaded.items):
        add("unknown_ratio", False, "全部模块 unknown，定性分析未完成")

    manifests = [base / "manifest.json", *sorted(base.glob("*/manifest.json"))]
    report_file = base / "analysis_report.md"
    report_hash = ""
    if report_file.is_file():
        report_hash = hashlib.sha256(report_file.read_bytes()).hexdigest()
    matching: list[tuple[Path, ReportManifest]] = []
    matching_without_coverage: list[tuple[Path, ReportManifest]] = []
    for candidate in manifests:
        if not candidate.is_file():
            continue
        try:
            parsed = ReportManifest.read(candidate)
        except Exception:
            continue
        if report_hash and parsed.report_hash == report_hash:
            if parsed.numeric_coverage:
                matching.append((candidate, parsed))
            else:
                matching_without_coverage.append((candidate, parsed))
    if not matching and matching_without_coverage:
        matching = matching_without_coverage[:1]
    if matching:
        def _sources_exist(item: tuple[Path, ReportManifest]) -> bool:
            candidate, parsed = item
            return all(
                (candidate.parent / name).is_file()
                for name in parsed.numeric_sources
            )

        usable = [item for item in matching if _sources_exist(item)]
        if usable:
            matching = usable
        matching.sort(
            key=lambda item: item[0].stat().st_mtime if item[0].is_file() else 0,
            reverse=True,
        )
    if not matching:
        for candidate in sorted(manifests, key=lambda item: item.stat().st_mtime if item.is_file() else 0, reverse=True):
            if not candidate.is_file():
                continue
            try:
                parsed = ReportManifest.read(candidate)
            except Exception:
                continue
            if parsed.numeric_coverage:
                matching.append((candidate, parsed))
                break
    if not matching:
        add("numeric_coverage", False, "缺少匹配当前报告的 manifest（需 report --save-snapshot）")
    else:
        try:
            manifest_path, manifest = matching[0]
            snapshot_dir = manifest_path.parent
            audit_path = snapshot_dir / "numeric_audit.json"
            from .facts import file_hash
            from .numeric_audit import audit as numeric_audit

            if not manifest.numeric_hash:
                add("numeric_coverage", False, "manifest 缺少 numeric_hash")
            elif not audit_path.is_file():
                add("numeric_coverage", False, "缺少 numeric_audit.json")
            elif file_hash(audit_path) != manifest.numeric_hash:
                add("numeric_coverage", False, "numeric_hash mismatch")
            else:
                source_paths = [snapshot_dir / name for name in manifest.numeric_sources]
                missing = [path.name for path in source_paths if not path.is_file()]
                if missing:
                    add("numeric_coverage", False, "numeric 来源缺失：" + ",".join(missing))
                else:
                    recomputed = numeric_audit(report_file, source_paths)
                    same_unknown = sorted(str(item) for item in manifest.numeric_unknown) == [
                        str(item) for item in recomputed["unknown"]
                    ]
                    manifest_coverage = float(manifest.numeric_coverage or 0)
                    passed = (
                        float(recomputed["coverage"]) >= 0.9999
                        and str(recomputed["status"]) == "pass"
                        and abs(manifest_coverage - float(recomputed["coverage"])) < 1e-9
                        and same_unknown
                    )
                    add(
                        "numeric_coverage",
                        passed,
                        f"recomputed={float(recomputed['coverage']):.4f} "
                        f"manifest={manifest.numeric_coverage or 'missing'} "
                        f"unknown={len(recomputed['unknown'])}",
                    )
        except Exception as exc:
            add("numeric_coverage", False, f"numeric audit 复算失败：{exc}")

    research_file = base / "research.json"
    if research_file.is_file() and matching:
        try:
            from .research import audit as research_audit
            from .research import load as load_research

            snapshot_dir = matching[0][0].parent
            metrics: dict[str, str] = {}
            metrics_path = snapshot_dir / "metrics.json"
            if metrics_path.is_file():
                payload = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
                for key, point in payload.items():
                    if isinstance(point, dict):
                        metrics[str(key)] = str(
                            point.get("display", point.get("value", ""))
                        )
            facts: dict[str, str] = {}
            for name in ("evidence.json", "reported_numbers.json"):
                path = snapshot_dir / name
                if not path.is_file():
                    continue
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                raw_items = (
                    payload
                    if isinstance(payload, list)
                    else payload.get("document_facts", [])
                )
                for item in raw_items:
                    if isinstance(item, dict) and item.get("id"):
                        facts[str(item["id"])] = str(
                            item.get("quote", item.get("value", ""))
                        )
            audit_result = research_audit(load_research(research_file), metrics, facts)
            add(
                "research_refs",
                audit_result["status"] == "pass",
                f"metrics={len(audit_result['metric_refs'])} "
                f"facts={len(audit_result['fact_refs'])} "
                f"errors={len(audit_result['errors'])}",
            )
            quality = audit_result.get("quality", {})
            claims = int(quality.get("claims", 0)) if isinstance(quality, dict) else 0
            dimensions = (
                len(quality.get("covered_dimensions", []))
                if isinstance(quality, dict)
                else 0
            )
            add(
                "research_quality",
                claims >= 1 and dimensions >= 1,
                f"claims={claims} dimensions={dimensions}",
            )
        except Exception as exc:
            add("research_refs", False, str(exc))
    return rows


def payload(code: str, rows: list[tuple[str, str, str]]) -> dict[str, object]:
    return {
        "code": str(code),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": "pass" if not failed(rows) else "fail",
        "rows": [
            {"name": name, "status": status, "detail": detail}
            for name, status, detail in rows
        ],
    }


def write_json(
    code: str,
    rows: list[tuple[str, str, str]],
    path: Path | str | None = None,
    root: Path | str | None = None,
) -> Path:
    target = (
        Path(path)
        if path is not None
        else (Path(root) if root is not None else output_root()) / str(code) / "qa.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(
        (json.dumps(payload(code, rows), ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
    )
    return target


def failed(rows: list[tuple[str, str, str]]) -> list[str]:
    return [name for name, status, _ in rows if status == "FAIL"]
