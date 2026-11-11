# 设计完成路线图（2026-11）

> 本文是 [target-architecture.md](target-architecture.md) 的执行版：原文档定义“五层架构 + 六条验收”，本文补齐它没定义的口径、生命周期、新鲜度、质量门、成本、可观测性与迁移契约，并给出可执行的波次计划。
>
> 状态：设计定稿，代码按波次推进；每一波结束都必须处于“可发布”状态。

## 0. 完成是什么意思

“完整”不是功能数量，而是**设计里每一条承诺都能指向一个测试或一行 CI**：

1. 五层各有契约与契约测试；
2. 六条验收标准各有一个自动化检查；
3. A/HK/US × 年报/中报/季报 各有一组 golden；
4. 任何一类失败都能在报告/站点上看见，而不是藏在 `failure.json`；
5. 日报在无人值守下连续运行，且指标达标；
6. 设计文档与代码同版本更新（ADR 制度）。

## 1. 审查记录：第一版方案的 14 个问题

| # | v1 的问题 | v2 的修正 |
|---|---|---|
| 1 | 改 payout 口径会改历史结论，v1 只说“要么标版本要么重建”，没决定 | 先冻结基线（W0.0），历史只打 `metric_version` 标签，不重算 |
| 2 | “跨产物一致性”同时出现在 W0 和 W5.3 | 唯一 owner 是 W5.3，W0 只做口径实现 |
| 3 | PIT 与 US 排在同一波，两个最不确定项互相拖累 | PIT 先做（影响 A/HK 日报），US 独立轨道，不阻塞 |
| 4 | 波次表漏了 W3/W6/W7/W9/W10 | v2 给出完整 WBS→波次映射 |
| 5 | 估时不含测试/迁移/文档，按历史（00700 PDF）至少低估 50% | 总额从 330 人日上调到 ≈536 人日（含 30% 缓冲） |
| 6 | “报告 0 个 code-rendered 数字”没有盘点 | 新增 W2.0 盘点工作项，先量化再估时 |
| 7 | 收紧质量门会让“失败日”变多，v1 只说“需要接受” | 明确 publish 策略变更需用户批准（ADR-04） |
| 8 | live CI 需要网络与 secret，GitHub Actions 不可行 | 改为“本地 nightly + GitHub 离线 CI”（ADR-12） |
| 9 | golden set 会被“批量重生成”悄悄改掉 | 新增 golden 更新协议（ADR-11） |
| 10 | “旧快照可重放”不可行（历史渲染器无法全部保留） | 改为版本标签 + 归档只读（ADR-08） |
| 11 | 多市场差异矩阵只写文档，必然腐烂 | 绑定 config 默认值 + 每市场一个测试（ADR-09） |
| 12 | 成本预算抽象，没有数字 | 给出每日/每月 token 与费用上限（ADR-06） |
| 13 | DoD “7 天无人工干预”不现实 | 改为回退率、漂移率、覆盖率三类指标 |
| 14 | 单人却排了并行波次 | 串行日历，每波可发布；并行只在“我 + 一个 agent”范围内 |

## 2. 锁定的设计决定（ADR 摘要）

| ADR | 决定 | 理由 |
|---|---|---|
| ADR-01 口径单一源 | payout/市值/币种/单位各只有一个 owner 函数，screener/report/cleanroom 全部调用；报告头打印口径 | 今天实测 01513 100% vs 1.13%，同一家公司两个答案 |
| ADR-02 结论生命周期 | claim 带 `evidence_hash`；证据不变不得改判；judgment 变更写 `verdict_history` 并在站点显示“变更原因” | 00270 四天两次翻转，用户无法信任 |
| ADR-03 数据新鲜度 | 缓存可跨天，但必须 `trade_date` 断言 + 报告头 `stale` 标记；stale 不得静默当 fresh | 1033 那次“服务在跑但隧道断”就是静默降级 |
| ADR-04 质量门分层 | 硬门（数字/证据/一致性）阻断发布；软门（研究深度/回退率）只告警；`publish_partial` 默认改成 False | 现在 fallback 21/40 仍 PASS，错误不可见 |
| ADR-05 Agent 四角色 | Extractor/Researcher/Writer/Auditor，schema + 工具白名单；单角色模式保留为回退 | 设计 §4.2 的要求，但现在只有一次 research 调用 |
| ADR-06 成本预算 | 每日 token 上限（默认 500k）、调用上限、超限降级为“只跑确定性报告”；记录实际用量 | 当前 40 只 ≈ 370k/日，四角色会翻倍 |
| ADR-07 可观测性 | 每日指标（coverage/fallback/drift/runtime/cost）+ health.txt + 阈值告警 | 现在只有 health.txt 几个字段 |
| ADR-08 快照版本 | manifest 增 `snapshot_version`；旧快照不迁移，归档 HTML 只读；新版本才能重渲染 | 保留全部历史渲染器不现实 |
| ADR-09 多市场矩阵 | 一张表：期间/币种/分红/治理/税档/底价/门槛的差异，直接生成 config 默认值与测试 | 现在 A/HK 差异散落在代码里 |
| ADR-10 研究质量 | 证据等级（一手>交易所>媒体）、一手来源比例、rubric 抽检；不达标只降级不伪造 | “有证据”不等于“证据对” |
| ADR-11 golden 协议 | golden 变更必须单独提交并写明原因；禁止批量重生成；CI 对比失败优先当 bug | 否则基线会被“顺手更新”抹掉 |
| ADR-12 live CI 形态 | 本地 nightly（真实 provider + 真实 LLM）+ GitHub 离线 CI（golden/fixture） | 无 secret/网络限制 |
| ADR-13 US 轨道 | 独立分支/独立配置，不阻塞 A/HK；未达标前不进 daily | US 的边际价值低于 A/HK |
| ADR-14 重建管线 | `turtle rebuild --date` 可从快照重算并重发站点；34 个 release 可批量重算 | 口径变更后需要一次性重算历史 |

## 3. 基线冻结（W0.0，第 1 周）

在改任何口径之前，先记录“改之前长什么样”：

1. 用当前代码对 `.runs/daily/2026-11-10` 全量生成一份 `baseline/`（报告 md + metrics + qa）；脚本 `tmp/freeze_baseline.py` 待写，逻辑是读 `status.json` 后逐票复制 `analysis_report.md`、`metrics.json`、`qa.json`，再从报告首行提取结论；
2. 记录 40 只的 R/GG/margin/verdict 到 `baseline/summary.csv`；
3. 记录当月 34 个 release 的首页 hash 清单；
4. 之后每次口径变更，都与这份基线 diff，差异必须解释。

## 4. WBS v2（全量，含依赖与验收）

> 估时为“人日”，已含测试；依赖列只写前置工作项。

### W0 一致性与基线（≈24 人日，第 1–3 周）

| ID | 工作 | 产出 | 依赖 | 估时 | 验收 |
|---|---|---|---|---|---|
| W0.0 | 基线冻结 | baseline/ + summary.csv | — | 3 | 可 diff |
| W0.1 | 支付率单一源 | `metrics/payout.py` + 三处调用改造 | W0.0 | 5 | 同日 ranking/report 偏差=0 |
| W0.2 | 市值/币种单一源 | `metrics/market_cap.py` + 站点/报告统一 | W0.0 | 5 | screener 与报告市值一致 |
| W0.3 | drift 留痕 | `verdict_history.json` + 站点展示 | W0.0 | 5 | 00270 类翻转有原因 |
| W0.4 | 回退可见性 | QA 增 `research_fallback_rate` 行 | — | 3 | >10% 记 WARN |
| W0.5 | 跨产物一致性检查 | QA 增 `cross_product_consistency` | W0.1/0.2 | 3 | 偏差 >0.5pp 即 FAIL |

### W1 数据层（≈81 人日，第 4–9 周）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W1.1 | provider 协议 v2（7→40+，Protocol + 契约测试） | 5 | mypy 全绿 + 每方法有测试 |
| W1.2 | 缓存跨天共享 + stale 语义 + `--refresh` | 4 | 首跑 <40 分钟；trade_date 断言 |
| W1.3 | HK 股东/分部 PDF 版式泛化（≥10 种） | 15 | 10 种版式回归通过 |
| W1.4 | 母公司报表/质押/回购/主营（HK/US） | 12 | 字段进 data pack，缺则 unknown |
| W1.5 | PIT vendor vintage + restatement + 公告日回填（A/HK） | 15 | 任意 as-of 可重建 |
| W1.6 | US provider（SEC companyfacts/submissions + CIK + 币种/期间 schema） | 25 | AAPL 报告可跑，标注 experimental |
| W1.7 | source ranking 三档进引擎与审计 | 5 | 冲突写 discrepancy |

### W2 Facts 层（≈45 人日，第 10–13 周）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W2.0 | code-rendered 数字盘点 | 3 | 清单化，逐项 owner |
| W2.1 | MetricPoint 全量迁移 | 12 | 报告 0 个 code-rendered 数字 |
| W2.2 | DocumentFact 页级贯通 | 10 | PDF 证据带页码 |
| W2.3 | 中报/季度/TTM 双跑→切换 | 12 | 双跑差异表 + 切换开关 |
| W2.4 | formula registry | 5 | 每个指标可追 formula_id |
| W2.5 | snapshot_version + 归档只读 | 3 | 旧快照可读不可重渲染 |

### W3 Research 层（≈40 人日，第 14–17 周）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W3.1 | claims 深度（6→10，evidence/claim ≥1.5） | 6 | 指标进 QA |
| W3.2 | 证据等级 + 一手来源比例 | 6 | 每 claim 标注等级 |
| W3.3 | claim 状态机（evidence_hash） | 8 | 证据不变不改判 |
| W3.4 | 行业/竞对结构化（CompetitorFact） | 10 | 竞对表有期间/来源 |
| W3.5 | 管理层结构化（任期/薪酬/关联交易/承诺） | 6 | 进 D4 |
| W3.6 | 研究质量 rubric + 抽检脚本 | 4 | 抽检报告可复现 |

### W4 Agent 编排（≈45 人日，第 18–22 周）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W4.1 | 四角色 + 工具白名单 + schema | 15 | 契约测试全过 |
| W4.2 | 编排器：状态机/断点恢复/预算/重试 | 12 | 中断可恢复 |
| W4.3 | fake-LLM 全链路 | 6 | CI 可跑 |
| W4.4 | LLM 质量回归（golden research + 人工标注） | 9 | 每版有基线分 |
| W4.5 | 多模型路由/降级 | 3 | 单模型故障可降级 |

### W5 Audit 层（≈30 人日，第 23–25 周）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W5.1 | numeric audit 按 source class | 8 | 每个数字有来源类 |
| W5.2 | citation audit（URL 可达 + 引文 + 页码） | 8 | 断链即 FAIL |
| W5.3 | consistency audit（结论/仓位 vs claims；跨产物） | 6 | 不一致即 FAIL |
| W5.4 | clean-room 抽样进 QA | 5 | 每日 2 只 |
| W5.5 | 发布策略（硬门/软门/publish_partial） | 3 | 需用户批准 |

### W6 质量基础设施（≈30 人日，第 26–28 周）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W6.1 | golden set（20–30 样本 × 关键字段） | 10 | CI diff |
| W6.2 | 本地 nightly live smoke | 8 | 每日 07:00 出报告 |
| W6.3 | 指标看板 + 告警 | 7 | 阈值触发通知 |
| W6.4 | 指标定义与口径文档 | 5 | 一页纸 |

### W7 报告层（≈30 人日，第 29–31 周）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W7.1 | 研究分章（D1–D6/行业/竞对/管理层/控股） | 12 | 16+6 章，无重复 |
| W7.2 | 表格渲染器（列头/单位/口径） | 8 | ragged=0 |
| W7.3 | 图表（价格/估值/敏感性） | 6 | 每图有 alt |
| W7.4 | PDF 导出 + 打印样式 | 4 | 可导出 |

### W8 产品（≈20 人日，第 32–33 周）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W8.1 | 推送多通道（企业微信/Server酱/PushPlus/WxPusher） | 4 | 配置即用 |
| W8.2 | 站点历史对比/diff | 8 | 可看变化 |
| W8.3 | 自选/提醒 | 8 | 可订阅单票 |

### W9 工程健康（≈25 人日，最后做）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W9.1 | CLI 拆分（_report 574 行等） | 15 | 函数 <200 行 |
| W9.2 | `except Exception` 收紧 + 类型覆盖 | 6 | 无裸捕获 |
| W9.3 | ADR/设计同步 | 4 | 每波更新 |

### W10 方法论（≈30 人日，与 W7 并行）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W10.1 | 因子3 11 步现金桥全调整 | 10 | V/X 项进结论 |
| W10.2 | 估值默认假设（WACC/SOTP） | 6 | 默认值有测试 |
| W10.3 | 回购注销/SBC treasury/期权稀释 | 6 | 股数口径统一 |
| W10.4 | 卖出规则 | 8 | 有明确触发条件 |

### W11 重建与回放（≈12 人日，第 34 周）

| ID | 工作 | 估时 | 验收 |
|---|---|---|---|
| W11.1 | `turtle rebuild --date` | 6 | 重算并重发站点 |
| W11.2 | 34 个 release 批量重算 | 4 | 口径变更可追溯 |
| W11.3 | 回滚演练 | 2 | 5 分钟内回滚 |

**合计 412 人日 + 30% 缓冲 ≈ 536 人日**（单人全职约 24 个月；每天 4 小时有效投入约 4 年）。这个数字本身就是一个结论：**不可能“先做完再上线”，只能按波次交付、每波可用**。

## 5. 波次与日历

| 波次 | 周 | 内容 | 出口条件 |
|---|---|---|---|
| Wave 0 | 1–3 | W0 全部 | ranking/report 一致；drift 可见 |
| Wave 1 | 4–9 | W1 缓存/PDF/母公司 + W2.0/2.5 | 首跑 <40 分钟；旧快照可读 |
| Wave 2 | 10–13 | W2 + W5.1/5.3 | 数字可追 source class |
| Wave 3 | 14–22 | W3 + W4 | 研究深度与四角色契约 |
| Wave 4 | 23–28 | W5 + W6 | 质量门与 golden |
| Wave 5 | 29–33 | W7 + W10 | 报告分章、方法论 |
| Wave 6 | 34–36 | W8/W9/W11 + US（W1.6） | 产品与工程收尾 |

规则：**每波结束必须发布一次，不允许长期在分支上**；US 轨道（W1.6）随时可插入，但不得阻塞 A/HK。

## 6. 风险登记册

| 风险 | 触发 | 缓解 |
|---|---|---|
| 口径变更改历史结论 | 改 payout/market_cap | 基线 diff + `metric_version` + 不重算历史 |
| LLM 成本失控 | 四角色上线 | ADR-06 预算/降级；先测一周 |
| PDF 版式不收敛 | 新品种 | 只承诺 10 种版式；其余降级 unknown |
| golden 被批量重生成 | CI 失败时 | ADR-11 协议 + 单独提交 |
| 质量门收紧导致可用性下降 | 硬门上线 | 先 WARN 两周再 FAIL |
| 单人排期过长 | 每波超期 | 按波次交付，允许“设计完成、实现排队” |
| 数据授权/费用 | US/PIT | 先确认取数边界再动工 |

## 7. 完成判据与指标

| 指标 | 阈值 | 采集 |
|---|---|---|
| numeric coverage=1.0 的报告占比 | ≥95% | QA |
| 跨产物 payout/margin 偏差 >0.5pp | 0 | QA |
| 研究回退率 | <10% | status.json |
| 无证据结论变更 | ≤1/日 | verdict_history |
| 每 claim 一手来源比例 | ≥50% | research-audit |
| 首跑耗时 | <40 分钟 | status.json |
| golden diff 失败 | 0 未解释 | CI |

## 8. 第 0 周 checklist

1. 冻结基线：写并运行 `tmp/freeze_baseline.py --date 2026-11-10`（首次先建脚本）
2. 写 `metrics/payout.py` + 单测（含 01513/02877/00220/00270 四个回归样例）
3. 改 screener/report 调用点，跑 `pytest tests/test_hk_screen.py tests/test_report_consistency.py`
4. 加 QA 两行（cross_product_consistency、research_fallback_rate）
5. 用 11-10 数据重跑 40 只，diff 基线，解释每一处结论变化
6. 维护文档索引（已完成：`target-architecture.md` §13 与 README 均已链接本文）

## 9. 与原设计验收的映射

| 原设计承诺 | 由谁关闭 |
|---|---|
| 数字 100% 可解析 | W2.1 + W5.1 + W6.1 |
| claim 100% 有证据 | W3.2 + W5.2 |
| 同一 snapshot 可复现 | ADR-08 + W2.5 |
| Agent 层可关闭 | 现状已满足 + W4 保留单角色回退 |
| period/annualized 可见 | W2.3 + ADR-09 |
| 三类审计可定位 | W5.1/5.2/5.3 |
| fake-LLM 契约 | W4.3 |
| US/PIT/中报覆盖 | W1.5/W1.6/W2.3 |
