# 上游龟龟框架 vs 本地 turtle-framework 对比分析

> 对比对象
> - 上游：<https://github.com/Polygon1865/Turtle_investment_framework>，clone 于 commit `8fc6291`（2026-04-11）。
> - 本地：`C:\PyProject\turtle-framework`，commit `9793fce`（2026-10-19，27 个提交）。
>
> 方法：拉取上游仓库与本地代码逐层对照；阅读关键实现与提示词；统计行数/测试数；对双方的坏味道做最小复现。所有行号均对应当前 clone/工作区。
>
> 结论先行：**这不是同一代产品的竞争，而是两种取舍。** 上游是"方法论 + LLM 代理工作流"，胜在数据覆盖、四因子深度、报告厚度和 Claude Code 集成；本地是"确定性计算内核 + 受限 LLM 表达"，胜在类型/币种/缺失值纪律、可复现、门禁和工程化。本地在工程上明显领先，但方法与覆盖尚未追平，且存在若干自身缺陷；上游的深度与覆盖面仍难以替代。
>
> **补充**：本文对比的是给定 URL 的 fork 快照（v1）。原仓库 v2.1-beta 的单独对比见 [upstream-v2-vs-local.md](upstream-v2-vs-local.md)；v2 在方法论、质量门、估值模块上均已明显前进，结论需结合两份文档阅读。本地 P0/P1 修复见 [p0-p1-fixes.md](p0-p1-fixes.md)。

---

## 1. 对比基线：仓库关系与规模

### 1.1 一个容易忽略的事实：该 URL 是 fork

GitHub API 显示该仓库 `fork: true`，父仓库是 [`terancejiang/Turtle_investment_framework`](https://github.com/terancejiang/Turtle_investment_framework)（352 stars / 105 forks）。本地 README 第 4 行引用的 `Pr0ph3tyyy/Turtle_investment_framework` 会被 GitHub 重定向到同一个 repo id `1196306613`，即 **`Pr0ph3tyyy` 是 `Polygon1865` 的旧账号名，本地 README 引用的就是该 fork 的旧地址**。

用完整历史对比：

| 项 | fork（给定 URL） | 原仓库 `terancejiang` |
|:--|:--|:--|
| HEAD | `8fc6291`，2026-04-11 | 2026-07-04 仍在更新 |
| 提交数 | 28 | 46 |
| 领先/落后 | 领先原仓库 8 个提交 | — |
| 差异 | 8 个提交主要是：MkDocs 发布、5 篇示例报告、港股限流回退、Tushare 私有 URL 修复 | — |

fork 独有的 8 个提交里，真正影响代码的只有两个修复（港股 `_safe_call` 限流回退、Tushare `_DataApi__http_url`），其余是文档/示例。**fork 落后原仓库 26 个提交**；原仓库已进入 **v2.0-beta**（PDF-first 单 Agent、共享定性模块、独立估值模块、HTML 报告、pre-flight 质量门、§17.10–13 预计算表），与原 fork 相比新增约 1.74 万行、删除约 0.56 万行。

这意味着：本文对"上游"的评价，针对的是 **2026-04-11 的 fork 快照**；如果你真正想对标的是这个项目的当前形态，应再看原仓库 v2。原仓库的 v2 在"质量门/定性模块"上已经朝本地的方向走了一步。

### 1.2 规模对照

| 维度 | 上游 fork | 本地 | 备注 |
|:--|--:|--:|:--|
| Python 源码 | 18 文件 / 7,839 行 | 38 文件 / 6,674 行 | 本地含 817 行 PDF 预处理与 285 行下载器，二者均为上游代码的移植；本地"自有内核"约 5,570 行 |
| 测试 | 15 文件 / 8,467 行 | 21 文件 / 1,559 行 | 测试函数 721 vs 137；pytest 收集约 757 vs 153（含参数化） |
| 提示词 | 10 文件 / 4,383 行 | 14 文件 / 398 行 | 上游含 1,493 行 Tushare API 参考 |
| 提交 | 28（fork） | 27 | 本地 27 个提交全部在 2026-10-19 |
| 依赖 | 13 项（含 pdfplumber/matplotlib/jupyter/mkdocs） | 5 项 + 可选 yfinance | 本地刻意最小化 |
| 打包/入口 | 无 `pyproject`/`setup.py`，脚本 + argparse | `pyproject.toml`，`turtle` console script | 本地是可安装包 |
| 文档 | MkDocs 站点 + 5 篇完整报告 + README | 单一 README | 上游文档成熟得多 |
| License | README 写 MIT，但无 LICENSE 文件 | 无 LICENSE | 两边都不完整；本地移植了上游代码，建议补来源与许可 |

---

## 2. 架构：数字由谁计算，是两条路线的分水岭

### 2.1 上游：脚本负责取数，LLM 负责分析与写报告

```
Tushare Pro / yfinance
        │
        ▼
tushare_collector.py（6 个 mixin 组装）
        │  逐段 get_* + compute_derived_metrics
        ▼
data_pack_market.md（§1–§17，Markdown 表）
        │
        ├── pdf_preprocessor.py → pdf_sections.json（P2/P3/P4/P6/P13/MDA/SUB）
        │
        ▼
Phase 1B WebSearch + Phase 2B PDF 精提取
        │
        ▼
Phase 3 LLM：四因子分析（读 references/ 逐步计算）
        │
        ▼
{公司}_{代码}_分析报告.md（1000+ 行，LLM 撰写）
```

关键点：**数据包只是"原材料"，四因子的比率、门槛、底价、评级主要由 LLM 按提示词重算**。脚本只预计算了 §17 的一部分（OE、门槛价、底价五法、λ 等），但报告中的数字仍可能被 LLM 重新推导或抄错。上游没有"数字只能来自脚本"的硬约束。

### 2.2 本地：代码算完，LLM 只做定性与叙述

```
Tushare / yfinance
        │
        ▼
provider → normalize（wide/长表统一为 StatementRow）→ FileCache / Parquet Store
        │
        ▼
metrics（dividends / statements / returns / valuation）
        │
        ▼
factors/engine.py：四因子确定性规则 → verdict
        │
        ├── report/pack.py → data_pack.md
        ├── report/analysis.py → analysis_report.md（Jinja2）
        │
        ▼
LLM：只产出 qualitative.json（证据化判断）与 narrative.md（不得引入新数字）
        │
        ▼
verify（URL+引文）→ qualitative --check → narrative → qa（交付门）
```

关键点：**R / GG / II / 安全边际 / 底价 / verdict 都由 Decimal 规则算出**；LLM 的产出被限制为"有证据的定性判断"和"使用白名单数字的叙述"。这是本地最核心的设计优势，也是它报告较短、覆盖较窄的原因。

### 2.3 分层对照

| 层 | 上游 | 本地 |
|:--|:--|:--|
| 取数 | `scripts/tushare_collector.py` + `tushare_modules/*`（6 mixin） | `data/tushare_provider.py` + `normalize.py` + `tushare_maps.py` |
| 缓存 | 每个 API 一个 JSON 缓存（TTL 7 天）+ 选股器 Parquet 缓存 | 内容寻址 JSON 缓存（endpoint+全部参数+schema 版本） |
| 存储 | 只落 Markdown/JSON，不建库 | `StatementRow` 长表 + Parquet（自然键去重）+ `snapshot_id` |
| 计算 | 脚本只算 §17 部分指标，其余交给 LLM | 全部指标在 `metrics/` + `factors/engine.py` |
| 报告 | LLM 按模板写 Markdown | Jinja2 确定性模板 |
| 编排 | `prompts/coordinator.md` + Claude Code slash command | `state.py` 状态机 + `prompts/agent/*` + 5 道门 |
| 入口 | 多个 `python scripts/xxx.py` | 单一 `turtle` CLI（14 个子命令） |

---

## 3. 数据层：上游覆盖更广，本地约束更严

### 3.1 接口与市场覆盖

| 能力 | 上游 fork | 本地 |
|:--|:--|:--|
| Tushare 接口数 | 约 28 个（含 VIP、HK、US） | 19 个（15 个 A/HK + 4 个 VIP 批量） |
| A 股 | ✅ 报表、分红、行情、周线、财务指标、审计、质押、回购、股东、主营构成 | ✅ 报表、分红、行情、周线、财务指标、审计 |
| 港股 | ✅ `hk_basic/hk_income/hk_balancesheet/hk_cashflow/hk_daily/hk_fina_indicator` + yfinance | ✅ 三大报表、`hk_daily`（yfinance 优先）、`hk_fina_indicator` 分红 |
| 美股 | ✅ `us_basic/us_daily/us_income/us_balancesheet/us_cashflow/us_fina_indicator` + yfinance | ❌ 显式 `NotImplementedError`（`tushare_provider.py:373`） |
| 母公司报表 | ✅ §3P/§4P | ❌ |
| 质押 / 回购 | ✅ §15/§16 | ❌（配置里有 `max_pledge_pct`，但无实现） |
| 股东 / 主营 / 分部 | ✅ top10_holders / fina_mainbz / 业务分部 | ❌ |
| 批量全市场 | ⚠️ Tier1 用批量行情，Tier2 逐只调用 | ✅ `income_vip/balancesheet_vip/cashflow_vip/fina_indicator_vip`，15 次调用覆盖全市场 5 年 |
| 数据包段数 | §1–§17 | 7 段（关键指标/五年趋势/分红/行情/估值/底价/数据问题） |

本地 README 已承认港股与 PDF 的限制（`README.md:49-54`），但"母公司报表/质押/回购/美股"的缺口没有集中说明；对价值投资框架而言，**质押与母公司现金（现金上游障碍）是上游因子 1B 的重要输入**，本地目前无法覆盖。

### 3.2 缓存、限速、失败处理

| 项 | 上游 | 本地 |
|:--|:--|:--|
| 缓存键 | 多数为 `api_ts_code`；选股器 `md5(key)`，**不含 fields/参数**（`screener_core.py:211`） | `sha256(endpoint + 排序后的全部参数 + schema_version)`（`cache.py:22-30`） |
| 缓存格式 | JSON（collector）/ Parquet+meta（screener） | JSON 内容寻址 + Parquet 长表 |
| TTL | 7 天 / 当日 / 168h / 24h | 默认 7 天，构造可配 |
| 限速 | 0.5s/次；失败 5 次、2s×attempt 退避 | 0.35s/次；3 次、2/4/6s |
| 权限/限频错误 | 同样退避 5 次（`tushare_collector.py:110-136`） | 检测"权限/没有接口/频率超限"立即抛错，不空转（`tushare_provider.py:132-136`） |
| 失败可见性 | 单段异常 `except: pass` 静默降级（`assembly.py:132-153`） | `FetchIssue` 记录并在报告"数据问题"段落展示 |
| 线程安全 | 串行 | 每线程一个 client + 全局节流锁（`tushare_provider.py:99-112`） |

本地缓存键包含全部参数和 schema 版本，是一个明确的正确性修复；上游 `md5(key)` 不含 `fields`，换字段可能命中旧缓存。但本地缓存把 DataFrame 转 `records` 存 JSON，大表（全市场 5 年）落盘体积与反序列化成本会高于 Parquet；目前 fast screen 实际依赖 Tushare 侧速度，未做本地批量缓存。

### 3.3 缺失值处理

上游大量使用 `or 0` 与 NaN 判断，缺失会被当成 0 参与 AA/结余/比率（如 `derived_metrics.py:828-835, 940-964`），只事后给 warning。本地把"缺失"建模为 `Metric(status=MISSING|NOT_APPLICABLE)`，排名按覆盖度加权，Tier2 质量门 fail-closed（缺 ROE/毛利率/负债率直接淘汰，`fast.py:134-146`）。这是本地最扎实的改进之一。

但本地也不是完全干净：`factors/engine.py:110-111` 对 `goodwill/total_assets` 用 `or Decimal("0")`，`valuation.build_valuation` 对 `finance_exp` 用 `or 0`；这些位置仍会把"缺失"变成 0。`dividends.payout_by_year` 在"有净利润但完全无分红记录"时返回 0（`dividends.py:64-65`），语义上可接受（无分红=支付率 0），但需要与"未取到分红数据"区分。

---

## 4. 单位、币种：本地设计正确，但港股实现仍有硬伤

### 4.1 上游的已知缺陷（本地重写的起点）

| # | 缺陷 | 证据 |
|:--|:--|:--|
| 1 | 港股一律按 HKD 标注，不读报表币种；00728/00285/02333/06862 实际为 RMB，报告作者手工纠正 | `infrastructure.py:15-22`；`docs/reports/00728.md:20`、`00285.md:19` |
| 2 | 美股 `total_mv` 存在双重缩放风险：文档口径为百万美元，`financials.py:155` 又除以 1e6，§17 却按原始 USD 使用；`us_daily.total_mv` 的真实口径未 100% 确认 | `financials.py:155`；`derived_metrics.py:416-423, 688`；`tushare_api_reference.md:1461` |
| 3 | 金额只有展示层 ÷1e6，内部仍是 float，跨币种无类型保护 | `format_utils.py:11`；`derived_metrics.py:485-495` |
| 4 | 港股用中国国债收益率作 Rf，且 II 用 `max(5%, Rf+3%)` | `other_data.py:219-223`；`derived_metrics.py:283-291` |

### 4.2 本地的设计

- `Money(amount: Decimal, currency: Currency)`，跨币种相加/相减直接抛 `CurrencyMismatchError`（`types.py:23-83`）。
- 取数层不缩放，存报表币种基础单位；只在展示层 `_m()/1000000`。
- 港股默认按 CNY 报表（多数内地企业），可用 `--currency HKD` 覆盖（`cli.py:194-203`）；但**这是按上市地推断，不是"币种来自报表"**，与 README 设计约束 #2 有出入。
- 港股报价与市值乘以 `fx=0.92` 折算到 CNY（`cli.py:221-225, 266, 270`），分红 DPS 也乘 fx（`dividends(dps_fx=fx)`）。

### 4.3 本地港股的三个实际 bug（本次用现有输出复现）

**(a) 价格历史没有折算，和折后价混用。** `cli.py:273-277` 的 `closes` 直接来自 `provider.weekly()`，港股返回的是 HKD 日线；而 `price` 已乘 0.92。结果是：

- `output/00700.HK/data_pack.md:62` 当前价 `384.38 CNY`；
- 同表 `52 周最高 664.00`、`52 周最低 411.00`、`10 年最低 165.66` 均为 HKD，没有币种标注；
- 底价锚点"10 年最低价"被直接当作 CNY 参与均值/中位数，腾讯的底价与溢价因此被高估（若按 0.92 折算，165.66→152.41，溢价会从 136.49% 升到约 152%）。

这违反本地自己的第一设计约束"金额必须带币种"。

**(b) 港股分红总额未知时显示 0.00。** `pack.py:247-265` 对 `event.total is None` 的港股事件只累加 DPS，`total` 保持 0，随后 `_m(0)` 渲染成 `0.00`。`output/00700.HK/data_pack.md:49-56` 六年"分红总额（百万元）"全部是 `0.00`，读者会误以为公司没分红。

**(c) 港股 DPS 是 TTM 型字段，逐年重复。** `normalize.py:194-227` 按年取 `dps_hkd`，但 `hk_fina_indicator` 的该字段在多个季度重复；结果 2020–2025 年 DPS 都是 `4.8760`。支付率用 `divi_ratio` 是对的，但"分红历史"的 DPS/股息隐含价并不可信。

这三条是本地当前最值得先修的缺陷（见 §10）。

---

## 5. 指标与四因子：同名不同算法，不能直接对比数字

### 5.1 公式对照

| 指标 | 上游 | 本地 | 评价 |
|:--|:--|:--|:--|
| 分红聚合 | 只取"实施"，`drop_duplicates(end_date)`，`div_lookup[year]` **覆盖**而非求和（`financials.py:1007-1029`；`infrastructure.py:246-251`） | 去重 `(period_end, dps)`，同财年多次分红**求和**（`normalize.py:142-191`；`dividends.py:26-68`） | 本地修复了上游最实质的缺陷 |
| 股息税 | 全程税前 | A 股 0%，港股 20%（`cli.py:279`） | 本地略好；A 股仍未建模持有期税率 |
| FCF | OCF − |Capex|（`financials.py:823-833`） | 同左（`statements.py:51-61`） | 一致 |
| Owner Earnings | `C + D − D×G`，G 按行业 0.7–1.8（`factor2` 提示词） | 同公式，但 **G 硬编码 1.0**（`engine.py:22,115`） | G=1 时 **OE 恒等于归母净利润**，"Owner Earnings"名不副实 |
| 粗算 R | AA×M/市值，AA 为现金口径（`screener_core.py:618-769`） | `OE×M×(1−税)/市值`（`returns.py:19-39`） | 本地是"净利润×支付率/市值"，不是上游的现金口径 |
| 精算 GG | 真实现金收入 − W1–W4 → AA（2 年/all/excl）→ λ/敏感性（`derived_metrics.py:838-1120`） | 近 2 年 FCF 均值 × M / 市值；敏感性按 0.9/0.8/0.7 等比缩放（`engine.py:131-148, 397-399`） | 本地是"FCF 回报率"，没有收入桥、营运资本调整、λ；标签叫"精算"会误导 |
| 门槛 II | A 股 max(3.5%, Rf+2%)；港股 max(5%, Rf+3%) | 同左（`config.py:40-46`） | 一致；上游在多处重复实现 |
| 底价五法 | 净流动资产/BVPS/10 年最低/股息隐含/悲观 FCF，**算术平均**（`derived_metrics.py:570-646`） | 同五法；数据包/报告实际优先用**中位数**（不可用时才用均值），分歧 >20% 时再封顶仓位（`pack.py:186-191`；`analysis.py:67-88`） | 本地更稳健，但 `composite_method` 配置项与实际行为不一致 |
| 负基准价 | 不剔除，负 composite 仍可能判"买入就是胜利"（`derived_metrics.py:635-646`） | 同样不剔除：600887 净流动资产/股 `-4.90`、腾讯 `-26.22` 仍进入均值 | **本地未修复**；只是用中位数缓解 |
| 可复现 | 报告含时间戳与 LLM 叙述，无快照 | `snapshot_id` + 确定性模板，同快照逐字节可复现 | 本地优势 |

### 5.2 结论

本地引擎不是上游四因子的"重写"，而是**同名标签下的一套简化模型**：

- 因子 2 在 G=1.0 时退化为"净利润 × 支付率 / 市值"；
- 因子 3 用历史 FCF 替代上游的"真实现金收入还原 + 经营流出 + λ"；
- 因子 4 的"安全边际"是 `GG − II`，上游还有 PE/PB 分位、11 项绝对估值、溢价区间等；
- 本地因子 1A/1B 只保留可自动计算的部分，其余标 `unknown`，而上游 1B 有模块〇–九（数据校准、资本强度、收款、护城河、周期、人力、治理、政策、MD&A、控股折价）。

因此：**本地报告与上游报告即使对同一只股票，R/GG/底价也不可直接比较**。如果本地要作为"龟龟策略"的实现，至少需要把 G 的行业系数、因子 3 的现金口径、底价负值处理补齐；否则应明确改名为"简化版四因子"。

---

## 6. 选股器：阈值同源，本地在速度与排名纪律上更好

| 项 | 上游 | 本地 |
|:--|:--|:--|
| 市场 | 仅 A 股 | 仅 A 股 |
| Tier1 过滤 | ST/PT/退市、剔金融、上市≥3 年、市值≥5 亿、换手≥0.1%、0<PB≤10、双通道 PE | 同左（`configs/screening.toml`；`tier1.py`） |
| Tier1 排名 | `0.4·dv + 0.3·(1/PE) + 0.3·(1/PB)`，主通道取前 150 + 观察 50 | 同左（`tier1.py:71-96`） |
| Tier2 否决 | 质押>70%、非标审计 | 审计意见 + 频繁换审计师；**无质押** |
| Tier2 质量门 | ROE≥8%、毛利≥15%、负债率≤70% | 同左，且缺失即淘汰（fail-closed） |
| Tier2 评分 | 20/20/25/15/20 百分位加权 | 同权重；缺失记 0 分，覆盖度<75% 不评分 |
| 并发 | 串行 for 循环（`screener_core.py:1193-1206`） | 线程池 6（`tier2.py:211-215`） |
| 全市场速度 | Tier1 ~5 秒，Tier2 逐只 | Fast 阶段 15 次 VIP 批量调用，README 称全市场约 25 秒 |
| 输出 | CSV（utf-8-sig）+ HTML + Notebook 图表 | CSV（浮点未四舍五入，如 `output/fast_top20.csv` 的 15 位小数） |

本地在"覆盖度感知排名"和"缺失即淘汰"上比上游严谨，Fast 阶段用 VIP 批量接口也是明显的性能优势。不足：没有 HTML/图表，CSV 未格式化；Tier2 的 `issues` 列永远是 0，数据问题没有随行输出；观察通道的规则比上游简化。

---

## 7. LLM 工作流与报告：上游厚，本地严

### 7.1 上游：一个完整的 Claude Code 研究流程

- **入口**：`.claude/commands/turtle-analysis.md`、`.claude/commands/download-report.md`、`.claude/skills/turtle-analysis/SKILL.md`，用户输入 `/turtle-analysis 600887`。
- **协调器**：`prompts/coordinator.md`（499 行）定义 Phase 0/1A/1B/2A/2B/3、AskUserQuestion 触发条件、checkpoint（"内部设置 checkpoint"）、异常处理表（PDF 失败降级、脚本失败提示、因子否决停止）。
- **Phase 1A**：`tushare_collector.py` 产出 `data_pack_market.md`（§1–§17）+ `available_fields.json`。
- **Phase 1B**：Agent WebSearch 补充治理/行业/子公司，追加到 §7/§8/§9B/§10/§13。
- **Phase 2A/2B**：`pdf_preprocessor.py` 提取 7 段文本 → Agent 精提取为 `data_pack_report.md`。
- **Phase 3**：`prompts/phase3_分析与报告.md`（532 行）+ 4 个因子参考文件（共 1,222 行）+ 1,493 行 API 参考；采用"渐进式披露"，Agent 按需加载；报告模板固定 9 章、因子 1B 含 3.0–3.10。
- **失败策略**：任何阶段失败都尽量降级继续，最终总要产出报告；因子否决则停止后续因子。
- **质量保障**：主要靠提示词里的"计算步骤 + 检查项"；`test_phase1b/2b/3_prompt.py` 等约有 130–150 项测试是**对提示词文本的子串断言**（如"必须出现 §4P"），不是对分析结果的验证。

**上游提示词里的规格矛盾（会影响执行一致性）**：

- Phase 0 的顺序在 coordinator 内两处写法不一致（`coordinator.md:135-147` vs `:420-429`）；
- Phase 1B 一处说"追加到 §7/8/9B/10"，另一处说"替换占位符"（`phase1_数据采集.md:24` vs `:229-236`）；
- Phase 3 一处说"关键数据缺失即终止"（`phase3_分析与报告.md:119`），slash command 却说"任何阶段失败都要产出最终报告"（`turtle-analysis.md:47`）。

**因子公式/阈值（供本地对照）**：

- F2：`I=C+D−D×G`，G 轻/中/重资产 = 0.7–1.0 / 1.0–1.3 / 1.2–1.8；`R=[C×M×(1−Q)+O]/市值`；`R<Rf` 或 `R<II×0.5` 否决，`II×0.5≤R<II` 边际。
- F3：真实现金收入 `S−AR净增−预收净减`；`AA` 默认取 2 年均值；`GG=[AA×M×(1−Q)+O]/市值`；λ 做收入敏感性；另给五维外推可信度，无独立数值否决门。
- F4：`GG<II` 且成长性支出 >30% 建议细化，否则排除；价值陷阱 N=0/1/≥2 → 低/中/高；目标买入价 = 市值×(GG/II)/总股本；无综合数值评分。
- 评级以"类别 + 仓位矩阵"表达，而不是单一分数；这与本地的 `verdict/position` 逻辑相近，但本地的阈值是硬编码 Decimal 规则。

**优点**：方法论完整、可解释、报告可读性极强；示例报告（`docs/reports/00728.md`，1,047 行、32 处 ⚠️）展示了深入的模块化分析、Warnings 机制和人工纠错过程。
**缺点**：报告数字由 LLM 重算，无法保证与数据包一致；没有交付门禁；提示词测试无法发现数值错误；对 Claude Code/Cowork 强依赖。

**示例报告也暴露了上游的数据纪律问题**：

- `00728.md` 的 D&A/Capex 在 §5 缺失后改用 WebSearch 数值（`:62-64, 363-364`），并自造 `§13.3`（`:1032`）；P2 缺失时把 CC 估成 0（`:643`）。
- `00506.md`（252 行）缺 1.5/3.x/5.x/9.1 等章节，且 HKD 与 RMB 混算（`:24-28, 100-112`），同一报告内 R 出现 7.34 与 7.44、EV/EBITDA 出现 3.7x 与 2.1x 两组数（`:186-188`）。
- `06862.md` 结论是"观察"，但 `docs/index.md:26` 显示"—"：`publish_report.py:98-113` 的正则先命中了正文 664 行的"最终判断：价值陷阱风险=高"，而不是结论段。
- 17 行的 `[DATA_MISSING|中]` 不符合 Phase 1 的警告分类格式。

这些不是"LLM 写得不好"，而是**缺少确定性数字层与发布门禁**的必然结果；恰好是本地要解决的问题。

### 7.2 本地：状态机 + 五道门

| 阶段 | 产物 | 门 |
|:--|:--|:--|
| intake | `run_state.json` | 代码可解析、venv/.env 可用 |
| data | `data_pack.md` | 关键段齐全；缺段记 warning |
| report_pdf | PDF、`pdf_sections.json`、`reported_numbers.json` | PDF 合法、章节命中 ≥4；否则降级无 PDF |
| qualitative | `qualitative.json` | `verify`（URL+引文匹配）+ `qualitative --check` |
| report | `narrative.md` | `narrative` 数字白名单 |
| qa | 交付说明 | `qa --write` 全 PASS 才能 `done` |

具体机制：

- **证据化定性**：6 个模块固定键；非 `unknown` 必须有 http(s) URL + 非空引文，否则自动降级（`qualitative.py:118-137`）。
- **事实校验**：`verify.py` 拉取 URL、NFKC 归一化、匹配引文，未通过则整模块降级（`verify.py:66-120`）。
- **数字白名单**：`narrative.py` 抽取叙述中的所有数字，只允许出现在 `analysis_report.md`/`data_pack.md`/`qualitative.json` 中；不允许换算/补零（`narrative.py:45-64`）。
- **QA 门**：缺 `run_state`、缺报告、定性全 unknown、叙述有不可追溯数字都会 FAIL（`qa.py:16-55`）。
- **黄金集**：`golden.py` 支持人工标注 CSV 与一致率评分，但 `golden_set.csv` 目前只有空模板（无标注），尚未产生可用的准确率数字。

**优点**：LLM 不能污染数字层；失败可定位、可重跑；产物可复现。
**缺点**：流程与提示词较短（398 行 vs 4,383 行），定性 rubric 只有 7 个小文件，分析深度明显不如上游；**本地没有 `.claude/commands`/`SKILL.md`**，这套 6 阶段流程目前需要手动喂给 Agent，开箱即用性弱于上游。

### 7.3 本地报告的实际质量问题（用现有输出复核）

- `output/600887.SH/analysis_report.md:8` 结论是"观察（底价口径分歧）"，但同报告 `:97` 因子 4 的"仓位建议"仍是"标准仓位"、`:98` 结论"买入"。`analysis.py:81-88` 在渲染时改了 verdict，却没有同步 factor 4 的 metrics，造成自相矛盾。
- 模板 `analysis.md.j2:72-78` 的"仍未验证"是**静态清单**，即使护城河/管理层已是正面判断，仍会列出"护城河类型与竞争格局、管理层与治理结构"。
- `analysis.md.j2:86` 写"未包含 LLM 定性判断"，但报告正文已包含 evidence-backed 定性结论与证据。
- 港股数据包的 `0.00` 分红与混币（见 §4.3）。

这些问题不影响"数字可追溯"的门禁，但会直接影响读者对报告的信任；修复成本很低，应优先处理。

---

## 8. 工程质量与测试

### 8.1 测试

| 项 | 上游 | 本地 |
|:--|:--|:--|
| 测试函数 | 721 | 137（pytest 收集 153） |
| 测试行数 | 8,467 | 1,559 |
| 数据 | 17 个 mock JSON（A/HK/US）+ MagicMock 注入 | 合成 `StatementRow`，无 provider mock |
| 类型 | 单元 + prompt 文本断言 + 集成（无 token skip） | 单元 + demo/CLI + 门禁测试 |
| 数值验证 | §17 衍生指标 83 个测试、screener 96 个测试 | metrics/factors/dividends/normalize 等精确 Decimal 断言 |
| 端到端 | 有集成测试（依赖 token） | 无真实数据回归；golden 集为空 |

**本次实际运行**：

- 本地 `pytest` 收集 153 项；**133 通过，20 个 setup error**。20 个错误全部是 `PermissionError`（写 `tmp_path` 被当前 Windows 沙箱 ACL 拒绝），没有断言失败。属于环境问题，不是测试逻辑失败。
- 上游收集 654 项（排除两个依赖 `pdfplumber` 的模块；本地 venv 未装该包），**全部 setup error，原因同样是 `PermissionError`**；因此本次无法验证上游测试通过率。其测试设计为离线，预计在正常环境可运行。

结论：上游测试"量大但偏文本契约"，本地测试"量小但更贴近数值正确性"。本地缺的是 **provider 解析层的 mock/fixture 测试** 和 **端到端 golden 回归**；上游缺的是对最终报告数字的断言。两者可以互补。

### 8.2 工具与工程化

| 项 | 上游 | 本地 |
|:--|:--|:--|
| 打包 | 无 | `pyproject.toml` + editable install + console script |
| 类型检查 | 无配置 | mypy strict 配置；实际 `mypy src` 报 **97 个错误** |
| Lint | 无 | ruff 配置；实际 `ruff check` 报 **368 条**（多为 FURB157/UP 风格项，含 8 个未使用 import） |
| CI | 仅 docs.yml | 无 |
| 依赖声明 | requirements.txt | pyproject（但 **pdfplumber 未声明**，`turtle pdf` 会在导入时失败） |
| 平台 | bash/init.sh（Unix 优先） | PowerShell/init.ps1（Windows 优先） |
| 配置 | `screener_config.py` dataclass | `configs/screening.toml` + dataclass + `.env` |
| 文档 | MkDocs + 5 篇报告 | README |
| 代码复用 | mixin 重复 7 个方法、多处 `except: pass` | 分层清晰，但 **`pdf/preprocessor.py` 与上游 100% 相同（817 行）**、`data/reports.py` 与上游 `download_report.py` 98.2% 相同 |

**关于"clean-room"**：README 第 3-5 行称"实现从头重写"。实际有两个文件是上游代码的移植：

- `src/turtlefw/pdf/preprocessor.py`：与上游 `scripts/pdf_preprocessor.py` 逐行相同（817 行，仅 CRLF 差异），文件头仍写着 `scripts/pdf_preprocessor.py` 与 `Feature #38/#43`；
- `src/turtlefw/data/reports.py`：与上游 `download_report.py` 差异仅"URL 白名单扩展 + Windows 关闭文件后删除"，其余 277 行基本相同，`reports.py:218` 还留着 "Print structured result block for Claude"。

这不一定是问题（复用成熟代码是合理的），但与"clean-room"表述冲突，且带来**许可/归属**问题（上游 README 声称 MIT 却无 LICENSE）。建议：要么重写这两个模块并补测试，要么在 README 与文件头明确"移植自上游，MIT，作者 terancejiang"，并补 LICENSE。

### 8.3 其他本地细节

- `configs/screening.toml:18` 的 `max_pledge_pct` 没有任何代码使用（质押数据未接入）。
- `configs/screening.toml:52` 的 `composite_method = "mean"` 在报告/数据包中实际被"中位数优先"覆盖（仅中位数不可用时才用它），配置语义与实际行为不一致。
- `.gitignore` 未忽略 `tmp/`、`init.log`，当前 `git status` 有未跟踪文件。
- 港股 `--currency HKD` 时，`_fx_for` 返回 1，但市值仍来自 yfinance 的 HKD 报价，OK；然而 52 周高低/10 年最低仍未换币，问题同 §4.3。

---

## 9. 优劣势矩阵

| 维度 | 上游 | 本地 | 判断 |
|:--|:--|:--|:--|
| 数据覆盖 | 28 接口，A/HK/US，质押/回购/股东/分部 | 19 接口，A/HK | 上游明显 |
| 四因子方法深度 | 1A/1B/2/3/4 完整步骤，参考文件 1.2k 行 | 简化确定性版本 | 上游明显 |
| 数值正确性/可复现 | 弱（float、LLM 重算、无快照） | 强（Decimal、快照、模板） | 本地明显 |
| 币种/单位纪律 | 弱（HKD 硬编码、美股 1e6） | 设计强，港股实现有 bug | 本地略优 |
| 缺失值处理 | 弱（`or 0`） | 强（三态 + fail-closed） | 本地明显 |
| 选股速度 | Tier1 快，Tier2 串行 | Fast 批量 + Tier2 并发 | 本地 |
| 报告丰富度 | 1,000+ 行、模块化、示例多 | 170 行、结构固定 | 上游明显 |
| 质量门/可审计 | 弱（prompt 约束） | 强（verify/narrative/qa） | 本地明显 |
| Claude Code 集成 | 完整 slash command/skill | 无 `.claude` 入口 | 上游明显 |
| 测试规模 | 721 函数/8.5k 行 | 137 函数/1.6k 行 | 上游 |
| 测试有效性 | 大量提示词文本断言 | 数值单测 + 门禁 | 本地略优 |
| 打包/CLI | 无 | 有 | 本地明显 |
| 文档/示例 | MkDocs + 5 篇报告 | README | 上游明显 |
| 维护成本 | 单仓脚本 + 提示词，耦合高 | 分层包，边界清晰 | 本地 |

---

## 10. 建议

### 10.1 本地优先修（按影响排序）

**P0（正确性/信任）**

1. **港股汇率统一**：`weekly/hk_history` 的 `close` 在进入 `closes` 前乘 `fx`，或让 `Money` 一路带币种；52 周高低/10 年最低同步换币。修复后重跑 00700 数据包。
2. **港股分红展示**：`total is None` 时显示 `—` 而不是 `0.00`；`hk_fina_indicator` 的 DPS 不要按年重复（用 `divi_ratio` 或按公告年度取一次），否则"股息隐含价"失真。
3. **因子 2/3 口径**：G=1.0 让 OE=净利润，建议按行业给 G，或在报告中明确写"OE 采用净利润近似"；因子 3 若不做收入桥/λ，改名为"FCF 回报率（简化）"，避免与上游"精算"混淆。
4. **底价负值**：净流动资产为负的锚点应剔除或做截断，不能进入均值；至少与中位数口径一起展示"有效锚点 n/5"。
5. **报告一致性**：verdict 修改后同步 factor 4 的仓位/结论；"仍未验证"改为动态生成；删除"未包含 LLM 定性判断"的错误声明。

**P1（可用性/工程）**

6. 在 `pyproject.toml` 增加 `pdfplumber`（或 `[project.optional-dependencies].pdf`），并为 `turtle pdf` 增加 smoke test；要么完成 M6，要么把 PDF 模块标为 legacy。
7. 增加 `.claude/commands/turtle-analysis.md` 与 skill 描述，把 6 阶段流程做成开箱即用入口（可直接参考上游的 52 行 command，替换为本地的 `state/pack/verify/qa` 命令）。
8. 为 provider 增加 mock fixture 测试（A/HK 两套 JSON），覆盖 `rows_from_hk_line_items`、分红去重、字段缺失、限频异常；这比继续加 metrics 单测更能防回归。
9. 增加 golden 数值回归：固定一份 Parquet 快照 + 期望报告关键数字，CI 中断言；同时把 `golden_set.csv` 填上真实人工标注，才能证明定性层的价值。
10. 清理 ruff/mypy（或放宽配置到可通过），加一个最小 GitHub Actions（pytest + ruff）。

**P2（能力补齐）**

11. 接入质押、回购、母公司报表（现金上游障碍）、股东/主营构成；这些是因子 1B 的关键输入。
12. 明确美股范围：要么实现 `us_*`，要么在 CLI 中给出清晰错误与路线图。
13. 数据包格式：给 52 周高低/10 年最低加币种，CSV 输出四舍五入，Tier2 的 `issues` 按股票累计。
14. 解决"移植代码"的归属与许可：补 LICENSE、文件头注明来源，或在 README 的"clean-room"表述上加限定。

### 10.2 上游值得保留/加强的

- 方法论深度：因子 1B 的模块〇–九、因子 2 的行业 G、因子 3 的现金桥与 λ、因子 4 的 11 项估值，是本地短期难以补齐的资产。
- 数据覆盖：美股、质押、回购、股东、分部、母公司报表。
- 报告可读性与示例：`docs/reports` 的 5 篇报告是很好的评测集，可用来校准本地的定性 rubric。
- 但应修：
  - 数据层：港股/美金币种与缩放、分红聚合、底价负值、NaN 崩溃、缓存键、`except: pass`；
  - 提示词层：Phase 0 顺序、1B 追加 vs 替换、Phase 3 终止 vs 必出报告三处规格矛盾；
  - 发布层：`publish_report.py` 的正则先匹配到"价值陷阱风险=高"导致索引结论错（`docs/index.md:26` 与 `06862.md` 不一致）；
  - 安全/整洁：`token_test.ipynb:19-20` 硬编码 Token、`.claude/skills/tushare` 指向仓库外路径、`tushare_api_reference.md` 未被任何 prompt 引用、README 仍宣称不存在的 `feature_list.json`/`claude-progress.txt`；
  - 测试：把"提示词文本断言"换成"报告数字回归"（固定 data pack → 期望 R/GG/II/底价/评级）。
- 最后：fork 已落后原仓库 26 个提交；若要继续用上游，建议直接跟进原仓库 v2，而不是在 fork 上二创。

### 10.3 选型建议

- **需要批量、可审计、可复现的筛选与估值**：用本地。它的数字层可信，门禁能防止 LLM 编数字；代价是方法简化、覆盖窄、报告短。
- **需要单只股票的深度研究、可读报告、完整四因子叙事**：用上游（建议直接用原仓库 v2，而不是落后 26 个提交的 fork）。它的方法完整、报告厚；代价是数字需要人工复核，且强依赖 Claude Code。
- **最佳组合**：用本地做"数据与数字层 + 门禁"，用上游的 factor 参考文件做"方法层"，LLM 只在本地白名单内写叙述——这正是本地已经走了一半的路，缺的是把上游的方法深度移植进确定性引擎，而不是把数字交回给 LLM。

---

## 11. 复现与说明

```powershell
# 拉取上游（当前 URL 是 fork；原仓库见 terancejiang/Turtle_investment_framework）
git -c http.sslBackend=openssl clone --depth 1 https://github.com/Polygon1865/Turtle_investment_framework.git .compare\upstream

# 本地
.\.venv\Scripts\python.exe -m pytest -q --basetemp=<可写目录>
.\.venv\Scripts\python.exe -m turtlefw.cli qa 600887
```

说明：

- 上游行号以 fork `8fc6291` 为准；原仓库 v2 已重构，部分路径/行号会变化。
- 本文的"上游缺陷"来自对 fork 代码的逐行审阅；`hk_fina_indicator.total_market_cap` 的单位、`us_daily.total_mv` 的真实口径两处未能 100% 确认，相关结论已按"风险/未确认"表述。
- 本次测试运行受 Windows 沙箱 ACL 影响（`tmp_path` 不可读），双方的通过率都不能作为最终结论；本地 133/153 通过、无断言失败，上游全部 setup error，原因均为 `PermissionError`。
- 分析用的上游 clone 已移出工作区，不在仓库内留下副本；当前残留的未跟踪项是项目原有的 `tmp/`、`init.log` 等（`.gitignore` 未覆盖）。

---

*本报告只做项目对比，不构成投资建议。*
