"""Analysis report rendering (four factors + verdict)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal
from typing import Any

from jinja2 import Environment, FileSystemLoader

from ..config import Settings
from ..factors.engine import FactorContext, FactorResult, final_verdict
from ..metrics import registry as metric_registry
from ..metrics import statements, valuation
from ..metrics.dividends import average_dps
from ..metrics.dps_check import crosscheck_dps
from ..qualitative import MODULES, all_evidence
from ..qualitative import summary as qual_summary
from ..types import Currency, DividendEvent, FetchIssue
from . import industry
from .extras import render_extras
from .format import TEMPLATE_DIR, _m, _num, _pct, _table
from .market import render_market

STATUS = {"pass": "通过", "veto": "否决", "unknown": "未验证", "info": "观察"}


def _pdf_value(raw: object) -> str:
    if raw in (None, ""):
        return "—"
    try:
        value = Decimal(str(raw))
    except Exception:
        return str(raw)
    return _m(value) if abs(value) >= Decimal("1000") else _num(value, 4)


def _dps_check_text(
    document_facts: Sequence[dict[str, Any]],
    dividends: Sequence[DividendEvent],
    *,
    fiscal_year: int | None,
    currency: Currency,
) -> str:
    for fact in document_facts:
        if fact.get("label") != "dps":
            continue
        try:
            pdf_dps = Decimal(str(fact.get("value")))
        except Exception:
            return ""
        check = crosscheck_dps(
            pdf_dps,
            dividends,
            fiscal_year=fiscal_year,
            currency=currency,
        )
        if check.status == "unavailable":
            return "DPS 核对：供应商无可用分红事件"
        return (
            f"DPS 核对：{check.status}；PDF {check.pdf_dps:.4f} / "
            f"供应商 {check.provider_dps:.4f}，差异 {check.diff_pct:.2f}%"
        )
    return ""


def render_analysis(
    ctx: FactorContext,
    results: dict[str, FactorResult],
    *,
    settings: Settings,
    snapshot_id: str,
    rf_source: str,
    issues: Sequence[FetchIssue] = (),
    as_of: str = "",
    research_md: str = "",
    research_sections: list[tuple[str, str]] | None = None,
    research_meta_md: str = "",
    research_summary_md: str = "",
    research_thesis_md: str = "",
    resolved_md: str = "",
    metrics_out: dict[str, object] | None = None,
    document_facts: Sequence[dict[str, Any]] = (),
    fact_rows: Sequence[dict[str, Any]] = (),
    industry_peers: Sequence[dict[str, Any]] = (),
    fundamental_extras: Mapping[str, Any] | None = None,
    industry_name: str = "",
    market_extras: Mapping[str, Any] | None = None,
) -> str:
    verdict, reason = final_verdict(results)
    rows = ctx.rows
    years = sorted({r.period_end.year for r in rows if r.period_type == "annual"})
    latest = max(years) if years else None

    income = statements.net_income(rows)
    revenue = statements.revenue(rows)
    fcf = statements.fcf_series(rows)
    debt = statements.interest_bearing_debt(rows)
    cash = statements.cash_and_equivalents(rows)
    equity = statements.equity(rows)
    payouts = {}
    from ..metrics import dividends as div_metrics

    payouts = div_metrics.payout_by_year(ctx.dividends, income, shares=ctx.shares)
    mean_payout, _ = div_metrics.mean_payout(payouts)

    min_fcf_recent = dict(sorted(fcf.items())[-5:])
    min_fcf = (
        min(min_fcf_recent.values())
        if min_fcf_recent and min(min_fcf_recent.values()) > 0
        else None
    )
    avg_dps = average_dps(ctx.dividends)
    floor = valuation.compute_floor(
        cash=cash.get(latest) if latest else None,
        trad_assets=statements.annual_series(rows, "balance", "trad_asset").get(latest)
        if latest
        else None,
        debt=debt.get(latest) if latest else None,
        equity=equity.get(latest) if latest else None,
        shares=ctx.diluted_shares or ctx.shares,
        closes=ctx.closes,
        average_dps=avg_dps,
        min_fcf=min_fcf,
        rf_pct=ctx.rf_pct,
        price=ctx.price,
        dividend_floor_pct=settings.valuation.dividend_discount_floor,
        composite_method=settings.valuation.composite_method,
        divergence_threshold=settings.valuation.divergence_threshold,
    )
    baselines = floor.baselines
    composite = floor.composite
    stats = floor.stats
    premium = floor.premium
    metric_ledger = metric_registry.build(
        ctx, results, composite=composite, premium=premium, stats=stats
    )
    industry_md = industry.render_section(
        str(ctx.code), metric_ledger, list(industry_peers), industry_name
    )
    fundamental_md = render_extras(fundamental_extras)
    fundamental_section = (
        f"## 十二、补充基本面（Tushare）\n\n{fundamental_md}\n\n"
        if fundamental_md
        else ""
    )
    market_md = render_market(market_extras)
    market_number = "十三" if fundamental_md else "十二"
    market_section = (
        f"## {market_number}、市场与宏观（Tushare）\n\n{market_md}\n\n"
        if market_md
        else ""
    )
    if fundamental_md and market_md:
        disclaimer_heading = "十四"
    elif fundamental_md or market_md:
        disclaimer_heading = "十三"
    else:
        disclaimer_heading = "十二"
    status_label = {"stable": "口径一致", "divergent": "口径分歧", "unavailable": "不可用"}[
        stats.status
    ]
    method_label = "中位数" if settings.valuation.composite_method == "median" else "均值"
    floor_note = (
        f"均值 {_num(stats.mean)} ｜ 中位数 {_num(stats.median)} ｜ "
        f"分歧 {_pct(stats.divergence)}（{status_label}）｜ 采用{method_label}"
    )
    if len(baselines) < 5:
        floor_note += f"；有效锚点 {len(baselines)}/5（缺失或非正已剔除）"
    if stats.status == "divergent":
        floor_note += "。均值受极值影响，建议以中位数为准，且仓位不高于「观察」。"
    elif stats.status == "unavailable":
        floor_note += "。底价不可用，无法据此确认安全边际。"

    def checks_table(result: FactorResult) -> str:
        return _table(
            ["检查项", "结果", "说明"],
            [[c.name, STATUS.get(c.status, c.status), c.detail] for c in result.checks],
            ["l", "l", "l"],
        )

    def metrics_table(result: FactorResult) -> str:
        ids = {
            "粗算回报率 R": "r",
            "精算回报率 GG": "gg",
            "门槛 II": "ii",
            "安全边际 KK": "margin",
        }
        return _table(
            ["指标", "数值"],
            [[k, metric_ledger.display(ids[k]) if k in ids else v] for k, v in result.metrics],
            ["l", "r"],
        )

    def metrics_table_from(values: dict[str, str]) -> str:
        ids = {
            "粗算回报率 R": "r",
            "精算回报率 GG": "gg",
            "门槛 II": "ii",
            "安全边际 KK": "margin",
        }
        return _table(
            ["指标", "数值"],
            [[k, metric_ledger.display(ids[k]) if k in ids else v] for k, v in values.items()],
            ["l", "r"],
        )

    f4 = results["4"]
    f4_metrics = dict(f4.metrics)
    # The final verdict can be capped by the floor-price rules; render that
    # final state in factor 4 instead of the pre-cap "买入/标准仓位".
    f4_metrics["结论"] = verdict
    if verdict == "排除":
        f4_metrics["仓位建议"] = "不建仓"
    elif verdict == "观察" and f4_metrics.get("仓位建议") in {"标准仓位", "70%", "50%"}:
        f4_metrics["仓位建议"] = "观察仓位"

    valuation_rows = [
        ["EV/EBITDA", metric_ledger.display("ev_ebitda")],
        ["净负债/EBITDA", metric_ledger.display("net_debt_ebitda")],
        ["扣除现金 PE", metric_ledger.display("cash_adj_pe")],
        ["P/B", metric_ledger.display("pb")],
        ["FCF 收益率", metric_ledger.display("fcf_yield")],
        ["股息率（3 年均 DPS）", metric_ledger.display("dividend_yield")],
        ["EBITDA 利润率", metric_ledger.display("ebitda_margin")],
        ["商誉/总资产", metric_ledger.display("goodwill_ratio")],
        ["底价均值", metric_ledger.display("floor.mean")],
        ["底价中位数", metric_ledger.display("floor.median")],
        ["口径分歧", f"{metric_ledger.display('floor.divergence')}（{status_label}）"],
    ]
    floor_rows = [[b.name, _num(b.value), b.formula] for b in baselines]

    if ctx.qualitative is not None:
        qual_rows = qual_summary(ctx.qualitative)
        qual_table = _table(
            ["模块", "判断", "置信度", "证据数"],
            [
                [label, {"positive": "正面", "neutral": "中性", "negative": "负面", "unknown": "未验证"}[judgment], confidence, str(count)]
                for label, judgment, confidence, count in qual_rows
            ],
            ["l", "l", "l", "r"],
        )
        evidence = all_evidence(ctx.qualitative)
        evidence_md = (
            "\n".join(
                f"- **{label}**（{source_type}{' · ' + page if page else ''}）：{url} — “{quote}”"
                for label, url, quote, source_type, page in evidence
            )
            or "未提供证据。"
        )
        if ctx.qualitative.discrepancies:
            discrepancy_table = _table(
                ["项目", "CLI", "文档/网页", "来源", "源优先级", "备注"],
                [
                    [
                        d.item,
                        d.cli_value,
                        d.doc_value,
                        d.source,
                        str(d.source_rank or "—"),
                        d.note,
                    ]
                    for d in ctx.qualitative.discrepancies
                ],
            )
        else:
            discrepancy_table = "未发现数字口径冲突。"
    else:
        qual_table = "未提供 qualitative.json，全部定性项标记为 unknown。"
        evidence_md = "未提供证据。"
        discrepancy_table = "未提供 qualitative.json。"

    # -- unknown list / disclaimer / thesis card -------------------------
    if ctx.qualitative is not None:
        unknown_labels = [
            label
            for key, label in MODULES.items()
            if (item := ctx.qualitative.get(key)) is None or item.judgment == "unknown"
        ]
        disclaimer = (
            "本报告由确定性规则生成；定性判断来自 evidence-backed qualitative.json，"
            "未通过校验的判断已降级为 unknown。不构成投资建议。"
        )
    else:
        unknown_labels = list(MODULES.values())
        disclaimer = "本报告由确定性规则生成，未提供定性输入，不构成投资建议。"
    unknown_md = "\n".join(f"- {label}" for label in unknown_labels) or "无（所有模块均有证据化判断）。"

    net_cash = statements.net_cash(rows, ctx.market_cap.currency)
    net_cash_latest = net_cash.get(latest) if latest else None
    net_cash_prev = net_cash.get(latest - 1) if latest is not None else None
    net_cash_status = "数据不足"
    if net_cash_latest is not None and net_cash_prev is not None:
        if net_cash_latest.amount < 0 <= net_cash_prev.amount:
            net_cash_status = "已触发"
        elif net_cash_latest.amount < 0 and net_cash_prev.amount < 0:
            net_cash_status = "持续为负"
        else:
            net_cash_status = "未触发"
    recent_fcf = [v for _, v in sorted(fcf.items())[-3:]]
    negative_fcf_years = sum(1 for value in recent_fcf if value <= 0)
    revenue_yoy = None
    if latest is not None and latest - 1 in revenue and revenue[latest - 1] > 0:
        revenue_yoy = (revenue[latest] / revenue[latest - 1] - 1) * 100

    def _triggered(value: bool | None) -> str:
        if value is None:
            return "数据不足"
        return "已触发" if value else "未触发"

    stop_rows = [
        [
            "净现金",
            "相对上年转负（critical）",
            metric_ledger.display("net_cash.latest"),
            net_cash_status,
        ],
        [
            "FCF 连续为负",
            "连续 2 年 < 0（critical）",
            f"{negative_fcf_years}/3 年为负",
            _triggered(negative_fcf_years >= 2),
        ],
        [
            "FCF 收益率",
            "< 5%（warning）",
            metric_ledger.display("fcf_yield"),
            _triggered(
                ctx.snapshot.fcf_yield is not None and ctx.snapshot.fcf_yield < Decimal("5")
            ),
        ],
        [
            "净负债/EBITDA",
            "> 2x（warning）",
            metric_ledger.display("net_debt_ebitda"),
            _triggered(
                ctx.snapshot.net_debt_ebitda is not None
                and ctx.snapshot.net_debt_ebitda > Decimal("2")
            ),
        ],
        [
            "营收同比",
            "< -20%（warning）",
            metric_ledger.display("revenue.yoy"),
            _triggered(revenue_yoy is not None and revenue_yoy < Decimal("-20")),
        ],
        [
            "商誉/总资产",
            "> 30%（warning）",
            metric_ledger.display("goodwill_ratio"),
            _triggered(
                ctx.snapshot.goodwill_ratio is not None
                and ctx.snapshot.goodwill_ratio > Decimal("30")
            ),
        ],
        [
            "质押率",
            "> 70%（critical）",
            _pct(ctx.pledge_pct),
            "数据未接入"
            if ctx.pledge_pct is None
            else ("已触发" if ctx.pledge_pct > Decimal("70") else "未触发"),
        ],
    ]
    thesis_core = (
        f"当前价 {metric_ledger.display('price')}，GG {metric_ledger.display('gg')} vs "
        f"II {metric_ledger.display('ii')}，安全边际 {metric_ledger.display('margin')}；"
        f"底价溢价 {metric_ledger.display('premium')}，可信度 {f4_metrics.get('外推可信度', '—')}，"
        f"价值陷阱 {f4_metrics.get('价值陷阱', '—')}。"
    )
    thesis_reasons = [
        f"穿透回报：R {metric_ledger.display('r')} / GG {metric_ledger.display('gg')}，门槛 II {metric_ledger.display('ii')}。",
        f"估值与安全边际：EV/EBITDA {metric_ledger.display('ev_ebitda')}，FCF 收益率 {metric_ledger.display('fcf_yield')}，底价溢价 {metric_ledger.display('premium')}。",
        f"分配与现金：支付率 {metric_ledger.display('payout.mean')}，净现金 {metric_ledger.display('net_cash.latest')} 百万元。",
    ]
    thesis_monitor = [
        "回购/增持公告（正面信号）",
        "盈利预警/业绩预告（critical）",
        "管理层或审计师变动（治理信号）",
        "股息政策变化（直接影响分配意愿）",
        "关联交易/资产注入（治理与结构风险）",
        "诉讼、处罚、债务评级变化（尾部风险）",
    ]
    thesis_catalysts = [
        f"分红率维持或提升（当前 {metric_ledger.display('payout.mean')}）",
        f"FCF 连续为正、净现金改善（当前 {metric_ledger.display('net_cash.latest')} 百万元）",
        "回购/增持落地" if ctx.buyback else "暂无回购/增持数据",
        f"估值回到门槛价 {f4_metrics.get('门槛对应价', '—')} 附近",
    ]
    thesis_holding = (
        "一年至两年（等待估值修复/分红兑现）"
        if verdict == "买入"
        else "暂不建仓；观察半年至一年，等待数据或价格改善"
    )
    data_basis = (
        "TTM（最新中报/季报滚动，仅流量科目年化）"
        if any(row.source == "ttm" for row in ctx.rows)
        else ""
    )

    context = {
        "code": str(ctx.code),
        "market": ctx.code.market.value,
        "currency": ctx.market_cap.currency.value,
        "generated_at": as_of,
        "as_of": as_of,
        "research_md": research_md,
        "research_sections": research_sections or [],
        "research_meta_md": research_meta_md,
        "research_summary_md": research_summary_md,
        "research_thesis_md": research_thesis_md,
        "resolved_md": resolved_md,
        "snapshot_id": snapshot_id,
        "verdict": verdict,
        "reason": reason,
        "rf": _pct(ctx.rf_pct),
        "rf_source": rf_source,
        "price": metric_ledger.display("price"),
        "market_cap": _m(ctx.market_cap.amount),
        "metric": metric_ledger.display,
        "metric_registry": metric_ledger,
        "industry_md": industry_md,
        "fundamental_section": fundamental_section,
        "market_section": market_section,
        "disclaimer_heading": disclaimer_heading,
        "data_basis": data_basis,
        "pdf_fact_rows": [
            [
                str(fact.get("label", "")),
                _pdf_value(fact.get("value")),
                str(fact.get("page", "")),
            ]
            for fact in document_facts
        ]
        + [
            [
                f"{row.get('item', '')}:{row.get('label', '')}",
                _pdf_value(row.get("value")),
                str(row.get("page", "")),
            ]
            for row in fact_rows
        ],
        "dps_check": _dps_check_text(
            document_facts,
            ctx.dividends,
            fiscal_year=latest,
            currency=ctx.market_cap.currency,
        ),
        "summary_table": _table(
            ["项目", "数值"],
            [
                ["粗算回报率 R", metric_ledger.display("r")],
                ["精算回报率 GG", metric_ledger.display("gg")],
                ["门槛 II", metric_ledger.display("ii")],
                ["安全边际", metric_ledger.display("margin")],
                [
                    "仓位建议",
                    "不建仓" if verdict == "排除" else f4_metrics.get("仓位建议", "—"),
                ],
                ["因子4 原始结论", dict(results["4"].metrics).get("结论", "—")],
                ["最终结论", verdict],
                ["底价（综合）", metric_ledger.display("floor")],
                ["当前价溢价", metric_ledger.display("premium")],
            ],
            ["l", "r"],
        ),
        "f1a_table": checks_table(results["1A"]),
        "f1b_table": checks_table(results["1B"]),
        "qual_table": qual_table,
        "qual_evidence_md": evidence_md,
        "discrepancy_table": discrepancy_table,
        "f2_table": metrics_table(results["2"]),
        "f3_table": metrics_table(results["3"]),
        "f3_checks": checks_table(results["3"]),
        "f4_table": metrics_table_from(f4_metrics),
        "f4_checks": checks_table(results["4"]),
        "valuation_table": _table(["指标", "数值"], valuation_rows),
        "floor_table": _table(["方法", "价格", "公式"], floor_rows, ["l", "r", "l"]),
        "composite": metric_ledger.display("floor"),
        "premium": metric_ledger.display("premium"),
        "floor_note": floor_note,
        "method_label": method_label,
        "payout": _pct(mean_payout),
        "unknown_md": unknown_md,
        "disclaimer": disclaimer,
        "thesis_core": thesis_core,
        "thesis_reasons_md": "\n".join(f"- {item}" for item in thesis_reasons),
        "thesis_stop_table": _table(
            ["检查项", "触发条件", "当前值", "状态"], stop_rows, ["l", "l", "r", "l"]
        ),
        "thesis_monitor_md": "\n".join(f"- {item}" for item in thesis_monitor),
        "thesis_position": f4_metrics.get("仓位建议", "—"),
        "thesis_catalysts_md": "\n".join(f"- {item}" for item in thesis_catalysts),
        "thesis_holding": thesis_holding,
        "issues_md": "\n".join(f"- {issue}" for issue in issues) or "未检测到数据问题。",
        "notes_1a": "；".join(results["1A"].notes),
        "notes_1b": "；".join(results["1B"].notes),
        "notes_2": "；".join(results["2"].notes),
        "notes_3": "；".join(results["3"].notes),
        "notes_4": "；".join(results["4"].notes),
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    if metrics_out is not None:
        metrics_out.update(metric_ledger.to_dict())
    return env.get_template("analysis.md.j2").render(**context)
