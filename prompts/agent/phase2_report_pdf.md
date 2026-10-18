# Phase 2：年报获取与解析

目标：拿到 PDF、定位 7 个章节、抽出可审计的文档数字。

## 步骤

1. **找 PDF（WebSearch）**，来源优先级：
   `static.cninfo.com.cn` > 上交所/深交所官网 > `www1.hkexnews.hk` > 雪球/同花顺。
   只接受 `.pdf` 链接；不要凭记忆构造 URL。

2. **下载**：

```powershell
python -m turtlefw.cli fetch-report --url "<PDF_URL>" --stock-code <数字代码> `
  --report-type 年报 --year <年份> --save-dir output/<标准化代码>
```

3. **解析**：

```powershell
python -m turtlefw.cli pdf --pdf output/<code>/<file>.pdf `
  --output output/<code>/pdf_sections.json --verbose
```

4. **抽文档数字**（reported_numbers.json，单位元，只抄合并报表）：

```json
{"items":[{"item":"revenue","value":"115931000000","source":"2025年报","page":"p.12"}]}
```

可用 item：`revenue/net_income/ocf/capex/equity/total_assets`。

5. **交叉审计**：

```powershell
python -m turtlefw.cli audit <code> --doc reported_numbers.json --threshold 1 `
  --write output/<code>/qualitative.json
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
  --artifact pdf=output/<code>/<file>.pdf `
  --artifact pdf_sections=output/<code>/pdf_sections.json
```
