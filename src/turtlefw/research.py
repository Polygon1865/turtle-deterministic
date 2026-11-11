"""Research-layer schema: claims must be evidence-backed and number-free.

The deterministic engine owns numbers. A research claim may reference a metric
placeholder (``{{metric:r}}``) or a fact placeholder (``{{fact:...}}``), but it
must not contain a raw numeric literal; the numeric guard rejects it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .facts import ResearchClaim, ResearchDecision, ResearchParam, file_hash

DIMENSIONS = {
    "D1": "商业模式与资本特征",
    "D2": "竞争优势与护城河",
    "D3": "外部环境与政策",
    "D4": "管理层与治理",
    "D5": "MD&A 与前瞻信号",
    "D6": "控股结构与股东",
}
JUDGMENTS = {"positive", "neutral", "negative", "unknown"}
CONFIDENCES = {"high", "medium", "low"}

_NUMBER = re.compile(r"(?<!\{)\b\d+(?:\.\d+)?%?\b")
_YEAR = re.compile(r"^(19|20)\d{2}$")
_PLACEHOLDER = re.compile(r"\{\{(metric|fact):([^}]+)\}\}")


def _resolve_lenient(
    text: str,
    *,
    metrics: Mapping[str, str],
    facts: Mapping[str, str] | None = None,
) -> str:
    """Render free-form prose with placeholders; missing ids become "—".

    ``claim.unknowns`` is prose about what the model could not verify.  A
    placeholder there (typically ``{{metric:parent_cash_ratio}}`` for a market
    that does not carry that metric) must not leave ``{{...}}`` in the report
    nor fail the whole render.
    """

    fact_map = facts or {}

    def replace(match: re.Match[str]) -> str:
        kind, key = match.group(1), match.group(2).strip()
        if kind == "metric" and key in metrics:
            return metrics[key]
        if kind == "fact" and key in fact_map:
            return fact_map[key]
        return "—"

    return _PLACEHOLDER.sub(replace, text)
_QUOTE_LIMIT = 400
_PARTIAL_NUMBER = re.compile(r"\d[\d,.]*$")
_TABLE_RULE = re.compile(r"^:?-{2,}:?$")


def _display_quote(text: str, limit: int = 280) -> str:
    """Turn a raw data-table quote into a readable one-line excerpt."""
    chunks: list[str] = []
    for raw in str(text).splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(cell and _TABLE_RULE.match(cell) for cell in cells):
                continue
            line = " · ".join(cell for cell in cells if cell)
        if line:
            chunks.append(line)
    flat = re.sub(r"\s+", " ", " / ".join(chunks)).strip()
    return _clip_quote(flat, limit)


def _evidence_label(item: Mapping[str, object]) -> str:
    """Use a human label for evidence; never expose internal: ids."""
    source_type = str(item.get("source_type", "web") or "web").lower()
    url = str(item.get("url", "") or "").strip()
    title = str(item.get("title", "") or "").strip()
    page = str(item.get("page", "") or "").strip()
    if source_type == "pdf":
        label = "年报 PDF" if not url else url
    elif source_type == "data":
        label = title or "数据包"
    elif url.startswith(("http://", "https://")):
        label = url
    else:
        label = title or source_type or "证据"
    if page and page not in label:
        label = f"{label} · 第 {page} 页"
    return label



def render_markdown(
    document: ResearchDocument,
    metrics: Mapping[str, str],
    facts: Mapping[str, str] | None = None,
    *,
    include_meta: bool = True,
    include_heading: bool = True,
    params_heading: str = "研究参数",
) -> str:
    """Render D1–D6 claims, params and decisions; unresolved refs fail loudly."""
    lines: list[str] = []
    fact_map = facts or {}
    by_dimension: dict[str, list[ResearchClaim]] = {}
    for claim in document.claims:
        by_dimension.setdefault(claim.dimension, []).append(claim)

    def resolve(text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            kind, key = match.group(1), match.group(2).strip()
            if kind == "metric" and key in metrics:
                return metrics[key]
            if kind == "fact" and key in fact_map:
                return fact_map[key]
            raise ValueError(f"unresolved placeholder {match.group(0)}")

        return _PLACEHOLDER.sub(replace, text)

    for dimension, label in DIMENSIONS.items():
        claims = by_dimension.get(dimension, [])
        if not claims:
            continue
        lines.extend(["", f"### {dimension} {label}", ""] if include_heading else [""])
        for claim in claims:
            statement = resolve(claim.statement)
            lines.append(
                f"- **{claim.claim_id}**（{claim.judgment} / {claim.confidence}）：{statement}"
            )
            for evidence_id in claim.evidence_ids:
                evidence = document.evidence.get(evidence_id)
                if not evidence:
                    continue
                label = _evidence_label(evidence)
                quote = _display_quote(str(evidence.get("quote", "")), 240)
                if not quote:
                    continue
                lines.append(f"  - 证据：{label}")
                lines.append(f"    > {quote}")
            if claim.unknowns:
                rendered_unknowns = "、".join(
                    _resolve_lenient(item, metrics=metrics, facts=fact_map)
                    for item in claim.unknowns
                )
                lines.append(f"  - 未验证：{rendered_unknowns}")
    if document.params:
        lines.extend(
            ["", f"### {params_heading}", "", "| 参数 | 值 | 置信度 |", "|:--|:--|:--|"]
        )
        for param in document.params:
            lines.append(
                f"| {param.label or param.param_id} | {resolve(param.value)} | {param.confidence} |"
            )
    if document.decisions:
        lines.extend(
            [
                "",
                "### 研究决策",
                "",
                "| 决策 | 候选 | 选择 | 理由 |",
                "|:--|:--|:--|:--|",
            ]
        )
        for decision in document.decisions:
            lines.append(
                f"| {decision.metric_id} | "
                f"{', '.join(decision.candidates)} | "
                f"{decision.selected} | {resolve(decision.reason)} |"
            )
    parts = [coverage_markdown(document), "\n".join(lines).strip()]
    evidence_table = evidence_markdown(document)
    if evidence_table:
        parts.append(evidence_table)
    if not include_meta:
        return "\n".join(lines).strip()
    return "\n\n".join(part for part in parts if part).strip()


def render_dimensions(
    document: ResearchDocument,
    metrics: Mapping[str, str],
    facts: Mapping[str, str] | None = None,
) -> dict[str, str]:
    sections: dict[str, str] = {}
    for dimension in DIMENSIONS:
        claims = tuple(
            claim for claim in document.claims if claim.dimension == dimension
        )
        if not claims:
            continue
        params = tuple(
            param for param in document.params if param.dimension == dimension
        )
        filtered = ResearchDocument(
            claims=claims,
            evidence=document.evidence,
            params=params,
        )
        body = render_markdown(
            filtered,
            metrics,
            facts,
            include_meta=False,
            include_heading=False,
            params_heading=f"{dimension} 研究参数",
        )
        if body:
            sections[dimension] = body
    return sections


def quality(document: ResearchDocument) -> dict[str, Any]:
    dimensions = {
        dimension: sum(1 for claim in document.claims if claim.dimension == dimension)
        for dimension in DIMENSIONS
    }
    unknown = sum(1 for claim in document.claims if claim.judgment == "unknown")
    evidence_backed = sum(
        1
        for claim in document.claims
        if claim.judgment != "unknown" and claim.evidence_ids
    )
    non_unknown = len(document.claims) - unknown
    total = len(document.claims)
    claim_coverage = evidence_backed / total if total else 1.0
    return {
        "claims": total,
        "dimensions": dimensions,
        "covered_dimensions": [key for key, count in dimensions.items() if count],
        "unknown": unknown,
        "evidence_backed": evidence_backed,
        "evidence_ratio": (
            round(evidence_backed / non_unknown, 4) if non_unknown else 1.0
        ),
        "claim_coverage": round(claim_coverage, 4),
        "claim_coverage_pct": round(claim_coverage * 100, 1),
        "unknown_ratio": round(unknown / total, 4) if total else 0.0,
        "unknown_ratio_pct": round(unknown / total * 100, 1) if total else 0.0,
        "params": len(document.params),
        "decisions": len(document.decisions),
        "evidence": len(document.evidence),
    }


def thesis_markdown(
    document: ResearchDocument,
    metrics: Mapping[str, str] | None = None,
    facts: Mapping[str, str] | None = None,
) -> str:
    metric_map = metrics or {}
    fact_map = facts or {}
    rows = [
        param
        for param in document.params
        if param.param_id.startswith("thesis.")
    ]
    if not rows:
        return ""

    def resolve(text: str) -> str:
        def replace(match: re.Match[str]) -> str:
            kind, key = match.group(1), match.group(2).strip()
            if kind == "metric" and key in metric_map:
                return metric_map[key]
            if kind == "fact" and key in fact_map:
                return fact_map[key]
            raise ValueError(f"unresolved placeholder {match.group(0)}")

        return _PLACEHOLDER.sub(replace, text)

    lines = ["| 项目 | 内容 |", "|:--|:--|"]
    for param in rows:
        lines.append(f"| {param.label or param.param_id} | {resolve(param.value)} |")
    return "\n".join(lines)


def summary_markdown(document: ResearchDocument) -> str:
    covered = sorted({claim.dimension for claim in document.claims})
    decisions = "；".join(
        f"{decision.metric_id}={decision.selected}"
        for decision in document.decisions
    )
    unknown = sum(1 for claim in document.claims if claim.judgment == "unknown")
    lines = [
        f"- 覆盖维度：{'、'.join(covered) if covered else '无'}",
        f"- claims：{len(document.claims)}（unknown {unknown}）",
        f"- params：{len(document.params)}；evidence：{len(document.evidence)}",
    ]
    if decisions:
        lines.append(f"- 关键决策：{decisions}")
    if unknown:
        lines.append(
            "- 未验证："
            + "、".join(
                claim.claim_id for claim in document.claims if claim.judgment == "unknown"
            )
        )
    return "\n".join(lines)


def render_meta(document: ResearchDocument) -> str:
    parts = [coverage_markdown(document), evidence_markdown(document)]
    return "\n\n".join(part for part in parts if part)


@dataclass(frozen=True, slots=True)
class ResearchDocument:
    claims: tuple[ResearchClaim, ...]
    evidence: dict[str, dict[str, object]]
    params: tuple[ResearchParam, ...] = ()
    decisions: tuple[ResearchDecision, ...] = ()


_METRIC_ALIASES = {
    "payout_spread": "policy.payout_spread",
    "floor_divergence": "floor.divergence",
    "floor_premium_veto": "policy.floor_premium_veto",
    "payout.mean": "payout.mean",
}


def canonical_metric_id(key: str, allowed: Iterable[str] = ()) -> str:
    """Resolve a common LLM shorthand to a registered metric id.

    LLMs sometimes emit ``{{metric:payout_spread}}`` instead of the registered
    ``policy.payout_spread``.  This is a narrow compatibility layer, not a
    numeric fallback: unresolved ids are still reported to the caller.
    """

    clean = str(key).strip().strip("?").strip()
    aliases = set(allowed)
    if clean in aliases:
        return clean
    alias = _METRIC_ALIASES.get(clean)
    if alias and (not aliases or alias in aliases):
        return alias
    suffix = [item for item in aliases if item.rsplit(".", 1)[-1] == clean]
    if len(suffix) == 1:
        return suffix[0]
    underscored = [item for item in aliases if item.replace(".", "_") == clean]
    if len(underscored) == 1:
        return underscored[0]
    return alias or clean


def normalize_placeholders(text: str, allowed: Iterable[str] = ()) -> str:
    """Normalize metric placeholders; leave facts and unknown ids untouched."""

    allowed_ids = tuple(dict.fromkeys(str(item) for item in allowed))

    def replace_match(match: re.Match[str]) -> str:
        kind, raw = match.group(1), match.group(2)
        if kind != "metric":
            return match.group(0)
        return "{{metric:" + canonical_metric_id(raw, allowed_ids) + "}}"

    return _PLACEHOLDER.sub(replace_match, text)


def normalize_document_placeholders(
    document: ResearchDocument,
    allowed: Iterable[str] = (),
) -> tuple[ResearchDocument, tuple[str, ...]]:
    """Normalize aliases in claims/params/decisions and report unresolved ids."""

    allowed_ids = set(str(item) for item in allowed)

    def convert(text: str) -> str:
        return normalize_placeholders(text, allowed_ids)

    claims = tuple(
        replace(
            claim,
            statement=convert(claim.statement),
            unknowns=tuple(convert(item) for item in claim.unknowns),
        )
        for claim in document.claims
    )
    params = tuple(replace(param, value=convert(param.value)) for param in document.params)
    decisions = tuple(
        replace(
            decision,
            metric_id=canonical_metric_id(decision.metric_id, allowed_ids),
            reason=convert(decision.reason),
        )
        for decision in document.decisions
    )
    normalized = replace(
        document,
        claims=claims,
        params=params,
        decisions=decisions,
    )
    unresolved: list[str] = []
    if allowed_ids:
        texts = [
            *(claim.statement for claim in normalized.claims),
            *(param.value for param in normalized.params),
            *(decision.reason for decision in normalized.decisions),
        ]
        for text in texts:
            for match in _PLACEHOLDER.finditer(text):
                if match.group(1) != "metric":
                    continue
                key = match.group(2).strip()
                if key not in allowed_ids:
                    unresolved.append(key)
    return normalized, tuple(dict.fromkeys(unresolved))



def _raw_numbers(text: str) -> list[str]:
    """Numbers not inside ``{{...}}`` and not standalone years."""
    without_placeholders = re.sub(r"\{\{.*?\}\}", "", text)
    numbers = []
    for match in _NUMBER.finditer(without_placeholders):
        token = match.group(0).rstrip("%")
        if _YEAR.match(token):
            continue
        numbers.append(match.group(0))
    return numbers


def load(path: Path | str) -> ResearchDocument:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    return load_payload(payload)


def snapshot_audit(snapshot_dir: Path | str) -> dict[str, Any]:
    """Audit the research document frozen in a snapshot.

    The result is stable enough to persist as ``research_audit.json``: it
    contains the research hash, reference maps, quality and errors.
    """
    root = Path(snapshot_dir)
    research_path = root / "research.json"
    if not research_path.is_file():
        raise ValueError(f"research.json not found: {research_path}")
    document = load(research_path)

    metrics: dict[str, str] = {}
    metrics_path = root / "metrics.json"
    if metrics_path.is_file():
        payload = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, dict):
            for key, point in payload.items():
                if isinstance(point, dict):
                    metrics[str(key)] = str(
                        point.get("display", point.get("value", ""))
                    )

    facts: dict[str, str] = {}
    for name in ("evidence.json", "reported_numbers.json"):
        path = root / name
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        raw_items = (
            payload if isinstance(payload, list) else payload.get("document_facts", [])
        )
        for item in raw_items:
            if isinstance(item, dict) and item.get("id"):
                facts[str(item["id"])] = str(
                    item.get("quote", item.get("value", ""))
                )

    result = audit(document, metrics, facts)
    result["research_sha256"] = file_hash(research_path)
    return result


def engine_decisions(
    document: ResearchDocument,
    *,
    allow: bool = False,
) -> dict[str, str]:
    """Return decisions only when explicitly enabled and evidence-backed.

    A decision is a numeric selection (G/M/Q/AA/scenario), not a free number.
    It is therefore disabled by default; enabling it requires an explicit
    command-line flag and at least one evidence id per decision.
    """
    if not document.decisions:
        return {}
    if not allow:
        raise ValueError(
            "research decisions are disabled; "
            "use --allow-research-decisions to apply them"
        )
    missing = [
        decision.decision_id
        for decision in document.decisions
        if not decision.evidence_ids
    ]
    if missing:
        raise ValueError(
            "research decisions require evidence: " + ", ".join(missing)
        )
    return {
        decision.metric_id: decision.selected for decision in document.decisions
    }


def audit(
    document: ResearchDocument,
    metrics: Mapping[str, str] | None = None,
    facts: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Check claim/param/decision references against rendered value maps."""
    metric_map = metrics or {}
    fact_map = facts or {}
    errors: list[str] = []
    metric_refs: set[str] = set()
    fact_refs: set[str] = set()

    def check_text(label: str, text: str) -> None:
        for match in _PLACEHOLDER.finditer(text):
            kind, key = match.group(1), match.group(2).strip()
            if kind == "metric":
                metric_refs.add(key)
                if key not in metric_map:
                    errors.append(f"{label}: unresolved metric {key!r}")
            else:
                fact_refs.add(key)
                if key not in fact_map:
                    errors.append(f"{label}: unresolved fact {key!r}")

    for claim in document.claims:
        check_text(claim.claim_id, claim.statement)
        if claim.judgment != "unknown" and not claim.evidence_ids:
            errors.append(f"{claim.claim_id}: non-unknown claim has no evidence")
    for param in document.params:
        check_text(param.param_id, param.value)
    for decision in document.decisions:
        check_text(decision.decision_id, decision.reason)
        if decision.selected not in decision.candidates:
            errors.append(f"{decision.decision_id}: selected is not a candidate")
    return {
        "status": "pass" if not errors else "review",
        "claims": len(document.claims),
        "params": len(document.params),
        "decisions": len(document.decisions),
        "evidence": len(document.evidence),
        "metric_refs": sorted(metric_refs),
        "fact_refs": sorted(fact_refs),
        "errors": errors,
        "quality": quality(document),
    }


# Industry vocabulary used to check that a research claim does not invent a
# business.  A statement may only *assert* an industry when a member of that
# group appears in the company profile or in the claim's own evidence quotes.
#
# 2026-10-29: the first version matched every mention of these words, so
# "地产销售下行压制需求" or "供应链管理" were read as industry assertions and the
# research layer fell back for 21 of 40 daily stocks.  The check now only looks
# inside identity assertions ("以…为主业", "主营…", "是一家…公司", …), and groups
# no longer contain operation nouns such as 供应链 that every manufacturer uses.
INDUSTRY_GROUPS: tuple[tuple[str, ...], ...] = (
    ("物业", "物业管理", "在管面积", "物业费", "property management", "property"),
    ("房地产", "地产", "开发商", "土地储备", "real estate", "developer"),
    ("餐饮", "火锅", "餐厅", "快餐", "restaurant", "hot pot", "catering"),
    ("白酒", "啤酒", "酒类", "葡萄酒", "wineries", "breweries", "spirits"),
    ("食品", "零食", "乳制品", "packaged foods", "food products"),
    ("饮料", "饮用水", "矿泉水", "果汁", "茶饮", "咖啡", "beverages", "soft drinks"),
    ("医药", "制药", "生物医药", "创新药", "中药", "drug manufacturers", "biotechnology"),
    ("医疗", "医疗器械", "医院", "诊断", "medical devices", "healthcare"),
    ("汽车", "整车", "乘用车", "商用车", "auto manufacturers", "vehicles"),
    ("银行", "商业银行", "零售银行", "banks"),
    ("保险", "寿险", "财险", "再保险", "insurance"),
    ("证券", "券商", "投行", "资产管理", "capital markets", "asset management"),
    ("半导体", "芯片", "晶圆", "集成电路", "semiconductors"),
    ("化工", "化肥", "农药", "涂料", "新材料", "chemicals"),
    ("煤炭", "焦煤", "煤化工", "coal"),
    ("电力", "发电", "新能源", "光伏", "风电", "水电", "utilities", "solar", "wind"),
    ("通信", "运营商", "电信", "5G", "telecom"),
    ("零售", "商超", "百货", "便利店", "retail"),
    ("电商", "互联网", "平台经济", "本地生活", "internet retail", "e-commerce"),
    ("游戏", "手游", "网络游戏", "electronic gaming", "gaming"),
    ("传媒", "影视", "广告", "出版", "entertainment", "advertising"),
    ("教育", "培训", "职业教育", "education"),
    ("航空", "机场", "民航", "airlines", "airports"),
    ("航运", "港口", "集装箱", "干散货", "shipping", "marine shipping"),
    ("钢铁", "普钢", "特钢", "steel"),
    ("有色金属", "铝", "铜", "黄金", "锂", "copper", "aluminum", "gold"),
    ("建筑", "工程", "基建", "施工", "engineering & construction"),
    ("机械", "工程机械", "设备制造", "industrial machinery", "machinery"),
    ("家电", "家用电器", "白色家电", "appliances"),
    ("纺织", "服装", "鞋类", "体育用品", "apparel", "footwear"),
    ("农业", "养殖", "生猪", "种植", "farm products", "agricultural"),
    ("物流", "快递", "仓储", "logistics", "freight"),
    ("租赁", "航运租赁", "融资租赁", "rental & leasing"),
    ("酒店", "旅游", "景区", "免税", "lodging", "resorts", "travel"),
)

# Only these sentence shapes assert what the company *is*.  A claim that names
# an industry as a driver, a customer or a comparison ("地产下行压制需求") is
# analysis, not an identity claim, and must not trigger the gate.
_IDENTITY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"以([^。；，,、]{1,24}?)(?:为主业|作为主业|为主要业务|为核心业务|为主营业务)"),
    re.compile(r"主营(?:业务)?(?:为|是|包括|涵盖)?\s*([^。；，,、]{1,24})"),
    re.compile(r"主要从事\s*([^。；，,、]{1,24})"),
    re.compile(r"(?:属于|身处|深耕)\s*([^。；，,、]{1,16}?)(?:行业|赛道|板块)"),
    re.compile(r"是一家\s*([^。；，,、]{1,20}?)(?:公司|企业|集团)"),
    re.compile(r"定位(?:为|于)\s*([^。；，,、]{1,24})"),
    re.compile(r"([^。；，,、]{1,24}?)(?:提供商|服务商|运营商|制造商|开发商)"),
)


def _identity_phrases(text: str) -> list[str]:
    phrases: list[str] = []
    for pattern in _IDENTITY_PATTERNS:
        for match in pattern.finditer(text):
            phrase = match.group(1).strip(" 　的")
            if phrase:
                phrases.append(phrase)
    return phrases


def unsupported_industry_terms(
    document: ResearchDocument, *, company_text: str
) -> list[str]:
    """Return ``label:term`` for industry assertions the profile does not support.

    ``company_text`` is the deterministic identity blob (name, industry and
    business summary from the data layer).  An assertion like "以物业管理及
    相关服务为主业" may only name an industry when that industry appears in the
    profile or in the claim's own evidence quotes; otherwise the text is
    fabrication even if its numbers are right.  This is the check the
    2026-10-29 Haidilao intro would have failed.
    """

    profile = (company_text or "").strip().casefold()
    problems: list[str] = []

    def evidence_text(claim: ResearchClaim) -> str:
        quotes: list[str] = []
        for evidence_id in claim.evidence_ids:
            entry = document.evidence.get(evidence_id)
            if isinstance(entry, dict):
                quotes.append(str(entry.get("quote") or ""))
        return "\n".join(quotes).casefold()

    def inspect(label: str, text: str, quotes: str) -> None:
        if not text:
            return
        for phrase in _identity_phrases(text):
            folded = phrase.casefold()
            for group in INDUSTRY_GROUPS:
                named = [term for term in group if term.casefold() in folded]
                if not named:
                    continue
                supported = any(
                    term.casefold() in profile or term.casefold() in quotes
                    for term in group
                )
                if not supported:
                    problem = f"{label}:{named[0]}"
                    if problem not in problems:
                        problems.append(problem)

    for claim in document.claims:
        if claim.judgment == "unknown":
            continue
        inspect(claim.claim_id, claim.statement, evidence_text(claim))
    for param in document.params:
        inspect(param.param_id, param.value, "")
    for decision in document.decisions:
        inspect(decision.decision_id, decision.reason, "")
    return problems


def coverage_markdown(document: ResearchDocument) -> str:
    all_claims = document.claims
    unknown = sum(1 for claim in all_claims if claim.judgment == "unknown")
    backed = sum(
        1
        for claim in all_claims
        if claim.judgment != "unknown" and claim.evidence_ids
    )
    coverage = backed / len(all_claims) if all_claims else 1.0
    lines = [
        "**研究覆盖**",
        "",
        f"- claims：{len(all_claims)}（unknown {unknown}）",
        f"- evidence-backed：{backed}/{len(all_claims)}（{coverage:.1%}）",
        f"- params：{len(document.params)}",
        f"- decisions：{len(document.decisions)}",
        f"- evidence：{len(document.evidence)}",
        "",
        "| 维度 | claims | unknown | evidence |",
        "|:--|--:|--:|--:|",
    ]
    for dimension, label in DIMENSIONS.items():
        claims = [claim for claim in document.claims if claim.dimension == dimension]
        dimension_evidence = {
            evidence_id
            for claim in claims
            for evidence_id in claim.evidence_ids
        }
        dim_unknown = sum(1 for claim in claims if claim.judgment == "unknown")
        lines.append(
            f"| {dimension} {label} | {len(claims)} | {dim_unknown} | "
            f"{len(dimension_evidence)} |"
        )
    if all_claims and coverage < 0.5:
        lines.extend(
            [
                "",
                f"> **研究覆盖偏低**：{backed}/{len(all_claims)} claims 有证据支撑，"
                "结论主要来自有限证据，需结合数据缺口阅读。",
            ]
        )
    if unknown:
        lines.extend(
            [
                "",
                "- unknown claims："
                + "、".join(
                    claim.claim_id
                    for claim in document.claims
                    if claim.judgment == "unknown"
                ),
            ]
        )
    return "\n".join(lines)


def _clip_quote(text: str, limit: int = _QUOTE_LIMIT) -> str:
    """Trim a quote without cutting a numeric token in half.

    The evidence index table used to truncate at 180 characters, which could
    turn ``10,882.00`` into ``10,88``.  That partial token is not present in
    ``research.json`` and therefore failed the strict numeric gate.
    """
    normalized = " ".join(str(text).split())
    while normalized.startswith(">"):
        normalized = normalized[1:].lstrip()
    if len(normalized) <= limit:
        return normalized
    cut = normalized[:limit]
    cut = _PARTIAL_NUMBER.sub("", cut)
    cut = cut.rstrip(" \t,，;；:：|")
    return f"{cut}…"


def evidence_markdown(document: ResearchDocument) -> str:
    if not document.evidence:
        return ""
    lines = ["**证据索引**", ""]
    for evidence_id, item in sorted(document.evidence.items()):
        label = _evidence_label(item)
        quote = _display_quote(str(item.get("quote", "")), _QUOTE_LIMIT)
        lines.append(f"- {label}")
        if quote:
            lines.append(f"  > {quote}")
    return "\n".join(lines)


def to_payload(document: ResearchDocument) -> dict[str, Any]:
    return {
        "evidence": list(document.evidence.values()),
        "claims": [
            {
                "claim_id": claim.claim_id,
                "dimension": claim.dimension,
                "statement": claim.statement,
                "judgment": claim.judgment,
                "confidence": claim.confidence,
                "evidence_ids": list(claim.evidence_ids),
                "as_of": claim.as_of,
                "unknowns": list(claim.unknowns),
            }
            for claim in document.claims
        ],
        "params": [
            {
                "param_id": param.param_id,
                "label": param.label,
                "value": param.value,
                "dimension": param.dimension,
                "evidence_ids": list(param.evidence_ids),
                "confidence": param.confidence,
            }
            for param in document.params
        ],
        "decisions": [
            {
                "decision_id": decision.decision_id,
                "metric_id": decision.metric_id,
                "selected": decision.selected,
                "candidates": list(decision.candidates),
                "reason": decision.reason,
                "evidence_ids": list(decision.evidence_ids),
            }
            for decision in document.decisions
        ],
        "quality": quality(document),
    }


def load_payload(payload: Mapping[str, Any]) -> ResearchDocument:
    evidence_raw = payload.get("evidence", [])
    evidence: dict[str, dict[str, object]] = {}
    for item in evidence_raw:
        key = str(item.get("id", "")).strip()
        if not key:
            raise ValueError("evidence missing id")
        evidence[key] = dict(item)
    validate_evidence(
        evidence.values(),
        allow_data=True,
    )

    claims: list[ResearchClaim] = []
    for raw in payload.get("claims", []):
        claim_id = str(raw.get("claim_id", "")).strip()
        dimension = str(raw.get("dimension", "")).strip().upper()
        statement = str(raw.get("statement", "")).strip()
        judgment = str(raw.get("judgment", "")).strip().lower()
        confidence = str(raw.get("confidence", "medium")).strip().lower()
        evidence_ids = tuple(str(x) for x in raw.get("evidence_ids", []))
        if not claim_id or not statement:
            raise ValueError("claim missing claim_id/statement")
        if dimension not in DIMENSIONS:
            raise ValueError(f"{claim_id}: invalid dimension {dimension!r}")
        if judgment not in JUDGMENTS:
            raise ValueError(f"{claim_id}: invalid judgment {judgment!r}")
        if confidence not in CONFIDENCES:
            raise ValueError(f"{claim_id}: invalid confidence {confidence!r}")
        if judgment != "unknown" and not evidence_ids:
            raise ValueError(f"{claim_id}: non-unknown claim requires evidence")
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                raise ValueError(f"{claim_id}: unknown evidence {evidence_id!r}")
        numbers = _raw_numbers(statement)
        if numbers:
            raise ValueError(
                f"{claim_id}: raw numbers in claim {numbers}; use {{{{metric:...}}}}"
            )
        claims.append(
            ResearchClaim(
                claim_id=claim_id,
                dimension=dimension,
                statement=statement,
                judgment=judgment,
                confidence=confidence,
                evidence_ids=evidence_ids,
                as_of=str(raw.get("as_of", "")),
                unknowns=tuple(str(x) for x in raw.get("unknowns", [])),
            )
        )

    params: list[ResearchParam] = []
    for raw in payload.get("params", []):
        param_id = str(raw.get("param_id", "")).strip()
        label = str(raw.get("label", "")).strip()
        value = str(raw.get("value", "")).strip()
        dimension = str(raw.get("dimension", "")).strip().upper()
        if not param_id or not value:
            raise ValueError("param missing param_id/value")
        if dimension and dimension not in DIMENSIONS:
            raise ValueError(f"{param_id}: invalid dimension {dimension!r}")
        evidence_ids = tuple(str(x) for x in raw.get("evidence_ids", []))
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                raise ValueError(f"{param_id}: unknown evidence {evidence_id!r}")
        numbers = _raw_numbers(value)
        if numbers:
            raise ValueError(
                f"{param_id}: raw numbers in param {numbers}; use {{{{metric:...}}}}"
            )
        params.append(
            ResearchParam(
                param_id=param_id,
                label=label or param_id,
                value=value,
                dimension=dimension,
                evidence_ids=evidence_ids,
                confidence=str(raw.get("confidence", "medium")).strip().lower(),
            )
        )

    decisions: list[ResearchDecision] = []
    for raw in payload.get("decisions", []):
        decision_id = str(raw.get("decision_id", "")).strip()
        metric_id = str(raw.get("metric_id", "")).strip()
        selected = str(raw.get("selected", "")).strip()
        candidates = tuple(str(item) for item in raw.get("candidates", []))
        reason = str(raw.get("reason", "")).strip()
        evidence_ids = tuple(str(x) for x in raw.get("evidence_ids", []))
        if not decision_id or not metric_id or not selected:
            raise ValueError("decision missing decision_id/metric_id/selected")
        if not candidates or selected not in candidates:
            raise ValueError(f"{decision_id}: selected must be one of candidates")
        for evidence_id in evidence_ids:
            if evidence_id not in evidence:
                raise ValueError(f"{decision_id}: unknown evidence {evidence_id!r}")
        if _raw_numbers(reason):
            raise ValueError(f"{decision_id}: raw numbers in decision reason")
        decisions.append(
            ResearchDecision(
                decision_id=decision_id,
                metric_id=metric_id,
                selected=selected,
                candidates=candidates,
                reason=reason,
                evidence_ids=evidence_ids,
            )
        )
    return ResearchDocument(
        claims=tuple(claims),
        evidence=evidence,
        params=tuple(params),
        decisions=tuple(decisions),
    )


def validate_evidence(
    items: Iterable[Mapping[str, object]],
    *,
    allow_data: bool = False,
) -> None:
    for item in items:
        url = str(item.get("url", "")).strip()
        quote = str(item.get("quote", "")).strip()
        source_type = str(item.get("source_type", "web")).strip()
        if not quote:
            raise ValueError(f"evidence {item.get('id')}: empty quote")
        if allow_data and source_type == "data":
            # Internal data evidence is addressable by its data: id; it has no
            # web URL, but still needs a quote/value.
            continue
        if source_type == "pdf" and url.startswith("pdf://"):
            # Page-addressed evidence from the PDF deep index. The page citation
            # is the address; the quote is still mandatory.
            continue
        if not url.startswith(("http://", "https://")):
            raise ValueError(f"evidence {item.get('id')}: invalid url")
