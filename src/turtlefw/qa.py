"""Deliverability gate for one analysis run.

Aggregates the artifacts and deterministic checks into PASS/FAIL rows so the
agent cannot claim completion while a required artifact is missing or a
narrative number is untraceable.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from . import narrative
from .facts import ReportManifest
from .paths import output_root
from .qualitative import load as load_qualitative


def _pit_lookahead_check(base: Path) -> tuple[bool, str]:
    """No statement row may be announced after the snapshot's ``as_of``.

    A-shares carry ``ann_date`` so this is a real look-ahead guard.  HK rows
    usually have no announcement date, which the detail text reports honestly
    rather than pretending the check passed.
    """

    from .backtest import lookahead_audit

    snapshot = base / "snapshot"
    if not (snapshot / "inputs.json").is_file():
        return True, "未保存快照，跳过前视审计"
    audit = lookahead_audit(snapshot)
    return audit.clean, audit.summary()


def _verdict_record_check(base: Path, report: Path) -> tuple[bool, str]:
    """The verdict must carry its evidence hash, and match the report.

    T3: a verdict may only change together with its evidence.  The record lives
    next to the snapshot so the next day's diff can explain a flip instead of
    silently re-deciding.
    """

    path = base / "snapshot" / "verdict.json"
    if not path.is_file():
        return False, "缺少 snapshot/verdict.json（重新渲染以写入结论记录）"
    try:
        record = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        return False, f"verdict.json 无法解析：{exc}"
    if not isinstance(record, dict) or not record.get("evidence_hash"):
        return False, "verdict.json 缺少 evidence_hash"
    verdict = str(record.get("verdict", ""))
    if not verdict:
        return False, "verdict.json 缺少 verdict"
    if report.is_file():
        text = report.read_text(encoding="utf-8-sig")
        match = re.search(r"\*\*(买入|观察|排除|减持)\*\*", text)
        if match and match.group(1) != verdict:
            return False, f"报告结论 {match.group(1)} ≠ 记录 {verdict}"
    return True, f"{verdict} · evidence {str(record['evidence_hash'])[:10]}"


_REPORT_METRIC_LABELS: tuple[tuple[str, str], ...] = (
    ("粗算回报率 R", "r"),
    ("精算回报率 GG", "gg"),
    ("门槛 II", "ii"),
    ("安全边际", "margin"),
    ("底价（综合）", "floor"),
)


def _table_rows(text: str, *, limit_lines: int = 80) -> dict[str, str]:
    """First ``| label | value |`` row per label in the report's opening table."""
    rows: dict[str, str] = {}
    for line in text.splitlines()[:limit_lines]:
        match = re.match(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<value>[^|]*?)\s*\|\s*$", line)
        if not match:
            continue
        label = match.group("label").strip()
        if label not in rows:
            rows[label] = match.group("value").strip()
    return rows


def _citation_audit_check(base: Path) -> tuple[bool, str]:
    """W5.2: surface unreachable citations recorded by ``turtlefw.cli citations``.

    The audit itself needs network access, so it runs as a separate command and
    writes ``<day>/citations.json``.  QA only reads that cache: a missing file
    means the audit was not run (PASS with a note), not that citations are good.
    """

    path = base.parent / "citations.json"
    if not path.is_file():
        return True, "未运行引用审计（python -m turtlefw.cli citations）"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError:
        return False, "citations.json 无法解析"
    urls = payload.get("urls") if isinstance(payload, dict) else None
    if not isinstance(urls, dict):
        return True, "citations.json 无 urls 记录"
    code = base.name
    entries = [
        (url, entry)
        for url, entry in urls.items()
        if isinstance(entry, dict) and str(entry.get("code") or code) == code
    ]
    if not entries:
        return True, "该标的无可审计的 http(s) 引用"
    failed = [url for url, entry in entries if not entry.get("ok")]
    if failed:
        sample = "、".join(failed[:3])
        return False, f"{len(failed)}/{len(entries)} 条引用不可达：{sample}"
    return True, f"{len(entries)} 条引用可达"


def _report_consistency_check(base: Path, report: Path) -> tuple[bool, str]:
    """Cross-artifact invariant: the report must not disagree with its metrics.

    W5.3: every number and the final verdict appear in several artifacts (report
    header, summary table, factor tables, metrics.json, verdict.json).  This row
    compares the report's summary rows against the frozen ``display`` values so a
    renderer that reads a different source (or edits one table) becomes visible.
    """

    metrics_path = base / "snapshot" / "metrics.json"
    if not report.is_file() or not metrics_path.is_file():
        return True, "缺少报告或指标，跳过一致性检查"
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        return False, f"metrics.json 无法解析：{exc}"
    text = report.read_text(encoding="utf-8-sig")
    rows = _table_rows(text)
    problems: list[str] = []
    checked = 0
    for label, key in _REPORT_METRIC_LABELS:
        shown = rows.get(label)
        point = metrics.get(key)
        if shown is None or not isinstance(point, dict):
            continue
        expected = str(point.get("display") or "").strip()
        if not expected:
            continue
        checked += 1
        if shown != expected:
            problems.append(f"{label} 报告 {shown} ≠ 指标 {expected}")
    verdict_line = re.search(r"\*\*(买入|观察|排除|减持)\*\*", text)
    verdict_record = base / "snapshot" / "verdict.json"
    expected_verdict = ""
    if verdict_record.is_file():
        try:
            record = json.loads(verdict_record.read_text(encoding="utf-8-sig"))
        except ValueError:
            record = {}
        expected_verdict = str(record.get("verdict") or "")
    summary_verdict = rows.get("结论", "")
    if verdict_line and summary_verdict and summary_verdict in {"买入", "观察", "排除", "减持"}:
        checked += 1
        if verdict_line.group(1) != summary_verdict:
            problems.append(f"结论行 {verdict_line.group(1)} ≠ 汇总表 {summary_verdict}")
    if expected_verdict and verdict_line and verdict_line.group(1) != expected_verdict:
        problems.append(f"结论行 {verdict_line.group(1)} ≠ verdict.json {expected_verdict}")
    if problems:
        return False, "；".join(problems[:4])
    return True, f"{checked} 项数字/结论一致"




_RESEARCH_FALLBACK_WARN = 0.10


def _research_fallback_row(base: Path) -> tuple[str, str]:
    """Surface a run where most LLM research fell back to deterministic text.

    A fallback is not a failure, but 23/40 (57%) falling back was invisible on
    2026-10-29 and 10-30; above 10% the day gets a WARN row instead of a clean
    PASS.
    """

    path = base.parent / "status.json"
    if not path.is_file():
        return "PASS", "无当天 status.json（单票运行）"
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except ValueError as exc:
        return "WARN", f"status.json 无法解析：{exc}"
    stocks = payload.get("stocks") if isinstance(payload, dict) else None
    if not isinstance(stocks, list) or not stocks:
        return "PASS", "当天没有股票记录"
    fallback = [
        str(item.get("code"))
        for item in stocks
        if isinstance(item, dict) and str(item.get("research") or "") in {"fallback", "off"}
    ]
    rate = len(fallback) / len(stocks)
    if rate > _RESEARCH_FALLBACK_WARN:
        sample = "、".join(fallback[:5])
        return "WARN", f"研究回退 {len(fallback)}/{len(stocks)}（{rate:.0%} > 10%）：{sample}"
    return "PASS", f"研究回退 {len(fallback)}/{len(stocks)}（{rate:.0%}）"


def run_qa(code: str, root: Path | str | None = None, *, allow_missing_qualitative: bool = False) -> list[tuple[str, str, str]]:
    base = (Path(root) if root is not None else output_root()) / str(code)
    rows: list[tuple[str, str, str]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        rows.append((name, "PASS" if ok else "FAIL", detail))

    def add_status(name: str, status: str, detail: str = "") -> None:
        rows.append((name, status, detail))

    state = base / "run_state.json"
    add("run_state", state.is_file(), "" if state.is_file() else "缺少 run_state.json")
    report = base / "analysis_report.md"
    add("report", report.is_file())
    if report.is_file():
        from .report.lint import lint_report, summary as lint_summary

        findings = lint_report(report.read_text(encoding="utf-8-sig"))
        add("report_structure", not findings, lint_summary(findings))
    add("verdict_record", *_verdict_record_check(base, report))
    add("report_consistency", *_report_consistency_check(base, report))
    add("citation_audit", *_citation_audit_check(base))
    add("pit_lookahead", *_pit_lookahead_check(base))
    add_status("research_fallback_rate", *_research_fallback_row(base))

    try:
        from .data.coverage import capabilities
        from .types import StockCode

        cap_rows = capabilities(StockCode.parse(str(code)))
        missing = [row.label for row in cap_rows if row.status == "missing"]
        add(
            "data_coverage",
            not missing,
            "missing: " + ",".join(missing) if missing else "no missing capabilities",
        )
    except Exception as exc:
        add("data_coverage", False, str(exc))

    qpath = base / "qualitative.json"
    unknown = 0
    loaded = None
    if not qpath.is_file():
        if allow_missing_qualitative:
            add("qualitative", True, "未提供（research-only；1A/1B 未验证）")
            add("evidence", True, "未提供（可选）")
            add("discrepancies", True, "未提供（可选）")
        else:
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
            if qpath.is_file():
                from .research_bridge import bridge

                _, bridged = bridge(document)
                effective = load_qualitative(qpath)
                _, remaining = bridge(document, effective)
                add(
                    "research_bridge",
                    not remaining or "research_bridge" in effective.source,
                    "no bridgeable claims"
                    if not bridged
                    else f"modules: {','.join(bridged)}",
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

    research_file = base / "research.json"
    research_audit_path = base / "research_audit.json"
    if research_file.is_file():
        if not research_audit_path.is_file():
            add("research_audit", False, "缺少 research_audit.json")
        else:
            try:
                audit_payload = json.loads(
                    research_audit_path.read_text(encoding="utf-8-sig")
                )
                actual = hashlib.sha256(research_file.read_bytes()).hexdigest()
                expected = str(audit_payload.get("research_sha256", ""))
                status = str(audit_payload.get("status", ""))
                add(
                    "research_audit",
                    status == "pass" and bool(expected) and actual == expected,
                    f"status={status or 'missing'} "
                    f"claims={audit_payload.get('claims', '?')} "
                    f"dimensions={len(audit_payload.get('quality', {}).get('covered_dimensions', []))}",
                )
            except Exception as exc:
                add("research_audit", False, str(exc))

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
            fact_refs = len(audit_result["fact_refs"])
            suffix = "（metric-only）" if fact_refs == 0 else ""
            add(
                "research_refs",
                audit_result["status"] == "pass",
                f"metrics={len(audit_result['metric_refs'])} "
                f"facts={fact_refs} "
                f"errors={len(audit_result['errors'])}{suffix}",
            )
            quality = audit_result.get("quality", {})
            claims = int(quality.get("claims", 0)) if isinstance(quality, dict) else 0
            dimensions = (
                len(quality.get("covered_dimensions", []))
                if isinstance(quality, dict)
                else 0
            )
            coverage = (
                float(quality.get("claim_coverage", 0.0))
                if isinstance(quality, dict)
                else 0.0
            )
            add(
                "research_quality",
                claims >= 1 and dimensions >= 1,
                f"claims={claims} dimensions={dimensions} "
                f"coverage={coverage:.1%}",
            )
            grades = (
                quality.get("evidence_grades", {})
                if isinstance(quality, dict)
                else {}
            )
            external = (
                int(quality.get("external_evidence", 0))
                if isinstance(quality, dict)
                else 0
            )
            unsupported = (
                list(quality.get("high_without_external", []))
                if isinstance(quality, dict)
                else []
            )
            grade_text = "、".join(
                f"{key} {value}" for key, value in sorted(dict(grades).items())
            ) or "无证据"
            if unsupported:
                add_status(
                    "research_grade",
                    "warn",
                    f"{len(unsupported)} 条 high 判断无 A/B 来源（仅数据包）："
                    + "、".join(unsupported[:5]),
                )
            elif external:
                add(
                    "research_grade",
                    True,
                    f"外部来源 {external} 条（{grade_text}）",
                )
            else:
                add_status(
                    "research_grade",
                    "warn",
                    f"证据全部来自数据包/无外部来源（{grade_text}）",
                )
        except Exception as exc:
            add("research_refs", False, str(exc))
    add("payout_consistency", *_payout_consistency(base, str(code)))
    return rows


def _metric_value(point: object) -> float | None:
    if isinstance(point, dict):
        point = point.get("value", point.get("display"))
    try:
        return float(str(point))
    except (TypeError, ValueError):
        return None


def _payout_consistency(base: Path, code: str) -> tuple[bool, str]:
    """HK only: ranking payout (latest annual ratio) must match the report.

    The two artifacts previously used different fraction/percent rules and
    different year windows.  Arithmetic now lives in ``metrics.payout``; this
    row catches the remaining case where one side silently falls back to a
    different source.
    """

    if not code.upper().endswith(".HK"):
        return True, "非港股，跳过"
    ranking = base.parent / "ranking_hk.csv"
    if not ranking.is_file():
        return True, "无榜单文件"
    metrics_path = base / "snapshot" / "metrics.json"
    if not metrics_path.is_file():
        return True, "无快照指标"
    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - a broken snapshot is a QA finding
        return False, f"metrics.json 读取失败：{exc}"
    latest = _metric_value(payload.get("payout.latest"))
    if latest is None:
        return True, "报告无最新年支付率"
    try:
        with ranking.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("code") or row.get("ts_code") or "").strip() != code:
                    continue
                rank_value = _metric_value(row.get("payout"))
                if rank_value is None:
                    return True, "榜单无支付率"
                if abs(rank_value - latest) <= 0.01:
                    return True, f"榜单 {rank_value:.2f}% = 报告 {latest:.2f}%"
                return False, f"榜单 {rank_value:.2f}% vs 报告 {latest:.2f}%"
    except Exception as exc:  # noqa: BLE001
        return False, f"榜单读取失败：{exc}"
    return True, "榜单无此股票"


def payload(code: str, rows: list[tuple[str, str, str]]) -> dict[str, object]:
    if failed(rows):
        status = "fail"
    elif any(row_status == "WARN" for _, row_status, _ in rows):
        status = "warn"
    else:
        status = "pass"
    return {
        "code": str(code),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "status": status,
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


def warned(rows: list[tuple[str, str, str]]) -> list[str]:
    return [name for name, status, _ in rows if status == "WARN"]
