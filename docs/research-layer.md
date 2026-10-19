# 研究层扩展路线

## 目标

在不放弃确定性数字内核的前提下，增加 v2 式 D1–D6 深度研究：

```text
Facts → Metrics → Decisions → Claims/Params → Composer → Gates
```

LLM 只写 ResearchDocument（claims/params/decisions），不写最终报告数字。

## Phase 1（已完成）

- `ResearchClaim`：D1–D6，非 unknown 必须有 evidence。
- `ResearchParam`：研究参数，值只允许 `{{metric:id}}` / `{{fact:id}}`。
- `ResearchDecision`：`selected` 必须属于 `candidates`，不允许自造数值。
- `render_markdown`：渲染 claims + params + decisions，并解析 metric/fact。
- PDF `document_facts` 注入 `{{fact:id}}`。
- QA 增加 `research` 行：加载/校验 research.json。

## Phase 2（已完成）

- `pdf-evidence`：从 `pdf_sections.json` 生成页级 `evidence.json`（section/page/quote/confidence/document_hash）。
- `pdf_sections.json` metadata 增加 `section_pages`。
- `report --evidence evidence.json` 将 section fact 注入 `{{fact:...}}`。
- claim 可绑定 `pdf:section:MDA` / `P4` / `SUB` 等，报告显示页号与引文。
- `ResearchParam` / `ResearchDecision` 已完成契约与校验；engine 接入留在 Phase 3。

## Phase 3（完成）：方法深度

- G 网格、M 三法、AA 变体、税档、悲观情景 k 已预计算为 Decision candidates。
- engine 已读取 `decisions`：
  - `g` 必须属于 G 网格；
  - `payout` 必须属于支付率候选；
  - `aa` 必须属于 AA 变体；
  - `tax` 必须属于税档情景；
  - `scenario` 必须属于 0.9/0.8/0.7；
  - 非法选择直接报错，不静默回退。
- 默认无 Decision 时保持原确定性路径。
- 报告研究决策表显示完整 candidates / selected / reason。

## Phase 4（部分完成）：数据覆盖

- 新增 `sec-audit`：用 SEC companyfacts 独立复核美股年表，不覆盖本地数据。
- 新增 SEC statement fallback：yfinance 美股报表为空时，用 SEC companyfacts 生成 `StatementRow`。
- 支持 revenue / net_income / operating profit / assets / equity / cash / debt / goodwill / OCF / capex / D&A / SBC。
- 新增 HK PDF evidence：`pdf:holder:<name>`、`pdf:segment:<name>`，带 P4/MDA 页号。
- SEC evidence 增加 `dividend_per_share` / `dividends_paid` / `shares_outstanding`。

## Phase 5（部分完成）：LLM / Agent

- 新增 `OpenAICompatibleLLM`（transport 可注入，测试不联网）。
- 新增 D1–D6 专用 system prompt：业务/护城河/外部/管理层/MD&A/控股。
- 新增 `research-agent --snapshot --out`：用 LLM 生成 `research.json`，再由 `load_payload` 校验。
- snapshot 有 `pdf_sections.json` / `data_pack.md` / `evidence.json` 时自动注入上下文。
- `agent` phase runner 可执行 `research=research-agent ...`。
- 仍待补：真实 LLM 输出回归、重试/成本预算。

## Phase 6（部分完成）：claim-level audit

- 新增 `coverage` 能力矩阵，data pack 第 16 段显示 available/partial/missing。
- Thesis Card 支持 `thesis.*` params 表格（核心论点/催化/风险等）。
- 新增 DSH 原生路径：
  - `.agents/skills/turtle-research/SKILL.md`
  - `.claude/commands/turtle-research.md`
  - `research-context` 导出 snapshot 上下文；
  - DSH 模型直接写 `research.json`，项目负责 validator/gate，不需要项目持有 API key。
- `research-agent --response`：离线回放 LLM JSON，用于 eval/回归，不发网络请求。
- `research-agent --min-claims/--min-dimensions`：不足时把反馈加入 prompt 重试。
- `qa` 增加 `research_quality` 和 `data_coverage`：显示研究覆盖和缺失数据能力。
- `qa` 增加 `research_refs` 行：用 snapshot 的 metrics/evidence 复算引用。
- 未解析 metric/fact、非 unknown 无证据、非法 decision 均失败。
- 报告支持 `--html` 同时输出 HTML（D1–D6 章节/证据表可直接渲染）。
- 仍待补：行业/竞对独立章节、claim 覆盖率统计。

## 红线

1. 报告数字只能来自 Metric/DocumentFact。
2. LLM 不能写最终报告。
3. Decision 只能从预计算候选选。
4. 非 unknown claim 必须有 evidence。
5. snapshot 记录 research/claims/decisions hash。
