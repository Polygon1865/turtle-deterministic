# 目标架构：确定性内核 + 研究信息层 + Agent 编排

> 原则：**数字只来自确定性代码；Agent 只生产“有证据的陈述”；报告由渲染器组装。**  
> 不在现有内核上改公式，新增层全部叠加；任何时刻都可以退回“无 Agent”模式。

## 1. 三层架构

```text
┌─────────────────────────────────────────────────────────────┐
│ 3. Research / Agent 层（可关闭）                              │
│  PDF 证据 → D1–D6 claims → 行业/竞对/管理层 → 报告研究段落      │
│  只写 claim/evidence，不写数字；数字用 placeholder 引用          │
└──────────────────────────▲──────────────────────────────────┘
                           │ fact_id / metric_id
┌──────────────────────────┴──────────────────────────────────┐
│ 2. Facts 层（确定性、可复现）                                  │
│  provider → 标准化报表 → metrics/grids → snapshot → fact ledger │
│  MetricPoint / DocumentFact / Evidence / SourceRank             │
└──────────────────────────▲──────────────────────────────────┘
                           │ raw files / API responses
┌──────────────────────────┴──────────────────────────────────┐
│ 1. Data 层（provider 可替换）                                  │
│  Tushare / HKEX PDF / SEC EDGAR / yfinance / 公告              │
│  period-aware、source ranking、PIT snapshot                    │
└─────────────────────────────────────────────────────────────┘

4. Audit 层（横切）：numeric audit / citation audit / consistency / clean-room / CI
```

关键约束：

1. **Agent 不参与算术**：不把 R/GG/底价/估值写进 prompt 让 LLM 算；Agent 只引用 `metric_id`。
2. **报告数字必须可解析**：研究段落里的数字只能是 `{{metric:r}}` / `{{fact:...}}`，渲染器填值；自由数字被 numeric guard 拒绝。
3. **每个 claim 必须有证据**：`evidence_id` + URL/page/quote；没有证据只能写 `unknown`。
4. **同一 snapshot 可复现**：数据/文档/研究 artifact 都有 hash；确定性部分逐字节一致。
5. **Agent 层可关闭**：关闭后仍能生成当前 Markdown/HTML 报告；研究段落为空或 `unknown`。

## 2. Facts 层设计

### 2.1 数据模型

```python
MetricPoint:
  id, name, value, unit, currency
  period: "2025A" | "2025H1" | "2025Q3"
  basis: "consolidated" | "parent"
  annualized: bool
  formula_id: "cash_bridge.aa_2y"
  source_fact_ids: list[str]
  snapshot_id, computed_at
  coverage: "ok" | "partial" | "missing"
```

```python
DocumentFact:
  id, document_hash, page, section
  label, value, unit, currency
  table_id, row/col
  extraction_method: "pdfplumber" | "manual" | "agent"
  confidence
  source_url
```

```python
Evidence:
  id, source_type: "document" | "web" | "data"
  url, page, quote, retrieved_at
  content_hash, source_rank
```

### 2.2 Source ranking

| 优先级 | 来源 | 用途 |
|:--|:--|:--|
| 1 | 年报/公告 PDF原文 | 会计数字、附注、MD&A、治理 |
| 2 | 交易所/巨潮/HKEX | PDF 获取与校验 |
| 3 | Tushare | 结构化报表、行情、分红、股东 |
| 4 | yfinance/SEC | 港股/美股补充 |
| 5 | 网页/行业数据 | 仅定性证据，需 URL+引文 |

同一指标多源冲突时：不自动覆盖，写 `discrepancy`，报告显示主源+冲突源。

### 2.3 Period / PIT

- `MetricPoint` 强制带 `period` 和 `annualized`；禁止拿 H1 和 FY 直接比较。
- 中报/季报：H1×2、Q1×4、Q3×4/3，标记 `annualized=True`；报告明确“年化参考”。
- PIT：`SnapshotStore(as_of, provider_version, raw_hash)`；`--as-of` 使用当时行情/上市状态/财务快照；财务快照需先回填历史，不能拿最新报表冒充 PIT。
- 暂不支持的（US、港股分部）标记 `not_applicable`，不猜。

## 3. Research 层设计

### 3.1 D1–D6 schema（不照抄 38 参数）

每个维度是**固定字段 + evidence 必填**，不是自由作文：

```json
{
  "dimension": "D2_moat",
  "claims": [
    {
      "claim_id": "D2.1",
      "statement": "品牌与渠道构成主要护城河",
      "judgment": "positive",
      "confidence": "high",
      "evidence_ids": ["ev_012", "ev_018"],
      "as_of": "2025-12-31",
      "unknowns": []
    }
  ]
}
```

- D1 商业模式/资本特征；
- D2 护城河（Greenwald 六步）；
- D3 外部环境/政策；
- D4 管理层/治理（承诺 vs 兑现）；
- D5 MD&A/前瞻信号；
- D6 控股结构/母公司/子公司/股东。

规则：

- 每个 claim 至少 1 条 evidence；没有 → `unknown`；
- 数字只能引用 `metric_id`，不能自由写；
- 行业/竞对表用结构化 `CompetitorFact`，带期间和来源；
- 38 参数不是目标，目标是**每个重要判断有出处**。

### 3.2 报告组装

```text
deterministic blocks: KPI / 财务趋势 / 因子 1–4 / 底价 / 估值 / Thesis Card
research blocks:     D1–D6 / 行业 / 竞对 / 管理层 / MD&A / 控股结构
audit block:         data issues / discrepancies / clean-room reviews
```

渲染器只接受：

- `{{metric:r}}`、`{{metric:gg}}` → 从 MetricPoint 解析；
- `{{fact:...}}` → 从 DocumentFact 解析；
- `{{claim:...}}` → 从 research JSON 解析，附 evidence 脚注。

数字 guard：报告/叙述里出现非 placeholder 的数字 → 拒绝（年份/页码/法规编号白名单除外）。

## 4. Agent 自动化设计

### 4.1 编排器

```text
run_state.json
  phase: data → document → research → compose → audit
  artifacts: data_pack, pdf_sections, footnotes, reported_numbers,
             research.json, report.md, audit.json
```

每阶段：

- 输入/输出 JSON schema；
- 失败可重试/降级（无 PDF → 网页证据；无 evidence → unknown）；
- 成本/步数预算；
- 断点恢复；
- 不把上一阶段自然语言当契约，只传 artifact 路径和 schema。

### 4.2 Agent 角色

| Agent | 只读 | 只写 | 禁止 |
|:--|:--|:--|:--|
| Extractor | PDF/footnotes | document_facts.json | 猜数字/改报表 |
| Researcher | facts/evidence/industry | research.json | 写报告、算指标 |
| Writer | research + metrics | narrative.md | 新数字/改结论 |
| Auditor | 原始数据+报告 | audit.json | 读草稿（clean-room） |

### 4.3 工具边界

Agent 只能调用白名单工具：

- `get_metric(id)`、`get_fact(id)`、`search_documents(query)`、`get_footnote_table(section)`；
- `write_claim(schema)`、`write_evidence(schema)`；
- 不提供 `write_report`、`calculate`、`edit_metrics`。

### 4.4 与 Claude Code 的关系

现有 `.claude/commands` 是入口；新增的 Python 编排器是**可选执行器**，不绑定 Claude：

- 本地/CI 可用 fake LLM 跑契约测试；
- 生产可用任意 LLM，只要求输出 schema；
- 没有 LLM 时，研究块为空，确定性报告仍完整。

## 5. Audit 层

1. **Numeric audit**：CLI vs PDF reported_numbers（已有）；
2. **Citation audit**：每个 evidence URL/page/quote 可校验；claim 无证据 → fail；
3. **Consistency audit**：结论/仓位/止损 vs research claims；数字 placeholder 解析失败 → fail；
4. **Clean-room**：独立进程，只读原始数据/PDF，不读草稿；输出 `cleanroom.json`；
5. **CI**：离线（pytest + 核心 mypy）→ nightly live smoke → release golden。

## 6. 数据覆盖路线

| 能力 | 现状 | 目标 |
|:--|:--|:--|
| A 股报表/治理/股东/主营 | 已接 | 保持 |
| 港股报表/行情/分红 | 已接 | 保持 |
| 港股股东/分部 | Tushare 无 | PDF 表格 + HKEX 公告 |
| US | 未接 | SEC companyfacts/submissions + yfinance 价格 |
| 中报/季度 | 数据包参考 | MetricPoint 年化 + TTM |
| PIT | 行情/上市状态部分 | SnapshotStore 回填财务 |
| 缓存刷新 | 无 | TTL + `--refresh` |
| 历史退市 | 部分 | `stock_basic` L/D/P + 历史快照 |

## 7. 实施顺序（保证不牺牲现有特性）

### Phase 1（先做，1–2 周）
- 引入 `Fact/MetricPoint/Evidence` 数据模型 + snapshot ID；
- 报告 composer 支持 placeholder；numeric guard；
- 现有 CLI 输出改为写 facts 后渲染（行为不变，测试保持）。

### Phase 2（2–3 周）
- PDF section schema + D1–D6 research schema；
- Extractor/Researcher 的 fake-LLM 契约测试；
- 附注表（P3/P4/P6）接到 claim；
- 报告研究段落 + 引文脚注。

### Phase 3（2–3 周）
- 中报/TTM、PIT snapshot、港股分部/股东 PDF；
- US provider（SEC + yfinance）；
- data pack 已扩到 16 段（口径/审计、现金桥、PDF 状态、TTM、公式、数据覆盖）；

### Phase 4（2 周）
- Agent 编排器、clean-room runner、live CI、golden set；
- 20–30 样本误报率评估。

## 8. 验收标准

- **确定性**：同一 snapshot + 同一 research artifact → 报告逐字节一致；
- **数字**：报告/叙述中 100% 数字可解析到 `metric_id`/`fact_id`；
- **证据**：非 unknown 的 claim 100% 有 evidence；无证据自动降级；
- **可关闭**：无 LLM 时仍生成完整的确定性报告；
- **数据**：period/annualized/source_rank 在数据包可见；
- **审计**：numeric/citation/consistency 三类失败可定位到 artifact；
- **测试**：fake LLM 契约测试 + 现有 404 测试不回退。

## 9. 明确不做

- 不让 Agent 重算 R/GG/底价/估值；
- 不把报告编辑权交给 Agent；
- 不为了“38 参数/1000 行”堆内容；
- 不把 clean-room 做成 LLM 自评；
- 不用最新财务冒充 PIT；
- 不因为数据缺失就猜数（保持 tri-state）。

## 10. 执行记录：Phase 1–2（2026-10-19）

已完成：

- `facts.py`：canonical JSON、content hash、`MetricPoint`、`Evidence`、`ResearchClaim`、`ReportManifest`；
- `research.py`：D1–D6 schema、claim/evidence 校验、数字字面量拦截；`turtle research --file`；
- `turtle snapshot`：生成 `manifest.json`，含 facts/config/research/template/report hash 与 `snapshot_id`；
- 报告确定性：
  - 移除 `datetime.now()`；
  - 52 周窗口改用 `as_of`，不再用 `date.today()`；
  - `render_data_pack`/`render_analysis` 增加 `as_of`；
- **离线 snapshot 渲染**：
  - `report --save-snapshot DIR` 冻结 rows/dividends/quote/history/治理/PDF/research/qualitative/config；
  - `report --snapshot DIR` 不访问 provider；
  - 实测 live vs offline 报告 SHA256 相同；
- **Research composer**：D1–D6 claim 用 `{{metric:r}}` 占位符解析，附证据链接，写入报告第十节；
- **Agent artifact 契约**：`turtle agent --dir` 检查 data/document/research/compose/audit 五阶段；
- **Clean-room 建议型**：`turtle cleanroom --snapshot --pdf-numbers`，独立源数值对比，输出 review；
- **TTM**：数据包 TTM 表 + `analyze/report/valuation --ttm` 合成年度行，沿用原引擎公式；
- **US（实验）**：yfinance 三大报表/行情/分红映射，补 `Total Debt`/`Goodwill`/SBC，`analyze AAPL` 可跑；
- **HK PDF 语义**：`pack --pdf-sections` 从 P4/MDA 抽股东与分部收入，校验分部合计=The Group；
- **PDF 附注进入数据包**：`pack --footnotes footnotes.json` 增加附注表格摘要；
- **MetricRegistry v1**：引擎新增 typed `FactorResult.values`；R/GG/II/安全边际从 Decimal 而非展示字符串进入 ledger；数据包 KPI/趋势/分红/行情/股东/分部/PDF 桥表也接 ledger；
- **DocumentFact v1**：`reported_numbers.json` 写入 `document_hash` + `document_facts`（页、标签、值、置信度）；cleanroom 输出文档 hash/fact 完整性；QA 增加 evidence 完整性检查；
- **metrics artifact 绑定**：`report --save-snapshot` 写 `metrics.json`，manifest 记录 `metrics_hash` 并在离线渲染时校验；
- **SourceRank 三档策略**：`--source-policy record-only|display-primary|engine-primary`；候选保留、冲突报告、engine-primary 显式改写输入；
- **source_id**：report snapshot 保存 provider rows/PDF 指纹或 PIT snapshot ID；
- **独立 clean-room**：`cleanroom` 通过独立子进程 `turtlefw.cleanroom_worker` 读取 snapshot+PDF，六项源审计 + 独立复刻 owner earnings/cash bridge/R/GG + document hash/rank；`--pdf-file` 可复核 PDF hash；
- **Agent fake-LLM 契约**：`ResearchAgent` + `FakeLLM`，输出必须过 research schema/evidence/numeric guard；
- **PIT 快照库**：`pit freeze/list/show/export/prune`，支持 restatement、as-of 选择、backfill 公告日累计快照；store lock + 原子 index；`pack/report --pit` 读取；
- **近似 PIT**：`pack/report --as-of` 按公告日过滤财务，市值用当日价×最新股本近似；报告标注 `[pit]` 提示；
- **DSH 输出根**：`TURTLE_OUTPUT_DIR` / `--output-dir`，受限沙箱可写 `.runs/`；
- **本地 smoke**：`turtle smoke --codes 600887,00700.HK,AAPL`，检查取数/report/snapshot/manifest；
- **manifest 校验**：`report --snapshot` 校验 facts/config/research/template/report hash；
- **测试**：`tests/conftest.py` 提供沙箱可写临时目录，404 收集 / 404 通过 / 0 setup error；
- **00700 已知差异**：收入 1.09% 解释为 Others 8,077，分区 4/7 是报告结构差异，见 `docs/00700-known-differences.md`。

尚未完成：

- **ResearchDocument v2**：D1–D6 claims + `params`（研究参数）+ `decisions`（G/M/AA/税档候选选择）；claim 只允许 `{{metric:id}}` / `{{fact:id}}`，不写裸数字；fact 来自 PDF `document_facts`；
- **全量 numeric guard**：`report --save-snapshot` 自动运行 numeric-audit，写入 `numeric_audit.json`、`numeric_hash`、`numeric_sources`；`qa` 校 hash 并**重算** coverage/unknown，不信任 manifest 摘要；600887/00700 达到 100%；
- **Agent phase runner**：`agent --command phase=cmd` 按 data/document/research/compose/audit 执行命令、校验 artifact、写 `.agent/*.log` 与 `agent_state.json`；无命令阶段只校验，不伪造 research；
- 数据包附注文本/表格摘要不进入数字 ledger（只做证据展示）；
- 少数叙述（质押/价值陷阱）未走 registry；
- 完整 vendor PIT/重述历史（本地 snapshot/backfill 已实现，但不是 vendor vintage）；
- D1–D6 仍由人工/外部 Agent 产出 `research.json`；fake-LLM 契约已有，真实模型适配未接；
- 更多港股版式的股东/分部语义回归；
- 真实 LLM 编排器、live CI、golden set；
- clean-room 已复刻 owner earnings/cash bridge，00700/600887 与 ledger 差异在舍入范围内；

### 本轮 review 修正

1. **原设计混淆了 `source_id` 和 `snapshot_id`**：raw 字节变化不应强制报告变化；已拆成 source（溯源）和 report snapshot（语义输入）。
2. **原设计假定报告已经是纯 facts 渲染**：实际 CLI 仍实时取数；Phase 1 先修确定性和 manifest，Phase 2 再做离线 snapshot。
3. **Agent 自动化不能先于 facts 契约**：没有 `MetricPoint/Claim` 校验，Agent 会重新引入自由数字；所以先做 schema/guard。
4. **US/PIT 不是“写个 provider”**：需要历史财务快照和 CIK/币种映射，放到 Phase 3。
5. **“逐字节一致”必须包含 renderer/template 版本**：否则模板改动会让旧 snapshot 无法复现；manifest 已包含。

## 12. Phase 3–4 边界与阻塞

| 项 | 状态 | 阻塞/边界 |
|:--|:--|:--|
| TTM | 已接入 | `--ttm` 把最新 interim 合成年度行；不改变公式，只改输入 |
| US | 实验可用 | yfinance 仅 4 年报表，无质押/股东/主营；字段可能变 |
| 港股股东/分部 | 已实现 00700 | `pack --pdf-sections` 从 P4/MDA 抽语义；需更多版式回归 |
| 完整 PIT | 部分 | 已实现本地 append-only snapshot + restatement/backfill；仍无 vendor 历史 vintage/重述覆盖 |
| 真实 LLM 编排 | 未做 | 无模型凭证；当前是 artifact 契约 + fake 测试 |
| live CI / golden | 未做 | 无远程仓库/secret；离线 CI 已就绪 |
| 完整 clean-room | 独立进程/复刻公式 | 00700/600887 R/GG 差异在舍入内；仍需覆盖更多公司/期数 |

这些不是“再写点代码”就能全部关闭的：PIT 需要历史数据，LLM 需要凭证，live CI 需要仓库权限。没有假装完成。
