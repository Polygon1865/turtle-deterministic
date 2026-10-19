# Turtle Framework 使用说明

> 当前审查基线：`339 passed`。本文按当前 CLI 实测编写，命令使用
> `.\.venv\Scripts\python.exe -m turtlefw.cli`，避免依赖 PATH 里的 `turtle`。

## 1. 这个项目做什么

Turtle Framework 是一个**确定性基本面研究管线**：

```text
数据源
  → ReportInputs / StatementRow
  → 指标与因子（Python Decimal）
  → research.json（可选 D1–D6 claims/params/decisions）
  → analysis_report.md / HTML
  → snapshot / numeric audit / QA
```

三条硬规则：

1. **报告数字只能来自 Python 指标或 PDF/SEC fact**；
2. **LLM 只写 research.json，不写最终报告数字**；
3. **同一 snapshot 离线重渲染必须逐字节一致**。

---

## 2. 环境与安装

### 2.1 要求

- Python **3.11+**
- Windows 优先；macOS/Linux 也可用
- Tushare Pro token（A 股/港股主数据；没有 token 可用 `--demo`）
- 可选：`pdfplumber`（PDF）、`yfinance`（港股/美股行情）

### 2.2 Windows 一键初始化

```powershell
cd C:\PyProject\turtle-framework
pwsh -File scripts\init.ps1
```

`init.ps1` 会：

- 创建 `.venv`
- 安装 `.[dev,pdf,hk]`
- 检查 `.env` / `TUSHARE_TOKEN`
- 创建 `output/`
- 运行测试

### 2.3 手动安装

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,pdf,hk]"
```

### 2.4 配置 Tushare

```powershell
Copy-Item .env.sample .env
notepad .env
```

填写：

```text
TUSHARE_TOKEN=your_token_here
```

`config.py` 会自动加载 `.env`。不要把 token 提交到 Git。

### 2.5 验证

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli --version
.\.venv\Scripts\python.exe -m turtlefw.cli --help
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 600887 --demo
```

`--demo` 使用内置合成数据，不需要 token。

---

## 3. 输出目录

默认：

```text
output/<code>/
```

受限环境（例如 DSH workspace-write）建议：

```powershell
$env:TURTLE_OUTPUT_DIR = ".runs"
```

或全局参数：

```powershell
turtle --output-dir .runs report 600887
```

所有写运行产物的命令共用这个根目录：

```text
output/600887.SH/
├─ data_pack.md
├─ analysis_report.md
├─ analysis_report.html
├─ qualitative.json
├─ research.json
├─ pdf_sections.json
├─ evidence.json
├─ reported_numbers.json
├─ qa.json
└─ snapshot/
   ├─ manifest.json
   ├─ inputs.json
   ├─ metrics.json
   ├─ numeric_audit.json
   ├─ data_pack.md
   ├─ research.json
   └─ research_provenance.json
```

---

## 4. 五分钟入门

### 4.1 纯演示（无 token）

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 600887 --demo
```

### 4.2 A 股最小生产流程

```powershell
$env:TURTLE_OUTPUT_DIR = ".runs"

# 1. 数据包
.\.venv\Scripts\python.exe -m turtlefw.cli pack 600887.SH --rf 1.6516 --rf-source "ICBC 2026-10-15"

# 2. 确定性报告
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --rf 1.6516 --rf-source "ICBC 2026-10-15" --html

# 3. 冻结 snapshot
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --rf 1.6516 --rf-source "ICBC 2026-10-15" `
  --save-snapshot .runs\600887.SH\snapshot

# 4. 用 snapshot 离线复现
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --snapshot .runs\600887.SH\snapshot
```

### 4.3 看数据覆盖

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli coverage 600887.SH
.\.venv\Scripts\python.exe -m turtlefw.cli coverage 00700.HK
.\.venv\Scripts\python.exe -m turtlefw.cli coverage AAPL
```

状态：

```text
available / partial / pdf_optional / not_applicable / external / missing
```

---

## 5. A 股完整流程

### 5.1 pack

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli pack 600887.SH `
  --pdf-numbers output\600887.SH\reported_numbers.json `
  --footnotes output\600887.SH\footnotes.json
```

常用参数：

- `--as-of YYYY-MM-DD`：按公告日做近似 PIT 过滤
- `--pit`：从本地 PIT 库读取
- `--rf / --rf-source`：无风险利率覆盖
- `--pdf-sections`：附带 PDF 章节

### 5.2 report

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --rf 1.6516 --rf-source "ICBC 2026-10-15" `
  --html
```

输出：

- `analysis_report.md`
- `analysis_report.html`（`--html`）

### 5.3 定性输入

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli qualitative 600887.SH --init
# 编辑 output/600887.SH/qualitative.json
.\.venv\Scripts\python.exe -m turtlefw.cli qualitative 600887.SH --check
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH
```

规则：

- `judgment`: `positive / neutral / negative / unknown`
- 非 `unknown` 必须有 evidence
- evidence 必须有 http(s) URL 和非空 quote
- 没有证据的判断会被降级为 `unknown`

### 5.4 绝对估值

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli valuation 600887.SH
```

包含 DCF/DDM/PE Band/PEG/PS、方法权重、5×5 DCF 敏感性、反推增长。

---

## 6. 港股流程

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli pack 00700.HK `
  --pdf-numbers output\00700.HK\reported_numbers.json `
  --pdf-sections output\00700.HK\pdf_sections.json

.\.venv\Scripts\python.exe -m turtlefw.cli report 00700.HK `
  --pdf-numbers output\00700.HK\reported_numbers.json `
  --evidence output\00700.HK\evidence.json `
  --html
```

注意：

- 港股报表币种优先读 yfinance `financialCurrency`；失败回退 CNY
- 可用 `--currency HKD` 显式覆盖
- `hk_daily` 限 1 次/小时；yfinance 失败时可能跳过行情
- 港股质押是 `not_applicable`，没有 A 股 `pledge_stat` 对应物
- 港股回购是 `partial`：`hk_cashflow` 回购股份 + HKEXnews 公告

### 港股回购公告

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli hkex-news `
  --code 00700 `
  --keyword "Next Day Disclosure" `
  --from 20240101 --to 20261231 `
  --out output\00700.HK\hkex_buyback.json
```

输出公告级 evidence：

```text
hkexnews:<NEWS_ID>
source_url = PDF
quote = 日期 + 标题
```

不解析公告金额。

---

## 7. 美股流程

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli pack AAPL.US
.\.venv\Scripts\python.exe -m turtlefw.cli report AAPL.US --html

# SEC 独立证据
.\.venv\Scripts\python.exe -m turtlefw.cli sec-evidence `
  --ticker AAPL --out output\AAPL.US\evidence.json

# SEC 复核
.\.venv\Scripts\python.exe -m turtlefw.cli sec-audit `
  --snapshot output\AAPL.US\snapshot `
  --ticker AAPL `
  --out output\AAPL.US\sec_audit.json
```

美股边界：

- yfinance 报表；空/失败时 SEC companyfacts fallback
- SEC 不提供股价；行情走 yfinance / `us_daily`
- 回购来自 SEC companyfacts / yfinance，`partial`
- 母公司 `not_applicable`
- 质押 `not_applicable`
- 10-K 分部、13F 股东：`external`

---

## 8. PDF-first 证据

### 8.1 下载/准备 PDF

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli fetch-report `
  --url "<雪球/同花顺 PDF URL>" `
  --stock-code SH600887 `
  --report-type 年报 `
  --year 2025
```

或手动放入：

```text
output/600887.SH/2025年报.pdf
```

### 8.2 章节预处理

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli pdf `
  --pdf output\600887.SH\2025年报.pdf `
  --output output\600887.SH\pdf_sections.json
```

### 8.3 审计数字与附注

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli pdf-numbers `
  --pdf output\600887.SH\2025年报.pdf --year 2025

.\.venv\Scripts\python.exe -m turtlefw.cli pdf-footnotes `
  --sections output\600887.SH\pdf_sections.json
```

### 8.4 页级证据

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli pdf-evidence `
  --sections output\600887.SH\pdf_sections.json `
  --output output\600887.SH\evidence.json
```

生成：

```text
pdf:section:<SECTION>
pdf:holder:<name>
pdf:segment:<name>
pdf:parent_company
```

### 8.5 带 PDF 出具报告

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --pdf-numbers output\600887.SH\reported_numbers.json `
  --evidence output\600887.SH\evidence.json `
  --html
```

---

## 9. D1–D6 Research

### 9.1 两种模式

1. **DSH 原生**：DSH 模型直接写 `research.json`，不需要项目 API key。
2. **OpenAI-compatible**：`research-agent` 调外部 API。

### 9.2 DSH 原生流程

在 DSH 中使用 `turtle-research` skill，或手动：

```powershell
# 1. 导出上下文
.\.venv\Scripts\python.exe -m turtlefw.cli research-context `
  --snapshot output\600887.SH\snapshot `
  --out output\600887.SH\snapshot\research_context.json

# 2. 由 DSH 模型写 research.json
#    路径：output/600887.SH/snapshot/research.json

# 3. 校验
.\.venv\Scripts\python.exe -m turtlefw.cli research-audit `
  --file output\600887.SH\snapshot\research.json `
  --metrics output\600887.SH\snapshot\metrics.json `
  --facts output\600887.SH\snapshot\evidence.json `
  --min-claims 6 --min-dimensions 3 `
  --out output\600887.SH\snapshot\research_audit.json

# 4. provenance
.\.venv\Scripts\python.exe -m turtlefw.cli research-provenance `
  --research output\600887.SH\snapshot\research.json `
  --snapshot output\600887.SH\snapshot `
  --provider dsh --model deepseek-v4-flash `
  --out output\600887.SH\snapshot\research_provenance.json
```

### 9.3 带 research 冻结报告

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --research output\600887.SH\snapshot\research.json `
  --save-snapshot output\600887.SH\snapshot_with_research
```

离线渲染：

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --snapshot output\600887.SH\snapshot_with_research
```

### 9.4 OpenAI-compatible 模式

```powershell
$env:TURTLE_LLM_API_KEY = "..."
$env:TURTLE_LLM_MODEL = "your-model"
.\.venv\Scripts\python.exe -m turtlefw.cli research-agent `
  --snapshot output\600887.SH\snapshot `
  --out output\600887.SH\research.json `
  --retries 1 --min-claims 6 --min-dimensions 3
```

离线回放：

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli research-agent `
  --snapshot output\600887.SH\snapshot `
  --out output\600887.SH\research.json `
  --response tests\fixtures\dsh_research_sample.json
```

### 9.5 research.json 最小结构

```json
{
  "evidence": [
    {
      "id": "ev1",
      "url": "https://example.com/report",
      "quote": "原文引文",
      "source_type": "web"
    }
  ],
  "claims": [
    {
      "claim_id": "D2.1",
      "dimension": "D2",
      "statement": "护城河来自品牌与渠道，R={{metric:r}}",
      "judgment": "positive",
      "confidence": "medium",
      "evidence_ids": ["ev1"],
      "unknowns": []
    }
  ],
  "params": [
    {
      "param_id": "thesis.core",
      "label": "核心论点",
      "value": "R={{metric:r}}；护城河稳定",
      "dimension": "D2",
      "evidence_ids": ["ev1"],
      "confidence": "medium"
    }
  ],
  "decisions": []
}
```

硬规则：

- 不能写裸数字；
- 只能 `{{metric:id}}` / `{{fact:id}}`；
- 非 `unknown` 必须有 evidence；
- Decision 只能从 candidates 选；
- 数字仍由 Python 计算。

---

## 10. Snapshot 与复现

### 10.1 冻结

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --save-snapshot output\600887.SH\snapshot `
  --research output\600887.SH\research.json
```

### 10.2 离线渲染

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --snapshot output\600887.SH\snapshot
```

### 10.3 完整性

`manifest.json` 包含：

- facts/config/research/template hash
- metrics/resolved/numeric hash
- report_hash
- numeric coverage/status/unknown

不要手动修改 snapshot 文件；修改后必须重新冻结。

### 10.4 strict numeric

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887.SH `
  --save-snapshot output\600887.SH\snapshot `
  --strict-numeric
```

`--strict-numeric` 必须与 `--save-snapshot` 一起使用；numeric review 时返回非零。

---

## 11. QA 与审计

### 11.1 QA

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli state 600887.SH --init
.\.venv\Scripts\python.exe -m turtlefw.cli qa 600887.SH
```

全部通过后写 `qa.json`：

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli qa 600887.SH --write
```

QA 检查：

- run_state / report / data coverage
- qualitative / evidence / discrepancies
- narrative 数字可追溯
- research
- research_quality
- research_provenance
- numeric_coverage
- research_refs

### 11.2 数字审计

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli numeric-audit `
  --report output\600887.SH\analysis_report.md `
  --source output\600887.SH\snapshot\metrics.json `
  --source output\600887.SH\snapshot\resolved_facts.json `
  --strict
```

### 11.3 cleanroom

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli cleanroom `
  --snapshot output\600887.SH\snapshot `
  --pdf-numbers output\600887.SH\reported_numbers.json `
  --strict
```

### 11.4 research audit

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli research-audit `
  --file output\600887.SH\research.json `
  --metrics output\600887.SH\snapshot\metrics.json `
  --facts output\600887.SH\snapshot\evidence.json `
  --min-claims 6 --min-dimensions 3
```

---

## 12. PIT 本地快照

```powershell
# 冻结当前知识状态
.\.venv\Scripts\python.exe -m turtlefw.cli pit freeze --code 600887
# 按公告日回填
.\.venv\Scripts\python.exe -m turtlefw.cli pit freeze --code 600887 --backfill
# 查看
.\.venv\Scripts\python.exe -m turtlefw.cli pit list --code 600887
# 按 as-of 出报告
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887 `
  --as-of 2025-06-30 --pit
```

PIT 是本地快照，不是 vendor 级历史数据库。

---

## 13. 选股与估值

### 13.1 快速筛选

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli screen --fast --fast-limit 20
```

### 13.2 深度分析

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli screen --fast --deep 10 --csv output\screen.csv
```

### 13.3 估值

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli valuation 600887
```

---

## 14. Agent 阶段运行

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli agent `
  --dir .runs\600887.SH `
  --command "data=C:\PyProject\turtle-framework\.venv\Scripts\python.exe -m turtlefw.cli pack 600887" `
  --command "compose=C:\PyProject\turtle-framework\.venv\Scripts\python.exe -m turtlefw.cli report 600887" `
  --resume
```

规则：

- 命令在 `--dir` 内执行；
- `--resume` 跳过已通过阶段；
- 建议使用绝对 Python 路径；
- 阶段：`data / document / research / compose / audit`。

---

## 15. 数据覆盖

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli coverage 600887.SH
.\.venv\Scripts\python.exe -m turtlefw.cli coverage 00700.HK
.\.venv\Scripts\python.exe -m turtlefw.cli coverage AAPL.US
.\.venv\Scripts\python.exe -m turtlefw.cli coverage 00700.HK --json
```

| 市场 | 覆盖 |
|:--|:--|
| A 股 | 三表、母公司、分红、回购、质押、股东、主营 |
| 港股 | 三表、行情、PDF 股东/分部、回购 partial、母公司 pdf_optional |
| 美股 | yfinance/SEC 报表、SEC evidence、回购 partial；分部/13F external |
| PIT | 本地 snapshot partial |

`external` 表示依赖外部数据源，不伪造。

---

## 16. 常见问题

### 16.1 没有 TUSHARE_TOKEN

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 600887 --demo
```

生产命令需要 token。

### 16.2 `yc_cb` 无权限

```powershell
--rf 1.6516 --rf-source "ICBC 2026-10-15"
```

### 16.3 港股币种

先让 yfinance 探测；失败回退 CNY。可显式：

```powershell
--currency HKD
```

### 16.4 `hk_daily` 限流

港股行情优先 yfinance；`hk_daily` 限 1 次/小时，限流时本次跳过，不等待。

### 16.5 受限环境写 output 失败

```powershell
$env:TURTLE_OUTPUT_DIR = ".runs"
```

### 16.6 snapshot 校验失败

不要手改 snapshot 的 `manifest.json` / `metrics.json` / `research.json`；重新冻结。

### 16.7 研究占位符未解析

说明 claim 引用了不存在的 metric/fact。检查：

```powershell
research-audit --metrics ... --facts ...
```

### 16.8 `external` 不是 bug

10-K 分部、13F 股东依赖外部数据源，当前不硬做。

---

## 17. 测试与 CI

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src --select F401,F601,F841
```

当前基线：

```text
339 tests passed
```

CI：

[.github/workflows/ci.yml](.github/workflows/ci.yml)

---

## 18. 命令地图

| 目标 | 命令 |
|:--|:--|
| 单股分析 | `analyze` |
| 数据包 | `pack` |
| 报告 | `report` |
| HTML | `report --html` / `html` |
| 估值 | `valuation` |
| 选股 | `screen` |
| 定性 | `qualitative` |
| PDF 章节 | `pdf` |
| PDF 数字 | `pdf-numbers` |
| PDF 附注 | `pdf-footnotes` |
| PDF 证据 | `pdf-evidence` |
| 研究校验 | `research` / `research-audit` |
| 研究上下文 | `research-context` |
| 研究 provenance | `research-provenance` |
| DSH/LLM 研究 | `research-agent` / `turtle-research` skill |
| snapshot | `report --save-snapshot` |
| 离线报告 | `report --snapshot` |
| PIT | `pit` |
| QA | `qa` |
| 数字审计 | `numeric-audit` |
| cleanroom | `cleanroom` |
| SEC | `sec-audit` / `sec-evidence` |
| HKEX | `hkex-news` |
| 覆盖矩阵 | `coverage` |
| Agent 阶段 | `agent` |
