"""Phase 2 industry templates and peer groups.

Templates are declarative: a KPI is rendered only when its metric/fact exists.
Missing data is shown as ``—`` with a reason, never filled with a number.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..facts import MetricRegistry
from .format import _table


@dataclass(frozen=True)
class KpiSpec:
    label: str
    metric_id: str = ""
    note: str = ""


@dataclass(frozen=True)
class Peer:
    code: str
    name: str
    market: str = ""


@dataclass(frozen=True)
class IndustryTemplate:
    key: str
    name: str
    description: str
    codes: tuple[str, ...]
    kpis: tuple[KpiSpec, ...]
    peers: tuple[Peer, ...] = field(default_factory=tuple)


TEMPLATES: dict[str, IndustryTemplate] = {
    "telecom": IndustryTemplate(
        key="telecom",
        name="运营商",
        description="移动/固网用户、ARPU、资本开支强度与股东回报。",
        codes=("600941.SH", "601728.SH", "600050.SH", "00728.HK"),
        kpis=(
            KpiSpec("营业收入 CAGR", "revenue.cagr"),
            KpiSpec("OCF/净利润", "ocf_ni_ratio"),
            KpiSpec("最新 FCF", "fcf.latest"),
            KpiSpec("DPS", "dps.pdf", "PDF/供应商分红"),
            KpiSpec("ARPU", note="需要运营商月度经营数据，PDF 未提供"),
            KpiSpec("5G 套餐渗透率", note="需要运营商月度经营数据，PDF 未提供"),
        ),
        peers=(
            Peer("600941.SH", "中国移动", "A"),
            Peer("601728.SH", "中国电信", "A"),
            Peer("600050.SH", "中国联通", "A"),
        ),
    ),
    "food": IndustryTemplate(
        key="food",
        name="食品饮料",
        description="产品结构、渠道、合同负债、库存与现金流质量。",
        codes=("600887.SH", "600519.SH", "000858.SZ"),
        kpis=(
            KpiSpec("营业收入 CAGR", "revenue.cagr"),
            KpiSpec("归母净利润 CAGR", "net_income.cagr"),
            KpiSpec("合同负债", "contract_liab"),
            KpiSpec("存货", "inventory"),
            KpiSpec("OCF/净利润", "ocf_ni_ratio"),
            KpiSpec("DPS", "dps.pdf", "PDF/供应商分红"),
            KpiSpec("渠道库存", note="需要渠道调研数据，PDF 未提供"),
        ),
        peers=(
            Peer("600887.SH", "伊利股份", "A"),
            Peer("600519.SH", "贵州茅台", "A"),
            Peer("000858.SZ", "五粮液", "A"),
        ),
    ),
    "internet": IndustryTemplate(
        key="internet",
        name="互联网",
        description="用户/流量、变现率、SBC 与自由现金流。",
        codes=("00700.HK", "09988.HK", "03690.HK", "01024.HK"),
        kpis=(
            KpiSpec("营业收入 CAGR", "revenue.cagr"),
            KpiSpec("归母净利润 CAGR", "net_income.cagr"),
            KpiSpec("OCF/净利润", "ocf_ni_ratio"),
            KpiSpec("最新 FCF", "fcf.latest"),
            KpiSpec("DPS", "dps.pdf", "PDF/供应商分红"),
            KpiSpec("MAU/DAU", note="需要公司季度经营数据，PDF 未提供"),
            KpiSpec("SBC/收入", note="需要 SBC 与收入同期口径，PDF 未完整提供"),
        ),
        peers=(
            Peer("00700.HK", "腾讯控股", "HK"),
            Peer("09988.HK", "阿里巴巴-W", "HK"),
            Peer("03690.HK", "美团-W", "HK"),
        ),
    ),
}


INDUSTRY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("telecom", ("电信", "通信", "卫星传输")),
    ("food", ("酒、饮料", "饮料", "食品制造", "农副食品")),
    ("internet", ("互联网", "软件和信息技术")),
)


def template_key_for(industry_name: str) -> str:
    """Map a Shenwan L1 industry name to a template key.

    Classification is authoritative when present: a code that was previously
    hard-coded to ``food`` must not silently keep that template if the vendor
    now says it belongs to another industry.  Callers fall back to the legacy
    code table only when no classification was obtained.
    """
    name = industry_name.strip()
    if not name:
        return ""
    for key, keywords in INDUSTRY_KEYWORDS:
        if any(word in name for word in keywords):
            return key
    return ""


def template_for(code: str, industry_name: str = "") -> IndustryTemplate | None:
    if industry_name.strip():
        return TEMPLATES.get(template_key_for(industry_name))
    normalized = code.strip().upper()
    for template in TEMPLATES.values():
        if normalized in template.codes:
            return template
    return None


def render_section(
    code: str,
    ledger: MetricRegistry,
    peer_metrics: list[dict[str, object]] | None = None,
    industry_name: str = "",
) -> str:
    template = template_for(code, industry_name)
    if template is None:
        if industry_name.strip():
            return (
                "## 行业分类\n\n"
                f"- 申万一级：{industry_name.strip()}\n"
                "- 采用模板：暂无专用模板\n"
                "- 来源：`tushare:index_member_all`\n\n"
                "> 财务指标仍按通用框架展示；不为该行业填充未经核实的 KPI。"
            )
        return ""
    rows: list[list[str]] = []
    for spec in template.kpis:
        if spec.metric_id and ledger.get(spec.metric_id) is not None:
            rows.append([spec.label, ledger.display(spec.metric_id), "可用"])
        else:
            rows.append([spec.label, "—", spec.note or "数据未取得"])
    peer_rows = [[peer.name, peer.code, peer.market or "—"] for peer in template.peers]
    financial = ""
    if peer_metrics:
        financial = "\n\n**Peer 财务对比**\n\n" + _table(
            ["公司", "营收 CAGR", "净利率", "ROE"],
            [
                [
                    str(row.get("name", "")),
                    str(row.get("revenue_cagr", "—")),
                    str(row.get("net_margin", "—")),
                    str(row.get("roe", "—")),
                ]
                for row in peer_metrics
            ],
            ["l", "r", "r", "r"],
        )
    classification = (
        f"\n\n> 申万一级：{industry_name.strip()}（`tushare:index_member_all`）"
        if industry_name.strip()
        else ""
    )
    return (
        f"## 行业模板：{template.name}\n\n"
        f"{template.description}"
        f"{classification}\n\n"
        + _table(["KPI", "数值", "状态"], rows, ["l", "r", "l"])
        + "\n\n**Peer 组**\n\n"
        + _table(["公司", "代码", "市场"], peer_rows, ["l", "l", "l"])
        + financial
        + "\n\n> Peer 财务指标缺失显示 `—`；本表不填未核实数字。"
    )
