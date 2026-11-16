# 指标定义与口径（一页纸）

本文件是报告数字的**唯一口径说明**。改任何公式、单位、优先级，必须同时改本文件、对应 ADR 与 golden 基线（`tests/fixtures/golden-daily-*.json`）。

## 1. 来源优先级

| 级别 | 产物 | 性质 | 可否作为报告数字来源 |
|---|---|---|---|
| 1 | `snapshot/metrics.json` | 冻结的 `MetricPoint`（value/display/unit） | ✅ 唯一权威 |
| 2 | `snapshot/inputs.json` 的 `rows` | 原始报表行（`ann_date` 过滤后） | 仅经 metrics 计算后使用 |
| 3 | `snapshot/research.json` | 研究层文本（claims/params/evidence） | ❌ 不得写数字，只写 `metric:id` 占位符 |
| 4 | `data_pack.md` / `analysis_report.md` | 渲染产物 | ❌ 派生物，不得反向作为输入 |

数字审计（`numeric_audit.py`）按来源类归属：`metric` > `financial` > `pdf` > `research` > `qualitative`；只在渲染后的数据包里出现的数字记 `pack_only`，不在任何源产物里的记 `unattributed`（即 unknown）。

## 2. 核心指标

| 指标 id | 定义 | 公式 | 单位 | 来源 | 校验 |
|---|---|---|---|---|---|
| `r` | 粗算穿透回报率 | 归母净利 × 支付率 / 总市值 | % | metrics | numeric audit / report_consistency |
| `gg` | 精算穿透回报率 | 两年平均 FCF × 支付率 / 总市值 | % | metrics | 同上 |
| `ii` | 门槛回报率 II | A 股 `max(3.5, rf+2.0)`；港股 `max(5.0, rf+3.0)` | % | `settings.returns` | 同上 |
| `margin` | 安全边际 | `gg − ii` | pp | metrics | 同上；golden tol=0.01 |
| `floor` | 资产底价（采用值） | 净流动资产/股 与 每股净资产 的中位数（≥2 锚） | 元/股 | metrics | `floor.divergence` |
| `floor.earnings` | 收益价值（采用值） | 股息隐含价 与 悲观 FCF 资本化 的中位数（≥2 锚） | 元/股 | metrics | `premium.earnings` |
| `floor.median` / `floor.mean` | 资产底价中位/均值 | 同一资产组统计 | 元/股 | metrics | 溢价计算以 `floor` 为准 |
| `floor.divergence` | 资产组口径分歧 | `|mean−median|/median` | % | metrics | >20% 标记 divergent |
| `floor.low_10y` | 十年最低价 | 前复权周线最低，只作参考，不进任何中位数 | 元/股 | metrics | 不参与溢价 |
| `premium` | 资产溢价 | `price/floor − 1` | % | metrics | 与 `margin` 不可混用 |
| `premium.earnings` | 收益价值溢价 | `price/floor.earnings − 1` | % | metrics | 唯一触发底价降级的口径 |
| `payout` | 支付率（报告展示） | 近三年 `payout.latest` 均值 | % | metrics | `payout_consistency`（港股榜单 0.01） |
| `payout.latest` | 最近年度支付率 | `divi_ratio` → `dps/eps` → 事件合计，三选一 | % | `metrics/payout.py` | 同上；>100% 截断且 `reliable=false` |
| `price` | 当前价（报表币种） | 港股为 `close × fx`，`quote.close_local` 保留原币 | 元/股 | metrics | 报告头显示「CNY（报价 HKD）」 |
| `market_cap` | 总市值 | 港股 `total_market_cap × fx`（CNY）；`market_cap_hkd` 保留 HKD 原值 | 元 | metrics / `screener/hk.py` | 榜单与报告同为 CNY（W0.2）；`payout_consistency` 不覆盖此项 |
| `pb` / `ev_ebitda` / `fcf_yield` | 估值倍数与收益率 | 见 `metrics/valuation.py` | 倍 / % | metrics | numeric audit |
| `net_cash` | 净现金 | 货币资金 + 交易性资产 − 有息负债 | 百万元 | metrics | 现金桥不可用时标 unknown |
| `capex_da_ratio` | 资本消耗强度 | `capex / D&A` | 倍 | metrics | <1 视为轻资产 |
| `ocf_ni_ratio` | 现金含量 | `OCF / 归母净利` | 倍 | metrics | <1 标记观察 |
| `aa_2y` | 两年平均自由现金流 | `mean(fcf_t, fcf_{t-1})` | 百万元 | metrics | GG 的分母来源 |
| `k_star` / `lambda` / `hh` | 固定成本占比 / 经营杠杆 / 粗算偏差 | 见 `metrics/cashflow.py` | — | metrics | hh 的绝对值决定外推可信度 |
| `rf` | 无风险利率 | 配置或 10Y 国债，取不到用默认 1.8% | % | settings / provider | 报告头标注来源 |

## 3. 三处易混口径

1. **支付率**：榜单/报告一律以 `payout.latest` 为可比口径；`payout`（三年均值）只用于展示。二者差异由 `payout_consistency` 行暴露，不允许同日两产物出现两个值。
2. **市值币种**：港股 `hk_fina_indicator.total_market_cap` 是 HKD；榜单（`ranking_hk.csv` 的 `market_cap`）与报告统一按 `fx.cny_per_hkd` 折成 CNY，另存 `market_cap_hkd` 供核对。市值门槛 `--min-market-cap-yi` 也是 CNY 口径。
3. **底价 vs 安全边际**：底价拆成两组——`floor`（资产安全垫：净流动资产/股、每股净资产）与 `floor.earnings`（收益价值：股息隐含价、悲观 FCF 资本化）；十年最低价只作参考，不进中位数。`premium` 是价格相对资产底价的溢价，`premium.earnings` 是相对收益价值的溢价；只有 `premium.earnings > 150%` 或收益组 divergent 才会把「买入」降为「观察」，资产组溢价不降级。`margin` 是 GG 相对门槛的余量（百分点）。三者不可互相替代，报告结论按 `margin` 与价值陷阱判定。

## 4. 容差与门

| 检查 | 容差 | 行为 |
|---|---|---|
| `numeric_coverage` | 0 unknown | 严格模式 >0 即 review |
| `report_consistency` | 逐字 | 报告值与 metrics `display` 不一致即 FAIL |
| `payout_consistency` | 0.01 | 榜单 vs 报告支付率超差即 FAIL |
| `citation_audit` | 可达性 | 缓存中任一 URL 不可达即 FAIL |
| `pit_lookahead` | 0 违规 | `ann_date > as_of` 即 FAIL |
| `metric_conflicts` | 任一 | 同一 id 重复渲染时按 `source_rank` 取权威源（审计报表行 > 派生值），冲突落 `snapshot/metric_conflicts.json` 并 WARN |
| `verdict_drift` | 逐字 | 证据哈希不变但结论变化即 FAIL；证据变化且结论变化 WARN |
| golden diff | 0.01 | 指标漂移、结论变更均报出 |

## 5. 公式登记表（W2.4）

每个 `MetricPoint.formula_id` 都必须在 `src/turtlefw/metrics/formulas.py` 里解析到一个定义（表达式、输入、归属模块）。显式公式 20 条，另有 8 条前缀规则覆盖逐行生成的 id：

| 前缀 | 覆盖 |
|---|---|
| `statement.` | `statement.<income\|balance\|cashflow>.<item>` 原始报表行 |
| `balance.` | 资产负债表派生值 |
| `factor.` | 四因子门槛/输出 |
| `policy.` | 政策与合规阈值 |
| `tax.` | 税档假设 |
| `scenario.` | 营收 ±10/20/30% 敏感性 |
| `extras.` | 补充基本面字段 |
| `.pdf` | 年报 PDF 提取值（后缀匹配） |

契约由 `tests/test_formula_registry.py` 守住：源码里新增 `formula_id=` 字面量或新的动态前缀而没登记，测试就失败。查询用 `python -c "from turtlefw.metrics.formulas import describe; print(describe('returns.safety_margin'))"`。

## 6. 变更流程


1. 写 ADR（`docs/roadmap-2026-11.md` §2）。
2. 改 `metrics/` 与 `src/turtlefw/metrics/payout.py` 等单一源。
3. 更新本文件对应行。
4. 重新冻结 `baseline/` 与 `tests/fixtures/golden-*.json`，并在提交信息里注明「golden 变更」。
