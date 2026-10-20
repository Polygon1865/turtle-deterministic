"""Attach a research document to an existing frozen snapshot without refetching."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from decimal import Decimal
from pathlib import Path

from ..facts import file_hash
from ..metrics import grids, statements
from ..paths import output_root
from ..types import Currency, Money, StockCode
from .. import state as st
from ..research import load as load_research
from ..research import quality as research_quality
from ..research import snapshot_audit
from ..research import engine_decisions
from . import snapshot as snap
from .html import convert_file
from ..pdf.fact_hash import pdf_facts_hash
from .manifest import build_manifest
from .pack import render_data_pack


class FinalizeError(Exception):
    pass


def finalize_research(
    snapshot_dir: Path | str,
    research_path: Path | str,
    out_dir: Path | str,
    *,
    report_path: Path | str | None = None,
    strict: bool = False,
    min_claims: int = 0,
    min_dimensions: int = 0,
    html: bool = False,
    allow_research_decisions: bool = False,
) -> Path:
    source = Path(snapshot_dir)
    target = Path(out_dir)
    research_file = Path(research_path)
    if not source.is_dir():
        raise FinalizeError(f"snapshot 不存在：{source}")
    if not research_file.is_file():
        raise FinalizeError(f"research 不存在：{research_file}")
    if source.resolve() == target.resolve():
        raise FinalizeError("out 不能与旧 snapshot 相同；finalize 必须写到新目录")
    if target.exists():
        raise FinalizeError(f"out 已存在：{target}")

    document = load_research(research_file)
    quality = research_quality(document)
    covered = quality["covered_dimensions"]
    if len(document.claims) < min_claims:
        raise FinalizeError(
            f"claims {len(document.claims)} < min_claims {min_claims}"
        )
    if len(covered) < min_dimensions:
        raise FinalizeError(
            f"dimensions {len(covered)} < min_dimensions {min_dimensions}"
        )
    decisions = engine_decisions(document, allow=allow_research_decisions)

    shutil.copytree(source, target)
    (target / "research.json").write_bytes(research_file.read_bytes())
    provenance = research_file.with_name("research_provenance.json")
    if provenance.is_file():
        shutil.copyfile(provenance, target / "research_provenance.json")

    inputs, settings = snap.load(target)
    pdf_fact_hash = pdf_facts_hash(
        {
            "document_facts": inputs.document_facts,
            "fact_rows": inputs.fact_rows,
            "dps": inputs.dps_fact,
        }
    )
    # Identity fields (facts/config/research/template/versions) do not include
    # report/metrics hashes, so the final snapshot id is available before
    # rendering. Use it for the header and the final manifest.
    final_snapshot_id = build_manifest(
        inputs, settings, target, pdf_fact_hash=pdf_fact_hash
    ).snapshot_id
    pack_path = target / "data_pack.md"
    if decisions:
        code = StockCode.parse(inputs.code)
        currency = Currency(inputs.currency)
        pack_path.write_text(
            render_data_pack(
                code,
                inputs.rows,
                inputs.dividends,
                quote=inputs.quote,
                history=inputs.history,
                market_cap=Money(Decimal(inputs.market_cap), currency),
                shares=Decimal(inputs.shares),
                diluted_shares=statements.diluted_shares(inputs.rows),
                rf_pct=Decimal(inputs.rf_pct),
                settings=settings,
                issues=inputs.issues,
                tax_pct=grids.default_tax_rate(code),
                rf_source=inputs.rf_source,
                parent_cash=Decimal(inputs.parent_cash) if inputs.parent_cash else None,
                pledge_pct=Decimal(inputs.pledge_pct) if inputs.pledge_pct else None,
                buyback=Money(Decimal(inputs.buyback), currency) if inputs.buyback else None,
                sbc=Money(Decimal(inputs.sbc), currency) if inputs.sbc else None,
                pdf_bridge=inputs.pdf_bridge,
                holders=inputs.holders,
                main_business=inputs.main_business,
                as_of=inputs.as_of,
                footnotes=inputs.footnotes,
                pdf_sections=inputs.pdf_sections,
                pit_note=inputs.pit_note,
                decisions=decisions,
                snapshot_id=final_snapshot_id,
                document_facts=inputs.document_facts,
            ),
            encoding="utf-8",
        )
    elif pack_path.is_file():
        pack_text = pack_path.read_text(encoding="utf-8")
        pack_text = re.sub(
            r"(数据快照：`)[0-9a-f]{8,32}(`)",
            rf"\g<1>{final_snapshot_id}\g<2>",
            pack_text,
            count=1,
        )
        pack_path.write_text(pack_text, encoding="utf-8")
    metrics_out: dict[str, object] = {}
    markdown, _verdict = snap.render(
        inputs,
        settings,
        snapshot_id=final_snapshot_id,
        snapshot_dir=target,
        metrics_out=metrics_out,
        refresh_metrics=True,
        allow_research_decisions=allow_research_decisions,
    )
    out_report = (
        Path(report_path)
        if report_path
        else output_root() / str(inputs.code) / "analysis_report.md"
    )
    out_report.parent.mkdir(parents=True, exist_ok=True)
    out_report.write_bytes(markdown.encode("utf-8"))
    if html:
        convert_file(out_report, out_report.with_suffix(".html"), title=inputs.code)
    artifact_base = output_root() / str(inputs.code)
    artifact_base.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(target / "research.json", artifact_base / "research.json")
    if (target / "research_provenance.json").is_file():
        shutil.copyfile(
            target / "research_provenance.json",
            artifact_base / "research_provenance.json",
        )

    (target / "metrics.json").write_bytes(
        (
            json.dumps(metrics_out, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
    )
    if inputs.resolved_facts:
        (target / "resolved_facts.json").write_bytes(
            (
                json.dumps(
                    inputs.resolved_facts,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            ).encode("utf-8")
        )

    research_audit = snapshot_audit(target)
    research_audit_path = target / "research_audit.json"
    research_audit_path.write_bytes(
        (json.dumps(research_audit, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
    )
    shutil.copyfile(research_audit_path, artifact_base / "research_audit.json")
    if research_audit["status"] != "pass":
        raise FinalizeError(
            "research audit 未通过：" + "; ".join(research_audit["errors"])
        )

    from ..numeric_audit import audit as numeric_audit

    sources = [
        target / "metrics.json",
        target / "resolved_facts.json",
        target / "inputs.json",
        target / "qualitative.json",
        target / "research.json",
        target / "data_pack.md",
        target / "reported_numbers.json",
        target / "evidence.json",
    ]
    if strict:
        sources = [item for item in sources if item.name != "inputs.json"]
    used_sources = [item for item in sources if item.is_file()]
    numeric = numeric_audit(out_report, used_sources, strict=strict)
    numeric_path = target / "numeric_audit.json"
    numeric_path.write_bytes(
        (json.dumps(numeric, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    if strict and numeric["status"] != "pass":
        raise FinalizeError(f"numeric gate 未通过：coverage={numeric['coverage']}")

    manifest = build_manifest(
        inputs,
        settings,
        target,
        report_hash=hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        metrics_hash=file_hash(target / "metrics.json"),
        resolved_hash=file_hash(target / "resolved_facts.json")
        if (target / "resolved_facts.json").is_file()
        else "",
        pdf_fact_hash=pdf_fact_hash,
        research_audit_hash=file_hash(research_audit_path),
        numeric_coverage=str(numeric["coverage"]),
        numeric_status=str(numeric["status"]),
        numeric_unknown=tuple(str(item) for item in numeric["unknown"]),
        numeric_hash=file_hash(numeric_path),
        numeric_sources=tuple(item.name for item in used_sources),
    )
    manifest.write(target / "manifest.json")
    if manifest.snapshot_id != final_snapshot_id:
        raise FinalizeError(
            "snapshot identity changed during finalize: "
            f"{final_snapshot_id} != {manifest.snapshot_id}"
        )
    errors = snap.verify_manifest(inputs, settings, markdown, manifest, target)
    if errors:
        raise FinalizeError("finalize 后校验失败：" + "; ".join(errors))

    state_path = artifact_base / "run_state.json"
    run = st.load(state_path) if state_path.is_file() else st.new(str(inputs.code))
    run.snapshot_id = manifest.snapshot_id
    st.add_artifact(run, "snapshot", str(target.resolve()))
    st.add_artifact(run, "analysis_report", str(out_report.resolve()))
    st.add_artifact(run, "research", str((target / "research.json").resolve()))
    st.add_artifact(run, "research_audit", str(research_audit_path.resolve()))
    if (target / "research_provenance.json").is_file():
        st.add_artifact(
            run, "research_provenance", str((target / "research_provenance.json").resolve())
        )
    if run.phase in ("intake", "data", "report_pdf", "qualitative", "report"):
        st.advance(run, "report")
    st.save(run, state_path)
    return target
