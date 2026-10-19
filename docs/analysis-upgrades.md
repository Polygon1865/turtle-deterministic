# 三项分析升级：SBC/稀释/复权、税档/OE、附注/股东分部

> 日期：2026-10-19  
> 目标：把“会改数字”的三类问题落地，而不是再加报告段落。

## 1. SBC / 稀释 / 复权 / point-in-time

### SBC
- PDF 抽取新增 `sbc`：优先 `Equity-settled share-based compensation`，其次 `股份支付费用`；
- 港股 00700 实测：SBC **25,660 百万元**（p.263，权益结算口径）；
- `AA` 扣减 SBC 后再算 GG；数据包/报告显示 SBC 和“已扣 SBC”；
- A 股 PDF 的“股份支付计入所有者权益的金额”不会被误当成 SBC（已修正别名）。

### 稀释
- `statements.diluted_shares()`：归母净利润 / 稀释 EPS；
- 00700：稀释后 **93.10 亿股**（当前总股本约 90.05 亿股）；
- 底价、DCF、PS、反推增长使用稀释后股数；分红/支付率仍用当前股本。

### 复权
- A 股 `weekly` 现在读取 Tushare `adj_factor`，按“最新因子=1”做后复权；
- 52 周高低、10 年最低、当前价同一价格基准；
- 新增 `metrics/prices.py` 纯函数 + 测试。

### point-in-time（部分）
- `screen --as-of YYYY-MM-DD`：合并 `L/D/P` 上市状态，按 `list_date/delist_date` 过滤；行情用该日 `daily_basic` 快照；
- **限制**：财务指标仍为最新报表，不是完整 PIT；真正 PIT 需要历史财务快照库。

## 2. 税档情景 + Owner Earnings 正常化

### 税档
- 因子 2/3 报告新增：
  - `税档情景 R`：A 股 0/10/20%；港股 28/20/20%；
  - `税档情景 GG`：同上；
- 结论仍按当前适用税率，情景只用于敏感性展示，不偷偷改结论；
- 例：600887 R 3.36% / 3.06% / 2.75%，GG 5.13% / 4.65% / 4.17%。

### Owner Earnings
- 新增 `metrics/owner_earnings.py`：
  `OE_t = NI_t + D&A_t − D&A_t×G − ΔWC_t`；
- 取最近 5 年正常化，而不是单年 NI；
- 因子 2、数据包、KPI 统一使用正常化 OE（缺失时回退当期）；
- 例：600887 OE 6,750.47 百万元；00700 OE 202,929.65 百万元。

## 3. PDF 附注结构 + 股东/主营

### PDF 附注
```powershell
turtle pdf --pdf report.pdf --output sections.json --verbose
turtle pdf-footnotes --sections sections.json --output footnotes.json
```
- 把 `pdf_sections.json` 里的 `[TABLE]` + 页码解析为：
  `{section: {pages, tables:[{page, rows}], text_excerpt}}`；
- 600887：P2/P3/P4/P6/P13/MDA/SUB 共 **16 张表**；
- 00700：P2 3 张表，P4/MDA/SUB 只有文本（港股版式不同）；
- 仍是“结构化上下文”，不是科目级语义映射；复杂表头/跨页表需人工复核。

### 股东/主营
- 新增 Tushare `top10_holders`、`fina_mainbz`；
- 数据包新增“股东与主营”：
  - 前十大股东（持股/比例）；
  - 主营/分部收入与利润；
- A 股可用；港股无对应接口，显示“未接入”。

## 4. 验证

- 全量测试：见 `p0-p1-fixes.md`（本轮新增 SBC/稀释、税档、OE、复权、PIT、附注、股东测试）。
- 真实 PDF：
  - 600887：6/6 审计数字；SBC 不误报；附注 7 段结构化；
  - 00700：6/6 审计数字；SBC 25,660；PDF 间接桥 303,052−112,881；稀释 93.10 亿股。
- 00700 报告：GG 从 1.31%（未扣 SBC）降到 **1.14%**（扣 SBC 后），结论“排除”。

## 5. 仍未完成

- 完整 point-in-time 财务快照（当前只有行情/上市状态 as-of）；
- 回购注销后的净股数、SBC 的 treasury-stock method 完整口径；
- 港股股东/分部（Tushare 无接口）；
- 附注表的科目级语义抽取（账龄/关联方/或有负债目前只到表格结构）；
- 期权/可转债稀释、少数股东/控股折价/SOTP。
