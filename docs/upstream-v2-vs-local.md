# 原仓库 v2.1-beta vs 本地 turtle-framework

> 对比对象
> - 上游：`terancejiang/Turtle_investment_framework`，HEAD `c61419c`（2026-07-04，**v2.1-beta**）。这是上一份报告里 fork 的**父仓库**，比 fork 多 26 个提交。
> - 本地：`C:\PyProject\turtle-framework`，HEAD `9793fce`（2026-10-19，27 个提交）。
>
> 方法：完整 worktree 对照代码/提示词/测试；用本地 venv 直接运行 v2 的 `quality_control`、`report_consistency` 做行为验证；测试套件受 Windows 沙箱 ACL 影响，见 §8。
>
> 一句话结论：**v2 把 v1 的"LLM 全算"改造成"LLM 选表 + 多重审计"，是方法论和覆盖面的巨大升级；但它没有变成本地这种"确定性内核"。** v2 赢在"分析什么、怎么分析"，本地赢在"数字从哪来、能不能复现"。两者仍是两种产品。
>
> **更新（2026-10-19）**：本文 §12.1 列出的本地 P0/P1 已修复，逐项记录见 [p0-p1-fixes.md](p0-p1-fixes.md)。本文保留修复前的诊断，便于对照。
>
> 第二轮已补：现金桥因子 3、母公司现金/质押/回购、估值分类与 5×5 敏感性/反推增长、中报年化参考、HTML 报告、`.claude` 入口、D1–D6/MDA rubric、PDF 章节定位 + 6 项审计数字自动抽取、港股间接现金桥。第二轮时仍缺：附注表格全量抽取、美股、股东/主营/分部、clean-room runner、CI 的 live smoke、黄金集。
>
> **第三轮更新（2026-10-19）**：SBC/稀释/复权/PIT、税档情景/OE 正常化、PDF 附注表格结构、A 股股东/主营已完成；最新差距矩阵见 [v2-gap-after-upgrades.md](v2-gap-after-upgrades.md)。

---

## 1. v2 相对 v1（fork）到底改了什么

| # | 增量 | 证据 | 性质 |
|:--|:--|:--|:--|
| 1 | 模块化：`shared/qualitative` + `strategies/turtle` + `strategies/valuation` | `README.md:249-289`；`CHANGELOG_V2.md:112-125` | 架构 |
| 2 | PDF-first 定性：年报 PDF 为主源，Tushare 只补历史序列 | `shared/qualitative/coordinator.md:5-6, 105-181` | 方法 |
| 3 | §17.10–17.13 预计算网格：M 三重校验、税后 R/GG 网格、G 网格、λ 敏感性 | `scripts/tushare_modules/derived_metrics.py:1222-1225, 1464-1560, 1595+` | 数字 |
| 4 | `computed_metrics.md`（CM§1–5）：亿元换算/同比/多年统计/分红支付率/PE 链 | `scripts/quality_control.py:1-16, 179-282` | 数字 |
| 5 | 多层审计门：clean-room 独立重算 + 跨段一致性脚本 + 数字审计 Agent + 硬门槛 | `shared/qualitative/coordinator.md:26-73, 261-314`；`scripts/report_consistency.py:194-211` | 质量 |
| 6 | 独立估值引擎：DCF/DDM/PE Band/PEG/PS + WACC + 反推 + 交叉验证 | `scripts/valuation_engine.py:1-8, 153-1068` | 能力 |
| 7 | TTL 缓存、行序防御、`--refresh-market` 增量刷新 | `CHANGELOG_V2.md:11-30`；`scripts/tushare_modules/financials.py:47-50` | 工程 |
| 8 | Thesis Card（论点/结构化止损/事件监控）+ HTML 仪表盘 | `strategies/turtle/phase3_valuation.md:347-419`；`scripts/report_to_html.py`；`shared/qualitative/templates/dashboard.html` | 报告 |
| 9 | 测试 721 → 875 个函数（参数化后约 923 项） | 本次统计；`CHANGELOG_V2.md:54` | 质量 |

v2 的核心设计思想可以概括为：**"高错率算术搬到 Python，LLM 只做选择与叙述，再由另一个 LLM/脚本审计"**。这比 v1 的"LLM 从数据包重算一切"前进了一大步，但仍不是"代码算完、LLM 只能引用"。

---

## 2. 架构对照

### 2.1 v2：三条入口，LLM 是分析师

```
/business-analysis
  Tushare 1A ∥ PDF 1B
        │
        ├─ quality_control.py → computed_metrics.md
        ├─ 六维定性（单 Agent，PDF-first）
        ├─ PDF 附注提取 → data_pack_report.md
        └─ clean-room 重算（并行、禁读草稿）
        │
        ▼
  report_consistency.py → numeric_audit Agent → 修复环（≤1）
        │
        ▼
  qualitative_report.md（+ 可选 HTML）

/turtle-analysis（依赖上面的 qualitative_report.md + data_pack_market.md）
  Step A 刷新行情 → Agent B（Step 0 + 查 §17 网格，11 步）
        → Agent C（估值 + 组装报告）→ {company}_{code}_分析报告.md

/valuation（依赖 qualitative_report.md）
  valuation_engine.py（Python 算）→ LLM 定性调整 → 估值报告
```

### 2.2 本地：一个确定性内核

```
Tushare/yfinance → provider → normalize → FileCache/Parquet
        │
        ▼
metrics（dividends/statements/returns/valuation）
        │
        ▼
factors/engine.py → verdict
        │
        ├─ report/pack.py → data_pack.md
        ├─ report/analysis.py → analysis_report.md（Jinja2）
        │
        ▼
LLM：qualitative.json（证据）→ narrative.md（白名单数字）
        │
        ▼
verify → qualitative --check → narrative → qa
```

### 2.3 关键差异

| 问题 | v2 | 本地 |
|:--|:--|:--|
| 谁算 R/GG/II/底价/评级 | LLM 从 §17 网格选行/选 G/选 M/选 AA，再写报告 | `factors/engine.py` 用 Decimal 算死 |
| LLM 能否改数字 | 能（网格之外仍可手算；报告由 LLM 写） | 不能（报告由 Jinja2 渲染） |
| 审计 | 另一个 LLM + 一致性脚本 + 字数门槛 | 确定性 verify/narrative/qa |
| 失败可复现 | 弱（无快照，报告含 LLM 叙述） | 强（snapshot_id + 模板） |
| 覆盖面 | 广（A/HK/US、质押/回购/母公司/股东/分部） | 窄（A/HK） |
| 方法深度 | 深（11 步现金桥、G 网格、λ、税档、5 陷阱） | 浅（简化四因子） |

---

## 3. 数据层：v2 补了工程，但没补本地最在意的"类型"

### 3.1 v2 的数据改进

- **TTL 缓存**：财报类 7 天、行情 24 小时；`ScreenerCache` 复用；缓存命中不触发限速（`CHANGELOG_V2.md:11-17`）。
- **行序防御**：券商 VIP 中继按"最旧在前"返回，v2 在 A/HK/US 四处强制 newest-first（`financials.py:47-50, 93-95, 156-158, 206-208`）。
- **增量刷新**：`--refresh-market` 只刷新 §1/§2/§11/§14，数据包 >7 天自动回退全量（`turtle-analysis.md:17-22`）。
- **§17.10–13 网格**：把 M 三法、税后 R/GG、G 系数、λ 敏感性预计算成表，Agent "查表选行"（`phase3_quantitative.md:24, 120-126, 350-389`）。
- **computed_metrics**：把亿元换算、同比、多年统计、分红支付率、PE 链做成 CM§1–5，定性报告只准引用（`quality_control.py`；本次已用 fixture 实测）。

### 3.2 v2 仍未解决的数据问题

| 问题 | v2 现状 | 本地现状 | 评价 |
|:--|:--|:--|:--|
| 港股报表币种 | 仍按代码后缀判定：`.HK` → HKD，数据包头部写"报表币种: HKD"（`infrastructure.py:15-22`；`assembly.py:108-121`） | 默认 CNY，可用 `--currency HKD`；但按上市地推断，不是读报表 | 两家都没做到"币种来自报表"；v2 更严重 |
| 港股跨币种 | `shared_tables.md:80-95` 要求用报表币种和汇率；但数据包没有汇率字段（`assembly.py` 无 FX），`_detect_currency` 又把港股当 HKD | 有 `fx=0.92`，但只折算价格/市值/DPS，未折算 `closes`（52 周/10 年低点） | v2 规则无法执行；本地部分执行、仍有混币 |
| 分红聚合 | `get_dividends()` 仍 `drop_duplicates(end_date)`，同财年多次分红只留一条（`financials.py:1040-1041`） | 按 `(period_end, dps)` 去重后求和（`normalize.py:142-191`） | 本地修复了 A 股；v2 仅靠 §17.10 三法交叉校验告警 |
| 底价负值 | 5 法算术平均，负值照进（`derived_metrics.py:624-646`） | 同样照进，但分歧时改用中位数并封顶仓位 | 两家都没剔除 |
| 缺失值 | 仍大量 `or 0`，只事后 warning | `Metric` 三态 + Tier2 fail-closed | 本地明显更好 |
| 美股 total_mv | 代码/测试按 raw USD 处理，显示再 ÷1e6（`financials.py:165`；`test_tushare_client.py:2861-2887`） | 不支持美股 | v2 口径以测试为准，但文档曾写"百万美元"，需实盘确认 |
| 缓存键 | 基础缓存仍是 `{api}_{ts_code}.json`（`tushare_collector.py:186-198`） | endpoint+全部参数+schema 的 sha256（`cache.py:22-30`） | 本地更严格 |
| CM 的市场覆盖 | `quality_control.py` 只认 A 股行名；HK 的"营业额/股东应占溢利"、US 的对应行名不在匹配表里，CM§1–5 基本为空（`quality_control.py:183-200`；`constants.py:17-33`） | 无 CM；但 data pack/指标按 A/HK 统一建模 | v2 的"确定性预算"只覆盖 A 股 |

### 3.3 数据覆盖

| 能力 | v2 | 本地 |
|:--|:--|:--|
| Tushare 接口 | 约 28 个（A/HK/US + VIP） | 19 个（A/HK + 4 VIP） |
| 美股 | ✅ | ❌ `NotImplementedError` |
| 母公司报表 §3P/§4P | ✅ | ❌ |
| 质押 §16 / 回购 §15 | ✅ | ❌（配置有 `max_pledge_pct`，未实现） |
| 股东 / 主营 / 分部 | ✅ | ❌ |
| 数据包段数 | §1–§17 + §17.10–13 网格 | 7 段 |
| 全市场批量 | Tier1 批量行情，Tier2 逐只串行 | Fast 15 次 VIP 批量 + Tier2 线程池 |

v2 的数据覆盖仍是本地短期难以追上的部分；本地的优势是"取数—存储—计算"的边界清晰、可复现。

---

## 4. 定量与四因子：v2 更深，本地更硬

### 4.1 公式对照

| 指标 | v2 | 本地 |
|:--|:--|:--|
| Owner Earnings | `C + D − D×G`，G 在 §17.12 的 12 档网格中选（0.7–1.8） | 同公式，但 **G 硬编码 1.0** → OE = 归母净利润 |
| 粗算 R | `[C×M×(1−Q)+O]/市值`，Q 按 A/HK/US 与持股渠道取档 | `OE×M×(1−税)/市值`；A 股 Q=0，港股 Q=20% |
| 精算 GG | `[AA×M×(1−Q)+O]/市值`，AA 有 AA_2y/AA_all/AA_excl 三变体 | 近 2 年 FCF 均值 × M × (1−税)/市值 |
| 收入敏感性 | §17.13 预计算 λ×(k−1)×S，给出临界收入倍数 k* | 无 λ，直接按 0.9/0.8/0.7 等比缩放 GG |
| 价值陷阱 | 5 项：现金流、护城河、行业衰退、分配意愿、管理层 | 3 项：现金流、分配意愿、杠杆（+底价约束） |
| 仓位 | 安全边际 × 可信度 × 陷阱矩阵（`phase3_valuation.md:81-93`） | `margin` 阈值 + 底价约束（`engine.py:321-345`） |
| 否决门 | **无否决门**（`phase3_quantitative.md:7`）；只在估值阶段排除 | 1A/1B/2/3 四道硬否决（`engine.py:464-479`） |
| 目标买入价 | `当前股价 × GG/II`，§17.11 预计算列 | `price × gg/ii`（`engine.py:281-283`） |
| 税档 | A 股 0/10/20%，港股 28/20%，美股 30/10% | A 股 0%，港股 20% |
| 可信度 | 5 维评级（收入波动、利润调整、HH、模式变化、λ） | 无独立可信度评级 |
| 底价 | 5 法算术平均，负值不剔除 | 5 法；中位数优先，分歧 >20% 封顶仓位 |

### 4.2 评价

- **方法深度**：v2 的 §17.10–13、11 步现金桥、λ、税档、G 网格、5 陷阱、可信度、Thesis Card，是本地简化版无法比的。v2 的"精算"确实是在还原真实现金收入与经营流出，本地只是"2 年 FCF 均值"。
- **但 v2 的 GG 也不是完整 11 步**：§17.5 的 AA 是 base case，明确不含 V1/V5/V_deduct/X1/X2（`derived_metrics.py:1029, 1159`），而 §17.11/§17.13 直接拿它当精算基准；G/M/AA/税档仍由 LLM 选。所谓"精算网格"是"预计算了若干近似情景"，不是"唯一正确结果"。
- **计算确定性**：v2 仍是"网格是 Python 算的，但选哪一行、选哪个 G/M/AA 由 LLM 决定，报告数字由 LLM 写"。v2 的 `quality_control` 和 §17 网格降低了算术错误，但没有消除"选错档/抄错数/改口径"的错误类别。
- **硬约束**：v2 取消了 v1 的否决门，改由估值矩阵和陷阱项间接排除；本地保留 1A/1B/2/3 硬否决。对"排雷"而言，本地更保守；对"深度研究"而言，v2 更灵活。
- **红牌检查的位置**：v1 的 1A/1B 在 v2 中不再作为独立阶段；审计意见/审计师更换/造假历史并入 D4（`qualitative_assessment.md:212-231`），护城河/周期并入 D2/D3，且没有单条红牌的硬否决。本地仍把审计意见、频繁更换审计师、造假前科等作为 1A 检查并可直接否决——这是本地相对 v2 在"排雷"上的结构性优势。
- **可复现**：同一数据包重跑，v2 的 LLM 输出可能变化；本地确定性部分逐字节一致。

**结论**：v2 的四因子是"更完整的模型"，本地是"更硬的执行器"。本地若要保持"确定性内核"，应把 v2 的 G 网格、M 三法、税档、λ、可信度改写成代码，而不是让 LLM 选表。

---

## 5. 定性：v2 深，本地"证据可验"

| 项 | v2 | 本地 |
|:--|:--|:--|
| 数据源 | 年报 PDF 为主（分页读/MD&A/治理），Tushare 补历史 | data_pack + 可选 PDF 章节（M6 未完成） |
| 维度 | D1 商业模式、D2 护城河（Greenwald 6 步）、D3 外部、D4 管理层、D5 MD&A、D6 控股 | 6 模块：moat/management/policy/fraud/understandability/controller |
| 结构化输出 | output_schema v1.2，38+ 参数（护城河评级、CR4、进入壁垒、供应商/需求/规模评级、监控 KPI 等），写在 Markdown 参数表里 | `qualitative.json`：modules/judgment/confidence/evidence{url,quote}/discrepancies |
| 证据 | `[src: CM§N/DP§N]` 溯源；clean-room 独立重算；numeric_audit 允许 critical 阻断 | 每条非 unknown 必须有 http(s) URL + 原文引文；`verify` 机械匹配；未通过自动降级 |
| 深度 | 行业指标锚点 36 行业；Greenwald 框架；写作风格规则；D2 竞对表 | 7 个 rubric（每个 15–25 行），深度明显不足 |
| 交付门 | 维度字数（600/800/300）、必备章节、参数完整性（**实际未校验**）、AUDIT_RESULT | 结构校验 + 证据 URL/引文 + 黄金集（空） |

**关键差异**：

- v2 的定性是**研究级**的：PDF-first + Greenwald + 行业锚点 + 38 参数 + 竞对表，能产出接近人类研究员的报告。
- 本地的定性是**可验证**的：URL 和引文必须真实存在，`verify` 会拉页面做机械匹配，未通过自动降级。但模块少、rubric 浅、没有 PDF 深度。
- v2 的审计是"另一个 LLM 审草稿"，能理解语义和口径差异，但可能放水；本地的 verify 是"代码查 URL/引文"，不会放水，但只能查"引文是否存在"，不能判断"引文是否支持结论"（本地用 `verifier.md` 让 LLM 做这一步，但没有强制门）。

结论：v2 的定性上限远高于本地；本地的证据下限更硬。两者可以组合：v2 的 D1–D6/Greenwald 框架 + 本地的 URL/引文/降级门。需要注意的是，v2 的产物是 Markdown 参数表，没有逐模块 `confidence`、证据 URL、`discrepancies` 这些机器可读字段；本地的 `qualitative.json` 在可机读、可校验、可统计上更完整。

---

## 6. 估值：v2 有独立引擎，本地有可测的底价

| 项 | v2 | 本地 |
|:--|:--|:--|
| 方法 | DCF（稳定/情景）、DDM、PE Band、PEG、PS、反推估值、交叉验证 | 5 法底价（净流动资产/BVPS/10 年低点/股息隐含/悲观 FCF）+ EV/EBITDA、现金调整 PE、FCF 收益率等 |
| 输入 | Tushare 数据包；WACC 用市场参数（A 6%/2.5%/25%，HK 5.5%/4%/16.5%，US 5%/4%/21%） | 报表 + 行情 + Rf；无 WACC |
| 谁算 | Python `valuation_engine.py`（1,516 行）算；LLM 做定性调整/情景选择（仍可能重算加权） | Python 完整算 |
| 测试 | **无 valuation_engine 测试** | 底价/估值函数有单测 |
| 集成 | `/valuation` 独立；龟龟因子 4 仍用 5 法底价，不调用 DCF | 因子 4 直接用底价/估值指标 |
| 输出 | `valuation_computed.md` + LLM 估值报告 | 报告内估值表/底价表 |

v2 的估值引擎是真实的 Python 实现（不是提示词），这是 v2 相对 v1 最大的能力增量之一；但它**没有测试**，且假设较粗（beta 按市值分档且档位阈值有 10 倍错误、ERP 固定、终值增长上限），LLM 还会对结果做"定性调整"。本地没有 DCF/DDM/PEG/PS，只有底价与倍数指标，但每个函数都有 Decimal 单测。

结论：v2 的估值**广度**胜出，本地的估值**可测性**胜出。若本地要补 DCF/DDM，建议直接移植 v2 的 `valuation_engine.py` 思路并补测试，而不是让 LLM 算。

---

## 7. 报告与质量门：v2 的"门"主要管定性报告，不管龟龟报告

### 7.1 v2 的质量门

| 门 | 实现 | 强制性 |
|:--|:--|:--|
| CM§1–5 预计算 | `quality_control.py` 解析 data pack，输出 computed_metrics.md | Python 生成；提示词要求只引用 |
| 跨段一致性 | `report_consistency.py` 14 类指标、±30 字窗口、年份聚类；冲突 advisory | 代码 exit 0/1，冲突不直接阻断 |
| 硬门槛 | 维度字数 600/800/300、必备章节、参数完整性 | 代码只查章节存在与 CJK 字数（`report_consistency.py:176-211`）；**参数完整性/4 评级未实现** |
| 数字审计 | `numeric_audit.md`：clean-room 对账、critical/major/minor、AUDIT_RESULT | **LLM 自报**；critical 未修复禁止交付 |
| 修复环 | 按"原文→修正"Edit，最多 1 次 | coordinator 执行 |
| 交付约定 | DELIVER ONLY，内部工件不交付 | 提示词约束 |

### 7.2 关键缺口

1. **龟龟报告不过审计门**：`report_consistency` / `numeric_audit` / `cleanroom` 只出现在 `shared/qualitative`，`strategies/turtle` 中没有引用。也就是说，v2 的四因子报告（R/GG/II/底价/评级）仍由 Agent B/C 写，没有跨段一致性或数字审计。这是 v2 最大的质量缺口——它把审计资源全给了定性报告。
2. **硬门槛名不副实**：`output_schema.md:114-126` 声称 `--gates` 校验"4 项评级必填、参数表无留空"，代码只校验章节存在与字数（`report_consistency.py:194-211`）。
3. **AUDIT_RESULT 是 LLM 自报**：没有代码复核审计结论；如果审计 Agent 放水，门就形同虚设。
4. **`[src:]` 无覆盖率检查**：无法保证每个数字都有溯源标注。
5. **单位规则矛盾**：`qualitative_assessment.md:11` 说正文百万元，`:35` 和 `writing_style_rules.md:25` 说正文亿元；CM 的亿元表与提示词的单位要求并存，容易混。
6. **US 门槛矛盾**：`shared_tables.md:75` 写美股 `max(5%, Rf+3%)`，`derived_metrics.py:287` 实现 `max(4%, Rf+2%)`。
7. **PDF-first 与 PDF 预处理提示词矛盾**：`phase2_PDF解析.md:207` 说只处理 `pdf_sections.json`、不打开 PDF，但 coordinator 让 Agent 直接 Read PDF。
8. **CM 只适配 A 股行名**：`quality_control.py:183-200` 找"营业收入/归母净利润/归母所有者权益"，而 HK/US 数据包用"营业额/股东应占溢利/股东权益"（`constants.py:17-33`）——CM§1–5 在港股/美股基本为空，v2 引以为傲的"确定性预算"实际上只覆盖 A 股。
9. **CM 解析细节**：`_num()` 用正则取第一个数字，括号负数 `(123)` 会被读成正的 123（`quality_control.py:76-90`）；CM§5 只认"总市值 (万元)/当前价格"，HK/US 不适用。
10. **HTML 依赖与硬编码**：`report_to_html.py:20` 导入 `markdown`，但 `requirements.txt` 没有该依赖；模板硬编码 `¥`、个人站导航和 `terancejiang.com`（`dashboard.html:8, 19-20, 42`），市值只解析"万元"（`report_to_html.py:281-288`），HK/US 会错；且零测试。
11. **估值引擎的 beta 档位错 10 倍**：`BETA_BY_CAP` 第一档阈值 `1_000_000` 百万 = 1 万亿，注释写">1000 亿"（`valuation_engine.py:47-52`），实际 1000 亿应约为 100,000 百万。

### 7.3 本地报告

- 确定性 Jinja2，170 行左右；数字与结论一致（除已知的 verdict/仓位不同步）。
- `verify`/`narrative`/`qa` 覆盖全流程；`narrative` 是数字白名单（所有数字必须来自 CLI 产物）。
- 但没有 v2 的"跨段冲突/语义审计/字数门槛/clean-room"；报告短、定性浅。
- 本地报告的实际问题（600887 样本）：结论"观察"而因子 4 仍写"标准仓位/买入"；"仍未验证"是静态清单；港股分红 `0.00`。这些是本地要修的。

### 7.4 报告形态

| 项 | v2 | 本地 |
|:--|:--|:--|
| Markdown | 龟龟 9 章 + Thesis Card（论点/止损/事件监控） | 9 节，170 行 |
| HTML | 定性报告可选（KPI 卡/verdict 横幅/暗色；无图表） | 无 |
| 示例 | v2 仓库无样例（`output/` 只有 `.gitkeep`） | `output/600887.SH` / `00700.HK` 有 2 份 |
| 发布 | 绑定个人站 terancejiang.com；无 report-to-html 命令 | 无 |

v2 的龟龟报告模板比本地丰富得多（Thesis Card 尤其有价值），但 v2 没有提交任何 v2 样例，质量只能从模板推断；本地的样例暴露了自己的不一致问题。

---

## 8. 测试与工程

| 项 | v2 | 本地 |
|:--|:--|:--|
| Python 源码 | 23 文件 / 11,321 行 | 38 / 6,674 行 |
| 提示词 | 41 文件 / 8,062 行（+ legacy 12/4,579） | 14 / 398 |
| 测试 | 24 文件 / 10,260 行 / **875 个函数**；排除 PDF 收集 808 项，含 PDF/参数化约 923 项 | 21 / 1,559 行 / 137 个函数，收集 153 项 |
| 提示词文本断言 | 约 165 个（19%）；其中 4 个文件仍断言 `prompts/`（v1 存档），不覆盖线上 `shared/`/`strategies/` | 0 |
| 数值/质量测试 | quality_control 24、report_consistency 16、grids 33、tushare 207、pdf 81、screener 96 | metrics/factors/dividends/normalize 等精确 Decimal 断言 |
| 空白 | 无 valuation_engine 测试、无 report_to_html 测试、无端到端/金标准、无 CI | 无 provider fixture 测试、无 golden 数值回归、无 CI |
| 打包/CLI | 无 `pyproject`/`setup.py`/console script | `pyproject.toml` + `turtle` 14 子命令 |
| 平台 | bash/`init.sh`，Windows 无等价 | PowerShell/`init.ps1`，Windows 优先 |
| 文档 | README 23KB，但多处过期（792 tests、coordinator_v2、cigarbutt、download-report） | README 4KB |
| 集成 | 4 个 slash command + skill；skill 的 tushare 符号链接指向被 ignore 的路径 | 无 `.claude` 入口 |

**测试运行说明（本次环境）**：

- v2 的 `tests/conftest.py:66-71` 有 autouse fixture 使用 `tmp_path`，而本机沙箱 ACL 拒绝 `tmp_path`，因此 v2 测试全部 setup error；这不是测试逻辑失败。
- 我改用直接调用 `quality_control.build_report()` 与 `report_consistency.extract/find_conflicts/check_gates()`，二者在 fixture 上均正常工作（CM§1–5 输出、冲突检测、字数门槛均符合预期）。
- 本地 153 项：133 通过、20 个 setup error（同一 ACL 原因），无断言失败。
- 双方的真实通过率需要在正常 Windows/Linux 环境重跑才能确认。

**结论**：v2 的测试数量约为本地 6 倍，新增的 quality/grid 测试确实覆盖了新增的确定性脚本；但仍有 165 个提示词文本断言、且 4 个文件测的是 v1 存档；最关键的 `valuation_engine.py`（1,516 行）和 `report_to_html.py` 没有测试。本地测试少，但更贴近"数字是否正确"；缺的是 provider 解析层与端到端。

---

## 9. 评分卡

| 维度 | v2.1-beta | 本地 | 胜者 |
|:--|:--|:--|:--|
| 数据覆盖 | 28 接口，A/HK/US，母公司/质押/回购/股东/分部 | 19 接口，A/HK | v2 |
| 数据工程（缓存/行序/刷新） | TTL + newest-first + refresh-market | 内容寻址缓存 + Parquet + 快照 | 平（各有所长） |
| 币种/单位 | 仍按后缀判 HKD；跨币种规则无 FX 支撑 | Money/Decimal；港股折算有 bug | 本地略优 |
| 缺失值 | `or 0` + warning | 三态 + fail-closed | 本地 |
| 四因子方法深度 | 11 步、G/M/税档/λ/可信度 | 简化版 | v2 |
| 计算确定性 | LLM 选表/写数 | 代码算死 | 本地 |
| 定性深度 | PDF-first D1–D6、Greenwald、38 参数 | 6 模块、浅 rubric | v2 |
| 证据可验证性 | `[src:]` + LLM 审计 + clean-room | URL/引文机械校验 + 自动降级 | 本地（机械）/ v2（语义） |
| 估值广度 | DCF/DDM/PE Band/PEG/PS/WACC/反推 | 5 法底价 + 倍数 | v2 |
| 报告丰富度 | 9 章 + Thesis Card + 可选 HTML | 170 行确定性 MD | v2 |
| 报告可审计 | 定性有门，龟龟报告无门 | 全流程确定性 + 门 | 本地 |
| 可复现 | 无快照，LLM 叙述 | snapshot_id + 模板 | 本地 |
| 打包/CLI | 无 | pyproject + 14 命令 | 本地 |
| 测试规模 | 875 函数/约 923 项 | 137/153 | v2 |
| 测试针对性 | 大量 prompt 断言；valuation/html 无测试 | 数值单测；缺 provider/golden | 本地略优 |
| Claude Code 集成 | 4 命令 + skill | 无 | v2 |
| 文档/示例 | README 丰富但过期；无 v2 样例 | README 短；有 2 份样例 | 平 |

---

## 10. v2 仍未解决的问题（按影响排序）

1. **龟龟报告不在审计门内**：`report_consistency`/`numeric_audit`/`cleanroom` 只服务 `shared/qualitative`，`strategies/turtle` 无引用（`strategies/turtle/coordinator.md`、`phase3_valuation.md` 全文搜索无命中）。四因子报告的数字仍可能被 LLM 抄错。
2. **港股报表币种仍错**：`.HK` → HKD（`infrastructure.py:15-22`），数据包头部硬写 HKD（`assembly.py:118-121`），而 00728/00285/02333/06862 等实际以 RMB 报表；`shared_tables.md:80-95` 的"报表币种/汇率"规则没有数据支撑（data pack 无汇率字段）。这会让市值、EV、股息率、底价与利润混币。
3. **分红聚合未修**：`get_dividends()` 仍 `drop_duplicates(end_date)`（`financials.py:1040-1041`），同财年中期+末期只留一条；§17.10 的三法交叉校验只能发现/绕开，不能修正 §6 的原表。
4. **底价负值未处理**：5 法算术平均，负的净流动资产照进（`derived_metrics.py:624-646`），可能把"买入就是胜利"判错。
5. **质量门名不副实**：`output_schema.md:114-126` 声称检查 4 评级/参数完整性，`report_consistency.py:194-211` 只查章节和字数；`AUDIT_RESULT` 是 LLM 自报；`[src:]` 无覆盖率校验。
6. **测试盲区**：`valuation_engine.py`（1,516 行）与 `report_to_html.py` 零测试；4 个 prompt 测试仍指向 v1 `prompts/`；无端到端/金标准；无 CI。
7. **文档/配置矛盾**：正文单位百万元 vs 亿元；美股 II `max(5,Rf+3)` vs 代码 `max(4,Rf+2)`；README 的 792 tests、`coordinator_v2.md`、`cigarbutt/`、`download-report` 均过期；`/business-analysis` 命令与 coordinator 双份维护、编号已漂移。
8. **UX/依赖**：`/turtle-analysis` 必须先跑 `/business-analysis`；`/valuation` 又依赖 BA 产物；3 个命令、无 CLI；bash-only；`.claude/skills/tushare` 是断链；`download-annual-report` 默认 `--save-dir "."`。
9. **无 v2 样例**：`output/` 只有 `.gitkeep`；Thesis Card/HTML 的实际质量没有被仓库内产物验证。
10. **没有本地这种类型/快照**：无 Money/Currency、无三态、无 Parquet 长表、无 snapshot_id；可复现性弱。
11. **实现级错误**：`quality_control.py` 只认 A 股行名，HK/US 的 CM§1–5 基本为空（`quality_control.py:183-200` vs `constants.py:17-33`）；`_num()` 会把括号负数读正（`quality_control.py:76-90`）；`report_to_html.py` 导入 `markdown` 但 `requirements.txt` 没声明；模板硬编码 `¥`/个人站（`dashboard.html:8, 19-20, 42`）且只解析"万元"市值（`report_to_html.py:281-288`）；`valuation_engine.py` 的 beta 市值档阈值差 10 倍（`:47-52`）。

---

## 11. 本地相对 v2 的真实差距（不是缺陷，是能力）

1. **覆盖**：美股、母公司报表、质押、回购、股东、分部、主营构成。
2. **定量方法**：G 系数网格、11 步现金桥、M 三法、税档、λ 敏感性、5 维可信度、5 陷阱、目标买入价。
3. **定性深度**：PDF-first、D1–D6、Greenwald 6 步、36 行业指标锚点、38 参数、竞对表。
4. **估值方法**：DCF/DDM/PE Band/PEG/PS、WACC、反推估值、交叉验证。
5. **报告**：9 章 + Thesis Card（结构化止损/事件监控）、可选 HTML 仪表盘。

这五项不是"修 bug"能补的，需要按模块逐步移植；其中第 2、4 项最适合直接写成确定性代码，而不是继续让 LLM 做。

---

## 12. 建议

### 12.1 本地：把 v2 的"方法"拿过来，把 v2 的"架构"留在外面

**P0（正确性，先于能力）**

1. 修港股：`closes` 换币、分红 `—`、DPS 去重；把 `--currency` 从"按上市地猜"改成"读报表/公告"。
2. 修报告一致性：verdict 与 factor 4 的仓位/结论同步；"仍未验证"动态生成；删"未包含 LLM 定性判断"的错误声明。
3. 明确 G/因子 3 口径：G=1 时 OE=净利润；要么实现行业 G 网格，要么改名为"简化 FCF 回报率"。
4. 底价负值剔除/截断；`composite_method` 与实际"中位数优先"对齐。

**P1（把 v2 的方法代码化）**

5. 把 §17.10–13 的思想移植成 `metrics/grids.py`：M 三法、税档、G 网格、λ、AA 变体，全部 Decimal + 单测；报告只引用，不允许手算。
6. 增加 5 陷阱、可信度评级、目标买入价、仓位矩阵；Thesis Card 可作为报告模板的一部分。
7. 定性层：引入 Greenwald D2 框架与行业指标锚点；保留本地 URL/引文校验；可选加 clean-room + 语义审计（LLM），但不得替代机械门。
8. 估值：移植 v2 的 DCF/DDM/PE Band/PEG/PS 思路，写成可测函数；不要直接调用 LLM 算。

**P2（覆盖与体验）**

9. 美股/质押/回购/母公司/股东/分部；优先级按策略需要。
10. 可选 HTML 仪表盘；CLI 增加 `screen --html`；报告 KPI 卡。
11. provider mock fixtures + golden 数值回归 + CI；清理 ruff/mypy；补 LICENSE/移植代码归属。

### 12.2 v2：把本地的"确定性"拿过来

1. 用 `Money(amount, currency)` 替代"代码后缀推币种"；数据包增加报表币种 + 汇率；港股 RMB 报表必须按 RMB 计算。
2. 分红聚合改成"按事件求和"；底价负值剔除；缺失值三态化。
3. 把 Agent B/C 的核心数字改为 Python 产出、LLM 只写解释；至少让龟龟报告也过 `report_consistency` + `numeric_audit`。
4. 兑现 `--gates` 的承诺（4 评级/参数完整性/[src:] 覆盖率）；`AUDIT_RESULT` 用代码复核。
5. 给 `valuation_engine` 和 `report_to_html` 补测试；修 4 个仍测 v1 prompts 的测试；加 CI。
6. 修实现级错误：CM 增加 HK/US 行名映射；`_num()` 处理括号负数；补 `markdown` 依赖；HTML 去掉个人站/`¥` 硬编码、支持 HK/US 市值；修 beta 档位阈值（1,000,000→100,000 百万）。
7. 修文档/单位/门槛矛盾；清理 README 过期内容；把 `/turtle-analysis` 的前置依赖改成可选或自动串行。
8. 打包/CLI/Windows 支持；可以借鉴本地的 `pyproject` + `turtle` 入口。

---

## 13. 选型判断

- **要"深度研究 + 可读报告 + 完整方法论"**：v2.1-beta。它已经是一个相当完整的"AI 研究员工作台"：PDF-first 定性、11 步现金桥、§17 网格、DCF/DDM、Thesis Card、定性报告的可选 HTML。
- **要"数字可信 + 可复现 + 可审计 + 可批量"**：本地。它把 R/GG/II/底价/评级算死，LLM 只能写证据化定性和白名单叙述；代价是覆盖窄、方法浅、报告短。
- **最佳组合**：本地做"确定性数字层 + 门禁"，v2 做"方法论与定性深度"；把 v2 的 G/M/税档/λ/可信度/5 陷阱/Greenwald 移植成本地的代码与 rubric，而不是把数字交回给 LLM。
- 如果只能选一个：**做投资决策/批量筛选，选本地；做单只股票深度研究，选 v2**。v2 的质量门已经明显缩小了差距，但它仍然不是"数字不会被 LLM 改写"的系统。

---

## 14. 复现与说明

```powershell
# v2（原仓库）
git clone --depth 1 https://github.com/terancejiang/Turtle_investment_framework.git
# 或从已有 clone 建 worktree
git -C <clone> worktree add --detach <v2-dir> origin/main

# 直接验证 v2 的两个确定性脚本
$env:PYTHONPATH="<v2-dir>\scripts"
python -c "import quality_control as qc, pathlib; t=pathlib.Path('tests/fixtures/sample_data_pack_market.md').read_text(encoding='utf-8'); print(qc.build_report(qc.parse_sections(t), [10,15,20,25,30], [1.0,0.9,0.8,0.7]))"
python -c "import report_consistency as rc, pathlib; t=pathlib.Path('tests/fixtures/sample_report_with_conflicts.md').read_text(encoding='utf-8'); print(rc.find_conflicts(rc.extract(t), 0.05)); print(rc.check_gates(t))"
```

说明：

- v2 行号以 `c61419c` 为准；v2.0-beta 的 README 与 v2.1-beta 的 CHANGELOG 存在版本号不一致，本文以 CHANGELOG 的 v2.1-beta 为准。
- v2 的 `quality_control` / `report_consistency` 已用 fixture 实测通过；测试套件因沙箱 ACL 无法整体运行，未把"全绿"作为结论。
- 上一份 `upstream-vs-local-comparison.md` 对比的是 fork（v1 快照）；本文对比的是原仓库 v2.1-beta。两份文档的"上游"不是同一个 commit，引用时请注意。

---

*本报告只做项目对比，不构成投资建议。*
