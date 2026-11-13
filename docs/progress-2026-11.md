# 项目改进进展（2026-11）

本文件记录 `docs/roadmap-2026-11.md` 的 T → C → M 执行进度。每一轮结束时更新：做了什么、证据在哪、还差什么。

## T 段（承诺范围，约 22 人日）

| 项 | 状态 | 产物与证据 |
|---|---|---|
| T1 基线冻结 + golden | ✅ 完成 | `scripts/golden.py`（`freeze` / `check`）；基线 `tests/fixtures/golden-daily-2026-11-10.json`（40 只，24.7KB）；测试 `tests/test_golden_baseline.py`（7 例）。现状：`check --date 2026-11-10` 返回一致。 |
| T2 口径单一源 | ✅ 完成 | 新增 `src/turtlefw/metrics/payout.py`（`vendor_ratio` / `dps_ratio` / `events_ratio` / `resolve` / `agree`）；`normalize.py` 与 `screener/hk.py` 共用同一算术，修掉 140.84% 被写成 1.41% 的分歧。引擎新增 `payout.latest`（最新财年支付率，区别于报告展示的三年均值），QA 新增 `payout_consistency` 行（榜单 vs 报告最新年，容差 0.01）。测试：`tests/test_payout_single_source.py`（7 例）、`tests/test_qa_payout_consistency.py`（5 例）。端到端：00270 重渲染后 QA 输出 `榜单 66.97% = 报告 66.97%`。附带修掉 `report --snapshot --save-snapshot` 的 `UnboundLocalError`，改为明确拒绝并加测试 `tests/test_cli_report_guards.py`。 |
| T3 结论稳定性 | ✅ 完成 | ① `research_bridge._claim_in_scope`：D1 只有 `business_model/business_mix/revenue_mix/segment/product_mix/understand` 类 claim 能进入「看不懂」，业绩下滑不再触发 1A 否决；聚合仍用 negative 优先（范围正确后无需加权）。② `snapshot.render` 写 `snapshot/verdict.json`（verdict/reason/inputs_hash/research_hash/evidence_hash），QA 新增 `verdict_record` 行（缺记录、缺 evidence_hash、与报告结论不一致都 FAIL）。测试：`tests/test_research_bridge.py` 新增「营收下滑不等于看不懂」；`tests/test_qa.py` 新增 verdict_record 两例。回放证据：`tmp/t3_scope_check.py` 显示 11-04/11-06 legacy=negative→scoped=neutral；`tmp/replay_day.py` 用当前代码重渲染 11-04/11-06/11-09 全部为 **买入**（原 11-04/11-06 是排除）。 |
| T4 失败可见 | ✅ 完成 | ① QA 新增 `research_fallback_rate`：读当天 `status.json`，`fallback/off` 占比 >10% 即 **WARN**（不再是干净 PASS），并列出前 5 只；`qa.payload` 新增 `warn` 状态，`qa.warned()` 供测试/消费方使用，`daily.qa_status` 早已支持 WARN。② 站点首页新增「研究回退」统计（>0 时红色），`site.py` 把 WARN 计为通过、回退数单独暴露。测试：`tests/test_qa.py` 增「23/40 → WARN + payload warn」「2/40 → PASS」两例。 |
| T5 缓存冷启动 | ✅ 完成 | `src/turtlefw/paths.py` 新增 `cache_root(runs_root)`：优先 `TURTLE_CACHE_DIR`，否则 `runs_root.parent/.cache`（默认 `.runs/.cache`），**所有日期共用**；`TushareProvider` 默认走它；`run_daily` 在启动任何子进程前导出 `TURTLE_CACHE_DIR` 并记入 `status["cache_dir"]`。测试 `tests/test_cache_root.py`（4 例）。效果：新交易日不再从空缓存冷启动（2026-10-30 那次 30 分钟撞 `screen_timeout_seconds=1800` 的事故根因）。 |
| T6 lint 发布门 | ✅ 完成 | `src/turtlefw/daily.py` 新增 `_structural_failures()`：扫全部 stocks 的 `qa.json`，任一 `report_structure=FAIL` 即阻止发布，`status["site"]` 记 `blocked: report_structure failed (...)`，旧 release 保留（与 `publish_partial` 并列成第二道门）。测试 `tests/test_daily.py::test_run_daily_blocks_publish_on_report_structure_failure`（monkeypatch `build_site` 断言不被调用）。`docs/daily-server.md` 补缓存共享与发布门说明。 |

## C 段（按需队列）

| 项 | 状态 | 产物与证据 |
|---|---|---|
| C1 港股 PDF 版式泛化 | 🟡 提取器已改，语料受限 | 现实：日常流水线 `pdf` 字段 600/600 为 `none`，磁盘只有 11 份年报（A 股 10 只 + 腾讯 00700），没有"34 份港股 PDF"可用来验证"港股版式"。改 `src/turtlefw/pdf/extract.py`：① `_wrapped_label_match` 支持跨行标签、label/value 夹心、跨页标签缝合；② `_plausible_value` 拒绝把日期里的年份当数值；③ 资产负债表状态机（标题页开启、续页需带总计类标记、其他报表标题关闭、highlight 页不计入）；④ 银行「归属于本行股东权益」别名；⑤ BALANCE_ITEMS 在近优分数里取最早页，避免母公司报表覆盖合并报表。语料结果（11 份真实 PDF）：revenue/net_income/ocf/total_assets 11/11、equity 6→**10/11**、capex 6→**9/11**；`tests/test_pdf_gold.py` 11 例与新增 `tests/test_pdf_extract_layout.py` 6 例全过。残差：601398（工商银行）PDF 文本层稀薄（408 页、中位 830 字符），只出 5 项；两家银行无「购建固定资产…」行。 |
| C2 港股股东/主营 | ✅ 完成（数据源受限） | Tushare 无港股股东/分部接口（`hk_holders`/`hk_fina_mainbz` 均报「请指定正确的接口名」）；`TushareProvider.holders()` 对 HK 分派到 `_hk_holders()`，用 Yahoo `institutional_holders`+`mutualfund_holders` 归一为 `holder_name/hold_ratio/hold_amount/holder_type/as_of/source="yahoo"`（进程内缓存、失败降级空列表）；数据包第 8 节标题改「机构与基金持仓（Yahoo，第三方，可能滞后）」并附披露日期，`business_summary` 非空时输出「主营描述（行业）」段，两者都缺才显示「未接入」。测试 `tests/test_pack_hk_holders.py` 6 例（Yahoo 标注、A 股仍叫前十大股东、主营描述、空态、provider 归一化、Yahoo 失败降级）。边界：分部收入仍只有 PDF 路径，母公司现金保持「未验证」。 |
| C4 US 市场 | ✅ 实验路径可跑通（不承诺生产） | 用 `KO.US` 做端到端冒烟（`run KO.US --no-qa`），暴露并修掉两个会让美股路径直接崩溃/说谎的问题：① T3 的 `_verdict_record` 用 `json.dumps(inputs_to_dict(...))` 算 `inputs_hash`，美股 inputs 里含 `Decimal` → `TypeError: Object of type Decimal is not JSON serializable`；改为与 `freeze` 相同的 `default=str`（哈希语义一致）。② 报告头、数据包头/尾、Peer 注脚、`补充基本面（Tushare）`/`市场与宏观（Tushare）` 标题对美股全部谎称 Tushare；新增 `src/turtlefw/report/format.py:data_source_label(market)`，美股渲染「yfinance + SEC（实验）」、章节标题「yfinance 实验」。冒烟结果：快照 `771650eb42c16154948a1e3af9114e9f`、numeric coverage 1.0000、报告 10,889B、结论「排除」（R 1.66% / GG 0.75% / 门槛 5.00%）。测试 `tests/test_market_labels.py` 3 例、`tests/test_pit_filter.py` 7 例；golden 报告哈希更新为 `3da019ad…`（头部新增「数据源」行属预期变更）。边界：美股无 screener、不进 `daily`（`markets=["A","HK"]`）、无 10-K/10-Q 文件级 DocumentFact、股东/质押/回购/主营仍缺、yfinance 只有近 4 个财年且字段标签会变。 |
| C3 归档回放 / 前视审计 | ✅ 完成（无 vendor vintage，不伪造 PIT） | 新增 `src/turtlefw/backtest.py`：`lookahead_audit(snapshot_dir)` 检查快照内是否有 `ann_date > as_of` 的财务行，`load_panel(runs_root)` 汇总多日 verdict/metrics，`churn_rows` 统计结论翻转，`render_markdown`/`write_report` 出报告；CLI `backtest --runs-root --out --limit --json`；QA 新增 `pit_lookahead` 行（无快照 → PASS 并说明跳过）。真机回放（2026-10-22 → 11-10，15 天、600 行、92 只）：**14/92 只翻转过、共 48 次**，其中 000651（margin 极差 0.29pp）、03877（0.26）、01065（0.43）、00857（0.93）、06862（0.85）等翻转时估值数字几乎没动 —— 翻转来自研究层判断。**前视审计抓到 1 个违规快照**：`2026-10-28` 的 20 条财务行公告日晚于 `as_of=20261021`（如 `600729.SH balance.accounts_receiv ann_date=20261029`），说明该日 PIT 过滤未生效，已由 QA 门暴露。**已修摄入侧**：`src/turtlefw/report/snapshot.py` 新增 `filter_as_of_rows(rows, as_of)`（规范化 `20261029`/`2026-10-29`/`2026/10/29`，剔除 `ann_date > as_of` 的行，无公告日的行保留），`src/turtlefw/cli.py` 在建 `ReportInputs` 前调用并在有剔除时追加 `FetchIssue(endpoint="pit-filter")`。用真实的 2026-10-28 `600729.SH` 快照验证：1524 行 → 剔除 51 行 → `lookahead_audit` 由「20 条违规」变为「全部不晚于 as_of」。测试 `tests/test_backtest.py` 7 例、`tests/test_pit_filter.py` 7 例。边界：真 PIT 需 vendor 历史版本；港股行普遍无 `ann_date`，QA 记为「无法核验」而不是 clean。 |
| C5 四角色 Agent | ✅ 完成（可回退） | 按 ADR-05/06 新增 `src/turtlefw/agent/roles.py`（`RoleSpec` 四角色 + 工具白名单 + `ToolBox` 越权即抛 `ToolNotAllowed`；`validate_extraction` 校验 quote/URL 并补 `ev-N` id；`validate_research_draft`；`assemble_payload`；`estimate_tokens`）、`src/turtlefw/agent/budget.py`（`TokenBudget(limit=500_000)` + `BudgetExceeded`）、`src/turtlefw/agent/pipeline.py`（extractor→researcher→writer→auditor；writer/auditor 确定性；任何 `RoleError/BudgetExceeded/ValueError/KeyError/TypeError` 先回退单角色 `ResearchAgent`，预算耗尽则 `deterministic_only`，`reason` 落盘可见）。CLI `research-agent --roles` 走流水线，`usage.json` 记 `roles`。离线回放验证（06862 快照 + `--response`）：`四角色流水线：extractor → researcher → writer → auditor`，输出 16 claims / 3 params，与单角色一致。测试 `tests/test_agent_roles.py` 9 例（注册表、白名单越权、schema 校验、happy path、schema 失败回退、预算耗尽降级、预算计费）。边界：四角色仍共用同一 `research.json` schema；`--roles` 默认关闭（daily 未切）。 |
| C6 卖出规则 / 组合层 | ✅ 完成（软规则需连续确认） | 新增 `src/turtlefw/holdings.py`：`Holding`/`Snapshot`/`SellSignal`，五条确定性规则——`verdict_downgrade`（买入→观察/排除/减持）、`margin_lost`（margin<0）、`value_trap`（≥2 项）、`stop_loss`（相对买入价回撤超阈值）、`floor_break`（现价<底价，watch 不强制卖）；`snapshot_from_run()` 只读归档（`snapshot/metrics.json` + 报告首行 + `snapshot/verdict.json`），不调用数据源；`check()` 单日、`check_window(confirm=N)` 要求**软规则连续 N 天**成立才算卖出信号，硬规则（margin/trap/止损）立即触发。CLI `holdings --file --date --runs-root --strict --confirm`，示例 `configs/holdings.example.json`。回放证据（11-02 买入 03877/00270，9 个归档日）：单日口径 `verdict_downgrade` 触发 **4 次/4 天**（两只各被“卖出”两次又买回）；`--confirm 2` 后 **0 次**——证明单日结论翻转是噪声，卖出纪律必须带持续性。测试 `tests/test_holdings.py` 9 例。边界：持仓文件手工维护；不处理加仓/仓位再平衡；`stop_loss` 只按成本价算，不跟踪最高价。 |


## W 段（roadmap 前置）

| 项 | 状态 | 产物与证据 |
|---|---|---|
| W0.0 基线冻结 | ✅ 完成 | 新增 `scripts/freeze_baseline.py`：`collect(day_dir)` 汇总每只的 verdict/reason/r/gg/ii/margin/floor/price/qa/claims/params + 报告 sha256；`freeze(date)` 写 `baseline/summary-<date>.csv`、`hashes-<date>.json`、`meta-<date>.json`，并把报告/指标/qa 副本放到 `.runs/baseline/<date>/`（git-ignored）；`check(date)` 与基线 diff（数值列带 Δ，含新增/消失标的）。已冻结 `.runs/daily/2026-11-10`：40 只、`baseline/summary-2026-11-10.csv`（7,788B），自检 `check` 一致。测试 `tests/test_freeze_baseline.py` 5 例。 |
| W0.1 发布策略（ADR-04） | ✅ 完成（用户批准：默认关闭） | `DailyConfig.publish_partial` 默认 `False`；`configs/daily.toml` 改 `publish_partial = false`；`scripts/daily_pipeline.py` 新增 `--publish-partial`（`default=None`，显式放行）；被阻断时 `status.site` 记 `blocked: N failed; partial publishing disabled`。测试 `tests/test_publish_policy.py` 4 例（默认值、阻断、显式放行、CLI 覆盖）。 |
| W0.3 快照版本（ADR-08） | ✅ 完成（用户批准：只读归档、不迁移） | `verify_manifest` 在 `snapshot_version`/`formula_version` 不匹配时输出「旧版本快照为只读归档，不自动迁移；请保留原报告，或从原始数据重新生成快照」，不再只报裸 hash mismatch；`facts.py` 常量处补 ADR-08 语义注释。测试 `tests/test_snapshot_version.py` 3 例。 |
| W5.3 跨产物一致性审计 | ✅ 完成（第一切片） | `src/turtlefw/qa.py` 新增 QA 行 `report_consistency`：`_report_consistency_check(base, report)` 解析报告开头 80 行的 `\| 标签 \| 值 \|` 行，把 `粗算回报率 R/精算回报率 GG/门槛 II/安全边际/底价（综合）` 与 `snapshot/metrics.json` 的 `display` 逐字比对，并核对报告结论行、汇总表「结论」、`snapshot/verdict.json` 三者一致；不一致即 FAIL 并列出差异（最多 4 条）。真实样例（2026-11-10 / 00270.HK）：`report_consistency PASS 5 项数字/结论一致`。测试 `tests/test_qa_report_consistency.py` 5 例（一致、数字漂移、汇总表结论不符、verdict.json 不符、缺指标跳过）。 |
| W5.2 引用审计 | ✅ 完成（第一切片） | 新增 `src/turtlefw/citations.py`：`check_url`（非 http(s) 拒绝、2xx/3xx 通过、异常归为「请求失败」）、`audit_day`（扫 `*/snapshot/research.json`、7 天缓存到 `<day>/citations.json`、`--limit` 截断）、`summarize`；CLI `citations --date --runs-root --limit --timeout --max-age --out`；QA 行 `citation_audit` 只读缓存（缺失 PASS 并注明「未运行引用审计」，不可达 FAIL）。测试 `tests/test_citations.py` 10 例。实测：手动跑过的 `.runs/06862.HK`（18 条 URL）6/6 可达；而 `.runs/daily` 下 682 份 research.json 的 15,813 条证据里只有 84 条带 http URL（仅 4 天、全部是手工运行的 06862/00700 等），日常 LLM 研究证据全部是 `source_type=data` 且 `url` 为空——审计目前几乎无外部链接可查，这个「研究层不引用外部来源」是下一层缺口（W3.2 evidence grading）。 |

## 本轮验证

```
.\.venv\Scripts\python.exe -m pytest -o addopts= -q -p no:cacheprovider
→ 743 passed in 250.61s

# ADR-04 / ADR-08 决策落地
.\.venv\Scripts\python.exe -m pytest tests\test_publish_policy.py tests\test_snapshot_version.py tests\test_daily.py tests\test_snapshot.py -q
→ 60 passed

# W5.3 跨产物一致性
.\.venv\Scripts\python.exe -m pytest tests\test_qa_report_consistency.py tests\test_qa.py tests\test_qa_payout_consistency.py -q
→ 26 passed

# W5.2 引用审计（离线单测 + 真实网络）
.\.venv\Scripts\python.exe -m pytest tests\test_citations.py -q
→ 10 passed
.\.venv\Scripts\python.exe -m turtlefw.cli citations --date . --runs-root tmp/cit_demo --limit 8
→ 6 条引用全部可达（06862.HK 手工研究的 6 个 web 来源全部 HTTP 200）

.\.venv\Scripts\python.exe -m ruff check --select F401,F601,F841 src
→ All checks passed!

.\.venv\Scripts\python.exe -m ruff check --select F401,F601,F841 scripts\freeze_baseline.py tests\test_freeze_baseline.py
→ All checks passed!

.\.venv\Scripts\python.exe -m mypy src\turtlefw\report\format.py src\turtlefw\report\pack.py src\turtlefw\report\analysis.py src\turtlefw\report\snapshot.py src\turtlefw\backtest.py src\turtlefw\qa.py src\turtlefw\citations.py src\turtlefw\agent\pipeline.py src\turtlefw\agent\roles.py src\turtlefw\agent\budget.py src\turtlefw\agent\research_agent.py src\turtlefw\holdings.py
→ Success: no issues found（`cli.py` 15 条、`tushare_provider.py` 41 条为既存告警，CI 名单不含这两个文件）

.\.venv\Scripts\python.exe -m mypy scripts\freeze_baseline.py
→ Success: no issues found

# W0.0：冻结并自检 2026-11-10 运行
.\.venv\Scripts\python.exe scripts\freeze_baseline.py freeze --date 2026-11-10
→ 基线已冻结 2026-11-10：40 只 → baseline\summary-2026-11-10.csv
.\.venv\Scripts\python.exe scripts\freeze_baseline.py check --date 2026-11-10
→ 与基线一致：2026-11-10

# 聚焦：缓存共享 + 发布门
.\.venv\Scripts\python.exe -m pytest tests\test_cache_root.py tests\test_daily.py tests\test_cache_refresh.py -q
→ 38 passed

# C1：11 份真实年报的抽取覆盖（改前 → 改后）
.\.venv\Scripts\python.exe tmp\pdf_corpus.py
→ revenue/net_income/ocf/total_assets 11/11
→ equity 6/11 → 10/11（缺 601398）
→ capex  6/11 → 9/11（两家银行无该行）

# C2：港股数据包第 8 节（真实 06862.HK，Yahoo 持仓 + 主营描述）
.\.venv\Scripts\python.exe -m turtlefw.cli pack 06862.HK --out tmp\c2_pack.md
→ **机构与基金持仓（Yahoo，第三方，可能滞后）**（10 行，披露日期 2026-09-30）
→ **主营描述（Consumer Cyclical / Restaurants）**
→ 不再出现「未接入股东/主营数据。」

# C3：归档回放 + 前视审计（15 天）
.\.venv\Scripts\python.exe -m turtlefw.cli backtest --runs-root .runs/daily --out tmp\backtest.md --json
→ 归档 15 天 ｜ 样本 600 ｜ 翻转标的 14/92 ｜ 前视违规快照 1/15
→ 2026-10-28：20 条财务行 ann_date 晚于 as_of=20261021（600729.SH balance.accounts_receiv ann_date=20261029）

# C3 摄入修复：同一快照剔除未来公告行后不再违规
.\.venv\Scripts\python.exe tmp\pit_check.py
→ stock=600729.SH as_of=20261021 rows=1524
→ before: 20 条财务行公告日晚于 as_of
→ dropped=51 kept=1473
→ after: 1473 行公告日均不晚于 as_of，0 行缺公告日

# C4：美股端到端冒烟（KO.US，修掉 Decimal 崩溃与「谎称 Tushare」）
$env:TURTLE_OUTPUT_DIR='tmp\us_smoke'; .\.venv\Scripts\python.exe -m turtlefw.cli run KO.US --no-qa
→ snapshot_id: 771650eb42c16154948a1e3af9114e9f
→ numeric coverage (strict): 1.0000 ｜ pass ｜ unknown=0
→ 结论：排除（R 1.66% / GG 0.75% / 门槛 5.00%）
→ 报告头：数据源：yfinance + SEC（实验）
→ 章节标题：补充基本面（yfinance 实验）/ 市场与宏观（yfinance 实验）

# C5：四角色流水线离线回放（06862 快照，LLM 用 --response 回放）
.\.venv\Scripts\python.exe -m turtlefw.cli research-agent --snapshot .runs\06862.HK\snapshot --out tmp\roles_06862.json --roles --response .runs\06862.HK\snapshot\research.json
→ 四角色流水线：extractor → researcher → writer → auditor
→ research.json 已写入 …：16 claims，3 params，0 decisions

# C6：卖出规则回放（11-02 买入 03877/00270，9 个归档日）
.\.venv\Scripts\python.exe tmp\replay_holdings.py
→ days=9 triggered_days=4  rule_counts=verdict_downgrade=4
→ confirm=2 triggered_days=0 rule_counts=
→ 单日结论翻转会把两只持仓各“卖出”两次又买回；要求连续 2 天确认后不再误触发

.\.venv\Scripts\python.exe -m turtlefw.cli holdings --file configs\holdings.example.json --date 2026-11-10 --confirm 2
→ 检查窗口：2026-11-09 → 2026-11-10（软规则需连续 2 天）
→ 00270.HK：买入 ｜ margin 4.84 ｜ 价 8.30 / 底价 4.62 ｜ 无卖出信号
→ 03877.HK：买入 ｜ margin 7.34 ｜ 价 2.32 / 底价 0.95 ｜ 无卖出信号

# T2 端到端：榜单/报告同口径
.\.venv\Scripts\python.exe tmp\render_t2.py; TURTLE_OUTPUT_DIR=tmp\t2code .\.venv\Scripts\python.exe -m turtlefw.cli qa 00270.HK
→ payout_consistency | PASS | 榜单 66.97% = 报告 66.97%
→ verdict_record     | PASS | 买入 · evidence 01fe0a4d6f

# T3 回放：11-04/11-06 不再因 1A 翻转
.\.venv\Scripts\python.exe tmp\replay_day.py 2026-11-04 2026-11-06 2026-11-09
→ 三天全部 买入（改前 11-04、11-06 为排除）
```

> `mypy src/turtlefw/daily.py` 仍有 2 条既存告警（`prior` 重复定义、`Resuming` 返回 Any），
> 非本轮引入，CI 的 mypy 名单不含该文件；T5/T6 改动的 `paths.py` 无告警。

## 已知约束

- 沙箱禁止命令写入 `tests/`、`src/`、`docs/` 等目录；`golden.py freeze` 写 `tests/fixtures/` 需要一次提权，或改用 `--out tmp/...` 再由编辑工具落盘。脚本本身在正常环境无此限制。
- 基线文件只覆盖“结论 + 关键指标”，不覆盖排版；模板改动不应触发 golden 差异，结论或数字变化才触发。
