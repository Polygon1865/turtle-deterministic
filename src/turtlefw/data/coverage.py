"""Explicit data-coverage contract.

This is not a data source. It makes missing capabilities visible instead of
letting a report imply coverage that does not exist.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..types import Market, StockCode


@dataclass(frozen=True, slots=True)
class Capability:
    key: str
    label: str
    status: str  # available | partial | pdf_optional | not_applicable | external | missing
    detail: str = ""


def capabilities(code: StockCode) -> list[Capability]:
    rows = [
        Capability("statements", "三大报表", "available", "主 provider"),
        Capability("dividends", "分红", "available", "主 provider"),
        Capability("quote", "行情/市值", "available", "主 provider"),
        Capability("weekly", "周线/历史", "available", "主 provider"),
    ]
    if code.is_a_share:
        rows.extend(
            [
                Capability(
                    "parent_cash",
                    "母公司现金",
                    "available",
                    "A 股治理接口（report_type=6；缺失时保持 unknown）",
                ),
                Capability("pledge", "质押", "available", "A 股治理接口"),
                Capability("buyback", "回购", "available", "A 股治理接口"),
                Capability("holders", "十大股东", "available", "A 股接口"),
                Capability("main_business", "主营构成", "available", "A 股接口"),
                Capability("pit", "PIT 本地快照", "partial", "本地 snapshot，非 vendor 历史"),
            ]
        )
    elif code.market is Market.HK:
        rows.extend(
            [
                Capability("holders", "主要股东", "partial", "PDF P4 提取"),
                Capability("segments", "业务分部", "partial", "PDF MDA 提取"),
                Capability("parent_cash", "母公司现金", "pdf_optional", "年报 Company-level statement 可抽取"),
                Capability("pledge", "质押", "not_applicable", "港股无标准化质押比例接口"),
                Capability("buyback", "回购", "partial", "hk_cashflow + HKEXnews 公告 evidence"),
                Capability("pit", "PIT 本地快照", "partial", "本地 snapshot，非 vendor 历史"),
            ]
        )
    elif code.market is Market.US:
        rows.extend(
            [
                Capability("statements_sec", "SEC 报表 fallback", "partial", "10-K companyfacts"),
                Capability("sec_evidence", "SEC evidence", "available", "companyfacts + filing"),
                Capability("parent_cash", "母公司现金", "not_applicable", "US GAAP 无标准母公司报表"),
                Capability("pledge", "质押", "not_applicable", "美股无对应制度"),
                Capability("buyback", "回购", "partial", "SEC companyfacts / yfinance"),
                Capability("holders", "主要股东", "external", "需 SEC 13F bulk 或第三方 API"),
                Capability("segments", "业务分部", "external", "需 10-K XBRL dimensions/正文解析"),
                Capability("pit", "PIT 历史", "missing", "本地无美股 PIT"),
            ]
        )
    return rows


def coverage_markdown(code: StockCode) -> str:
    rows = capabilities(code)
    lines = [
        "| 能力 | 状态 | 说明 |",
        "|:--|:--|:--|",
    ]
    for row in rows:
        lines.append(f"| {row.label} | {row.status} | {row.detail} |")
    return "\n".join(lines)
