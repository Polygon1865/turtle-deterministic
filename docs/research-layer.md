# 研究层扩展路线（Phase 1 已完成）

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
- 测试：claims 裸数字、未知 evidence、非法 Decision、QA research。

## Phase 2（下一步）：PDF-first 证据

- 页级 `DocumentFact`：page / section / quote / table / confidence。
- D1–D6、MDA、SUB 分节提取。
- claim 绑定到 fact；报告显示页码与引文。
- numeric audit 覆盖 research claims。

## Phase 3：方法深度

- G 网格、M 三法、AA 变体、税档、λ/k*。
- 全部预计算为 Decision candidates。
- LLM 只选候选 + 理由；默认走确定性选择。

## Phase 4：数据覆盖

- US SEC；港股母公司/股东/分部；质押/回购；PIT 历史。
- 先补数据契约，再补报告章节。

## Phase 5：LLM/Agent

- 真实 LLM adapter；research phase 输出 ResearchDocument。
- phase runner：data → document → research → compose → audit。
- 无 LLM 时仍可产出确定性简版报告。

## 红线

1. 报告数字只能来自 Metric/DocumentFact。
2. LLM 不能写最终报告。
3. Decision 只能从预计算候选选。
4. 非 unknown claim 必须有 evidence。
5. snapshot 记录 research/claims/decisions hash。
