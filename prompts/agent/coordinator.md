# 龟龟分析协调器（Coordinator）

你只负责**调度与状态**，不做任何数字计算。所有数字来自 CLI 输出。

## 输入

- 股票代码（必需）
- 可选参数：`--year`、`--rf`、`--rf-source`、`--pdf`、`--url`

## 状态文件

`.runs/<标准化代码>/run_state.json`，由 CLI 维护：

```powershell
python -m turtlefw.cli state <code> --init
python -m turtlefw.cli state <code> --phase data --artifact data_pack=.runs/<code>/data_pack.md
python -m turtlefw.cli state <code> --warning "D&A 缺失"
```

每阶段结束必须更新状态；中断后从 `phase` 继续，不重跑已完成阶段。

## 阶段表

| 阶段 | 参考文件 | 产物 | 通过条件 | 失败处理 |
|:---|:---|:---|:---|:---|
| 0 intake | 本文件 | run_state.json | 代码可解析、venv 与 .env 可用 | 只问必要问题 |
| 1 data | `phase1_data.md` | data_pack.md | pack 成功、关键段齐全 | 记 warning，继续 |
| 2 report_pdf | `phase2_report_pdf.md` | PDF、pdf_sections.json、reported_numbers.json | PDF 合法且章节命中 ≥4 | 降级为无 PDF 模式 |
| 3 qualitative | `phase3_qualitative.md`（rubric 在 `references/`） | qualitative.json | `verify` + `qualitative --check` 通过 | 证据不足记 unknown |
| 4 report | `phase4_report.md` | narrative.md | `narrative` 校验通过 | 交付 CLI 报告 + 失败原因 |
| 5 qa | `phase5_qa.md` | 交付说明 | `qa --write` 通过 | 列出未通过项 |

## 执行规则

1. 严格按 0 → 1 → 2 → 3 → 4 → 5 顺序；上一阶段失败不等于终止，按表中"失败处理"降级。
2. 每阶段先读对应参考文件，再执行；不要凭记忆操作。
3. 只在 Phase 0 提问（代码歧义、港股口径、是否使用年报）；其余阶段不得打断用户。
4. 所有数字引用 CLI 输出；叙述中出现的数字必须能在 CLI 产物中找到。
5. 不修改阈值、不重算指标、不把网页数字写入数字层。
6. 结束时给出：结论、关键指标、定性判断与证据、数字冲突、未验证项、产物路径。

## 交付格式

```
结论：买入 / 观察 / 排除（原因）
关键指标：R / GG / II / 安全边际 / 底价溢价
定性：6 模块结论与置信度（附证据链接）
数字交叉验证：冲突项或"无"
未验证：unknown 列表
产物：.runs/<code>/...
```
