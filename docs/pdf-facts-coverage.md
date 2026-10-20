# PDF Facts 覆盖矩阵

状态按六项验收：value / page / unit / source_fact_ids / data_pack / report。

| 字段 | value | page | unit | source_fact_ids | data_pack | report | 状态 |
|:--|:--|:--|:--|:--|:--|:--|:--|
| accounts_receiv | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 完成 |
| inventory | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 完成 |
| contract_liab | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 完成 |
| dps | ✅ | ✅ | ✅ | ✅ | 证据表 | ✅ | 完成；未覆盖 Tushare 分红指标 |
| main_business | ✅ | ✅ | ✅ | ✅ | 合并行 | ✅ | 完成 |
| capex_detail | not_applicable | not_applicable | not_applicable | not_applicable | not_applicable | not_applicable | 源 PDF 无可解析多行 capex 表；只记录总 Capex，不伪造 |

说明：

- `accounts_receiv` / `inventory` / `contract_liab` 会覆盖资产负债表对应 annual 行，MetricPoint 的 `source_fact_ids` 指向 `pdf:<item>:<page>`。
- `dps` 进入 `reported_numbers.json` 的 `document_facts`，报告和 data pack 的「PDF 证据」表展示；尚未替换 Tushare DPS 指标。
- `main_business` 由 `fact_rows` 转成 data pack 分部行，并生成 `main_business.<label>` MetricPoint；PDF label 优先去重。
- `capex_detail` 不得伪造：11 份官方 PDF 只有总 Capex，没有多行明细表。
- 2026-10-21：用户确认 A，`capex_detail` 作为已接受的 `not_applicable`；Phase 2 覆盖 Gate 放行。
