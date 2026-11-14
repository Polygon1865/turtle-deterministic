# 报告里还没进 MetricRegistry 的数字（W2.0 盘点）

由 `scripts/inventory_numbers.py` 生成；改动机器可读源，不要手改本文。
口径：f-string 数字格式、`Decimal.quantize`、`format()`、以及 `_pct/_m/_ratio_pct/_num/_x` 等共享格式化函数；
已走 `metric_ledger.display()` 或 `{{metric:…}}` 的行不计入。

合计：**89** 处，分布在 5 个文件。

| 文件 | 处数 | 最集中的函数 |
| --- | --- | --- |
| `pack.py` | 32 | `render_data_pack` (31) |
| `market.py` | 26 | `_flow_section` (7) |
| `extras.py` | 17 | `_indicator_section` (7) |
| `analysis.py` | 11 | `render_analysis` (7) |
| `html.py` | 3 | `markdown_to_html` (3) |

## `pack.py`（32 处）

| 行 | 函数 | 方式 | 片段 |
| --- | --- | --- | --- |
| 59 | `_quote_note` | fstring | `price_text = f"{Decimal(str(local)):,.2f}"` |
| 242 | `render_data_pack` | helper | `_m(aa_bridge[year].surplus),` |
| 280 | `render_data_pack` | helper | `f"均值 {_num(stats.mean)} ｜ 中位数 {_num(stats.median)} ｜ "` |
| 281 | `render_data_pack` | helper | `f"分歧 {_pct(stats.divergence)}（{status_label}）｜ 采用{method_label}"` |
| 385 | `render_data_pack` | helper | `("eps", eps, lambda value: _num(value, 2), "元"),` |
| 450 | `render_data_pack` | fstring | `f"{ocf[y] / net_income[y] * 100:.2f}%"` |
| 475 | `render_data_pack` | helper | `_m(raw),` |
| 476 | `render_data_pack` | helper | `_m(raw * factor) if raw is not None else "—",` |
| 481 | `render_data_pack` | fstring | `f"年化系数 ×{factor:.2f}；仅作参考，不替代年报。"` |
| 493 | `render_data_pack` | helper | `ttm_rows.append([label, _m(value)])` |
| 518 | `render_data_pack` | helper | `dps_display = _num(bucket["dps"], 4) if bucket["dps_reliable"] else "—"` |
| 569 | `render_data_pack` | helper | `["股份支付 SBC（百万元）", _m(sbc_amount) if sbc_amount else "—"],` |
| … | | | 其余 20 处 |

## `market.py`（26 处）

| 行 | 函数 | 方式 | 片段 |
| --- | --- | --- | --- |
| 30 | `_m` | helper | `def _m(value: Any) -> str:` |
| 34 | `_num` | helper | `def _num(value: Any, digits: int = 2) -> str:` |
| 38 | `_pct` | helper | `def _pct(value: Any) -> str:` |
| 43 | `_major_value` | helper | `text = _num(row.get("value"))` |
| 80 | `_research_section` | helper | `_m(row.get("revenue")),` |
| 81 | `_research_section` | helper | `_m(row.get("net_profit")),` |
| 82 | `_research_section` | helper | `_num(row.get("eps")),` |
| 83 | `_research_section` | helper | `_num(row.get("pe")),` |
| 103 | `_macro_value` | helper | `return _pct(value)` |
| 105 | `_macro_value` | helper | `return f"{_num(value, 0)} 亿元"` |
| 106 | `_macro_value` | helper | `return _num(value)` |
| 119 | `_macro_section` | helper | `_pct(row.get("yoy")) if row.get("yoy") is not None else "—",` |
| … | | | 其余 14 处 |

## `extras.py`（17 处）

| 行 | 函数 | 方式 | 片段 |
| --- | --- | --- | --- |
| 40 | `_money` | helper | `return _m(amount) if amount is not None else "—"` |
| 45 | `_count` | helper | `return _num(amount, 0) if amount is not None else "—"` |
| 56 | `_indicator_section` | helper | `_pct(_d(row.get("roe"))),` |
| 57 | `_indicator_section` | helper | `_pct(_d(row.get("gross_margin"))),` |
| 58 | `_indicator_section` | helper | `_pct(_d(row.get("net_margin"))),` |
| 59 | `_indicator_section` | helper | `_pct(_d(row.get("debt_ratio"))),` |
| 60 | `_indicator_section` | helper | `_pct(_d(row.get("ocf_to_revenue"))),` |
| 61 | `_indicator_section` | helper | `_num(_d(row.get("eps"))),` |
| 62 | `_indicator_section` | helper | `_num(_d(row.get("bps"))),` |
| 91 | `_forecast_section` | helper | `_pct(_d(row.get("p_change_min"))),` |
| 92 | `_forecast_section` | helper | `_pct(_d(row.get("p_change_max"))),` |
| 120 | `_forecast_section` | helper | `_pct(_d(row.get("roe"))),` |
| … | | | 其余 5 处 |

## `analysis.py`（11 处）

| 行 | 函数 | 方式 | 片段 |
| --- | --- | --- | --- |
| 40 | `_price_text` | fstring | `local_text = f"{Decimal(str(local)):,.2f}"` |
| 96 | `_pdf_value` | helper | `return _m(value) if abs(value) >= Decimal("1000") else _num(value, 4)` |
| 122 | `_dps_check_text` | fstring | `f"DPS 核对：{check.status}；PDF {check.pdf_dps:.4f} / "` |
| 123 | `_dps_check_text` | fstring | `f"供应商 {check.provider_dps:.4f}，差异 {check.diff_pct:.2f}%"` |
| 222 | `render_analysis` | helper | `f"均值 {_num(stats.mean)} ｜ 中位数 {_num(stats.median)} ｜ "` |
| 223 | `render_analysis` | helper | `f"分歧 {_pct(stats.divergence)}（{status_label}）｜ 采用{method_label}"` |
| 288 | `render_analysis` | helper | `floor_rows = [[b.name, _num(b.value), b.formula] for b in baselines]` |
| 416 | `render_analysis` | helper | `_pct(ctx.pledge_pct),` |
| 523 | `render_analysis` | helper | `"rf": _pct(ctx.rf_pct),` |
| 527 | `render_analysis` | helper | `"market_cap": _m(ctx.market_cap.amount),` |
| 579 | `render_analysis` | helper | `"payout": _pct(mean_payout),` |

## `html.py`（3 处）

| 行 | 函数 | 方式 | 片段 |
| --- | --- | --- | --- |
| 535 | `markdown_to_html` | fstring | `"@media(max-width:900px){.layout.with-toc{grid-template-columns:1fr}.toc{display:none}"` |
| 536 | `markdown_to_html` | fstring | `".quickread{grid-template-columns:1fr}}",` |
| 540 | `markdown_to_html` | fstring | `"th,td{padding:8px 9px}.quickread{padding:15px}.qr-grid{grid-template-columns:1fr 1fr}"` |

## 归属建议

- `analysis.py` 的汇总表/因子表：应迁到 `MetricPoint`，数字由 registry 提供。
- `pack.py` 的数据包行：多为原始行值，保留但标注 `source_fact_ids`。
- `html.py`：只应格式化已解析的字符串，出现数字格式说明解析层漏了。
- 每次迁移后重跑本脚本，数字应单调下降；W2.1 的验收是降到 0。
