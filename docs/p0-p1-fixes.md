# 本地 P0/P1 修复记录

> 日期：2026-10-19
> 基线：`9793fce`
> 范围：上一轮对比分析中列出的本地 P0（正确性）与 P1（把 v2 方法代码化）。

## P0 修复

### 1. 港股汇率与报价

- 新增 `_fx_history()`：港股报价历史（close/high/low）在进入数据包/报告前按 `fx` 折算到报表币种。
- `analyze`、`pack`、`report` 三处统一使用折算后的历史，52 周高低、10 年最低与当前价不再混币。
- 52 周高低/10 年最低在数据包中带币种标注。
- 港股数据包会显示 52 周/10 年价格，底价锚点不再把 HKD 当 CNY。

### 2. 港股报表币种与 DPS

- `TushareProvider.reporting_currency()`：港股权先用 Yahoo `financialCurrency`，失败回退 CNY 并提示；`--currency` 仍可显式覆盖。
- `hk_dividend_events()`：若 `dps_hkd` 在 ≥3 个年度完全相同，标记 `dps_reliable=False`；`average_dps()` 与股息隐含价跳过这些行。
- 分红总额为 `None` 时显示 `—`，不再显示 `0.00`；数据包增加不可靠 DPS 的说明。
- 港股 USD 报表直接给出明确错误，不再静默混币。

### 3. 报告一致性

- 底价分歧的封顶从渲染层移到 `factors/engine.py`：`divergent` 时直接改 verdict/position，因子 4 表与最终结论一致。
- 报告新增"因子4 原始结论 / 最终结论"两行；汇总仓位取最终仓位。
- "仍未验证"改为根据 `qualitative.json` 动态生成，不再硬编码。
- 免责声明区分"有定性输入/无定性输入"，删除"未包含 LLM 定性判断"的错误声明。

### 4. G 与因子 3 口径

- 删除硬编码 `G=1.0`，改为 `metrics/grids.py` 的 G 网格：按 Capex/D&A 中位数选轻/中/重资产档（0.85/1.15/1.50，可在 `[returns]` 配置）。
- 因子 3 改名为"穿透回报率精算（现金桥）"，AA 使用真实现金收入−经营流出−Capex 的现金桥；组件缺失时保留实际销售收现并标 `derived_bridge / complete=False`，再回退 OCF−Capex。
- 增加 λ 收入敏感性/临界收入倍数；λ ≤ 0 或不可用时回退为 AA 等比缩放，避免"收入下降、回报率反而上升"的错误方向。

### 5. 底价与 composite

- `five_baselines()` 剔除 ≤0 的锚点（净流动资产为负不再进入均值）。
- 新增 `valuation.choose_composite()`，CLI/数据包/报告/选股器统一使用配置的 `composite_method`。
- 默认改为 `median`；`composite_method` 只接受 `mean|median` 并校验。
- 底价说明显示"有效锚点 n/5（缺失或非正已剔除）"。

## P1 新增

### 1. 确定性 grids（`metrics/grids.py`）

- 税档：A 股 0/10/20%，港股 28/20%，美股 30/10%。
- 支付率三法：DPS/EPS、现金流（上界）、事件合计；事件合计为默认，法1/法3 偏差 >15% 标记不可靠并封顶；法2 仅在事件合计缺失时兜底。
- G 网格：12 档，按 Capex/D&A 强度选择。
- AA 变体、λ、收入敏感性、临界收入倍数、5 维可信度。

### 2. 5 项价值陷阱 + 仓位矩阵

- 陷阱：现金流恶化、分配意愿、杠杆、护城河收窄、行业结构性衰退、管理层损害价值（6 项，unknown 不计数）。
- 仓位矩阵：安全边际 × 可信度 × 陷阱数；底价分歧/溢价 >150%/支付率法1与法3冲突会封顶。
- 目标买入价保留并进入报告。

### 3. Thesis Card

- 报告新增"投资论点卡"：核心论点、仓位、买入理由、基本面止损表、事件监控清单。
- 止损表状态分为 `已触发/未触发/持续为负/数据不足/数据未接入`；净现金用"相对上年转负"避免把入场已为负误判为刚触发。

### 4. 绝对估值

- 新增 `metrics/valuation_models.py`：WACC、DCF、DDM、PE Band、PEG、PS、交叉验证。
- 新增 `turtle valuation <code>`：DCF/DDM/PE Band/PEG/PS 快照 + 综合公平价/空间；假设在输出中明示。
- 纯函数有单测，不依赖 token。

### 5. 定性 rubric

- `moat.md` 升级为 Greenwald 六步（行业地图/量化验证/双框架/虚假优势/竞对/监控 KPI）。
- 新增 `industry_metrics.md`：30+ 行业核心指标锚点。
- `phase3_qualitative.md` 要求先定位行业、按六步分析，并引用行业锚点。
- 新增 `cleanroom.md`（可选独立复核），明确不能替代 `verify/qualitative/narrative/qa` 机械门。
- `phase4/phase5` 增加 Thesis Card 一致性、不重复止损表的约束。

### 6. 依赖与文档

- `pyproject.toml` 增加 `[pdf]`（pdfplumber）与 `[hk]`（yfinance）extra；`init.ps1` 安装 `.[dev,pdf,hk]`。
- README 更新港股币种、DPS、估值命令、M7 状态。
- 新增 `html` 命令（无第三方依赖的 Markdown→HTML）。
- 新增 `.claude/commands/turtle-analysis.md`、`turtle-valuation.md` 与 skill 入口。

### 7. 现金桥与治理数据

- 新增 `metrics/cashflow.py`：真实现金收入、经营流出、Capex、现金结余；`AA_2y/AA_all/AA_excl` 使用现金桥。
- 现金桥组件缺失时，用 `经营活动现金流入小计 − OCF` 推导总流出；保留实际销售收现，标 `derived_bridge / complete=False`，再缺失回退 `OCF−Capex`。
- A 股新增母公司报表（`report_type=6`）、质押率（`pledge_stat`）、回购（`repurchase`）。
- 因子 1A 增加质押率 >70% 否决；因子 1B 增加母公司现金/合并现金 <50% 的现金上游否决；因子 2 的 O 使用回购金额。
- 数据包新增"治理与资本动作"（母公司现金、质押率、年均回购）。

### 8. 估值分类与敏感性

- `valuation_models.classify_company()`：蓝筹/成长/混合，返回方法权重。
- `dcf_sensitivity()`：5×5 WACC/终值增长矩阵；`implied_growth_pct()`：反推 5 年增长。
- `turtle valuation` 输出公司类型、ROE/支付率/营收 CAGR、权重、敏感性矩阵与反推增长。

### 9. 中报/季报、Thesis Card 与 HTML

- 数据包新增"最新中报/季报（年化参考）"：Q1×4、H1×2、Q3×4/3，不替代年报。
- Thesis Card 增加预期催化剂、预期持有周期；质押率/回购/母公司现金进入止损与监控。
- `turtle html --input <md> [--output <html>]` 生成自带样式的 HTML。

### 10. 定性 D1–D6 与 PDF-first

- `phase3_qualitative.md` 增加 D1–D6 → 本地模块映射；新增 `references/mda.md`（D5）。
- PDF-first 规则：`pdf_sections.json` 命中 ≥4/7 时优先 PDF 原文，D1/D2/D4/D5/D6 至少各 1 条
  `source_type=document` 且 `page` 非空的证据；PDF 缺失才用网页且 confidence ≤ medium。
- 新增 `pdf-numbers --pdf ... --year ...`：从合并报表自动抽取 6 项审计数字（revenue/net_income/ocf/capex/equity/total_assets），输出 `reported_numbers.json`；`tests/test_pdf_extract.py` 含真实 PDF roundtrip。600887/00700 2025 年报已实测。
- 港股现金桥补充为“PDF 间接桥”：净利润→D&A→营运资本→经营产生现金→税→OCF→Capex；Tushare 缺毛利收付明细，但 PDF 的间接法调节表可完整还原。`report/pack --pdf-numbers` 用最新一年 PDF 数字覆盖。
- A 股 `finance_exp` 修正为 `fin_exp`；港股 D&A 修正为 `加:折旧及摊销`；缓存 schema 升到 `turtle-4`。
- 新增 [tushare-fields.md](tushare-fields.md)：逐字段权限/缺失降级/换账号复测脚本。
- 新增 `.github/workflows/ci.yml`（离线 pytest + 核心模块 mypy）与 [cleanroom-ci-plan.md](cleanroom-ci-plan.md)。
- 新增 `tests/test_pdf_sections.py` 覆盖章节定位与上下文提取。

## 验证

```powershell
# 新增/相关测试（全部通过）
.\.venv\Scripts\python.exe -m pytest tests/test_grids.py tests/test_valuation_models.py `
  tests/test_hk_currency.py tests/test_report_consistency.py tests/test_factors.py `
  tests/test_metrics.py tests/test_pack.py tests/test_dividends.py tests/test_normalize.py `
  tests/test_tier2.py tests/test_cli.py tests/test_fast.py -q

# 真实数据 smoke（输出到临时目录）
.\.venv\Scripts\python.exe -m turtlefw.cli pack 600887 --out "$env:TEMP\turtle-smoke\data_pack.md" --rf 1.6516
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887 --out "$env:TEMP\turtle-smoke\analysis_report.md" --rf 1.6516
.\.venv\Scripts\python.exe -m turtlefw.cli valuation 600887 --rf 1.6516
.\.venv\Scripts\python.exe -m turtlefw.cli html --input "$env:TEMP\turtle-smoke\analysis_report.md"
```

- 全量测试：**2026-10-19 基线为 418 项收集/418 通过；2026-10-21 当前基线为 494 项收集/494 通过，0 失败**（`tests/conftest.py` 提供沙箱可写临时目录 fixture）。
- 600887 live smoke：数据包/报告均生成；R 4.52%、GG 5.13%、现金桥 7/7 年、质押率 6.29%、回购 O 588.95 百万元；报告结论"观察"，因子 4 与 Thesis Card 一致。
- 00700.HK live smoke（`yfinance 1.7.0`）：当前价 418.38 CNY、52 周高 610.88、10 年低 152.40；底价 152.40、溢价 152.21%；港股指间接现金桥 6/7 年（2021 缺上年余额），AA 仍为 OCF−Capex。
- **真实年报验证**：600887（259 页，cninfo）7/7 章节、6/6 数字、audit 无冲突；00700（282 页，HKEX）4/7 章节、6/6 数字，audit 仅营业收入差 1.09%（PDF 751,766 vs Tushare 743,689，差额为 Others 分部 8,077）。详见 [pdf-extraction-validation.md](pdf-extraction-validation.md)。
- 港股 PDF 间接现金桥：净利润 229,801 → D&A 66,028 → 营运资本 16,904 → 经营产生现金 347,751 → 税 −44,699 → OCF 303,052 → Capex 112,881（百万元）。
- 三项分析升级（SBC/稀释/复权、税档/OE、附注/股东分部）的实现与限制见 [analysis-upgrades.md](analysis-upgrades.md)。
- yfinance 的 SQLite 缓存默认在用户缓存目录，沙箱下不可写；`TushareProvider._yf_hk()` 现在把它指到 `%TEMP%/turtle-yf-cache`，否则会报 "unable to open database file"。
- `FileCache.put()` 在写缓存失败时不再中断取数（只读 checkout/沙箱 ACL 下仍可分析）。

## 仍未完成

- **PDF 附注全量抽取**：6 项审计数字 + 港股间接现金桥已自动抽取；附注表格/科目级（应收账款账龄、关联方、或有负债）仍是章节上下文，不做结构化抽取。
- **港股现金桥**：港股没有毛利收现/付现明细；已接入 PDF 间接桥（净利润→D&A→营运资本→经营产生现金→税→OCF→Capex），但本质上不是直接法。
- **Tushare 字段**：逐字段状态见 [tushare-fields.md](tushare-fields.md)；`c_paid_goods_srv`、`c_pay_oth_act` 本账号不返回，换账号需复测。
- **美股**：yfinance/SEC 实验路径已接入（非 A 股主路径），但 US PIT、完整股东/分部/母公司语义仍缺；不再声称 `NotImplementedError`。
- **clean-room/语义审计**：已实现独立子进程 runner，见 [cleanroom-ci-plan.md](cleanroom-ci-plan.md)；数值源审计、document hash 与独立 owner earnings/cash bridge 复刻已接入。
- **估值假设**：DCF/DDM 的 ERP/β/终值增长仍是规则默认值，不是公司特定假设；输出中已明示。
- **CI/黄金集**：`.github/workflows/ci.yml` 已加（离线 pytest + 核心 mypy），但未推送/启用；live smoke 与 `golden_set.csv` 评分未接。
