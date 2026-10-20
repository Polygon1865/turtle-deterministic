# Phase 4：叙述与报告

目标：在 CLI 报告之上写一段人类可读的叙述，**不引入任何新数字**。

## 输入（只读）

- `.runs/<code>/analysis_report.md`（CLI 生成，结论与指标）
- `.runs/<code>/data_pack.md`（数据包）
- `.runs/<code>/qualitative.json`（定性判断与证据）
- 若 Phase 2 产出了 `reported_numbers.json`，先重跑确定性报告并传入 PDF 数字，同时冻结 snapshot：
  `python -m turtlefw.cli report <code> --pdf-numbers .runs/<code>/reported_numbers.json --save-snapshot .runs/<code>/snapshot`
- 若无 PDF 数字，也必须冻结 snapshot：
  `python -m turtlefw.cli report <code> --save-snapshot .runs/<code>/snapshot`

## 结构（固定）

```markdown
## 结论
一句话结论，注明是买入/观察/排除及首要原因。

## 关键指标
只列 CLI 已有的数字（R、GG、II、安全边际、底价溢价）。

## 依据
2–4 条：估值、现金流、分红、定性判断（引用证据链接）。

## 风险与未验证
数字冲突、unknown 模块、数据缺口。

## 下一步
需要补的数据或需要跟踪的事件。
```

## 规则

1. 叙述中每个数字必须能在上述三个文件中找到；不得四则运算、不得换算单位、不得补零；
2. 不改变 CLI 结论，也不新增仓位建议；
3. 定性判断只能引用 `qualitative.json` 中已有的 judgment；
4. 长度控制在 500 字以内，不堆砌指标；
5. 不重复 CLI 报告里的 Thesis Card/止损表；叙述只解释"为什么"，执行条件以 CLI 报告为准。

## 校验

```powershell
python -m turtlefw.cli narrative <code> --file .runs/<code>/narrative.md
```

- 报出"无法追溯的数字"：删掉该数字或回到 CLI 产物里找依据，**不许改报告去迁就叙述**；
- 通过后更新状态：

```powershell
python -m turtlefw.cli state <code> --phase report `
  --artifact narrative=.runs/<code>/narrative.md
```
