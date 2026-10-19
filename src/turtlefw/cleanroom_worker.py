"""Independent clean-room worker.

Runs as a separate process and reads only the frozen snapshot inputs and the
PDF-reported numbers. It does not import the factor engine, report renderer or
metric registry. Its job is to catch source/period/unit errors and to provide a
second, deliberately simple penetration-return calculation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median
from typing import Any


def dec(value: Any) -> Decimal | None:
    if value in (None, "", "—", "nan"):
        return None
    try:
        return Decimal(str(value).replace(",", ""))
    except InvalidOperation:
        return None


def _mean(values: list[Decimal]) -> Decimal | None:
    return sum(values, Decimal("0")) / Decimal(len(values)) if values else None


def _series(
    annual: dict[int, dict[tuple[str, str], Decimal]],
    statement: str,
    item: str,
) -> dict[int, Decimal]:
    return {
        year: values[(statement, item)]
        for year, values in annual.items()
        if (statement, item) in values
    }


def _sum_series(
    annual: dict[int, dict[tuple[str, str], Decimal]],
    statement: str,
    items: tuple[str, ...],
) -> dict[int, Decimal]:
    result: dict[int, Decimal] = {}
    for year, values in annual.items():
        present = [values[(statement, item)] for item in items if (statement, item) in values]
        if present:
            result[year] = sum(present, Decimal("0"))
    return result


def _payout(
    events: list[dict[str, Any]],
    income: dict[int, Decimal],
    shares: Decimal | None,
) -> Decimal | None:
    totals: dict[int, Decimal] = {}
    explicit: dict[int, list[Decimal]] = {}
    seen: set[tuple[int, str]] = set()
    years_with_events: set[int] = set()
    for event in events:
        year = int(event.get("fiscal_year", 0))
        event_id = str(event.get("event_id", ""))
        if not year or (year, event_id) in seen:
            continue
        seen.add((year, event_id))
        years_with_events.add(year)
        payout_pct = dec(event.get("payout_pct"))
        if payout_pct is not None:
            explicit.setdefault(year, []).append(payout_pct)
            continue
        total = dec(event.get("total"))
        if total is None and bool(event.get("dps_reliable", False)) and shares:
            dps = dec(event.get("dps"))
            total = dps * shares if dps is not None else None
        if total is not None:
            totals[year] = totals.get(year, Decimal("0")) + total
    payouts: dict[int, Decimal | None] = {}
    for year, value in income.items():
        if year in explicit:
            payouts[year] = _mean(explicit[year])
        elif value <= 0:
            payouts[year] = None
        elif year not in totals:
            payouts[year] = None if year in years_with_events else Decimal("0")
        else:
            payouts[year] = totals[year] / value * Decimal("100")
    recent = sorted(payouts, reverse=True)[:3]
    recent_values: list[Decimal] = []
    for year in recent:
        payout_value = payouts[year]
        if payout_value is not None:
            recent_values.append(payout_value)
    return _mean(recent_values)



def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--pdf-file", default=None)
    parser.add_argument("--threshold", type=str, default="1")
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    snapshot = Path(args.snapshot)
    inputs = json.loads((snapshot / "inputs.json").read_text(encoding="utf-8-sig"))
    pdf = json.loads(Path(args.pdf).read_text(encoding="utf-8-sig"))
    threshold = Decimal(args.threshold)
    actual_document_hash = ""
    if args.pdf_file and Path(args.pdf_file).is_file():
        digest = hashlib.sha256()
        with Path(args.pdf_file).open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        actual_document_hash = digest.hexdigest()
    claimed_document_hash = str(pdf.get("document_hash", ""))
    document_hash_verified = (
        actual_document_hash == claimed_document_hash
        if actual_document_hash
        else None
    )

    rows = inputs.get("rows", [])
    annual: dict[int, dict[tuple[str, str], Decimal]] = {}
    for row in rows:
        if row.get("period_type") != "annual":
            continue
        year = int(str(row.get("period_end", ""))[:4])
        row_value = dec(row.get("value"))
        if row_value is not None:
            annual.setdefault(year, {})[(str(row.get("statement")), str(row.get("item")))] = row_value
    latest = max(annual) if annual else None
    values = annual.get(latest, {}) if latest is not None else {}

    def metric_value(statement: str, item: str) -> Decimal | None:
        return values.get((statement, item))

    canonical = {
        "revenue": metric_value("income", "revenue"),
        "net_income": metric_value("income", "n_income_attr_p"),
        "ocf": metric_value("cashflow", "n_cashflow_act"),
        "capex": metric_value("cashflow", "c_pay_acq_const_fiolta"),
        "equity": metric_value("balance", "total_hldr_eqy_exc_min_int"),
        "total_assets": metric_value("balance", "total_assets"),
    }
    labels = {
        "revenue": "营业收入",
        "net_income": "归母净利润",
        "ocf": "经营现金流",
        "capex": "资本开支",
        "equity": "归母权益",
        "total_assets": "总资产",
    }
    checks: list[dict[str, Any]] = []
    for item in pdf.get("items", []):
        key = str(item.get("item", ""))
        base = canonical.get(key)
        doc = dec(item.get("value"))
        if base is None or doc is None or base == 0:
            checks.append({"item": key, "label": labels.get(key, key), "status": "missing"})
            continue
        diff = abs(doc - base) / abs(base) * Decimal("100")
        checks.append(
            {
                "item": key,
                "label": labels.get(key, key),
                "snapshot_value": str(base),
                "document_value": str(doc),
                "diff_pct": str(diff.quantize(Decimal("0.01"))),
                "status": "pass" if diff <= threshold else "review",
                "source": f"{item.get('source', '')} {item.get('page', '')}".strip(),
                "source_rank": int(item.get("source_rank", 1)),
            }
        )

    market_cap = dec(inputs.get("market_cap"))
    buyback = dec(inputs.get("buyback")) or Decimal("0")
    sbc = dec(inputs.get("sbc")) or Decimal("0")
    shares = dec(inputs.get("shares"))
    dividends = inputs.get("dividends", [])
    income_series = _series(annual, "income", "n_income_attr_p")
    revenue_series = _series(annual, "income", "revenue")
    da_series = _sum_series(
        annual,
        "cashflow",
        ("depr_fa_coga_dpba", "amort_intang_assets", "lt_amort_deferred_exp"),
    )
    capex_series = _series(annual, "cashflow", "c_pay_acq_const_fiolta")
    payout = _payout(dividends, income_series, shares)

    # G: Capex/D&A median over the last five years.
    ratios = [
        abs(capex_series[year]) / da_series[year]
        for year in sorted(set(capex_series) & set(da_series))[-5:]
        if da_series[year] > 0
    ]
    ratio = Decimal(str(median(float(value) for value in ratios))) if ratios else None
    g_light, g_mid, g_heavy, g_default = (
        Decimal("0.85"),
        Decimal("1.15"),
        Decimal("1.50"),
        Decimal("1.00"),
    )
    config_path = snapshot / "config.toml"
    if config_path.is_file():
        config = tomllib.loads(config_path.read_text(encoding="utf-8"))
        returns_cfg = config.get("returns", {})
        g_light = dec(returns_cfg.get("g_light")) or g_light
        g_mid = dec(returns_cfg.get("g_mid")) or g_mid
        g_heavy = dec(returns_cfg.get("g_heavy")) or g_heavy
        g_default = dec(returns_cfg.get("g_default")) or g_default
    if ratio is None:
        g = g_default
    elif ratio < Decimal("0.9"):
        g = g_light
    elif ratio < Decimal("1.3"):
        g = g_mid
    else:
        g = g_heavy

    # Owner earnings: 5-year normalised if possible, otherwise current year.
    oe_values: list[Decimal] = []
    ar = _series(annual, "balance", "accounts_receiv")
    inventory = _series(annual, "balance", "inventories")
    payable = _series(annual, "balance", "acct_payable")
    for year in sorted(set(income_series) & set(da_series))[-5:]:
        net_income = income_series.get(year)
        depreciation = da_series.get(year)
        if net_income is None or depreciation is None:
            continue
        wc_change = Decimal("0")
        if year - 1 in ar and year in ar:
            wc_change += ar[year] - ar[year - 1]
        if year - 1 in inventory and year in inventory:
            wc_change += inventory[year] - inventory[year - 1]
        if year - 1 in payable and year in payable:
            wc_change -= payable[year] - payable[year - 1]
        oe_values.append(net_income + depreciation - depreciation * g - wc_change)
    oe = _mean(oe_values)
    if oe is None and latest is not None:
        net_income = income_series.get(latest)
        depreciation = da_series.get(latest)
        if net_income is not None and depreciation is not None:
            oe = net_income + depreciation - depreciation * g

    # Cash bridge (same definitions as the main engine, independently coded).
    revenue = revenue_series
    cash_received = _series(annual, "cashflow", "c_fr_sale_sg")
    inflow_total = _series(annual, "cashflow", "c_inf_fr_operate_a")
    prepayments = _series(annual, "balance", "prepayments")
    advance = _series(annual, "balance", "adv_receipts") or _series(
        annual, "balance", "contract_liab"
    )
    goods = _series(annual, "cashflow", "c_paid_goods_srv")
    employees = _series(annual, "cashflow", "c_paid_to_for_empl")
    taxes = _series(annual, "cashflow", "c_paid_for_taxes")
    other = _series(annual, "cashflow", "c_pay_oth_act")
    ocf = _series(annual, "cashflow", "n_cashflow_act")
    capex = capex_series
    surplus: dict[int, Decimal] = {}
    for year in sorted(set(revenue) | set(ocf) | set(cash_received) | set(inflow_total)):
        rev = revenue.get(year)
        cash_in = cash_received.get(year)
        ar_change = ar[year] - ar[year - 1] if year in ar and year - 1 in ar else None
        advance_change = (
            advance[year] - advance[year - 1]
            if year in advance and year - 1 in advance
            else None
        )
        prepay_change = (
            prepayments[year] - prepayments[year - 1]
            if year in prepayments and year - 1 in prepayments
            else None
        )
        true_cash = cash_in
        if true_cash is None and rev is not None:
            ar_increase = max(ar_change or Decimal("0"), Decimal("0"))
            advance_decrease = max(-(advance_change or Decimal("0")), Decimal("0"))
            prepay_increase = max(prepay_change or Decimal("0"), Decimal("0"))
            true_cash = rev - ar_increase - prepay_increase - advance_decrease
            if advance_change is not None and advance_change > 0:
                true_cash += advance_change
        parts = [goods.get(year), employees.get(year), taxes.get(year), other.get(year)]
        present = [value for value in parts if value is not None]
        outflows = sum(present, Decimal("0")) if len(present) >= 3 else None
        derived = False
        if outflows is None and inflow_total.get(year) is not None and ocf.get(year) is not None:
            outflows = inflow_total[year] - ocf[year]
            derived = True
        if derived and rev is not None and ar_change is not None and advance_change is not None:
            true_cash = (
                rev
                - max(ar_change, Decimal("0"))
                - max(prepay_change or Decimal("0"), Decimal("0"))
                - max(-advance_change, Decimal("0"))
                + max(advance_change, Decimal("0"))
            )
        capex_value = abs(capex[year]) if year in capex else None
        if true_cash is not None and outflows is not None:
            surplus_value = true_cash - outflows - (capex_value or Decimal("0"))
        elif ocf.get(year) is not None:
            surplus_value = ocf[year] - (capex_value or Decimal("0"))
        else:
            continue
        surplus[year] = surplus_value
    pdf_bridge = inputs.get("pdf_bridge") or {}
    for year_text, bridge in pdf_bridge.items():
        year = int(year_text)
        ocf_value = dec(bridge.get("ocf"))
        capex_value = dec(bridge.get("capex"))
        if ocf_value is not None and capex_value is not None:
            surplus[year] = ocf_value - abs(capex_value)
    aa_values = [surplus[year] for year in sorted(surplus)]
    aa_value: Decimal | None = None
    if aa_values:
        aa_value = _mean(aa_values[-2:])
    if aa_value is None:
        fcf_values = [
            ocf[year] - abs(capex.get(year, Decimal("0")))
            for year in sorted(ocf)
        ]
        aa_value = _mean(fcf_values)

    code = str(inputs.get("code", ""))
    tax = Decimal("20") if code.endswith(".HK") else Decimal("10") if code.endswith(".US") else Decimal("0")
    independent: dict[str, Any] = {"formula": "owner_earnings.cash_bridge"}
    independent["g"] = str(g)
    if payout is not None:
        independent["payout"] = str(payout)
    if oe is not None:
        independent["oe"] = str(oe)
    if aa_value is not None:
        independent["aa"] = str(aa_value)
    if market_cap and market_cap > 0 and payout is not None and oe is not None:
        factor = payout / Decimal("100") * (Decimal("1") - tax / Decimal("100"))
        r_value = (oe * factor + buyback) / market_cap * Decimal("100")
        independent["r"] = str(r_value.quantize(Decimal("0.01")))
    if market_cap and market_cap > 0 and payout is not None and aa_value is not None:
        factor = payout / Decimal("100") * (Decimal("1") - tax / Decimal("100"))
        gg_value = ((aa_value - sbc) * factor + buyback) / market_cap * Decimal("100")
        independent["gg"] = str(gg_value.quantize(Decimal("0.01")))

    ledger: dict[str, Any] = {}
    metrics_path = snapshot / "metrics.json"
    if metrics_path.is_file():
        metrics = json.loads(metrics_path.read_text(encoding="utf-8-sig"))
        for key in ("r", "gg"):
            point = metrics.get(key)
            if isinstance(point, dict):
                ledger[key] = point.get("value")
    comparisons: dict[str, Any] = {}
    for key in ("r", "gg"):
        actual = dec(independent.get(key))
        expected = dec(ledger.get(key))
        if actual is None or expected is None or expected == 0:
            comparisons[key] = {"status": "missing"}
            continue
        diff = abs(actual - expected) / abs(expected) * Decimal("100")
        comparisons[key] = {
            "independent": str(actual),
            "ledger": str(expected),
            "diff_pct": str(diff.quantize(Decimal("0.01"))),
            "status": "pass" if diff <= Decimal("25") else "info",
        }

    review = [check for check in checks if check["status"] == "review"]
    formula_review = [
        key
        for key, item in comparisons.items()
        if item.get("status") == "info"
    ]
    if document_hash_verified is False:
        review.append({"item": "document_hash", "status": "review"})
    result = {
        "mode": "independent-subprocess",
        "snapshot": str(snapshot),
        "pdf_numbers": str(args.pdf),
        "pdf_file": str(args.pdf_file or ""),
        "document_hash": claimed_document_hash,
        "actual_document_hash": actual_document_hash,
        "document_hash_verified": document_hash_verified,
        "document_fact_count": len(pdf.get("document_facts", [])),
        "row_count": len(rows),
        "latest_year": latest,
        "checks": checks,
        "independent_metrics": independent,
        "ledger_comparison": comparisons,
        "formula_review": formula_review,
        "status": "review" if review else "pass",
    }
    text = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
