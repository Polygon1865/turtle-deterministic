# PDF Facts 覆盖矩阵

状态按六项验收：value / page / unit / source_fact_ids / data_pack / report。

| 字段 | value | page | unit | source_fact_ids | data_pack | report | 状态 |
|:--|:--|:--|:--|:--|:--|:--|:--|
| accounts_receiv | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 完成 |
| inventory | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 完成 |
| contract_liab | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | 完成 |
| dps | ✅ | ✅ | ✅ | ✅ | 证据表 | ✅ | 完成；未覆盖 Tushare 分红指标 |
| main_business | ✅ | ✅ | ✅ | ✅ | 合并行 | ✅ | 完成 |
| capex_detail | — | — | — | — | — | — | 未完成；当前没有多行 capex 解析器 |

说明：

- `accounts_receiv` / `inventory` / `contract_liab` 会覆盖资产负债表对应 annual 行，MetricPoint 的 `source_fact_ids` 指向 `pdf:<item>:<page>`。
- `dps` 进入 `reported_numbers.json` 的 `document_facts`，报告和 data pack 的「PDF 证据」表展示；尚未替换 Tushare DPS 指标。
- `main_business` 由 `fact_rows` 转成 data pack 分部行，报告中以「PDF 证据」展示；尚未生成独立 MetricPoint。
- `capex_detail` 不得伪造：当前 PDF 抽取器没有多行 capex 表格解析器。
