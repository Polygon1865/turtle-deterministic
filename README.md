# Turtle Investment Framework (clean-room)

确定性取数 + 四因子分析的 A 股 / 港股基本面研究系统。设计思路沿用
[龟龟投资框架](https://github.com/Pr0ph3tyyy/Turtle_investment_framework)，
实现从头重写，修正了原项目在单位、币种、分红聚合、缺失值处理上的已知缺陷。

## 状态

| 里程碑 | 内容 | 状态 |
|:---|:---|:---|
| M0 | 骨架 / 配置 / 类型 / CLI / Windows 安装脚本 | 完成 |
| M1 | Tushare 数据层（缓存、限速、长表归一化、Parquet 存储） | 完成 |
| M2 | 指标层（分红、现金流、穿透回报率、五法底价） | 完成 |
| M3 | 选股器（Tier1 过滤 + 覆盖度感知排名） | Tier1 完成，Tier2 待做 |
| M4 | 四因子（确定性部分）+ 数据包 + 分析报告 | 完成 |
| M5 | 定性层（evidence-backed JSON + 校验 + 报告合并） | 完成（LLM 自动填充为可选） |
| M6 | PDF 附注提取 | 待做 |

## 快速开始（Windows）

```powershell
cd C:\PyProject\turtle-framework
pwsh -File scripts\init.ps1

# 把 Tushare token 写进 .env（config.py 会自动加载）
Copy-Item .env.sample .env
notepad .env

.\.venv\Scripts\python.exe -m turtlefw.cli --help
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 600887 --demo
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 600887
.\.venv\Scripts\python.exe -m turtlefw.cli analyze 00700.HK --currency CNY
.\.venv\Scripts\python.exe -m turtlefw.cli pack 600887
.\.venv\Scripts\python.exe -m turtlefw.cli report 600887 --rf 1.6516 --rf-source "ICBC 2026-10-15"
```

`--rf/--rf-source` 用于 `yc_cb` 无权限时传入带出处的无风险利率（例如券商/银行日报）。

### 定性输入（evidence-backed）

```powershell
turtle qualitative 600887 --init     # 生成 output/600887.SH/qualitative.json 模板
turtle qualitative 600887 --check    # 校验：判断值、置信度、URL、引文
turtle report 600887                 # 自动读取同目录 qualitative.json
```

规则：`judgment` 必须是 `positive/neutral/negative/unknown`；非 unknown 但**没有证据**会被自动降级为 `unknown`；证据必须含 http(s) URL 与非空引文。LLM 或人工填写走同一套校验。

已知限制（M1/M2 阶段）：

- 港股默认按人民币报表处理（多数港股内地企业），港元报表请加 `--currency HKD`。
- 港股行情走 `hk_daily`，该接口限 **1 次/小时**，被限流时本次分析会跳过行情，不会重试等待。
- 港股总市值/股本暂未接入，因此港股的穿透回报率与底价暂为「不可用」（M3 接 yfinance 行情源）。
- `yc_cb` 无权限时回退到 `configs/screening.toml` 的 `default_rf`。

macOS / Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m turtlefw.cli analyze 600887 --demo
```

## 设计约束

1. **金额必须带币种**：`Money(amount, currency)`，跨币种运算抛异常，必须显式传汇率。
2. **报表币种来自报表**，不按上市地推断（港股大量公司以人民币报表）。
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
├─ metrics/           # dividends / statements / returns / valuation
├─ screener/          # rank / tier1
└─ report/            # bundle / render + Jinja2 模板
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest
```

全部测试离线运行，不需要 Tushare token。
