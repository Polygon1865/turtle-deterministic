# Phase 2：年报获取与解析

目标：拿到 PDF、定位 7 个章节、抽出可审计的文档数字。

## 步骤

1. **找 PDF（WebSearch）**，来源优先级：
   `static.cninfo.com.cn` > 上交所/深交所官网 > `www1.hkexnews.hk` > 雪球/同花顺。
   只接受 `.pdf` 链接；不要凭记忆构造 URL。

2. **下载**：

```powershell
python -m turtlefw.cli fetch-report --url "<PDF_URL>" --stock-code <数字代码> `
  --report-type 年报 --year <年份> --save-dir .runs/<标准化代码>
```

3. **解析章节**：

```powershell
python -m turtlefw.cli pdf --pdf .runs/<code>/<file>.pdf `
  --output .runs/<code>/pdf_sections.json --verbose
```

3b. **页级索引（供深度研究上下文）**：

```powershell
python -m turtlefw.cli pdf-index --pdf .runs/<code>/<file>.pdf `
  --output .runs/<code>/pdf_index.json
```

4. **结构化附注表格**：

```powershell
python -m turtlefw.cli pdf-footnotes --sections .runs/<code>/pdf_sections.json `
  --output .runs/<code>/footnotes.json
```

输出每个章节的 `pages/tables/text_excerpt`；P3/P4/P6 的账龄、关联方、或有负债表可直接引用，
但表头语义仍需 Agent 结合上下文判断。

5. **自动抽取审计数字**：

```powershell
python -m turtlefw.cli pdf-numbers --pdf .runs/<code>/<file>.pdf `
  --year <年份> --report-type 年报 --output .runs/<code>/reported_numbers.json
```

默认抽取 6 项：`revenue/net_income/ocf/capex/equity/total_assets`。港股年报还会附带
`cash_bridge`（净利润→D&A→营运资本→经营产生现金→税→OCF→Capex）。必须人工复核
`value/page/confidence`；抽取为空或页面对不上时，再按下面的手工格式补录：

```json
{"items":[{"item":"revenue","value":"115931000000","source":"2025年报","page":"p.12"}]}
```

6. **用 PDF 数字重跑数据包/报告**：

```powershell
python -m turtlefw.cli pack <code> --pdf-numbers .runs/<code>/reported_numbers.json
python -m turtlefw.cli report <code> --pdf-numbers .runs/<code>/reported_numbers.json
```

港股有 `cash_bridge` 时，报告 AA 会标为 `PDF间接现金桥`；这是间接法，**不是**
直接法毛利收现/付现桥。

7. **交叉审计**：

```powershell
python -m turtlefw.cli audit <code> --doc reported_numbers.json --threshold 1 `
  --write .runs/<code>/qualitative.json
```

## 验收

- PDF 通过 `%PDF-` 校验；
- `pdf_sections.json` 至少命中 4/7（P2/P3/P4/P6/P13/MDA/SUB）；
- 审计命令返回 0。

## 失败处理

| 情况 | 处理 |
|:---|:---|
| 找不到 PDF | 跳过，state 记 warning，进入 Phase 3 用无 PDF 模式 |
| 章节命中 <4 | 记 warning，定性证据主要依赖网页 |
| 数字冲突 | 由 audit 写入 discrepancies，不覆盖 CLI |

## 状态更新

```powershell
python -m turtlefw.cli state <code> --phase report_pdf `
  --artifact pdf=.runs/<code>/<file>.pdf `
  --artifact pdf_sections=.runs/<code>/pdf_sections.json
```
