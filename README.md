# Turtle Framework

[![CI](https://github.com/Polygon1865/turtle-deterministic/actions/workflows/ci.yml/badge.svg)](https://github.com/Polygon1865/turtle-deterministic/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**确定性的 A 股 / 港股 / 美股基本面研究框架。**

数字由 Python `Decimal` 管线和冻结快照计算；LLM/DSH 只负责可选的 D1–D6 研究文本。
同一 snapshot 重新渲染，确定性部分逐字节一致。

> **完整逐步说明见 [docs/USAGE.md](docs/USAGE.md)。**
> 本 README 只介绍项目定位、快速开始、核心工作流和边界。

---

## 它解决什么问题

普通“AI 研报”把取数、计算、判断、写报告混在一起，容易出现：

- 数字由模型计算或改写；
- 币种、单位、分红口径混用；
- 报告不可复现；
- 数据缺失被模型补成假值；
- PDF 证据和结论对不上。

Turtle Framework 把链路拆开：

```text
数据源
  → StatementRow / ReportInputs
  → Python Decimal 指标与因子
  → research.json（可选 D1–D6）
  → analysis_report.md / HTML
  → snapshot / numeric audit / QA
```

### 三条硬规则

1. **报告数字只能来自 Python 指标或 PDF/SEC fact。**
2. **LLM/DSH 只写 `research.json`，默认不改变数字；只有显式 `--allow-research-decisions` 才可从预计算 candidates 选择，且必须带 evidence。**
3. **同一 snapshot 离线重渲染必须逐字节一致。**

---

## 核心能力

| 能力 | 说明 |
|:--|:--|
| 确定性四因子 | 资产质量、穿透回报率、精算、估值 |
| 五法底价 | 均值/中位数、口径分歧检测 |
| G / M / AA / 税档 | Capex/D&A 网格、支付率三法、AA 变体 |
| 现金桥 | PDF/报表现金桥，缺失才回退 OCF−Capex |
| 绝对估值 | DCF / DDM / PE Band / PEG / PS |
| 定性层 | evidence-backed JSON，非 unknown 必须有 URL + quote |
| PDF-first | 章节定位、审计数字、附注、页级 evidence |
| D1–D6 Research | claims / params / decisions，claim-level audit |
| DSH 原生研究 | DSH 模型直接写 `research.json`，不需要项目 API key |
| Snapshot | facts/config/research/metrics/report hash 冻结 |
| QA | research/numeric/provenance/coverage 门控 |

---

## 当前数据覆盖

```powershell
python -m turtlefw.cli coverage 600887.SH
python -m turtlefw.cli coverage 00700.HK
python -m turtlefw.cli coverage AAPL.US
```

| 市场 | 三表 | 母公司 | 分红 | 回购 | 质押 | 股东/分部 |
|:--|:--|:--|:--|:--|:--|:--|
| A 股 | 完成 | 完成 | 完成 | 完成 | 完成 | 完成 |
| 港股 | 完成 | `pdf_optional` | 完成 | `partial` | `not_applicable` | PDF `partial` |
| 美股 | yfinance + SEC fallback | `not_applicable` | 完成 | SEC `partial` | `not_applicable` | 分部/13F `external` |

状态含义：

- `available`：本地可用；
- `partial`：可用但不完整；
- `pdf_optional`：只能从年报 PDF 证据入口补充；
- `not_applicable`：没有标准化口径；
- `external`：需要外部数据源，本地不硬做；
- `missing`：本地应有但尚未接入。

**不会用合并现金冒充母公司现金，也不会用假数据填 13F/10-K 分部。**

---

## 快速开始

### 1. 环境

- Python **3.11+**
- Tushare Pro token（A/港股主数据；演示模式不需要）
- 可选：`pdfplumber`（PDF）、`yfinance`（港股/美股行情）

### 2. Windows 初始化

```powershell
cd C:\PyProject\turtle-framework
pwsh -File scripts\init.ps1
```

手动安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev,pdf,hk]"
```

### 3. 配置 Tushare

```powershell
Copy-Item .env.sample .env
notepad .env
```

```text
TUSHARE_TOKEN=your_token_here
```

### 4. 无 token 演示

```powershell
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 600887 --demo
```

### 5. A 股最小生产流程

```powershell
$env:TURTLE_OUTPUT_DIR = ".runs"

# 一键确定性流程：单次取数 → data_pack/report/snapshot → QA
turtle run 600887.SH --rf 1.6516 --rf-source "ICBC 2026-10-15"
```

也可以拆开执行：

```powershell
turtle pack 600887.SH --rf 1.6516 --rf-source "ICBC 2026-10-15"
turtle report 600887.SH --rf 1.6516 --rf-source "ICBC 2026-10-15" --html
turtle report 600887.SH --save-snapshot .runs\600887.SH\snapshot
```

`run` 的产物：

```text
.runs/600887.SH/
├─ data_pack.md
├─ analysis_report.md
├─ analysis_report.html
├─ qa.json
└─ snapshot/
```

> `TURTLE_OUTPUT_DIR` 用于受限环境。默认根目录是 `.runs/`；也可使用
> `python -m turtlefw.cli --output-dir .runs ...`。
>
> 下文 `turtle` 指 `.venv\Scripts\turtle.exe`；未安装 console script 时，
> 等价命令是 `.\.venv\Scripts\python.exe -m turtlefw.cli`。

---

## 在 DSH / Claude Code 中使用

### 一键确定性流程

DSH / Claude Code：

```text
/turtle-run 600887 --rf 1.6516
```

两者最终都执行：

```text
turtle run <code> [args]
```

### 完整确定性 + D1–D6

Claude Code：

```text
/turtle-full 600887 --rf 1.6516
```

DSH：

```text
使用 turtle-full skill 分析 600887
```

流程：

```text
run → snapshot
→ research-context
→ DSH/Claude 写 research.json
→ research-audit
→ research-provenance
→ finalize（不重新取数）
→ report/HTML
→ QA
```

> `/turtle-full` 是 **research-only**：不运行 PDF/定性 Agent。
> 没有 `qualitative.json` 时 1A/1B 保持“未验证”；需要完整定性请用
> `/turtle-analysis`。

### 完整 Agent 流程

```text
/turtle-analysis 600887
```

- DSH：生成分析提示词，需发送后由 Agent 执行；
- Claude Code：进入完整 Agent 工作流；
- `/turtle-analysis` 走 PDF/定性，不等于 `/turtle-full` 的 D1–D6 research。

---

## 主要工作流

### A 股

```powershell
turtle pack 600887.SH
turtle qualitative 600887.SH --init
turtle qualitative 600887.SH --check
turtle report 600887.SH --html
turtle valuation 600887.SH
```

### 港股

```powershell
turtle pack 00700.HK
turtle report 00700.HK --pdf-numbers .runs\00700.HK\reported_numbers.json --html
```

港股注意：

- 报表币种优先读 yfinance `financialCurrency`，失败回退 CNY；
- 可用 `--currency HKD` 覆盖；
- `hk_daily` 限 1 次/小时，失败时本次可能跳过行情；
- 港股质押是 `not_applicable`；
- 港股回购是 `partial`（`hk_cashflow` + HKEXnews 公告）。

### 美股

```powershell
turtle pack AAPL.US
turtle report AAPL.US --save-snapshot .runs\AAPL.US\snapshot --html
turtle sec-evidence --ticker AAPL --out .runs\AAPL.US\evidence.json
turtle sec-audit --snapshot .runs\AAPL.US\snapshot --ticker AAPL
```

美股注意：

- 报表走 yfinance，空/失败时 SEC companyfacts fallback；
- SEC 不提供股价，行情走 yfinance / `us_daily`；
- 10-K 分部、13F 股东是 `external`。

---

## PDF-first 证据

```powershell
# 1. 年报 PDF（雪球/同花顺）或手动放入
turtle fetch-report --url "<PDF URL>" --stock-code SH600887 --report-type 年报 --year 2025

# 2. 章节定位
turtle pdf --pdf .runs\600887.SH\2025年报.pdf --output .runs\600887.SH\pdf_sections.json

# 3. 审计数字 / 附注
turtle pdf-numbers --pdf .runs\600887.SH\2025年报.pdf --year 2025
turtle pdf-footnotes --sections .runs\600887.SH\pdf_sections.json

# 4. 页级研究证据
turtle pdf-evidence --sections .runs\600887.SH\pdf_sections.json --output .runs\600887.SH\evidence.json

# 5. 带证据出报告
turtle report 600887.SH --pdf-numbers .runs\600887.SH\reported_numbers.json --evidence .runs\600887.SH\evidence.json
```

PDF evidence 包含：

```text
pdf:section:<SECTION>
pdf:holder:<name>
pdf:segment:<name>
pdf:parent_company
```

`pdf:parent_company` 只提供公司层面资产负债表的证据入口，不解析金额。

---

## D1–D6 Research（DSH 原生）

推荐用 DSH 的 `turtle-full` / `turtle-research` skill：

```text
.agents/skills/turtle-full/SKILL.md
.agents/skills/turtle-research/SKILL.md
```

流程：

```text
research-context
  → DSH 模型写 research.json
  → research-audit
  → research-provenance
  → finalize（不重新取数）
  → report / HTML
  → QA
```

手动命令：

```powershell
turtle research-context `
  --snapshot .runs\600887.SH\snapshot `
  --out .runs\600887.SH\snapshot\research_context.json

# 由 DSH 写 .runs/600887.SH/snapshot/research.json

turtle research-audit `
  --file .runs\600887.SH\snapshot\research.json `
  --metrics .runs\600887.SH\snapshot\metrics.json `
  --facts .runs\600887.SH\snapshot\evidence.json `
  --min-claims 6 --min-dimensions 3

turtle research-provenance `
  --research .runs\600887.SH\snapshot\research.json `
  --snapshot .runs\600887.SH\snapshot `
  --provider dsh --model deepseek-v4-flash `
  --out .runs\600887.SH\snapshot\research_provenance.json

turtle finalize `
  --snapshot .runs\600887.SH\snapshot `
  --research .runs\600887.SH\snapshot\research.json `
  --out .runs\600887.SH\snapshot_final `
  --min-claims 6 --min-dimensions 3 `
  --strict --html
```

也可以用 OpenAI-compatible 模式：

```powershell
$env:TURTLE_LLM_API_KEY = "..."
$env:TURTLE_LLM_MODEL = "your-model"
turtle research-agent --snapshot .runs\600887.SH\snapshot --out research.json
```

离线回放不需要网络：

```powershell
turtle research-agent --snapshot .runs\600887.SH\snapshot --out research.json `
  --response tests\fixtures\dsh_research_sample.json
```

研究硬规则：

- 不写裸数字，只能 `{{metric:id}}` / `{{fact:id}}`；
- 非 `unknown` 必须有 evidence；web/document evidence 必须有 http(s) URL + quote，内部 data evidence 可用 `data:` id + quote；
- Decision 默认禁用；只有显式 `--allow-research-decisions` 才可从预计算 candidates 选，且必须有 evidence；
- 未解析引用、非法 Decision、无 evidence 的 Decision 直接失败。

---

## Snapshot 与 QA

### 冻结与离线复现

```powershell
turtle report 600887.SH --save-snapshot .runs\600887.SH\snapshot
turtle report 600887.SH --snapshot .runs\600887.SH\snapshot
```

`manifest.json` 记录：

- facts/config/research/template hash
- metrics/resolved/numeric hash
- report_hash
- numeric coverage/status/unknown

不要手动修改 snapshot 文件；修改后重新冻结。

### QA

```powershell
turtle state 600887.SH --init
turtle report 600887.SH --save-snapshot .runs\600887.SH\snapshot
turtle qa 600887.SH
turtle qa 600887.SH --write
```

确定性/研究-only 流程无 `qualitative.json` 时使用：

```powershell
turtle qa 600887.SH --allow-missing-qualitative
```

QA 包含：

```text
run_state / report / data_coverage
qualitative / evidence / discrepancies
narrative
research / research_quality / research_refs
research_audit
research_provenance
numeric_coverage
```

### 数字审计

```powershell
turtle numeric-audit `
  --report .runs\600887.SH\analysis_report.md `
  --source .runs\600887.SH\snapshot\metrics.json `
  --source .runs\600887.SH\snapshot\resolved_facts.json `
  --strict
```

---

## 数据源与外部边界

| 数据 | 来源 |
|:--|:--|
| A 股三表 | Tushare `income` / `balancesheet` / `cashflow` |
| A 股母公司 | Tushare `report_type=6` |
| A 股回购/质押 | Tushare `repurchase` / `pledge_stat` |
| 港股三表 | Tushare `hk_income` / `hk_balancesheet` / `hk_cashflow` |
| 港股行情/股东 | yfinance，`hk_daily` fallback |
| 港股回购 | `hk_cashflow` 回购股份 + HKEXnews 公告 evidence |
| 美股三表 | yfinance，SEC companyfacts fallback |
| 美股回购 | SEC companyfacts / yfinance |
| PIT | 本地 snapshot |

详细调研见 [docs/data-sources.md](docs/data-sources.md)。

### 明确不做

- 港股母公司金额：只做 PDF evidence，不伪造；
- 港股质押：`not_applicable`；
- 美股母公司/质押：`not_applicable`；
- 美股 10-K 分部、13F：`external`。

---

## 项目结构

```text
src/turtlefw/
├─ types.py          # Money / Currency / StockCode
├─ config.py         # TOML + .env
├─ data/             # Tushare / SEC / HKEXnews / coverage
├─ metrics/          # dividends / statements / returns / grids / valuation
├─ factors/          # 四因子引擎
├─ screener/         # Tier1 / Fast / Tier2
├─ pdf/              # 章节 / 数字 / 附注 / evidence
├─ research.py       # ResearchDocument / audit / render
├─ report/           # data pack / analysis / snapshot / HTML
├─ agent/            # phase runner / LLM / DSH research
├─ qa.py             # 交付门控
└─ pit.py            # 本地 PIT 快照
```

---

## 测试与 CI

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check src --select F401,F601,F841
```

当前基线：

```text
363 tests passed
```

CI：pytest + selected ruff + selected mypy，见
[.github/workflows/ci.yml](.github/workflows/ci.yml)。

---

## 文档索引

- [详细使用说明](docs/USAGE.md)
- [数据源调研](docs/data-sources.md)
- [研究层](docs/research-layer.md)
- [Snapshot 复现](docs/snapshot-byte-identical.md)
- [PIT 本地快照](docs/pit.md)
- [PDF 提取验证](docs/pdf-extraction-validation.md)
- [美股实验边界](docs/us-experimental.md)
- [Tushare 字段](docs/tushare-fields.md)
- [v2 差距](docs/v2-gap-after-upgrades.md)

---

## 安全

- `TUSHARE_TOKEN` 只放 `.env` 或环境变量，不提交；
- `TURTLE_LLM_API_KEY` 只放环境变量；
- SEC 请求建议设置 `SEC_USER_AGENT`；
- 不要提交 `.runs/`、PDF、snapshot 中的私有数据。

---

## License

[MIT](LICENSE) © 2026 Polygon1865

---

> 本项目仅用于研究与教育，不构成投资建议。
