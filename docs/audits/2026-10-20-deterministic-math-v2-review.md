# 当前项目确定性数学与架构审查

审查日期：2026-10-20  
当前 HEAD：`a238437`  
v2 参照：`.runs/v2ref`，HEAD `c61419c`（v2.1-beta，2026-07-04）  
审查方式：只读代码、测试、快照与运行产物；未修改项目代码。

> 修复进展（2026-10-20）：母公司 `report_type=6`、DPS 四路径统一、pack GG 加回购、现金桥 3/4 组件/缺 Capex 状态、clean-room 现金桥、snapshot/config/formula 闭合、ResearchDecision 默认禁用 + 显式 allow、路径漂移、fast screen 缺失 FCF 已修；Phase 0 又统一 engine/analysis/pack/CLI 的 floor 计算、finalize 的 decision-aware data pack、债务组件完整度、QA data_coverage、旧 snapshot formula 保护，以及 A 股 Data Pack 2.0（应收/存货/合同负债/预收/预付/OCF-净利润/股东/主营），以及 PDF 对上述经营质量字段的确定性提取/审计映射。仍保留：债务数值仍是存在项求和（只补状态）、QA research_quality、货币旁路、CAGR/单位等 P2。

---

## 结论

当前项目**仍然存在架构漂移，且漂移已经影响到数字正确性**。

一句话：

> **确定性内核本身大多算对了，但同一批数字有多个独立实现；报告、数据包、KPI、因子引擎、clean-room 之间会给出不同结果。**

最严重的不是某一个公式写错，而是：

```text
同一个 AA / DPS / GG / floor
→ engine 一套
→ report.pack 一套
→ report.analysis 一套
→ cli.kpi_summary 一套
→ cleanroom_worker 又一套
```

这导致“同一 snapshot”可以产出互相矛盾的确定性输出。

同时仍存在若干真实计算缺陷：

1. 推导现金桥的收入/流出口径不一致；
2. 数据包 GG 漏加回购 O；
3. 只有数据包修了 DPS 未完成财年，引擎/报告/KPI 没修；
4. SBC/回购没有进入 λ 敏感性与 k*；
5. 缺失 Capex 时 FCF=OCF，缺失债务时只汇总部分债务；
6. clean-room 仍保留旧现金桥逻辑；
7. 母公司现金疑似取错 Tushare `report_type`；
8. snapshot ID、config hash、formula version 不闭合。

---

## 一、架构漂移

### 1. 名义架构

```text
Facts → Metrics → Factor Engine → Report Snapshot → Jinja2
```

目标架构文档要求：

- 数字只来自确定性代码；
- Agent 只写 claim/evidence；
- 同一 snapshot 可复现；
- 报告数字只能通过 metric placeholder 解析。

### 2. 实际数据流

```text
                          ┌─ engine.py (R/GG/floor/DPS/OE)
StatementRow → metrics ───┼─ pack.py (data_pack 的 R/GG/floor/AA/DPS)
                          ├─ analysis.py (report 的 floor/DPS)
                          ├─ cli.kpi_summary (KPI 的 R/GG/floor/DPS)
                          └─ cleanroom_worker.py (独立复算，但公式已旧)
```

`report/snapshot.py` 会再生成一次 `render_analysis`，`snapshot.render` 又维护一份 `metric_map`。  
`registry.py` 的 docstring 自己也承认：

> “unmigrated report values remain code-rendered and are visible as remaining drift.”

这不是“同一个函数被多次调用”，而是**同一组公式被多次重写**。

### 3. 直接后果

#### 3.1 600941 报告与数据包不一致

同一份 `.runs/designfix/600941.SH`：

| 指标 | 报告 | 数据包 |
|:--|--:|--:|
| DPS 3 年均值 | 3.9614（引擎/分析） | 4.5946（pack） |
| 底价均值 | 92.88 | 97.10 |
| 口径分歧 | 45.07% | 51.67% |
| 股息隐含价 | 132.05 | 153.15 |

原因：

- `pack.py` 的 `average_dps` 已排除未完成 FY2026；
- `engine.py`、`analysis.py`、`cli.py` 仍把 FY2026 中期 2.51 计入。

结果同一份报告内部也矛盾：

```text
股息率 = 4.49%    （snapshot/pack 口径）
底价股息隐含价 = 132.05（engine 3.9614 口径；按 4.49% 应为 153.15）
```

#### 3.2 数据包 GG 漏加回购

- `engine.py` 的 GG 包含 `ctx.buyback`；
- `pack.py` 的 GG 传 `Money.zero(currency)`；
- `pack.py` 的 R 却包含回购。

demo 实测：

```text
engine/report GG = 5.60%
data pack GG     = 5.04%
```

有回购的公司会出现报告与数据包 GG 不一致。

#### 3.3 research decisions 只影响报告，不影响数据包

`render_data_pack()` 没有 `decisions` 参数。研究选择：

```text
G / payout / tax / AA / scenario
```

只会进入 `snapshot.render` → `engine.run` → 报告；数据包仍是默认值。

所以 `/turtle-full` 只要研究层做出 decision：

```text
报告 = decision 后结果
data_pack = 默认结果
```

两者不再对应。

#### 3.4 finalize 复制旧 data_pack

`finalize.py` 使用 `shutil.copytree(source, target)`，然后只重新渲染 report，不重新渲染 data_pack。  
因此：

- run 之后修改代码；
- 或研究 decisions 改变输入；

data_pack 仍是旧版本，final report 是新版本。

---

## 二、真实计算缺陷

### P0-1 推导现金桥的收入/流出口径仍不一致

当前 `cashflow.py`：

```text
true_cash = cash_in                    # 实际销售收现
outflows = inflow_total − OCF          # 全部经营流出（含其他经营项目的流出）
surplus = true_cash − outflows − capex
```

代数展开：

```text
surplus = OCF − capex − (inflow_total − cash_in)
        = OCF − capex − 其他经营流入
```

也就是说：

- 扣除了**所有**经营流出；
- 但没有计入**其他经营流入**。

这不是简单的“保守”，而是**收入与流出不同基准**。

复现（600887 snapshot）：

```text
AA_2y（当前）        = 10,691,424,354
OCF − Capex 两年均值 = 14,534,349,203
差额                 = 其他经营流入
GG 5.13% → 6.85%
margin 1.47pp → 3.20pp
```

后者跨过 1.5pp 仓位阈值，可能把“观察/50%”变成“买入”。

**判断：**

- 如果 AA 定义为“全部经营现金结余”，当前算法错误；
- 如果 AA 定义为“仅销售收现覆盖全部经营支出”，这是保守口径，但必须在文档、标签、测试中明确，不能叫“真实现金收入−经营流出”的中性 AA；
- 当前测试 `tests/test_cashflow.py:51-72` 把该口径固化了，但没有说明它排除了其他经营流入。

**建议：**

1. 推导流出时令 `true_cash = inflow_total`（等价 OCF−Capex，基准一致）；或
2. 该年直接回退 `OCF−Capex`，标 `complete=False`；或
3. 如果坚持销售收现口径，必须只扣销售相关流出，并在标签写“销售收现保守口径（不含其他经营流入）”。

---

### P0-2 母公司现金疑似取错报表类型

代码：

```python
# src/turtlefw/cli.py:368
parent_rows = provider.statements(code, report_type="4")
```

但：

- `docs/data-sources.md:22`：“Tushare 文档定义 **6** 才是母公司报表”；
- `README.md:438`：A 股母公司使用 `report_type=6`；
- v2 `financials.py:534-540` 使用 `report_type="6"`；
- `docs/p0-p1-fixes.md:88` / `docs/tushare-fields.md:14` 仍写 4，文档自身冲突。

`report_type=4` 通常是“调整合并报表”，不是母公司报表。  
600941 observed `parent_cash=242,275,000,000` 正好等于 2024 年合并货币资金，进一步支持这个怀疑。

**影响：**

- 因子 1B 的“母公司现金/合并现金”检查；
- 现金上游否决；
- 报告中的治理/控股结构判断。

**必须 live 复核 Tushare 返回，然后统一改成 6（或从 provider 读取明确的报表类型）。**

---

### P0-3 报告/数据包/指标账本使用不同的 R/GG/floor 口径

除 DPS、回购外，还有：

- `pack.py` 在 OE/AA 缺失时用 `Money.zero`，R/GG 变成 0.00%，而 engine 返回 None/“—”；
- `analysis.py` 重新计算 floor，而不是消费 engine 的 `floor`；
- `registry.py` 的 `payout.mean.value` 是原始支付率均值，`display` 却来自引擎推荐值；
- `snapshot.render` 的 research placeholder 使用 probe metrics，但报告正文/数据包又各有一套。

**影响：**

- 研究 placeholder 可能引用与报告正文不同的数字；
- numeric audit 只能验证“某个数字在来源中出现过”，不能验证语义；
- 报告结论与数据包/指标账本可能不一致。

**建议：**

引入唯一的 `MetricSnapshot`（或 `ReportComputation`）：

```text
inputs + decisions
  → 一次计算
  → R/GG/II/margin/floor/premium/DPS/OE/AA
  → 同时供 report、pack、kpi、research placeholders、cleanroom 使用
```

禁止各模块重新实现同一公式。

---

### P0-4 snapshot ID / config hash / formula version 不闭合

#### snapshot ID

`finalize.py` 渲染报告时：

```python
snapshot_id=_snapshot_id(inputs.rows)
```

而 `report --snapshot` 使用：

```python
manifest.snapshot_id
```

现有 600941 产物：

```text
报告 header: 2ae7026f403e6f72
manifest:    02934373ad92ac327727f75e230c7a0d
```

最终报告显示的快照 ID 与 manifest 不一致。离线复现时，header 会变化，可能导致 `report_hash` 校验失败。

#### config hash

`config.py:save_snapshot()` 只序列化部分配置，未包括：

- `g_default`
- `default_rf`
- `divergence_threshold`
- `max_pledge_pct` 等 screening 字段

这些字段会改变结果，但 `config_hash` / `snapshot_id` 不变。

#### formula version

`FORMULA_VERSION = "2026-10-19.1"` 在最近多次公式修复后仍未更新。  
同一 `snapshot_id` 可以因为代码变更而渲染出不同报告，违背 snapshot 语义。

**建议：**

- 报告与 manifest 统一使用 final snapshot ID；
- config hash 序列化完整有效配置；
- 每次公式变更 bump formula version，或把代码/公式 hash 纳入 manifest；
- `finalize` 校验 source manifest 的 formula version。

---

### P0-5 确定性边界被 ResearchDecision 松动

`ResearchDecision` 允许 LLM 选择：

```text
g / payout / tax / aa / scenario
```

并直接进入 engine：

- `engine.py:143-149` G
- `engine.py:153-164` payout
- `engine.py:185-194` tax
- `engine.py:208-214` AA
- `engine.py:261-267` scenario

`research.py:516-542` 只要求 `selected ∈ candidates`，**不要求 decision 有 evidence**。  
模型可以无证据地把税率从 0 改到 20%，把 G 从 0.85 改到 1.50，从而改变 R/GG/结论。

旧文档仍写：

- “LLM 不能改数字”
- “代码算死”
- “税档只展示”

这些已经过时。

这不是说 decision 一定不该存在；它是“受限选择”，不是“自由计算”。  
但必须：

- decision 必须有 evidence 或明确标记为 `judgment`；
- 报告必须显示 decision 来源和影响；
- 文档改写为“LLM 只能做受约束的数字选择”。

---

## 三、其他真实缺陷

### P1-1 SBC / 回购没有进入 λ 敏感性与 k*

`engine.py` 中：

```text
aa_net = aa − SBC
GG     = (aa_net × M × (1−Q) + O) / 市值
```

但 λ 敏感性传的是 `aa`，不是 `aa_net`；`revenue_sensitivity` / `break_even` 也不含 O。  
结果：

- `k=1` 的情景 GG 不等于展示的 GG；
- 有 SBC 时，00700 约 13% 的 SBC 被漏掉；
- k* 和情景方向系统性偏移。

### P1-2 `scenario_gg_10/20/30` ledger 与报告展示不一致

- 报告展示来自 `sensitivity`（λ 口径）；
- `values` 中的 `scenario_gg_10/20/30` 用 `gg × k` 等比缩放。

00700 实测：

```text
报告：1.02% / 0.74% / 0.45%
ledger：1.18% / 1.04% / 0.91%
```

研究 placeholder 可以引用到错的一版。

### P1-3 数据包把缺失 OE/AA 当成 0%

`pack.py`：

```python
Money(oe, currency) if oe is not None else Money.zero(currency)
Money(aa_net, currency) if aa_net is not None else Money.zero(currency)
```

缺失时：

- R/GG = 0.00%；
- “R 判定 = below_rf”。

引擎同路径返回 None/“—”。缺失被当成确定性失败。

### P1-4 缺 Capex / 债务组件时静默变成 0 或部分和

- `statements.fcf_series`：`capex or 0` → FCF = OCF；
- `cashflow`：capex 缺失时 `complete=True`；
- `interest_bearing_debt`：只汇总存在的债务项；
- `net_cash`：债务缺失时仍能返回“净现金”。

影响：

- FCF 收益率、min_fcf、AA 回退、净现金、EV/EBITDA 全部可能偏乐观；
- 文档说“缺失即 FCF/现金桥缺失”，代码没有遵守。

### P1-5 现金桥“3/4 流出组件”被标成完整

```python
outflows = sum(present) if len(present) >= 3 else None
...
complete = True
```

只缺一个流出组件时，仍标 `cash_bridge / complete=True`，覆盖率计入完整桥。  
应要求 4 个组件齐全，或标 `derived_bridge / complete=False`。

### P1-6 clean-room 仍是旧现金桥逻辑

`cleanroom_worker.py:300-307` 仍然：

```python
if derived:
    true_cash = revenue − AR − prepay − advance...
```

和主引擎的新逻辑不同；且公式差异 ≤25% 只记 info。  
因此 clean-room 无法验证本次修复，甚至会“证明旧错误是对的”。

### P1-7 research 证据/语义边界有洞

- `research.py:443-445` 对 `source_type="data"` 跳过 URL 校验；
- `tests/fixtures/dsh_research_sample.json` 的 `data:governance` 无 URL；
- 报告证据表出现空来源；
- D6 claim 把 `parent_cash_ratio` 写成“母公司现金/市值”，实际 metric 是“母公司现金/合并现金”；
- `research.audit` 只校验 placeholder 能解析，不校验语义；
- `load_payload` 不检查 `unknowns` / `param.label` 中的裸数字。

**数字可追溯 ≠ 语义正确。**

### P1-8 QA/研究质量门槛偏弱

- `qa.data_coverage` 即使有 missing 也返回 PASS（只把 missing 写进 detail）；
- `research_quality` 只要求 1 claim / 1 dimension，弱于 `finalize --min-claims 6 --min-dimensions 3`；
- `numeric_audit` 的 `coverage` 使用“去重 unknown 数 / 总 token 数”，不是逐 token 覆盖率；
- `research_audit` 只检查结构计数。

### P1-9 显式 `--currency HKD` 可能静默混币

`tushare_provider.statements(currency=HKD)` 只改标签，不把人民币报表折算成 HKD；  
但行情/市值按 HKD 处理，8% 左右混币。

### P1-10 路径漂移

默认输出已是 `.runs/`，但：

- `.claude/commands/turtle-analysis.md`
- `.claude/commands/turtle-full.md`
- `.claude/skills/turtle-analysis/SKILL.md`
- `prompts/agent/*`

仍有 30+ 处 `output/<code>/...`。按这些入口执行会写错目录。

### P1-11 full / analysis / research 语义分裂

- `/turtle-full` 是 deterministic + D1–D6 research，但**不产 qualitative**；
- `/turtle-analysis` 产 qualitative，但**不产 D1–D6 research**；
- 两套定性栈并存：
  - `qualitative.json`：6 模块，供 1A/1B；
  - `research.json`：D1–D6，供报告章节/decisions；
- 没有单一入口同时产出两者；
- 文档和用户容易把 `/turtle-full` 当成“完整分析”。

---

## 四、公式审计结论

| 公式/模块 | 数学正确性 | 当前状态 |
|:--|:--|:--|
| R = (OE×M×(1−Q)+O)/MC | ✅ 公式 | ⚠️ OE/数据包/报告多路径；与 v2 的 C 基准不同 |
| GG = (AA_net×M×(1−Q)+O)/MC | ✅ 公式 | ❌ AA 基准不一致；pack 漏 O；λ/k* 漏 SBC/O |
| II = max(floor,Rf+spread) | ✅ | A/HK 正确；US 使用 HK 门槛，需明确 |
| margin = GG−II | ✅ 数值 | 展示为 `%`，实际是 pp，语义易误读 |
| AA = 现金收入−经营流出−Capex | ⚠️ | 收入/流出基准不一致；缺失/3 组件/回退 |
| FCF = OCF−|Capex| | ✅ 公式 | ❌ 缺 capex 时 FCF=OCF |
| OE = NI+D&A−D&A×G−ΔWC | ✅ | ⚠️ D&A 部分缺失；标签已修 |
| G 网格 | ✅ | 缺 D&A 时默认 G；可接受但需标注 |
| M 三法 | ✅ | 事件、现金流、DPS/EPS；有数据依赖 |
| 税档 | ✅ | HK 两档同 20%；US 默认 10% |
| 底价五法 | ✅ 公式 | ⚠️ 净流动资产只扣有息负债；DPS 多路径 |
| composite median/mean | ✅ | 负锚点已过滤；配置实际行为一致 |
| premium | ✅ | — |
| CAGR | ✅ 数学 | 标签“5 年”实际 4 个年度间隔 |
| DCF/DDM/PE/PEG/PS | ✅ 公式 | 假设硬编码；未并入主报告；无 peer/SOTP |
| λ 敏感性/k* | ✅ 公式 | ❌ 漏 SBC/O；scenario ledger 错 |
| 排序/筛选 | ⚠️ | pandas float/NaN；fast 缺失 FCF 填 0 |

---

## 五、v2 对比（当前最新）

### 5.1 架构

| 项 | v2.1-beta | 当前 |
|:--|:--|:--|
| 入口 | Claude prompts：BA → turtle → valuation | CLI + Claude commands + DSH skills |
| 谁算数字 | Python 网格 + LLM 选行/写报告 | Python 算；LLM 写 research，但 decision 可选 G/M/tax/AA |
| 审计 | 定性报告有 CM/一致性/clean-room/LLM audit；龟龟报告无门 | 全报告 numeric traceability/QA；clean-room 尚未同步 |
| 快照 | 无 snapshot/hash | manifest/snapshot，但 ID/config/formula 有缺口 |
| 数据 | A/HK/US、28 接口、PDF-first | A 完整；HK 部分；US 实验；PDF 章节/evidence |

### 5.2 方法

| 能力 | v2 | 当前 |
|:--|:--|:--|
| 现金桥 | 11 步 S/T/U、W1–W4、V1/V5、X1/X2； revenue-based | 实际收现 + 经营流出 + Capex；推导/间接/PDF；未覆盖 V/X |
| 因子 3 | AA_2y/all/excl、λ、税档 | 同有多数，但 AA 基准缺陷；SBC/O 未贯通 |
| G/M/税档 | Python 网格，LLM 选 | 12 档 G、M 三法、AA/税档；默认确定性 |
| 估值 | 1516 行 engine；DCF/DDM/PE/PEG/PS/WACC/敏感性 | 纯函数 DCF/DDM/PE/PEG/PS/5×5/反推；无 peer/SOTP |
| D1–D6 | 45 参数、PDF-first、36 行业锚点 | claims/params/decisions + evidence schema；深度靠模型 |
| 报告 | 9 章 + Thesis Card + HTML | 9 节 + 基础 Thesis + 轻量 HTML |

### 5.3 质量/测试

| 项 | v2 | 当前 |
|:--|:--|:--|
| 测试 | 923 collected；valuation/html 零测试；154 项 legacy prompt | 346 passed；公式/快照/research 测试；无跨模块不变量/golden/live CI |
| 质量门 | CM/一致性/clean-room/LLM audit；AUDIT_RESULT 自报 | numeric audit/QA；clean-room 旧逻辑；research_quality 1/1 |
| 可复现 | 无 | snapshot/manifest；ID/hash 缺口 |

### 5.4 结论

- **v2 仍然领先**：PDF-first 定性深度、45 参数、行业锚点、因子 3 全调整、数据覆盖（港股/美股母公司、股东/分部/质押/回购）、估值广度、报告厚度。
- **当前项目仍然领先**：Decimal/Money、确定性 CLI、snapshot/QA、可测的纯函数、研究 evidence schema、无 LLM 改最终报告。
- **但当前项目正在向 v2 的“LLM 选表”靠拢**：ResearchDecision 允许无证据改变 G/M/Q/AA。若继续扩大，会失去“数字确定性”的核心差异。
- **v2 也不应被当作正确性标杆**：其 valuation beta 档位 10× 错误、CM 只有 A 股行名、阈值矛盾、无 snapshot、LLM 自报审计。

---

## 六、修复优先级

### P0（先修，否则结论不可信）

1. **统一现金桥基准**：`inflow_total` 配总流出，或明确“销售收现保守口径”；更新测试。
2. **单一计算源**：engine/pack/analysis/kpi/cleanroom 共用同一个 `MetricSnapshot`；禁止重复公式。
3. **修母公司 `report_type`**：live 确认 6，修 `_governance` 和 coverage。
4. **修 snapshot 闭合**：final ID、config hash 全字段、formula version bump。
5. **修 pack/data pack**：GG 加 O；缺失 OE/AA 不转 0；decisions 进入 pack 或明确 pack 不反映 decision。

### P1

6. DPS 全路径统一排除未完成财年。
7. SBC/O 进入 λ、k*、scenario ledger。
8. FCF/债务/D&A 缺失三态。
9. cash bridge 只有 4/4 组件才 complete。
10. clean-room 同步新公式并降低容差/加测试。
11. research decision 增加 evidence/来源约束。
12. `research.py` data evidence URL、semantic audit、QA 1/1 门槛。
13. 修 30+ 处 `output/` 路径漂移。
14. 明确 full/analysis/research 的产品语义。

### P2

15. CAGR 标签、margin 单位、cash_adj_pe 命名。
16. HK 税档重复/历史复权、buyback 单位、config fields。
17. fast screen 缺失值、screener float/NaN。
18. 文档同步：README run 流程、report_type、v2 基线、测试数、负锚点、time 依赖。

---

## 七、测试建议（最关键）

当前 346 项测试全绿，但没有阻止上述漂移。至少补：

```text
1. engine R/GG/floor/DPS == pack 同一输入
2. engine R/GG/floor/DPS == analysis == kpi_summary
3. 缺失 OE/AA/Capex/debt 时输出 None，不是 0
4. derived AA：true_cash 与 outflow 同基准
5. 3/4 流出组件不得标 complete
6. GG 对 O 单调；k=1 的 λ 情景 == 展示 GG
7. scenario_gg_* ledger == 报告展示
8. 完整/推导/OCF 三种现金桥的标签/coverage
9. DPS 四路径一致（pack/engine/analysis/kpi）
10. 同一 snapshot finalize 后 header ID == manifest ID
11. 修改 config 字段必须改变 config_hash
12. cleanroom AA/OE/R/GG 与 engine 差异 < 0.01
```

---

## 八、审查边界

- 未修改任何项目文件；
- 未重新取数；
- 所有复算基于现有 snapshot 和只读脚本；
- 测试基线 346 passed（本次未修改代码）；
- 工作区在审查时干净。

**最终判断：当前项目不是“数学公式整体错误”，而是“确定性内核已被多路径实现和受限 LLM decision 侵蚀”。先统一计算源和现金桥基准，再谈追 v2 的覆盖与深度。**
