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
    status: str  # available | partial | missing | external
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
                Capability("parent_cash", "母公司现金", "available", "A 股治理接口"),
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
                Capability("parent_cash", "母公司现金", "missing", "当前无港股母公司接口"),
                Capability("pledge", "质押", "missing", "港股无对应接口"),
                Capability("buyback", "回购", "missing", "港股无对应接口"),
                Capability("pit", "PIT 本地快照", "partial", "本地 snapshot，非 vendor 历史"),
            ]
        )
    elif code.market is Market.US:
        rows.extend(
            [
                Capability("statements_sec", "SEC 报表 fallback", "partial", "10-K companyfacts"),
                Capability("sec_evidence", "SEC evidence", "available", "companyfacts + filing"),
                Capability("parent_cash", "母公司现金", "missing", "当前无美股母公司接口"),
                Capability("pledge", "质押", "missing", "美股无对应接口"),
                Capability("buyback", "回购", "partial", "yfinance 字段，未进入因子"),
                Capability("holders", "主要股东", "missing", "未接入 13F"),
                Capability("segments", "业务分部", "missing", "未解析 10-K 分部"),
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
