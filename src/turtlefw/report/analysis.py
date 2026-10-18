"""Analysis report rendering (four factors + verdict)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from jinja2 import Environment, FileSystemLoader

from ..config import Settings
from ..factors.engine import FactorContext, FactorResult, final_verdict
from ..metrics import statements, valuation
from ..qualitative import JUDGMENTS, MODULES, all_evidence, summary as qual_summary
from ..types import FetchIssue
from .pack import TEMPLATE_DIR, _m, _num, _pct, _table, _x, average_dps

STATUS = {"pass": "通过", "veto": "否决", "unknown": "未验证", "info": "观察"}


def render_analysis(
    ctx: FactorContext,
    results: dict[str, FactorResult],
    *,
    settings: Settings,
    snapshot_id: str,
    rf_source: str,
    issues: Sequence[FetchIssue] = (),
) -> str:
    verdict, reason = final_verdict(results)
    rows = ctx.rows
    years = sorted({r.period_end.year for r in rows if r.period_type == "annual"})
    latest = max(years) if years else None

    income = statements.net_income(rows)
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
    baselines = valuation.five_baselines(
        cash=cash.get(latest) if latest else None,
        trad_assets=statements.annual_series(rows, "balance", "trad_asset").get(latest)
        if latest
        else None,
        debt=debt.get(latest) if latest else None,
        equity=equity.get(latest) if latest else None,
        shares=ctx.shares,
        closes=ctx.closes,
        average_dps=average_dps(ctx.dividends),
        min_fcf=min_fcf,
        rf_pct=ctx.rf_pct,
        dividend_floor_pct=settings.valuation.dividend_discount_floor,
    )
    composite = valuation.composite(baselines, settings.valuation.composite_method)
    premium = valuation.premium(ctx.price, composite) if ctx.price and composite else None

    def checks_table(result: FactorResult) -> str:
        return _table(
            ["检查项", "结果", "说明"],
            [[c.name, STATUS.get(c.status, c.status), c.detail] for c in result.checks],
            ["l", "l", "l"],
        )

    def metrics_table(result: FactorResult) -> str:
        return _table(["指标", "数值"], [[k, v] for k, v in result.metrics], ["l", "r"])

    f4 = results["4"]
    f4_metrics = dict(f4.metrics)
    f2_metrics = dict(results["2"].metrics)
    f3_metrics = dict(results["3"].metrics)

    valuation_rows = [
        ["EV/EBITDA", _x(ctx.snapshot.ev_ebitda)],
        ["净负债/EBITDA", _x(ctx.snapshot.net_debt_ebitda)],
        ["扣除现金 PE", _x(ctx.snapshot.cash_adj_pe)],
        ["P/B", _x(ctx.snapshot.pb)],
        ["FCF 收益率", _pct(ctx.snapshot.fcf_yield)],
        ["股息率（3 年均 DPS）", _pct(ctx.snapshot.dividend_yield)],
        ["EBITDA 利润率", _pct(ctx.snapshot.ebitda_margin)],
        ["商誉/总资产", _pct(ctx.snapshot.goodwill_ratio)],
    ]
    floor_rows = [[b.name, _num(b.value), b.formula] for b in baselines]

    if ctx.qualitative is not None:
        rows = qual_summary(ctx.qualitative)
        qual_table = _table(
            ["模块", "判断", "置信度", "证据数"],
            [
                [label, {"positive": "正面", "neutral": "中性", "negative": "负面", "unknown": "未验证"}[judgment], confidence, str(count)]
                for label, judgment, confidence, count in rows
            ],
            ["l", "l", "l", "r"],
        )
        evidence = all_evidence(ctx.qualitative)
        evidence_md = (
            "\n".join(
                f"- **{label}**：{url} — “{quote}”" for label, url, quote in evidence
            )
            or "未提供证据。"
        )
    else:
        qual_table = "未提供 qualitative.json，全部定性项标记为 unknown。"
        evidence_md = "未提供证据。"

    context = {
        "code": str(ctx.code),
        "market": ctx.code.market.value,
        "currency": ctx.market_cap.currency.value,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "snapshot_id": snapshot_id,
        "verdict": verdict,
        "reason": reason,
        "rf": _pct(ctx.rf_pct),
        "rf_source": rf_source,
        "price": _num(ctx.price),
        "market_cap": _m(ctx.market_cap.amount),
        "summary_table": _table(
            ["项目", "数值"],
            [
                ["粗算回报率 R", f2_metrics.get("粗算回报率 R", "—")],
                ["精算回报率 GG", f3_metrics.get("精算回报率 GG", "—")],
                ["门槛 II", f2_metrics.get("门槛 II", "—")],
                ["安全边际", f4_metrics.get("安全边际 KK", "—")],
                ["仓位建议", "不建仓" if verdict == "排除" else f4_metrics.get("仓位建议", "—")],
                ["因子4 独立结论", f4_metrics.get("结论", "—")],
                ["底价（综合）", _num(composite)],
                ["当前价溢价", _pct(premium)],
            ],
            ["l", "r"],
        ),
        "f1a_table": checks_table(results["1A"]),
        "f1b_table": checks_table(results["1B"]),
        "qual_table": qual_table,
        "qual_evidence_md": evidence_md,
        "f2_table": metrics_table(results["2"]),
        "f3_table": metrics_table(results["3"]),
        "f4_table": metrics_table(results["4"]),
        "f4_checks": checks_table(results["4"]),
        "valuation_table": _table(["指标", "数值"], valuation_rows),
        "floor_table": _table(["方法", "价格", "公式"], floor_rows, ["l", "r", "l"]),
        "composite": _num(composite),
        "premium": _pct(premium),
        "payout": _pct(mean_payout),
        "issues_md": "\n".join(f"- {issue}" for issue in issues) or "未检测到数据问题。",
        "notes_1a": "；".join(results["1A"].notes),
        "notes_1b": "；".join(results["1B"].notes),
        "notes_2": "；".join(results["2"].notes),
        "notes_3": "；".join(results["3"].notes),
        "notes_4": "；".join(results["4"].notes),
    }

    env = Environment(loader=FileSystemLoader(TEMPLATE_DIR), autoescape=False)
    return env.get_template("analysis.md.j2").render(**context)
