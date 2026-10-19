# PDF 抽取实盘验证：600887 / 00700

> 日期：2026-10-19  
> 样本：2025 年年度报告，A 股 + 港股各一份。  
> 目的：验证 `fetch-report`、`pdf`（章节定位）、`pdf-numbers`（6 项审计数字）、`audit`、以及港股 PDF 间接现金桥。

## 1. 下载

| 样本 | 来源 | 大小 | 结果 |
|:--|:--|--:|:--|
| 600887.SH 伊利股份 2025 年报 | `http://static.cninfo.com.cn/finalpage/2026-04-30/1225259562.PDF` | 1.50 MB / 259 页 | `fetch-report` SUCCESS |
| 00700.HK 腾讯控股 2025 年报 | `https://www1.hkexnews.hk/listedco/listconews/sehk/2026/0409/2026040901231.pdf` | 4.00 MB / 282 页 | `fetch-report` SUCCESS |

`fetch-report` 的 allowlist 覆盖 `static.cninfo.com.cn` 与 `www1.hkexnews.hk`；`rdfile.dzh.com.cn` 不在 allowlist，这是有意的（优先交易所/巨潮官方源）。

## 2. 章节定位

```powershell
turtle pdf --pdf 600887_2025_年报.pdf --output 600887_sections.json --verbose
turtle pdf --pdf 00700_2025_年报.pdf --output 00700_sections.json --verbose
```

| 样本 | 命中 | 说明 |
|:--|:--|:--|
| 600887 | **7/7** | P2/P3/P4/P6/P13/MDA/SUB 全部命中 |
| 00700 | **4/7** | P2/P4/MDA/SUB；P3/P6/P13 在港股年报中没有对应章节或关键词不同 |

M6 验收阈值是 4/7，港股样本刚好达标；港股 P3/P6/P13 属于“不适用/缺失”，不应强行用 A 股规则匹配。

## 3. 六项审计数字

```powershell
turtle pdf-numbers --pdf <pdf> --year 2025 --output reported_numbers.json
turtle audit <code> --doc reported_numbers.json --threshold 1
```

### 600887.SH

| 项目 | PDF 抽取 | 页码 | 审计 |
|:--|--:|--:|:--|
| 营业收入 | 115,636,231,250.05 | 86 | 通过 |
| 归母净利润 | 11,565,166,497.81 | 87 | 通过 |
| OCF | 14,343,920,490.32 | 89 | 通过 |
| Capex | 3,036,644,156.68 | 90 | 通过 |
| 归母权益 | 54,655,690,475.89 | 83 | 通过 |
| 总资产 | 152,098,516,632.34 | 82 | 通过 |

**6/6，audit 无冲突。**

### 00700.HK

| 项目 | PDF 抽取 | 页码 | 审计 |
|:--|--:|--:|:--|
| 营业收入 | 751,766,000,000.00 | 130 | **差 1.09%** |
| 归母净利润 | 224,842,000,000.00 | 130 | 通过 |
| OCF | 303,052,000,000.00 | 139 | 通过 |
| Capex | 112,881,000,000.00 | 139 | 通过（PPE 87,482 + 无形 25,399） |
| 归母权益 | 1,154,152,000,000.00 | 133 | 通过 |
| 总资产 | 2,038,986,000,000.00 | 132 | 通过 |

**6/6 抽取；audit 只报营业收入 1.09% 差异。**

原因：PDF 的 `Revenues` 合计 751,766 百万；Tushare `hk_income` 的“营业额”为 743,689 百万，差额 8,077 百万正好是 PDF 分部中的 `Others`。这是**数据源差异**，不应由抽取器改数；`audit` 保留告警是正确的。

Capex 的另一个真实问题：Tushare 原先只映射“购建无形资产及其他资产”25,393，漏了 PPE 87,482。现在 HK cashflow 把两项相加，CLI 112,875 vs PDF 112,881（0.005%），audit 通过。

## 4. 港股 PDF 间接现金桥

`pdf-numbers` 在港股 PDF 上会额外输出：

```json
"cash_bridge": {
  "net_profit": "229801000000.00",
  "depreciation_amortisation": "66028000000.00",
  "working_capital_change": "16904000000.00",
  "cash_generated_from_operations": "347751000000.00",
  "income_tax_paid": "-44699000000.00",
  "ocf": "303052000000.00",
  "capex": "112881000000.00",
  "page": "139"
}
```

然后：

```powershell
turtle pack 00700.HK --pdf-numbers 00700_numbers.json
turtle report 00700.HK --pdf-numbers 00700_numbers.json
```

报告会标为 `AA_2y（PDF间接现金桥+历史口径）`，并显示净利润 → D&A → 营运资本 → 经营产生现金 → 所得税 → OCF → Capex。

### 为什么不是“直接桥”
腾讯年报的现金流量表采用**间接法**，没有“销售商品收到现金/购买商品支付现金/支付职工现金”等毛利收付科目。即使读 PDF，也无法凭空得到直接法现金桥。现在做的是**能拿到的最完整版本：PDF 间接桥**，不是伪造直接桥。

## 5. 仍需注意

- 真实年报版式多：当前规则覆盖“合并报表 + 中文/英文常见标签”，仍需更多样本（银行、地产、红筹、同股不同权）验证。
- PDF 页眉/页码与 PDF 物理页可能差 1；输出使用物理页，人工复核时以 PDF 阅读器页码为准。
- 港股营收的 Tushare/PDF 差异应保留在 `discrepancies`，不要静默覆盖。
- PDF 附注表格（账龄、关联方、或有负债）仍是章节上下文，不是结构化表。
