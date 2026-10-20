# 600941 `/turtle-full` 只读审查

审查对象：`session-4776ff7f-f3bb-4778-b9a2-7474c7d7c07c`
审查时间：2026-10-20 08:58 HKT
审查方式：只读检查会话事件、`.runs/600941.SH` 与源码工作区；未重跑写数据的命令，未向原会话发送消息。

---

## 结论

这次 `/turtle-full 600941 --rf 1.6516` **行为上完成了**：

- deterministic `run` 完成；
- research 完成（11 claims / D1–D6 / 17 evidence / 4 params）；
- research audit 曾通过；
- provenance 与 research hash 一致；
- `finalize --strict` 完成；
- QA 12 项 PASS；
- numeric coverage `1.0`。

但它**不是干净可复现的完成**：

1. 工作区有 4 个**未提交源码修改**，是本次流程中临时修的框架缺陷；
2. `research_audit.json` 被主动删除，最终 snapshot 缺少审计 artifact；
3. `run_state` 没有记录 snapshot/research artifact；
4. `qualitative.json` 缺失，QA 通过的是 `--allow-missing-qualitative`，报告 1A/1B 仍是“未验证”；
5. 报告有一个轻微重复标题。

**判断：条件通过。**
流程本身可用，但在提交/清理这些改动前，不能把结果视为从当前 HEAD 可复现的正式交付。

---

## 修复状态

审查后已应用以下修复：

| 问题 | 状态 |
|:--|:--|
| 4 个未提交框架修复 | 已保留并纳入本次改动 |
| `research_audit.json` 缺失 | `finalize` 现在自动生成并写入 `snapshot_final`，manifest 记录 `research_audit_hash` |
| `run_state` 不记录 artifact | `run` / `finalize` 现在写入 `snapshot_id` 及 snapshot/report/research/audit/provenance |
| `qualitative` 语义不清 | QA 标记为 `research-only；1A/1B 未验证`，文档/skill 明确 full 不包含 PDF/定性 |
| 重复“研究摘要”标题 | 已移除 summary 的重复粗体标题 |
| `facts=0` | 保留为 `metric-only` 提示，不再隐藏；当前 600941 确实只有 metric refs |

修复后 600941 重新 finalize/QA：

```text
QA 13 项 PASS
research_audit: status=pass claims=11 dimensions=6
numeric_coverage: recomputed=1.0000 manifest=1.0 unknown=0
research_refs: metrics=12 facts=0 errors=0（metric-only）
```

验证：

```text
344 tests passed
ruff src: pass
mypy 相关模块: pass
```

注意：旧目录 `.runs/600941.SH/snapshot_final` 是修复前产物；修复后验证产物为
`.runs/600941.SH/snapshot_final_fixed`。正式交付前应删除或归档旧目录。

---

---

## 一、执行时间线

| 时间（HKT） | 事件 | 结果 |
|:--|:--|:--|
| 08:45:02 | 新会话创建 | `session-4776...` |
| 08:45:09 | 输入 `/turtle-full 600941 --rf 1.6516` | 开始 |
| 08:45:13–08:45:18 | 读取 `.claude/commands/turtle-full.md`、README、turtle-full skill | 入口说明 |
| 08:48:41 | `run 600941 --rf 1.6516 --no-qa` 开始 | 单次取数 |
| 08:48:42 | run 完成 | snapshot + data pack + report |
| 08:48:46 | research-context 生成 | 上下文 |
| 08:50:12–08:52:26 | 写/修 research.json | 11 claims |
| 08:52:39 | research-audit | pass |
| 08:52:41 | 删除 `research_audit.json` 和旧 `snapshot_final` | 审计 artifact 丢失 |
| 08:52:44 | finalize --strict --html | snapshot_final |
| 08:52:46 | QA --write --allow-missing-qualitative | 12 PASS |
| 08:53:18 | 最终汇总 | 结论：排除 |

---

## 二、阶段检查

| 阶段 | 状态 | 证据 |
|:--|:--|:--|
| `run` | 完成 | `.runs/600941.SH/snapshot` |
| data pack | 完成 | `.runs/600941.SH/data_pack.md` |
| research-context | 完成 | `snapshot/research_context.json` |
| research.json | 完成 | 11 claims / 6 dims / 17 evidence / 4 params |
| research audit | 曾 pass，artifact 缺失 | 会话 seq 913 报告 pass，但文件被删 |
| provenance | 完成 | `snapshot/research_provenance.json` |
| finalize | 完成 | `snapshot_final` |
| QA | 12 项 PASS | `qa.json` |
| 定性/PDF | 未执行 | 1A/1B 未验证 |

关键产物：

```text
.runs/600941.SH/
├─ analysis_report.md              26,086 bytes
├─ analysis_report.html            32,567 bytes
├─ research.json                   12,651 bytes
├─ research_provenance.json
├─ qa.json                         12 rows, status=pass
├─ snapshot/
└─ snapshot_final/
```

`snapshot_final/manifest.json`：

```text
numeric_status: pass
numeric_coverage: 1.0
research_hash == provenance.research_sha256
report_hash == analysis_report.md sha256
```

---

## 三、问题清单

### P0：工作区存在未提交的框架修改

本次流程为了让 600941 通过，修改了：

```text
src/turtlefw/metrics/registry.py
src/turtlefw/numeric_audit.py
src/turtlefw/report/snapshot.py
tests/test_numeric_audit.py
```

`git status` 仍显示这些文件为 modified，未提交。

#### 1. `metrics/registry.py`

原代码在 latest 指标显示时误用了循环残留变量：

```python
coverage="ok" if value is not None else "missing",
display=_display(False, value),
```

改为：

```python
coverage="ok" if period_value is not None else "missing",
display=_display(False, period_value),
```

这是真实缺陷：`revenue/net_income/capex/ocf/equity.latest` 可能显示错误值（如全部 `15.00`）。

#### 2. `report/snapshot.py`

research 占位符以前使用临时 `metric_map`，导致：

- `底价—元`
- 百分比丢 `%`（如 `59.98`、`45.07`、`3.42`）

修复方式：在渲染 research 前先用同一 `render_analysis` 生成 registry display，再解析占位符。

#### 3. `numeric_audit.py`

research 覆盖统计会输出：

```text
claims：11
params：4
decisions：0
evidence：17
```

numeric audit 严格模式原来把这些派生计数当未知数字。修复方式：把 `research.json` 的集合长度视为可追溯，并加测试。

#### 影响

- 这次的 `snapshot_final` 依赖未提交代码；
- 从当前 HEAD `976d70e` 无法复现同一结果；
- 会话自称 “343 tests passed”，但当前 HEAD 的测试基线是 342；未提交测试增加了 1 项；
- 这些修复需要单独审查、提交，不能留在 dirty worktree。

**建议：**

1. 单独提交这 4 个文件；
2. 提交前审查 `numeric_audit` 的“结构计数可追溯”是否过宽；
3. 从干净 commit 重新跑一次 600941，确认结果一致；
4. 若不想接受这些修复，则回滚并修复报告显示，而不是让 full 依赖 dirty code。

---

### P1：`research_audit.json` 被删除

会话 seq 910 生成：

```text
.runs/600941.SH/snapshot/research_audit.json
```

seq 913 报告：

```text
audit status: pass claims=11 dims=6 evidence=17 errors=0
```

但 seq 917 又执行：

```text
Remove-Item .../research_audit.json
```

最终：

```text
snapshot/research_audit.json       不存在
snapshot_final/research_audit.json 不存在
```

QA 只有 `research_refs` / `research_quality` 行，没有 audit artifact。

**影响：**

- 无法离线复核当时 audit 的 errors/quality 详细结果；
- 只能依赖 QA 聚合行和会话记录；
- 与“artifact 可审计”的目标不一致。

**建议：**

- 保留 `research_audit.json` 到 `snapshot_final`；
- 把它加入 finalize 的 artifact 列表；
- QA 增加 `research_audit` 行或检查该文件 hash。

---

### P1：`run_state` 没有记录 snapshot/research

当前：

```json
{
  "phase": "done",
  "snapshot_id": null,
  "artifacts": {},
  "warnings": []
}
```

实际已有：

```text
snapshot/snapshot_id = 按 manifest
snapshot_final/snapshot_id
research.json
research_provenance.json
```

**影响：**

- 状态文件无法告诉后续会话最终 snapshot 是哪一个；
- `run_state` 只表示“done”，不表示“用了哪个 research/snapshot”；
- 中断恢复和审计会依赖目录猜测。

**建议：**

- `run` / `finalize` 自动写入：
  - `snapshot_id`
  - `snapshot` 路径
  - `research` 路径
  - `research_provenance` 路径
- 或在 `turtle-full` skill 中显式 `state --artifact`。

---

### P1：QA 通过但 `qualitative.json` 缺失

`qa.json`：

```text
qualitative | PASS | 未提供（确定性/研究流程）
```

`analysis_report.md` 中：

```text
因子 1A：未验证
因子 1B：未验证
```

这不是 bug，是 `/turtle-full` 的设计边界：

```text
/turtle-full = deterministic + D1-D6 research
不是 PDF/定性 Agent 全流程
```

但“12 项 QA 全 PASS”容易被误读为完整分析。
**建议：**

- 在 README/CLI 输出中明确标注 `research-only`；
- 或在最终汇总中写明“未执行 qualitative/PDF，1A/1B 未验证”；
- 不要把 `/turtle-full` 与 `/turtle-analysis` 混称为完整分析。

---

### P2：报告重复“研究摘要”标题

报告实际：

```text
line 23: ## 研究摘要
line 25: **研究摘要**
```

`analysis_summary` 模板已有标题，`summary_markdown` 又输出粗体标题。

**建议：**

- `summary_markdown` 去掉首行 `**研究摘要**`，或模板不再加 `##`。

---

### P2：`research_refs facts=0`

QA：

```text
research_refs | metrics=12 facts=0
```

研究只引用了 metric 占位符，没有 `{{fact:...}}`。
这不算失败，但意味着：

- PDF/SEC structured fact 未进入 claims；
- 研究证据主要是外部 URL，而非 snapshot fact。

**建议：**

- 如果希望 D1–D6 与 PDF/SEC fact 绑定，补充至少一条 `{{fact:...}}`；
- 或者在 QA 中区分“metric-only research”，避免看起来像事实层全覆盖。

---

### P2：`/turtle-full` 在 DSH 是 handoff，不是完全自动

DSH 的命令入口实际执行：

```text
确定性 run --no-qa
→ 返回下一条提示，要求使用 turtle-full skill
```

模型写 research、audit、finalize、QA 仍由 Agent 后续执行。
这不是本次 600941 的问题，但入口语义应在 README 说明：

- `/turtle-full` ≠ 完全由 CLI 自动完成；
- 它是“确定性启动 + Agent handoff”。

---

## 四、做得好的部分

- `run` 使用 `.runs`，没有再次卡在 `output/` 权限；
- 单次取数得到 data pack + report + snapshot；
- 11 claims 覆盖 D1–D6；
- 17 条 evidence 有 URL + quote；
- research audit 曾 pass；
- provenance hash 与 research/snapshot manifest 一致；
- finalize 没有重新取数；
- final report/QA numeric coverage 1.0；
- QA 12 项 pass。

---

## 五、修复优先级

| 优先级 | 动作 |
|:--|:--|
| P0 | 审查并提交 4 个未提交框架修改；从干净 commit 复跑 600941 |
| P1 | 保留 `research_audit.json` 到 snapshot_final |
| P1 | `run_state` 写入 snapshot/research artifact |
| P1 | 明确 `/turtle-full` 是 research-only，不包含 qualitative/PDF |
| P2 | 修复重复“研究摘要”标题 |
| P2 | 决定是否需要 fact-backed research |

---

## 六、验收标准

修复后应满足：

```text
git status --short 为空
343 tests passed（或更新为真实数量）
snapshot_final/research_audit.json 存在
run_state.snapshot_id 非空
run_state.artifacts 包含 research/snapshot
qa.json 的 research_provenance/research_quality/numeric_coverage 均 PASS
从干净 commit 重跑 600941 结果一致
```

---

## 七、只读边界

本次审查：

- 未修改 `.runs/600941.SH`；
- 未重跑 `run/finalize/qa`；
- 未向 `session-4776...` 发送消息；
- 未修改源码；
- 只新增本报告文件。
