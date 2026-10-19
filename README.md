# Turtle Investment Framework (clean-room)

确定性取数 + 四因子分析的 A 股 / 港股 / 美股（实验）基本面研究系统。设计思路沿用
[龟龟投资框架](https://github.com/Pr0ph3tyyy/Turtle_investment_framework)，
实现从头重写，修正了原项目在单位、币种、分红聚合、缺失值处理上的已知缺陷。

## 状态

| 里程碑 | 内容 | 状态 |
|:---|:---|:---|
| M0 | 骨架 / 配置 / 类型 / CLI / Windows 安装脚本 | 完成 |
| M1 | Tushare 数据层（缓存、限速、长表归一化、Parquet 存储） | 完成 |
| M2 | 指标层（分红、现金流、穿透回报率、五法底价） | 完成 |
| M3 | 选股器（Tier1 + Fast + Tier2） | 完成（Fast 全市场约 25s，Tier2 并发） |
| M4 | 四因子（确定性部分）+ 数据包 + 分析报告 | 完成 |
| M5 | 定性层（evidence-backed JSON + 校验 + 报告合并） | 完成（LLM 自动填充为可选） |
| M6 | PDF 附注提取 | 完成（章节定位 + 6 项审计数字 + 附注表格结构化；600887/00700 2025 年报已实测） |
| M7 | 确定性 grids、DCF/DDM、Thesis Card、SBC/税档/Owner Earnings | 完成（P0/P1 + 分析升级） |

## 快速开始（Windows）

```powershell
cd C:\PyProject\turtle-framework
pwsh -File scripts\init.ps1

# PDF/港股行情依赖已包含在 init.ps1 的 .[dev,pdf,hk] 中
.\.venv\Scripts\python.exe -m pip install -e ".[pdf,hk]"

# 把 Tushare token 写进 .env（config.py 会自动加载）
Copy-Item .env.sample .env
notepad .env

.\.venv\Scripts\python.exe -m turtlefw.cli --help
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 600887 --demo
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 600887
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 00700.HK
.\.venv\Scripts\python.exe -m turtlefw.cli analyze AAPL
.\.venv\Scripts\python.exe -m turtlefw.cli smoke --codes 600887,00700.HK,AAPL --rf 1.6516 --rf-source "smoke"
.\.venv\Scripts\python.exe -m turtlefw.cli pack 600887
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887 --rf 1.6516 --rf-source "ICBC 2026-10-15" --html
.\.venv\Scripts\python.exe -m turtlefw.cli valuation 600887
.\.venv\Scripts\python.exe -m turtlefw.cli html --input output\600887.SH\analysis_report.md
.\.venv\Scripts\python.exe -m turtlefw.cli pdf-numbers --pdf output\600887.SH\2025年报.pdf --year 2025
.\.venv\Scripts\python.exe -m turtlefw.cli pdf-footnotes --sections output\600887.SH\pdf_sections.json
.\.venv\Scripts\python.exe -m turtlefw.cli pdf-evidence --sections output\600887.SH\pdf_sections.json --output output\600887.SH\evidence.json
.\.venv\Scripts\python.exe -m turtlefw.cli pack 600887 --footnotes output\600887.SH\footnotes.json
.\.venv\Scripts\python.exe -m turtlefw.cli pack 600887 --as-of 2025-06-30
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887 --as-of 2025-06-30
# agent 命令在 --dir 内执行；先激活 .venv，或把 python 改成绝对路径
.\.venv\Scripts\python.exe -m turtlefw.cli agent --dir .runs\600887.SH --command "data=python -m turtlefw.cli pack 600887" --command "compose=python -m turtlefw.cli report 600887"
.\.venv\Scripts\python.exe -m turtlefw.cli report 00700.HK --pdf-numbers .runs\reports\00700_numbers_doc.json --source-policy display-primary
.\.venv\Scripts\python.exe -m turtlefw.cli numeric-audit --report .runs\600887.SH\analysis_report.md --source .runs\600887.SH\data_pack.md --source .runs\600887.SH\snapshot\metrics.json --source .runs\600887.SH\snapshot\resolved_facts.json
.\.venv\Scripts\python.exe -m turtlefw.cli pit freeze --code 600887 --backfill
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887 --as-of 2025-06-30 --pit
.\.venv\Scripts\python.exe -m turtlefw.cli pack 00700.HK --pdf-numbers output\00700.HK\reported_numbers.json
.\.venv\Scripts\python.exe -m turtlefw.cli pack 00700.HK --pdf-sections output\00700.HK\pdf_sections.json
.\.venv\Scripts\python.exe -m turtlefw.cli report 00700.HK --pdf-numbers output\00700.HK\reported_numbers.json
.\.venv\Scripts\python.exe -m turtlefw.cli screen --as-of 2025-06-30
.\.venv\Scripts\python.exe -m turtlefw.cli research --file output\600887.SH\research.json
.\.venv\Scripts\python.exe -m turtlefw.cli research-context --snapshot output\600887.SH\snapshot --out output\600887.SH\research_context.json
.\.venv\Scripts\python.exe -m turtlefw.cli research-provenance --research output\600887.SH\snapshot\research.json --snapshot output\600887.SH\snapshot --provider dsh --model deepseek-v4-flash --out output\600887.SH\snapshot\research_provenance.json
.\.venv\Scripts\python.exe -m turtlefw.cli research-agent --snapshot output\600887.SH\snapshot --out output\600887.SH\research.json --response tests\fixtures\research_response.json
.\.venv\Scripts\python.exe -m turtlefw.cli research-agent --snapshot output\600887.SH\snapshot --out output\600887.SH\research.json --model <model>
.\.venv\Scripts\python.exe -m turtlefw.cli research-audit --file output\600887.SH\research.json --metrics output\600887.SH\snapshot\metrics.json --facts output\600887.SH\snapshot\evidence.json
.\.venv\Scripts\python.exe -m turtlefw.cli sec-audit --snapshot output\AAPL.US\snapshot --ticker AAPL --out output\AAPL.US\sec_audit.json
.\.venv\Scripts\python.exe -m turtlefw.cli sec-evidence --ticker AAPL --out output\AAPL.US\evidence.json
.\.venv\Scripts\python.exe -m turtlefw.cli coverage AAPL
.\.venv\Scripts\python.exe -m turtlefw.cli snapshot 600887 --as-of 2025-12-31 --out output\600887.SH\manifest.json
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887 --save-snapshot output\600887.SH\snapshot `
  --research output\600887.SH\research.json
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887 --snapshot output\600887.SH\snapshot
.\.venv\Scripts\python.exe -m turtlefw.cli cleanroom --snapshot output\600887.SH\snapshot `
  --pdf-numbers output\600887.SH\reported_numbers.json
.\.venv\Scripts\python.exe -m turtlefw.cli agent --dir output\600887.SH\snapshot
```

### 受限环境输出目录

默认写入 `output/`。在 DSH workspace-write 等受限环境，把运行产物根目录改到工作区可写目录：

```powershell
$env:TURTLE_OUTPUT_DIR = ".runs"
# 或全局参数（放在子命令之前）
turtle --output-dir .runs report 600887
```

`pack/report/state/qa/qualitative/narrative/golden` 共用同一个根目录；`TURTLE_OUTPUT_ROOT` 是兼容别名。

PDF 实测记录（600887 / 00700）见 [docs/pdf-extraction-validation.md](docs/pdf-extraction-validation.md)；
00700 的已知收入差异与分区缺口见 [docs/00700-known-differences.md](docs/00700-known-differences.md)；
SBC/稀释/复权、税档/OE、附注/股东分部的实现见 [docs/analysis-upgrades.md](docs/analysis-upgrades.md)；
美股支持边界见 [docs/us-experimental.md](docs/us-experimental.md)；
更新后相对 v2 的真实差距见 [docs/v2-gap-after-upgrades.md](docs/v2-gap-after-upgrades.md)；
目标架构与 Phase 1 执行记录见 [docs/target-architecture.md](docs/target-architecture.md)；
PIT 快照库见 [docs/pit.md](docs/pit.md)。

`.claude/commands/turtle-analysis.md` 和 `.claude/skills/turtle-analysis/SKILL.md` 提供 Claude Code 入口；
流程仍以 `prompts/agent/coordinator.md` 为准。

`--rf/--rf-source` 用于 `yc_cb` 无权限时传入带出处的无风险利率（例如券商/银行日报）。

港股报表币种：优先读取 Yahoo Finance 的 `financialCurrency`（多数内地港股为 CNY），
失败时回退 CNY 并提示；可用 `--currency HKD` 显式覆盖。港元 DPS 若在多个年度
重复，会被标记为不可靠并从 DPS 均值/股息隐含价中剔除（支付率仍可用）。

### 定性输入（evidence-backed）

```powershell
turtle qualitative 600887 --init     # 生成 output/600887.SH/qualitative.json 模板
turtle qualitative 600887 --check    # 校验：判断值、置信度、URL、引文
turtle report 600887                 # 自动读取同目录 qualitative.json
```

规则：`judgment` 必须是 `positive/neutral/negative/unknown`；非 unknown 但**没有证据**会被自动降级为 `unknown`；证据必须含 http(s) URL 与非空引文。LLM 或人工填写走同一套校验。

`research.json` 还支持：

- `params`：研究参数表（如护城河评级、行业、CR4），值只能使用 `{{metric:id}}` / `{{fact:id}}`；
- `decisions`：G/M/AA/税档等**有限候选选择**，`selected` 必须属于 `candidates`，LLM 不能自造数值。

### 确定性 grids 与绝对估值

`report` 不再由 LLM 选 G/M/AA：`metrics/grids.py` 用 Capex/D&A 强度选 G，用三法交叉校验
支付率 M，用 AA_2y/AA_all/AA_excl 变体，并给出 λ 收入敏感性、5 维可信度、6 项价值陷阱
和仓位矩阵。因子 3 优先使用真实现金收入−经营流出−Capex 的现金桥（组件缺失才回退
OCF−Capex）；数据包增加母公司现金、质押率、回购、最新中报/季报年化参考。
`turtle valuation <code>` 提供 DCF/DDM/PE Band/PEG/PS 快照、公司类型与方法权重、5×5 DCF
敏感性、反推增长（显式假设、可单测），报告末尾附 Thesis Card（论点/催化剂/持有周期/止损/监控）。

```powershell
turtle valuation 600887
```

已知限制（M1/M2 阶段）：

- 港股报表币种优先用行情元数据探测，失败时默认 CNY；港元报表请显式 `--currency HKD`。
- 港股行情走 `yfinance`（失败再走 `hk_daily`）；`hk_daily` 限 **1 次/小时**，被限流时本次分析会跳过行情，不会重试等待。
- 港股 DPS 若来自 `hk_fina_indicator` 且多年重复，会被标记为不可靠；支付率仍按 `divi_ratio` 计算。
- `yc_cb` 无权限时回退到 `configs/screening.toml` 的 `default_rf`。
- 港股现金桥为“PDF 间接桥”：line-item 缺毛利收付明细，用净利润→D&A→营运资本→经营产生现金→税→OCF；不是直接法。
- PDF 6 项审计数字可自动抽取（`pdf-numbers`）；`pdf-footnotes` 只做表格结构化，账龄/关联方/或有负债的科目级语义仍需人工/Agent 解释。
- `screen --as-of` 只把上市状态/行情切到该日；财务指标仍是最新报表，不是完整 point-in-time。
- SBC 目前主要来自 PDF（港股权益结算口径）；A 股无稳定字段，回购注销后的净股数也未完全建模。
- 股东/主营只覆盖 A 股（Tushare `top10_holders` / `fina_mainbz`）；港股无对应接口。
- 美股走 yfinance（近 4 个年度报表），字段可能随供应商变化；质押/股东/主营暂缺。
- Tushare 字段/权限逐项状态见 [docs/tushare-fields.md](docs/tushare-fields.md)。
- clean-room/CI 的落地条件见 [docs/cleanroom-ci-plan.md](docs/cleanroom-ci-plan.md)。

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m turtlefw.cli analyze 600887 --demo
```

## 设计约束

1. **金额必须带币种**：`Money(amount, currency)`，跨币种运算抛异常，必须显式传汇率。
2. **报表币种优先来自数据源元数据**：港股用 `financialCurrency` 探测，不可得时回退 CNY；
   不按上市地/交易币种推断。
3. **取数不缩放**：数据库存原始单位（元），只在展示层转百万元。
4. **单一指标口径**：分红、穿透回报率、底价各只有一个函数，选股器与报告共用。
5. **缺失值三态**：`OK / MISSING / NOT_APPLICABLE`，门禁 fail-closed，排名按覆盖度加权。
6. **可复现**：同一数据快照重新渲染，确定性部分逐字节一致。

## 目录

```
src/turtlefw/
├─ types.py           # Money / Currency / StockCode / Metric
├─ config.py          # TOML 配置 + .env
├─ data/              # provider / normalize / cache / store
├─ metrics/           # dividends / statements / returns / valuation / grids / cashflow / valuation_models
├─ screener/          # rank / tier1
└─ report/            # bundle / render / HTML + Jinja2 模板
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

全部测试离线运行，不需要 Tushare token。CI 配置见 `.github/workflows/ci.yml`（pytest + 核心模块 mypy）。
