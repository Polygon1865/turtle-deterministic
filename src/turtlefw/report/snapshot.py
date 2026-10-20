"""Frozen report inputs and offline rendering.

A ``ReportInputs`` bundle stores everything the deterministic report needs:
statement rows, dividends, quote/history, governance, PDF overrides, audit,
qualitative JSON and the effective config TOML. Rendering from the bundle does
not touch any provider and does not read the clock.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from ..config import Settings, load_settings
from ..data.protocol import StatementRow
from ..facts import (
    ReportManifest,
    config_payload,
    content_hash,
    file_hash,
    statement_payload,
    template_hash,
)
from ..factors.engine import FactorContext, run
from ..metrics import grids, statements
from ..metrics.valuation import build_valuation
from ..qualitative import load as load_qualitative
from ..report.analysis import render_analysis
from ..report.pack import _snapshot_id, average_dps
from ..types import Currency, DividendEvent, FetchIssue, Money, StockCode


def resolve_markdown(payload: list[dict[str, Any]]) -> str:
    if not payload:
        return ""
    from ..metrics.source_resolver import render_markdown

    return render_markdown(payload)


RESEARCH_SECTION_TITLES = {
    "D1": "D1 商业模式与资本特征",
    "D2": "D2 护城河与竞争格局",
    "D3": "D3 外部环境与政策",
    "D4": "D4 管理层与治理",
    "D5": "D5 MD&A 与前瞻信号",
    "D6": "D6 控股结构与股东",
}


@dataclass(slots=True)
class ReportInputs:
    code: str
    currency: str
    as_of: str
    rows: list[StatementRow]
    dividends: list[DividendEvent]
    quote: dict[str, Any] | None
    history: list[dict[str, Any]]
    market_cap: str
    shares: str
    price: str | None
    rf_pct: str
    rf_source: str
    parent_cash: str | None = None
    pledge_pct: str | None = None
    buyback: str | None = None
    sbc: str | None = None
    audit: list[dict[str, Any]] = field(default_factory=list)
    pdf_bridge: dict[int, dict[str, str | None]] | None = None
    issues: list[FetchIssue] = field(default_factory=list)
    config_toml: str = ""
    has_qualitative: bool = False
    source_id: str = ""
    source_policy: str = "record-only"
    resolved_facts: list[dict[str, Any]] = field(default_factory=list)


def inputs_to_dict(inputs: ReportInputs) -> dict[str, Any]:
    return {
        "code": inputs.code,
        "currency": inputs.currency,
        "as_of": inputs.as_of,
        "rows": [
            {
                "code": row.code,
                "period_end": row.period_end.isoformat(),
                "period_type": row.period_type,
                "statement": row.statement,
                "item": row.item,
                "value": str(row.value),
                "currency": row.currency.value,
                "source": row.source,
                "ann_date": row.ann_date.isoformat() if row.ann_date else None,
            }
            for row in inputs.rows
        ],
        "dividends": [
            {
                "fiscal_year": event.fiscal_year,
                "event_id": event.event_id,
                "dps": str(event.dps),
                "currency": event.currency.value,
                "total": str(event.total) if event.total is not None else None,
                "ann_date": event.ann_date.isoformat() if event.ann_date else None,
                "payout_pct": str(event.payout_pct) if event.payout_pct is not None else None,
                "dps_reliable": event.dps_reliable,
            }
            for event in inputs.dividends
        ],
        "quote": inputs.quote,
        "history": inputs.history,
        "market_cap": inputs.market_cap,
        "shares": inputs.shares,
        "price": inputs.price,
        "rf_pct": inputs.rf_pct,
        "rf_source": inputs.rf_source,
        "parent_cash": inputs.parent_cash,
        "pledge_pct": inputs.pledge_pct,
        "buyback": inputs.buyback,
        "sbc": inputs.sbc,
        "audit": inputs.audit,
        "pdf_bridge": inputs.pdf_bridge,
        "issues": [
            {
                "endpoint": issue.endpoint,
                "code": issue.code,
                "message": issue.message,
                "retryable": issue.retryable,
            }
            for issue in inputs.issues
        ],
        "has_qualitative": inputs.has_qualitative,
        "source_id": inputs.source_id,
        "source_policy": inputs.source_policy,
        "resolved_facts": inputs.resolved_facts,
    }


def inputs_from_dict(payload: dict[str, Any]) -> ReportInputs:
    rows = [
        StatementRow(
            code=str(row["code"]),
            period_end=date.fromisoformat(str(row["period_end"])),
            period_type=str(row["period_type"]),
            statement=str(row["statement"]),
            item=str(row["item"]),
            value=Decimal(str(row["value"])),
            currency=Currency(str(row["currency"])),
            source=str(row["source"]),
            ann_date=date.fromisoformat(str(row["ann_date"])) if row.get("ann_date") else None,
        )
        for row in payload.get("rows", [])
    ]
    dividends = [
        DividendEvent(
            fiscal_year=int(event["fiscal_year"]),
            event_id=str(event["event_id"]),
            dps=Decimal(str(event["dps"])),
            currency=Currency(str(event["currency"])),
            total=Decimal(str(event["total"])) if event.get("total") is not None else None,
            ann_date=date.fromisoformat(str(event["ann_date"])) if event.get("ann_date") else None,
            payout_pct=(
                Decimal(str(event["payout_pct"])) if event.get("payout_pct") is not None else None
            ),
            dps_reliable=bool(event.get("dps_reliable", True)),
        )
        for event in payload.get("dividends", [])
    ]
    return ReportInputs(
        code=str(payload["code"]),
        currency=str(payload["currency"]),
        as_of=str(payload["as_of"]),
        rows=rows,
        dividends=dividends,
        quote=payload.get("quote"),
        history=list(payload.get("history", [])),
        market_cap=str(payload["market_cap"]),
        shares=str(payload["shares"]),
        price=payload.get("price"),
        rf_pct=str(payload["rf_pct"]),
        rf_source=str(payload.get("rf_source", "")),
        parent_cash=payload.get("parent_cash"),
        pledge_pct=payload.get("pledge_pct"),
        buyback=payload.get("buyback"),
        sbc=payload.get("sbc"),
        audit=list(payload.get("audit", [])),
        pdf_bridge=(
            {int(key): value for key, value in payload["pdf_bridge"].items()}
            if payload.get("pdf_bridge")
            else None
        ),
        issues=[
            FetchIssue(
                endpoint=str(issue.get("endpoint", "")),
                code=str(issue.get("code", "")),
                message=str(issue.get("message", "")),
                retryable=bool(issue.get("retryable", False)),
            )
            for issue in payload.get("issues", [])
        ],
        config_toml=str(payload.get("config_toml", "")),
        has_qualitative=bool(payload.get("has_qualitative", False)),
        source_id=str(payload.get("source_id", "")),
        source_policy=str(payload.get("source_policy", "record-only")),
        resolved_facts=list(payload.get("resolved_facts", [])),
    )


def freeze(
    inputs: ReportInputs,
    settings: Settings,
    directory: Path | str,
    *,
    qualitative_source: Path | str | None = None,
    research_source: Path | str | None = None,
) -> Path:
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    payload = inputs_to_dict(inputs)
    config_text = settings.config_path.read_text(encoding="utf-8")
    (root / "config.toml").write_text(config_text, encoding="utf-8")
    if qualitative_source is not None and Path(qualitative_source).is_file():
        (root / "qualitative.json").write_text(
            Path(qualitative_source).read_text(encoding="utf-8-sig"), encoding="utf-8"
        )
        payload["has_qualitative"] = True
    if research_source is not None and Path(research_source).is_file():
        (root / "research.json").write_text(
            Path(research_source).read_text(encoding="utf-8-sig"), encoding="utf-8"
        )
    (root / "inputs.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return root


def load(directory: Path | str) -> tuple[ReportInputs, Settings]:
    root = Path(directory)
    payload = json.loads((root / "inputs.json").read_text(encoding="utf-8-sig"))
    config_path = root / "config.toml"
    settings = load_settings(config_path) if config_path.is_file() else load_settings()
    return inputs_from_dict(payload), settings


def verify_manifest(
    inputs: ReportInputs,
    settings: Settings,
    markdown: str,
    manifest: ReportManifest,
    snapshot_dir: Path | str,
) -> list[str]:
    """Return human-readable mismatches for a frozen snapshot render."""
    root = Path(snapshot_dir)
    errors: list[str] = []
    if manifest.code != inputs.code:
        errors.append(f"code: manifest={manifest.code} inputs={inputs.code}")
    if manifest.as_of != inputs.as_of:
        errors.append(f"as_of: manifest={manifest.as_of} inputs={inputs.as_of}")
    if manifest.currency != inputs.currency:
        errors.append(f"currency: manifest={manifest.currency} inputs={inputs.currency}")
    actual_facts = content_hash(statement_payload(inputs.rows))
    if actual_facts != manifest.facts_hash:
        errors.append("facts_hash mismatch")
    actual_config = content_hash(config_payload(settings))
    if actual_config != manifest.config_hash:
        errors.append("config_hash mismatch")
    research_file = root / "research.json"
    actual_research = file_hash(research_file) if research_file.is_file() else ""
    if actual_research != manifest.research_hash:
        errors.append("research_hash mismatch")
    audit_file = root / "research_audit.json"
    actual_audit = file_hash(audit_file) if audit_file.is_file() else ""
    if manifest.research_audit_hash and actual_audit != manifest.research_audit_hash:
        errors.append("research_audit_hash mismatch")
    actual_template = template_hash(Path(__file__).parent / "templates")
    if manifest.template_hash and actual_template != manifest.template_hash:
        errors.append("template_hash mismatch")
    actual_report = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    if manifest.report_hash and actual_report != manifest.report_hash:
        errors.append("report_hash mismatch")
    metrics_file = root / "metrics.json"
    actual_metrics = file_hash(metrics_file) if metrics_file.is_file() else ""
    if manifest.metrics_hash and actual_metrics != manifest.metrics_hash:
        errors.append("metrics_hash mismatch")
    resolved_file = root / "resolved_facts.json"
    actual_resolved = file_hash(resolved_file) if resolved_file.is_file() else ""
    if manifest.resolved_hash and actual_resolved != manifest.resolved_hash:
        errors.append("resolved_hash mismatch")
    numeric_file = root / "numeric_audit.json"
    actual_numeric = file_hash(numeric_file) if numeric_file.is_file() else ""
    if manifest.numeric_hash and actual_numeric != manifest.numeric_hash:
        errors.append("numeric_hash mismatch")
    return errors


def render(
    inputs: ReportInputs,
    settings: Settings,
    *,
    snapshot_id: str | None = None,
    snapshot_dir: Path | str | None = None,
    qualitative_path: Path | str | None = None,
    research_path: Path | str | None = None,
    metrics_out: dict[str, object] | None = None,
    facts: dict[str, str] | None = None,
    refresh_metrics: bool = False,
) -> tuple[str, str]:
    code = StockCode.parse(inputs.code)
    currency = Currency(inputs.currency)
    rows = inputs.rows
    years = sorted({r.period_end.year for r in rows if r.period_type == "annual"})
    latest = max(years) if years else None
    def income(item: str) -> dict[int, Decimal]:
        return statements.annual_series(rows, "income", item)

    def balance(item: str) -> dict[int, Decimal]:
        return statements.annual_series(rows, "balance", item)

    fcf = statements.fcf_series(rows)
    market_cap = Money(Decimal(inputs.market_cap), currency)
    shares = Decimal(inputs.shares)
    price = Decimal(inputs.price) if inputs.price is not None else None
    snapshot = build_valuation(
        market_cap=market_cap.amount if market_cap.amount > 0 else None,
        cash=statements.cash_and_equivalents(rows).get(latest) if latest else None,
        debt=statements.interest_bearing_debt(rows).get(latest) if latest else None,
        equity=statements.equity(rows).get(latest) if latest else None,
        net_income=income("n_income_attr_p").get(latest) if latest else None,
        revenue=income("revenue").get(latest) if latest else None,
        operate_profit=income("operate_profit").get(latest) if latest else None,
        finance_exp=income("finance_exp").get(latest) if latest else None,
        da=statements.da_series(rows).get(latest) if latest else None,
        fcf=fcf.get(latest) if latest else None,
        goodwill=balance("goodwill").get(latest) if latest else None,
        total_assets=balance("total_assets").get(latest) if latest else None,
        dps=average_dps(inputs.dividends),
        price=price,
    )
    qualitative = None
    if snapshot_dir is not None:
        qual_path = Path(snapshot_dir) / "qualitative.json"
        if qual_path.is_file():
            qualitative = load_qualitative(qual_path)
    elif qualitative_path is not None and Path(qualitative_path).is_file():
        qualitative = load_qualitative(Path(qualitative_path))
    research_document = None
    research_candidate = (
        Path(snapshot_dir) / "research.json"
        if snapshot_dir is not None
        else Path(research_path) if research_path is not None else None
    )
    if research_candidate is not None and research_candidate.is_file():
        from ..research import load as load_research

        research_document = load_research(research_candidate)
    decisions = {
        decision.metric_id: decision.selected
        for decision in (research_document.decisions if research_document else ())
    }
    ctx = FactorContext(
        code=code,
        rows=rows,
        dividends=inputs.dividends,
        market_cap=market_cap,
        shares=shares,
        diluted_shares=statements.diluted_shares(rows),
        price=price,
        rf_pct=Decimal(inputs.rf_pct),
        tax_pct=grids.default_tax_rate(code),
        settings=settings,
        snapshot=snapshot,
        closes=[
            Decimal(str(item["close"]))
            for item in inputs.history
            if item.get("close") is not None
        ],
        audit=inputs.audit,
        qualitative=qualitative,
        pledge_pct=Decimal(inputs.pledge_pct) if inputs.pledge_pct else None,
        parent_cash=Decimal(inputs.parent_cash) if inputs.parent_cash else None,
        buyback=Money(Decimal(inputs.buyback), currency) if inputs.buyback else None,
        sbc=Money(Decimal(inputs.sbc), currency) if inputs.sbc else None,
        pdf_cash_bridge=inputs.pdf_bridge,
        decisions=decisions,
    )
    results = run(ctx)
    metric_map = {
        "r": dict(results["2"].metrics).get("粗算回报率 R", "—"),
        "gg": dict(results["3"].metrics).get("精算回报率 GG", "—"),
        "ii": dict(results["2"].metrics).get("门槛 II", "—"),
        "margin": dict(results["4"].metrics).get("安全边际 KK", "—"),
        "floor": dict(results["4"].metrics).get("底价（综合）", "—"),
        "price": f"{price:.2f}" if price is not None else "—",
    }
    for result in results.values():
        for key, value in result.values:
            if value is None or key in metric_map:
                continue
            is_percent = key in {
                "payout",
                "payout.mean",
                "payout.spread",
                "parent_cash_ratio",
                "pledge_pct",
                "buyback_ratio",
                "ar_ratio",
                "revenue_cv",
                "hh",
                "price_percentile",
            } or key.startswith(("tax_", "scenario_"))
            metric_map[key] = (
                f"{value:.2f}%" if is_percent else f"{value:,.2f}"
            )
    if ctx.pledge_pct is not None:
        metric_map.setdefault("pledge_pct", f"{ctx.pledge_pct:.2f}%")
    if ctx.buyback is not None and ctx.market_cap.amount:
        metric_map.setdefault(
            "buyback_ratio",
            f"{ctx.buyback.amount / ctx.market_cap.amount * Decimal('100'):.2f}%",
        )
    if ctx.parent_cash is not None and ctx.market_cap.amount:
        metric_map.setdefault(
            "parent_cash_ratio",
            f"{ctx.parent_cash / ctx.market_cap.amount * Decimal('100'):.1f}%",
        )
    if "payout.mean" not in metric_map:
        from ..metrics import dividends as div_metrics

        income_series = statements.net_income(ctx.rows)
        payouts = div_metrics.payout_by_year(
            ctx.dividends, income_series, shares=ctx.shares
        )
        mean_payout, _ = div_metrics.mean_payout(payouts)
        if mean_payout is not None:
            metric_map["payout.mean"] = f"{mean_payout:.2f}%"
    if "buyback.latest" not in metric_map:
        buyback_series = statements.annual_series(ctx.rows, "cashflow", "buyback")
        if buyback_series:
            metric_map["buyback.latest"] = f"{buyback_series[max(buyback_series)]:,.2f}"
    if not refresh_metrics:
        if research_path is not None:
            metrics_file = Path(research_path).with_name("metrics.json")
        elif snapshot_dir is not None:
            metrics_file = Path(snapshot_dir) / "metrics.json"
        else:
            metrics_file = None
        if metrics_file is not None and metrics_file.is_file():
            stored = json.loads(metrics_file.read_text(encoding="utf-8-sig"))
            if isinstance(stored, dict):
                for key, value in stored.items():
                    if isinstance(value, dict) and value.get("display"):
                        metric_map[str(key)] = str(value["display"])
    research_md = ""
    research_sections: list[tuple[str, str]] = []
    research_meta_md = ""
    research_summary_md = ""
    research_thesis_md = ""
    fact_map = dict(facts or {})
    if research_document is not None:
        from ..research import (
            render_dimensions,
            render_markdown,
            render_meta,
            summary_markdown,
            thesis_markdown,
        )

        if not fact_map and snapshot_dir is not None:
            reported = Path(snapshot_dir) / "reported_numbers.json"
            if reported.is_file():
                payload = json.loads(reported.read_text(encoding="utf-8-sig"))
                for item in payload.get("document_facts", []):
                    fact_id = str(item.get("id", ""))
                    if fact_id:
                        fact_map[fact_id] = f"{item.get('value', '')} {item.get('unit', '')}".strip()
            evidence = Path(snapshot_dir) / "evidence.json"
            if evidence.is_file():
                payload = json.loads(evidence.read_text(encoding="utf-8-sig"))
                if isinstance(payload, list):
                    for item in payload:
                        if isinstance(item, dict) and item.get("id"):
                            fact_map[str(item["id"])] = str(item.get("quote", ""))
        # Render once without research so placeholders resolve against the
        # canonical metric-registry displays (floor/premium units included)
        # instead of the ad-hoc result strings built above.
        probe_metrics: dict[str, object] = {}
        render_analysis(
            ctx,
            results,
            settings=settings,
            snapshot_id=snapshot_id or _snapshot_id(rows),
            rf_source=inputs.rf_source,
            issues=inputs.issues,
            as_of=inputs.as_of,
            metrics_out=probe_metrics,
            resolved_md=resolve_markdown(inputs.resolved_facts),
        )
        metric_map.update(
            {
                str(key): str(value["display"])
                for key, value in probe_metrics.items()
                if isinstance(value, dict) and value.get("display")
            }
        )
        research_md = render_markdown(research_document, metric_map, fact_map)
        section_map = render_dimensions(research_document, metric_map, fact_map)
        research_sections = [
            (RESEARCH_SECTION_TITLES[dimension], body)
            for dimension, body in section_map.items()
            if dimension in RESEARCH_SECTION_TITLES
        ]
        research_meta_md = render_meta(research_document)
        research_summary_md = summary_markdown(research_document)
        research_thesis_md = thesis_markdown(
            research_document, metric_map, fact_map
        )
    markdown = render_analysis(
        ctx,
        results,
        settings=settings,
        snapshot_id=snapshot_id or _snapshot_id(rows),
        rf_source=inputs.rf_source,
        issues=inputs.issues,
        as_of=inputs.as_of,
        research_md=research_md,
        research_sections=research_sections,
        research_meta_md=research_meta_md,
        research_summary_md=research_summary_md,
        research_thesis_md=research_thesis_md,
        metrics_out=metrics_out,
        resolved_md=resolve_markdown(inputs.resolved_facts),
    )
    return markdown, dict(results["4"].metrics).get("结论", "观察")
