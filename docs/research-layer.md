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

## Phase 3（部分完成）：方法深度

- G 网格、M 三法、AA 变体、税档已预计算为 Decision candidates。
- engine 已读取 `decisions`：
  - `g` 必须属于 G 网格；
  - `payout` 必须属于支付率候选；
  - `aa` 必须属于 AA 变体；
  - `tax` 必须属于税档情景；
  - 非法选择直接报错，不静默回退。
- 默认无 Decision 时保持原确定性路径。
- 仍待补：λ/k* 作为显式 Decision、完整候选表展示。

## Phase 4：数据覆盖

- US SEC；港股母公司/股东/分部；质押/回购；PIT 历史。
- 先补数据契约，再补报告章节。

## Phase 5（部分完成）：LLM / Agent

- 新增 `OpenAICompatibleLLM`（transport 可注入，测试不联网）。
- 新增 `research-agent --snapshot --out`：用 LLM 生成 `research.json`，再由 `load_payload` 校验。
- `agent` phase runner 可执行 `research=research-agent ...`。
- 仍待补：真实 D1–D6 prompt 模板、重试/成本预算、LLM 输出质量回归。

## Phase 6（部分完成）：claim-level audit

- `research-audit`：校验 claim/param/decision 的 metric/fact 占位符。
- `qa` 增加 `research_refs` 行：用 snapshot 的 metrics/evidence 复算引用。
- 未解析 metric/fact、非 unknown 无证据、非法 decision 均失败。
- 仍待补：报告章节深度、HTML、claim 覆盖率统计。

## 红线

1. 报告数字只能来自 Metric/DocumentFact。
2. LLM 不能写最终报告。
3. Decision 只能从预计算候选选。
4. 非 unknown claim 必须有 evidence。
5. snapshot 记录 research/claims/decisions hash。
