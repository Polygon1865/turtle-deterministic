# 项目架构与报告模版评审

审查日期：2026-10-28  
当前 HEAD：`e6e8f01`  
审查方式：只读。源码通读、287 份历史报告量化、单快照重渲染、四路只读审计；未修改项目代码。  
样本口径：`.runs/**/analysis_report.md` 共 287 份，其中 229 份是 10-21→10-27 的生产报告（A 股 105 / 港股 124），下称 PROD；因模板在样本期内反复改动（同一天最多 3–8 种 H2 签名：10-22 7 种 n=73、10-23 8 种 n=63、10-26 7 种 n=47、10-27 3 种 n=40），另以 10-27 的 40 份作为「当前模板」样本。

---

## 结论

**报告已经是一份数据转储文档，而不是决策文档；更关键的是，没有任何一条流水线会因为这些缺陷而变红。**

四句话：

1. **结构没有模型。** 章节编号是模板里手写的字符串，章节是否出现由数据决定（`{{ industry_md }}`、`{{ fundamental_section }}`），编号靠 `"十三" if fundamental_md else "十二"` 这样的表达式拼出来。结果：77.7% 的 PROD 报告存在未编号二级标题，10-27 的 40 份是 40/40；「研究参数」这份同名小节每份出现 6 次。
2. **内容错配。** 结论区中位 12 行、占 2.9%；而「研究判断 D1–D6」中位占 32.6%、「补充基本面 + 市场与宏观」中位合计 15.2%（601633 这一份三者合计 61.5%）。100% 的报告都有占位小节（占全部小节的 70.5%），13.1% 的表格行含 `—`（纯占位单元格 3.9%）。
3. **证据链失效。** evidence 的 quote 字段本身就是 markdown 表格原文，渲染时被 ` · ` 拍平、按 240/280 字符截断：22 条证据里 0 条带 url、0 条带页码；同一段引文在一份报告里被重复贴出（118 条 blockquote 只有 55 条唯一）；表格层级被压平后，分项与合计平级，同一个数字以两个标签出现两次。
4. **观测面缺席。** QA 对报告的检查只有「文件存在」；`template_hash` 只哈希 `templates/` 下的 j2，不含 analysis/pack/html；唯一全文回归是 demo 分支的 sha256。因此第 1–3 条没有任何一条会让 CI 失败。

---

## 一、报告模版：十个结构性问题

### 1.1 章节编号不是模型，是字符串

当前模板 `src/turtlefw/report/templates/analysis.md.j2` 只有 171 行，`## 一、结论` 到 `## 十一、研究判断` 全部硬编码；末三节由 `analysis.py` 拼接：

```python
# src/turtlefw/report/analysis.py:164-182
fundamental_section = (
    f"## 十二、补充基本面（Tushare）\n\n{fundamental_md}\n\n" if fundamental_md else ""
)
market_number = "十三" if fundamental_md else "十二"
market_section = (
    f"## {market_number}、市场与宏观（Tushare）\n\n{market_md}\n\n" if market_md else ""
)
if fundamental_md and market_md:
    disclaimer_heading = "十四"
elif fundamental_md or market_md:
    disclaimer_heading = "十三"
else:
    disclaimer_heading = "十二"
```

模板第 165 行是三者粘合处：

```jinja
{{ fundamental_section }}{{ market_section }}## {{ disclaimer_heading }}、数据来源与免责声明
```

还有三个二级标题游离开编号之外：模板第 13 行的 `## PDF 证据`（条件渲染，出现时夹在「一、结论」与「二、因子 1A」之间）、`## 行业分类`（`src/turtlefw/report/industry.py:162`）、`## 行业模板：X`（`industry.py:214`）。三者都不参与编号。

更糟的是结构可以被数据劫持：00027.HK 的证据引文里含一段多行 markdown，渲染时 `## 13. PDF 抽取状态` 逃出引用块，直接成为报告的一级标题——同一份报告里出现 **6 次**（第 489/521/571/603/612/646 行），后面紧跟的 bullet 也一并变成了报告正文。证据内容能改写文档结构，说明「证据」与「结构」之间没有任何隔离。

实测（601633.SH 当前代码重渲染，865 行）：

| 行号 | 章节 | 行数 | 占比 | 编号由谁决定 |
|---:|---|---:|---:|---|
| 6 | 一、结论 | 20 | 2.3% | 模板写死 |
| 26 | 行业分类 | 24 | 2.8% | `industry.py:162`，无编号 |
| 50 | 研究摘要 | 8 | 0.9% | 模板写死标题，无编号 |
| 58 | 二、因子 1A | 14 | 1.6% | 模板写死 |
| 72 | 三、因子 1B | 29 | 3.4% | 模板写死 |
| 101 | 四、因子 2 | 14 | 1.6% | 模板写死 |
| 115 | 五、因子 3 | 27 | 3.1% | 模板写死 |
| 142 | 六、因子 4 | 36 | 4.2% | 模板写死 |
| 178 | 七、估值指标与底价 | 27 | 3.1% | 模板写死 |
| 205 | 八、数据问题 | 61 | 7.1% | 模板写死 |
| 266 | 九、投资论点卡 | 55 | 6.4% | 模板写死 |
| 321 | 十、来源冲突决策 | 6 | 0.7% | 模板写死 |
| 327 | 十一、研究判断 | 278 | 32.1% | 模板写死 |
| 605 | 十二、补充基本面 | 163 | 18.8% | 字符串拼接 |
| 768 | 十三、市场与宏观 | 91 | 10.5% | 字符串拼接 |
| 859 | 十四、数据来源与免责声明 | 7 | 0.8% | 字符串拼接 |

后果不止「难看」：

- 目录不可靠。`html.py:44-52` 的 `_toc_html` 只收 level==2，行业分类/研究摘要以未编号项进入目录。
- 视图靠标题前缀匹配。`html.py:124-131` 用「一、结论」「六、因子 4」「九、投资论点卡」这些字符串决定面板分组；改标题 → 静默掉进 appendix。
- 无法引用。想讨论「第五节」时，第五节在有些报告里是因子 3、在另一些里是别的东西（因为插入节的位置随 PDF/行业模板变化）。
- 测试把现状锁死。`tests/test_industry.py:77/106` 断言 `## 行业分类` 存在；`tests/test_pack.py:126/152` 断言 `## 17. 补充基本面（Tushare）`，同文件 `:172` 断言 `## 17. 市场与宏观（Tushare）`——同一个 17 号被两节占用（哪一节存在，后一节就顶上），数据包用阿拉伯数字、报告用中文序号，同一项目两套编号约定，且数据包这一套也已经会漂。

量化：PROD 中 **178/229 = 77.7%** 的报告至少有一个未编号 H2；构成 `## 研究摘要` 136 份、`## 行业分类` 89 份、`## 行业模板：X` 31 份、`## 13. PDF 抽取状态` 2 份（共 11 处，全部是引文逃逸）。10-27 的 40 份里，研究摘要 40/40、行业分类 20/40、PDF 引文逃逸 1/40（即上面 00027.HK 的 6 处）。

### 1.2 模板只做插值，布局逻辑在 Python

`analysis.md.j2` 171 行，`analysis.py` 567 行，`context` 字典约 100 个键，全部是预渲染好的 Markdown 字符串（`f1a_table`、`issues_md`、`thesis_monitor_md`…），模板里几乎没有逻辑，只有 `{% if %}` 和 `{{ }}`。

这不是「模板薄、逻辑厚」的风格选择，而是**章节由数据决定**：`{{ industry_md }}` 自带一个 `## 行业分类`；`{{ fundamental_section }}` 自带编号；`{{ research_md }}`/`research_sections` 自带 `### 研究参数`。模板无法知道最终会出现几节、编号是多少，所以编号只能由 Python 猜。

同一原因造成空行和粘连：`Environment(loader=..., autoescape=False)`（`analysis.py:564`）没有 `trim_blocks` / `lstrip_blocks`，`{% if %}` 块行各自留下换行，实测 22-25 行连续 4 个空行；`## 十、` 前后各两个空行。

### 1.3 一份报告承担四种读者，体量倒挂

| 读者想要 | 对应内容 | 601633 行数 | 占比 |
|---|---|---:|---:|
| 5 秒决策 | 一、结论 | 20 | 2.3% |
| 30 分钟论证 | 二～七（四因子 + 估值） | 147 | 17.0% |
| 审计/复核 | 八、九、十 | 122 | 14.1% |
| 原始数据附录 | 十一 + 十二 + 十三 | 532 | 61.5% |

PROD 的口径更极端：结论节中位 12 行（2.9%），十一、研究判断中位占全文 32.6%（最高 56.6%），十二+十三中位 15.2%（最高 49.1%）。

排序也不是按读者问题，而是按数据源：十二「补充基本面（Tushare）」、十三「市场与宏观（Tushare）」——Tushare 拉回来什么就贴什么。这类内容对结论的边际贡献接近零，却占了全文 1/6 到 1/2。

同时 **100% 的报告含占位小节**，占位小节占全部小节 **2448/3471 = 70.5%**；占位 token 累计 未验证 4243 / unknown 3946 / 未提供 2265 / 未取得 751 / 未接入 604（PROD）。一份报告平均有 60 处「不知道」。

### 1.4 重复：同一份 research.json 被投影五次

`research.json` 被五个函数分别渲染到五个位置：

| 渲染器 | 位置 | 内容 |
|---|---|---|
| `research.py:248 summary_markdown` | 第 50 行「研究摘要」 | 计数 + 维度覆盖 |
| `research.py:522 coverage_markdown` | 十一开头「研究覆盖」 | 计数 + 维度覆盖（与上一行重叠） |
| `research.py:596 evidence_markdown` | 十一「证据索引」 | 全量证据 + 引文 |
| `research.py:76 render_markdown` | 十一各 claim | 同一引文再贴一次 |
| `research.py:216 thesis_markdown` | 九、投资论点卡 | 由 claims 再摘要一次 |

实测后果：

- 当前渲染全文 118 条 blockquote，唯一 55 条，**63 条重复（53%）**；单条引文最多重复 7 次。
- 10-27 的 40 份报告里，1961 张表中 **521 张（26.6%）** 是同文内完全重复的副本，29/40 份受影响。全库口径：8443 张表 1610 张重复（19.1%），103/229 份受影响；最差样本一份报告 84 张表里 51 张重复。
- `### 研究参数` 每份 6 次（D1–D6 各一次），59.4% 的报告有这 6 个同名标题，全库冗余标题 680 个。原因在 `research.py:155-180`：`render_dimensions` 按 dimension 过滤 params 后，对每个维度重新调用 `render_markdown`，而 `render_markdown:124-129` 无条件输出一张「参数｜值｜置信度」表。附带副作用：`dimension` 为空或不在 D1–D6 的 params 永远不会被渲染（数据丢失）。
- 同一段证据在八（定性证据）用 `_display_quote(quote, 280)`（`analysis.py:45`），在十一（claim 内联）用 `_display_quote(quote, 240)`（`research.py:117`）——同一份证据，两种截断长度。

### 1.5 证据链退化为「原文 dump + 截断」

`research.json` 的 evidence.quote 直接存 markdown 表格原文，例如：

```
| 2026-06-30 | 2.76% | 18.37% | 2.41% | 62.00% | 10.22% | 0.29 | 10.18 |
| 2026-03-31 | 1.07% | 18.45% | 2.10% | 59.85% | 7.25% | 0.11 | 10.31 |
```

渲染后（`_display_quote`，`research.py:38-53`）：

```
> 2026-06-30 · 2.76% · 18.37% · 2.41% · 62.00% · 10.22% · 0.29 · 10.18 / 2026-03-31 · 1.07% · ...
```

八列数字，没有一个列名；两行之间用 ` / `；这份引文共有四个报告期，从第三期起被 280 字符截断成 `…`。读者无法判断 2.76% 是毛利率还是净利率，也看不到被截掉的期数。

层级同样丢失。地区收入分部被压成：

```
> 本国 · 45,813.74 · — / 地区 · 102,101.43 · — / 其他国家的 · 56,287.69 · — / 其他国家 · 56,287.69 · —
```

45,813.74 + 56,287.69 = 102,101.43：`地区` 是合计行，另外两行是分项，但拍平后四者平级，同一个 56,287.69 以两个标签出现两次。基于这段证据写出的 claim 是「最新分部表显示海外收入高于国内收入」——结论可能对，但证据本身已经不可核验。

其他硬指标：

- `snapshot/qualitative.json` 里 22 条 evidence，**带 url 的 0 条、带 page 的 0 条**，`source=research_bridge`；渲染出的来源标签 22 条全部是 `（data · 数据包）`——零信息量。
- 10-27 的 40 份报告共 2056 条 `- 证据：` 行，只有 413 条（20.1%）带 `data_pack://`/`tushare://`/`pdf://` 任一来源定位；其余只有一句标签 + 引文。
- 1089 条 claim 里 97 条（8.9%）连 `- 证据：` 行都没有。
- 截断发生在句子中间：`汇兑收益同比减少约17.59亿元(去年同…`——读者看不到后半句，也没有原文可跳转。

### 1.6 表格是字符串，不是数据

`src/turtlefw/report/format.py:42-52` 的 `_table` 直接 `" | ".join(str(cell))`，不转义；`html.py:31` 的 `_cells` 再按 `|` 切分。任何单元格里的竖线都会把表撕开。

最稳定的触发点是因子 4 的说明列：`medium（…粗算偏差 |HH|=medium…）`。结果：

- 当前模板 10-27 的 40 份报告，**40/40 都有 ragged 行**，13196 行里 841 行（6.4%），最差单份 379 行里 32 行错位。全库 285/287 份、3472 行。
- 单位缺失：取「≥5 行且 ≥5 个四位数金额」的 923 张表，**797 张（86.3%）表头没有任何单位词**；单位在 `百万元`（报告财务表）、`亿元`（`market.py:104-105` 市场数据）、`亿股`（`pack.py:328`）、`元` 之间混用。
- 占位：13.1% 的表格行含 `—`（PROD 7480/56905；10-27 口径 1526/13196）；纯 `—` 单元格 3.9%（9018/231028）。

表格本应是结构化对象（列名、单位、对齐、格式化器、转义），现在是一段拼出来的文本，所以既不能校验，也不能复用，更不能安全地嵌进 HTML。

### 1.7 结论区与因子区互相覆盖，且改写的理由不显示

`analysis.py:510-527` 组装结论表时直接改写了因子 4 的结论：

```python
"仓位建议": "不建仓" if verdict == "排除" else f4_metrics.get("仓位建议"),   # :519
"因子4 原始结论": dict(results["4"].metrics).get("结论"),                    # :521
```

结论表同时出现「因子4 原始结论」和「最终结论」两行，但**没有任何一句解释二者为何不同**。实测 PROD **48/229 = 21.0%** 的报告里二者不一致（观察→排除 44 份、买入→排除 4 份）；当前模板 10-27 是 9/40 = 22.5%。

否决原因更是硬编码在 `src/turtlefw/factors/engine.py:811-826`：

```python
def final_verdict(results: dict[str, FactorResult]) -> tuple[str, str]:
    if results["1A"].passed is False:
        return "排除", "因子1A 触发否决"
    if results["1B"].passed is False:
        return "排除", "因子1B 管理层触发否决"   # :815 —— 与 1B 里真正被否决的检查无关
```

601633.SH 的当前报告就是活例子：

- 第 8 行：`**排除** — 因子1B 管理层触发否决`
- 第 80 行：`| 现金上游障碍 | 否决 | 母公司现金/合并现金 34.1%（<50%，现金可能滞留子公司） |`
- 第 82 行：`| 管理层与治理 | 观察 | 正面（置信度 medium，2 条证据） |`

真正的否决项是「现金上游障碍」，文案写的是「管理层」。

### 1.8 结果列语义坍缩

`engine.py:783-794` 的定性检查默认 `ok_status="info"`：

```python
def _qualitative_check(..., ok_status: str = "info") -> Check:
    status = "veto" if (veto_on_negative and item.judgment == "negative") else ok_status
    return Check(name, status, detail)
```

`analysis.py:26` 把 `info` 映射成「观察」，`pass` 映射成「通过」。于是 1B 表的「结果」列只有两种值：否决 / 观察。601633 的 1B 表 8 行里 5 行显示「观察」，其中说明文字写着「正面」「负面」「中性」——列名问的是通过与否，列内容答的是定性倾向，两者对不上。同一个「通过」语义在 `STATUS` 里存在，却没有一条路径会用到它。

### 1.9 口径、单位、币种、日期四不统一

- **日期**：页首 `数据截至：20261027`，供应商原始 8 位格式，PROD 229/229 = 100%；别处出现 `2026-10-19 01:27:45`。qa/README 都要求可读日期。
- **币种**：港股 124 份里 **103 份（83.1%）** 写「报表币种：CNY」却给港元当前价，仅 6 份提到汇率；`门槛对应价` 带币种的 0/229。
- **底价**：结论表写「底价（综合）8.07」，同一份报告的证据 blob 写「底价均值 8.29 / 中位数 8.07 / 采用中位数 8.07」。均值、中位数、采用值三者并存，结论表用了一个新词「综合」，读者无法判断它是哪一个。底价在全文有 5 种叫法。
- **溢价/边际**：结论表并列「安全边际 -1.55%」与「当前价溢价 76.02%」，前者是 GG−II 的收益率差，后者是价格差，都是百分比，都在同一张表里。`当前价溢价` 与 `底价溢价` 98.7% 的时间数值相同，却起了两个名字。
- **两个价格锚**：结论表只给底价，`门槛对应价` 只在因子 4/七节出现；有该指标的报告里 55.3%（115/208）门槛对应价高于底价（中位 +11.1%），且无币种标注。
- **枚举泄漏**：`底价口径 | stable` 直接把内部枚举值写进报告。

### 1.10 沉默的空值

四条路径对缺失的处理各不相同，且都不报错：

| 位置 | 行为 |
|---|---|
| `facts.py:142-154` `display()` 未知 metric | 返回 `"—"` |
| `facts.py:156-166` `resolve()` 未知占位符 | 抛异常 |
| `analysis.py:564` Jinja 环境 | 无 `StrictUndefined`，缺变量 → 空串 |
| `html.py:147-150` `_quick_read` 抓不到 | 返回空，HTML 照写（`html.py:540-563` 无条件） |

同一份代码里「未知→破折号」与「未知→异常」并存，取决于走哪条路径。报告头「数据口径」只在 TTM 时才有值，非 TTM 报告直接缺行（601633 第 3 行就没有）。

---

## 二、架构：六个结构性问题

### 2.1 报告不是可校验的产物

- `src/turtlefw/qa.py:30`：`add("report", (base / "analysis_report.md").is_file())`——报告这一行的全部含义是「文件在」。
- QA 共 13 行：run_state / report / data_coverage / qualitative / evidence / discrepancies / narrative / research / research_provenance / research_audit / unknown_ratio / numeric_coverage / research_refs+research_quality。判定只有三种：文件存在、JSON 自洽、数字 token 可回溯（`numeric_audit.py` 阈值 0.9999）。**没有一条检查 Markdown 的结构。**
- `report_hash` 不匹配时，`qa.py:200-212` 会退回到「最近一个带 numeric_coverage 的 manifest」继续审数字——审的根本不是当前这份报告。
- 路径也不一致：同一份定性证据，报告从 `snapshot/qualitative.json` 读（1B 表显示 5 模块 22 条证据），QA 从运行产物目录（与报告同级）的 `qualitative.json` 读（`qa.py:46`）。601633 的这个文件只在 snapshot 里，于是 `qa.json` 写着「未提供（research-only；1A/1B 未验证）」，而报告里 1A/1B 有完整定性判断。**QA 的结论与报告内容互相打脸，且没人发现。**
- 发布链把「存在 + 数字可溯」当合格：`daily.py:657` 只读 qa.json，`daily.py:682-684` PASS/WARN 即 ok，`publish_partial` 默认 True，`tests/test_daily.py:500-524` 甚至固化了「qa=fail 仍然发布」。

### 2.2 同一个数字有多条实现路径，且已经分叉

三处最硬的证据：

1. **同一快照，两份产物数字不同。** `output/600887.SH`（快照 `5ecaed4fe2ae70c0`）：analysis 写 GG 5.13%、底价均值 32.08；data_pack 写 GG 4.80%、32.10。成因是两条独立路径：`pack.py:241 valuation.build_valuation(...)` 自己组参数，`factors/engine.py` 另算一套；而 `finalize.py:161-169` 在没有 decisions 时只对 data_pack 做一次 snapshot id 正则替换，不重算。
2. **payout 六处独立推导**：`factors/engine.py:122-130`、`report/pack.py:139-148`（漏 `payout_reliable`）、`report/analysis.py:127-128`、`report/snapshot.py:559-564`、`cleanroom_worker.py:86-102`、`screener/fast.py:101-108`。分支条件已经不同：`metrics/dividends.py:66` 用 `income is None or income <= 0`，`cleanroom_worker.py:90` 用 `value <= 0`。
3. **同名函数四种实现、两种语义**：`report/format.py:18 _pct`、`factors/engine.py:70 _pct` 返回 `f"{value:,.2f}%"`（值已是百分数）；`cli.py:28 _pct` 做 `value * 100`（值是比率）；`report/market.py:38 _pct` 转调 format 版本。谁调用谁决定数字差 100 倍。

此外 `analysis.py:118-157` 在 `metric_registry.build()` 之前又独立重算了一遍 income/revenue/fcf/debt/cash/equity/payout/floor；`metrics/registry.py:3-6` 的模块 docstring 自己承认 "unmigrated report values remain code-rendered and are visible as remaining drift"——漂移是设计里明写的现状。

### 2.3 模版、渲染器、HTML 三方用中文字符串当契约

- 模板用 `## 一、结论` 这样的中文字符串当锚点；
- `html.py:125-131` 用这些字符串决定面板归属（六处硬编码：125/127/129/139/198/265）；
- `html.py:135-140` 按 `{"证据索引","定性证据","数字交叉验证","研究参数"}` 决定折叠；
- `html.py:198` 用 `"## 研究摘要" in text and "**研究覆盖**" in text` 判断「有没有研究内容」；
- 测试用同样的字符串做断言（`test_industry.py:77` 断言 `## 行业分类`）。

这是四份互相不知道对方存在的契约。改一个标题 → 面板静默错位、折叠失效、目录少一项，但所有测试全绿。

### 2.4 快照不可重放

`facts.py:87-91` 的 `template_hash` 只哈希 `report/templates/` 下的 j2 文件，**不含 analysis.py / pack.py / html.py / research.py**；`engine_version` 恒为 `0.1.0`。所以：

- 渲染逻辑（analysis.py / pack.py / html.py）改过多次，template_hash 都不变，快照看起来仍然「有效」；
- 反过来，模板改动会让旧快照失效且**无法迁移**。实测：

```
python -m turtlefw.cli report 601633.SH --snapshot .runs/daily/2026-10-27/601633.SH/snapshot
→ snapshot 校验失败：template_hash mismatch; report_hash mismatch
```

- `verify_manifest`（`snapshot.py:378-380`）只在 template_hash 非空时比较；旧 manifest 没有该字段时校验被跳过；QA 从不校验这两个 hash。

结论：快照保存了「数字可复现」，但没有保存「报告可复现」。这是一份投资报告最需要的东西。

### 2.5 编排逻辑落在 CLI

- `cli.py:2762` 的 `_report(...)` 有 **22 个参数、574 行**，函数体内直接 `TushareProvider(get_token())`、`apply_ttm`、`PitStore().load`；
- `cli.py:2361 _run_cmd` 330 行；`main` 是 37 条 `if args.command ==`；
- 输出根通过进程环境变量传递：`cli.py:3966 os.environ["TURTLE_OUTPUT_DIR"] = args.output_dir`，`paths.py:20` 每次调用重新读，`output_root()` 被 9 个模块调用 33 次；`paths.py:26 output_path` 是死 API；
- 存在真实循环依赖：`site.py:25 from .daily import qa_status` ↔ `daily.py:1051 from .site import build_site, publish_site`；另有 `metrics/registry.py:15 → factors.engine`、`data/tushare_provider.py:23 → metrics.prices`、`screener/tier2.py:143 → report.pack` 三条反向边；
- 7 个测试文件 import cli 私有函数（如 `tests/test_hk_currency.py:6 from turtlefw.cli import _fx_history, _unit_for`）。

### 2.6 测试锁碎片，不锁整体

- `tests/test_html.py` 83 行，7 个用例全部用 5–15 行手写片段，只断言局部 token（`report-tabs`、`quickread`、`<td>粗算回报率 R</td>` 不出现），没有一个用例覆盖真实报告。
- 唯一全文回归 `tests/test_report_consistency.py:100-106` 是 demo 分支的 sha256——固化的正是「含空日期、11 张只有表头的表」的输出。
- `tests/test_snapshot.py:324-335` 的 byte-identical 只是同进程 `a == b`。
- 76 个测试文件、321 个测试函数；`tests/test_cli.py` 22 行 4 个测试，没有一个是 `report` 命令。
- CI 的 ruff 只开三条规则（`F401,F601,F841`）；mypy 只列 32 个文件，**cli.py、daily.py、site.py 与 data/ 大部分不在列**。

---

## 三、为什么这些问题能长期存在

三条反馈回路全部缺失：

| 回路 | 现状 | 后果 |
|---|---|---|
| 结构断言 | QA 只查文件存在；无 lint；golden 只覆盖 demo | 编号漂移、空节、错表、占位符永远不会失败 |
| 数字同源 | R/GG/底价/payout 多处重算；registry 自认 drift | 同一快照两份产物可以给出不同数字 |
| 版本可重放 | template_hash 不含渲染器；旧快照拒绝渲染 | 无法回答「这份报告是用哪个版本生成的」，也无法 A/B 模板改动 |

对应的三个反例（都能证明回路缺失，不是理论担忧）：

1. 601633 的 `qa.json` 13 行全 PASS，而报告结论的否决原因写错了检查项；
2. `output/600887.SH` 同一快照 GG 5.13 vs 4.80；
3. 历史报告不能用当前代码重渲染（template_hash mismatch）。

---

## 四、优先级与路线

### P0（先做，1–2 周）

| # | 事项 | 落点 | 验收 |
|---|---|---|---|
| P0-1 | 新增 `report/lint.py`：编号连续且唯一、禁无编号 H2、空节、空表、`—`/TODO/`{{` 占位、日期格式、连续空行 ≤1、ragged 表 | `qa.run_qa` 注册 `report_structure`；`finalize` 与 `daily` 发布前调用 | lint 对现有 40 份报告全部报错（当前基线），修完后 0 错 |
| P0-2 | 章节模型化：`Section(id, title, level, required)` 列表，编号由渲染器生成，模板只遍历 | `analysis.md.j2` 去掉全部手写 `## 一、`；删除 `analysis.py:164-182` 的字符串拼接；`industry.py` 不再自带 `## ` | 未编号 H2 = 0；同一份快照重复渲染 H2 序列稳定 |
| P0-3 | 单一数字源：抽 `report/model.py`，R/GG/底价/payout 只算一次，pack 与 analysis 共享 | 删除 `pack.py` 内重算与 `analysis.py:118-157`；`finalize` 无条件重算两份产物 | 同快照 analysis 与 data_pack 数字差 = 0 |
| P0-4 | manifest 增 `renderer_hash`（analysis/format/html/research），去掉 truthiness 跳过；QA 校验 | `facts.py:87-91`、`snapshot.py:378-380` | 旧快照给出明确「不可重放」而不是含糊 mismatch |

本轮已实施 P0-1、P0-2 的编号部分、P0-4；P0-3（单一数字源）未做，原因见第七节。

### P1（2–6 周）

| # | 事项 | 说明 |
|---|---|---|
| P1-1 | evidence schema：`id / url / page / table_ref / quote(短) / level`，引用改 `[E12]` 式 | 报告只贴短摘 + 定位；全量证据进附录或单独 JSON；消灭 53% blockquote 重复 |
| P1-2 | 表格渲染器：`Table(columns=[(name, unit, fmt)], rows, align)`，统一转义与单位 | ragged 归零；单位缺失归零；`\|HH\|` 类问题从根上消失 |
| P1-3 | 报告拆成三段产物：`decision.md`（1 页）、`report.md`（因子论证）、`appendix.md`（D1–D6/数据/市场） | 解决 61% dump 与读者混淆；HTML 三个入口 |
| P1-4 | `final_verdict` 返回结构化原因（`which check / which dimension`），结论表显示「因子4 原始结论 → 最终结论」的差异与理由 | 21%/22.5% 的静默覆盖变成可解释 |
| P1-5 | 结果列语义：区分「通过/否决/观察/未验证」，`info` 不再冒充「观察」 | 1B 表不再出现「观察 + 正面」 |

### P2（持续）

- HTML 面板从结构（Section id）派生，不再匹配中文标题；
- CLI 拆 service 层（`report_service.py`），`_report` 降到 ≤8 参数；输出根显式传参，删除 env 旁路；
- 文档校正：`docs/snapshot-byte-identical.md:3` 称快照含「渲染器版本」（实际不含）、`README.md:560` 的 ruff 规则与 CI 不符、`README.md:487-497` QA 清单漏 `unknown_ratio`、`docs/research-layer.md:92-93` 的 50% 告警未实现。

---

## 五、验收指标

| 指标 | 当前基线（10-27 / 40 份） | 目标 |
|---|---:|---:|
| 未编号 H2 报告占比 | 100% | 0 |
| 重复 H3（`### 研究参数`） | 100%（6 次/份） | 0 |
| ragged 表行 | 6.4%（841/13196），40/40 份 | 0 |
| 表头无单位的金额表 | 86.3%（797/923） | 0 |
| 占位小节占比 | 70.5% | < 5% |
| 含 `—` 的表格行 | 13.1% | < 2%（且注明原因） |
| 重复表占比 | 26.6% | 0 |
| blockquote 重复率 | 53% | < 10% |
| 证据带 url + page | 0/22 条（601633 快照实测） | 100% |
| 因子4 原始结论 ≠ 结论 且无解释 | 22.5% | 0 |
| analysis / data_pack 数字差 | 存在（600887） | 0 |
| 旧快照可重渲染 | 0（template_hash mismatch） | 100% 或明确不可重放 |

---

## 六、不建议做的事

- **不要为了降体量直接删 dump。** 十二/十三/十一 对审计有价值，问题在位置和形式，不在存在。解法是分层（决策/论证/附录），不是删除。
- **不要让 LLM 去摘要报告。** 当前问题是结构不可校验，加一层生成模型只会让不可校验的内容更多。
- **不要先改 HTML。** HTML 只是投影；先有 Section 模型与 lint，HTML 才能从结构派生。
- **不要靠「记得跑一次」代替 lint。** 三条回路里最容易补、收益最大的是 P0-1。

---

## 七、本轮已实施的修改（2026-10-28）

复核完数字后，按 P0 里成本最低、能立刻让缺陷「变红」的几项先改了代码；未做的项在最后列出。

| # | 改动 | 位置 | 验证 |
|---|---|---|---|
| 1 | 新增结构 lint：H2 必须中文序号且连续、同级标题不重复、空节、ragged 表、裸 8 位日期、`{{ }}` 残留、`。；` 粘连、围栏奇偶 | 新增 `src/turtlefw/report/lint.py`；接入 `src/turtlefw/qa.py:31-36` 的 `report_structure` 行 | 601633 重渲染 0 finding；`tests/test_report_lint.py` 13 个用例 |
| 2 | 章节编号改为渲染后统一重排：模板/industry/pack 里写的「一、」「十二」全部被剥掉重编 | 新增 `src/turtlefw/report/normalize.py`；`src/turtlefw/report/analysis.py:580` | 601633 由 16 个 H2 构成「一…十六」连续序列；目录 16 条 |
| 3 | 表格单元格转义 `\|`，HTML 侧按未转义竖线切分 | `src/turtlefw/report/format.py:42-54`；`src/turtlefw/report/html.py:31` | `外推可信度 … \|HH\| …` 不再把行切成 4 列 |
| 4 | 否决原因取实际 `veto` 的检查名，不再写死「管理层」 | `src/turtlefw/factors/engine.py:811-826` | 结论行与 1B 表触发项一致 |
| 5 | 六个同名 `### 研究参数` 改为 `### D1 研究参数` 等 | `src/turtlefw/research.py:83,155-180` | 重复 H3 归零 |
| 6 | 8 位原始日期渲染为 `YYYY-MM-DD` | `src/turtlefw/report/analysis.py:28-38` | `数据截至：2026-10-27` |
| 7 | 因子说明改 `_join_notes`：去尾句号后单个 `；` 连接 | `src/turtlefw/report/analysis.py:40-48` | 601633 的 `。；` 由 2 处降为 0 |
| 8 | verdict=排除 时隐藏「买入/持有理由」「预期催化剂」「持有周期」 | `src/turtlefw/report/templates/analysis.md.j2:109` | 601633 显示「已排除，不建立仓位」 |
| 9 | 治理事实的 quote 由 Python repr 改为可读句子 | `src/turtlefw/cli.py:1679-1701` | 新 research run 不再产出 `parent_cash=…; audit=[{…}]`（旧快照内已冻结的引文不变） |
| 10 | manifest 增 `renderer_hash`（`report/*.py` + `templates/`），校验时比较 | `src/turtlefw/facts.py:94`；`src/turtlefw/report/manifest.py:54`；`src/turtlefw/report/snapshot.py:382` | 渲染器变更不再只表现为 `template_hash` 不变而 `report_hash` 变 |
| 11 | 模板不再手写章节序号：13 个 `## 一、…` 全部改为无编号标题 | `src/turtlefw/report/templates/analysis.md.j2` | 编号只由 `renumber` 生成；模板与目录不再各存一份真相 |
| 12 | 日期（`YYYY-MM-DD` / `YYYYMMDD`）按追溯信息处理，不再计入数字覆盖率 unknown | `src/turtlefw/numeric_audit.py:17-19,69-73` | 06862.HK 首跑 strict coverage 0.9985（唯一 unknown 是报告头日期里的 `28`）；新增 `test_calendar_dates_are_provenance_not_metrics` 后为 1.0000 |
| 13 | `finalize` 在 research 内容未变时保留原始字节与 provenance 哈希（此前无条件 `json.dumps` 重排） | `src/turtlefw/report/finalize.py:80-108` | 06862.HK 的 QA `research_provenance` 由 FAIL 变 PASS；内容被归一化改写时才更新 `research_sha256` |

以上第 12、13 项是本次重跑 06862.HK 完整流程（run → research-context → research.json → audit → provenance → finalize → qa）时暴露的两个真实缺陷：前者让 strict 数字门永远差一个日期 token，后者让每一份正常 research.json 在 finalize 后都过不了 provenance 校验。

`renderer_hash` 故意不进入 `_identity_payload`，所以 `snapshot_id` 仍只由输入决定；它记录的是「这份快照由哪套渲染器产出」，不改变快照身份。

未做（按原路线留给后续）：

- **P0-3 单一数字源**：`pack.py`/`analysis.py` 仍各算一遍 R/GG/底价，`output/600887.SH` 的 5.13 vs 4.80 仍然存在；这是改动面最大的一项，需要先抽 `report/model.py`。
- **P1 全部**：evidence schema、结构化 Table、报告拆三段、结构化 verdict、结果列语义。
- 旧快照仍然不可重渲染 —— 这是有意的：`template_hash`/`renderer_hash` 不匹配时应当明确拒绝，而不是静默产出另一份数字。

---

## 附录 A：复现

```bash
# 1. 用当前代码重渲染旧快照（故意绕过 manifest 校验）
python tmp/render_from_snapshot.py \
  .runs/daily/2026-10-27/601633.SH/snapshot tmp/render_current_601633.md

# 2. 快照不可重放
python -m turtlefw.cli report 601633.SH \
  --snapshot .runs/daily/2026-10-27/601633.SH/snapshot
# → snapshot 校验失败：template_hash mismatch; report_hash mismatch

# 3. 跨报告结构统计
python tmp/cur27.py      # 10-27 的 40 份：未编号 H2 / ragged / 占位 token
python tmp/cur27b.py     # 重复表 / 因子4 结论冲突
python tmp/evcount.py    # 证据行定位率
python tmp/verify1.py    # PROD 229 份：本次复审所用的口径（verify2–6 为分项复核）

# 4. 修复后的结构自检（lint 也可直接扫历史报告）
python -c "import sys,pathlib;sys.path.insert(0,'src');from turtlefw.report.lint import lint_report;print(lint_report(pathlib.Path('tmp/render_after.md').read_text(encoding='utf-8')))"
```

本文用到的中间产物：`tmp/render_current_601633.md`（修复前渲染结果，865 行）、`tmp/render_after.md`（修复后 845 行）、`tmp/xstat.json`（逐份明细）。

## 附录 B：已核验的关键代码位置

正文引用的行号是**修复前**（HEAD `e6e8f01`）的状态；本轮改动后的新行号见「七、本轮已实施的修改」。

| 主题 | 位置 |
|---|---|
| 章节硬编码（修复前） | `src/turtlefw/report/templates/analysis.md.j2:6,13,30,35,145,165`（现在模板已无序号，由 `normalize.renumber` 生成） |
| 编号拼接（已删除） | `src/turtlefw/report/analysis.py:189-198` 现在只拼 section 文本，不含序号 |
| 无编号 H2 来源 | `src/turtlefw/report/industry.py:162,214` |
| 引文拍平与截断 | `src/turtlefw/research.py:38-53,117`；`src/turtlefw/report/analysis.py:29-47` |
| 五次投影 | `src/turtlefw/research.py:76,158,224,256,530,604` |
| 表格不转义（修复前） | `src/turtlefw/report/format.py:42-54`（现由 `_cell` 转义）；`src/turtlefw/report/html.py:31` |
| 结论表覆盖 | `src/turtlefw/report/analysis.py:522-538` |
| 否决原因硬编码 | `src/turtlefw/factors/engine.py:811-826` |
| 结果列坍缩 | `src/turtlefw/factors/engine.py:783-794`；`src/turtlefw/report/analysis.py:50` |
| 空值策略分裂 | `src/turtlefw/facts.py:142-166`；`src/turtlefw/report/analysis.py:576` |
| QA 只查文件存在 | `src/turtlefw/qa.py:31` |
| manifest 回退 | `src/turtlefw/qa.py:200-212` |
| template_hash | `src/turtlefw/facts.py:87-97`；`src/turtlefw/report/snapshot.py:378-385` |
| 双渲染（探测指标） | `src/turtlefw/report/snapshot.py:621-660` |
| 双产物不一致 | `src/turtlefw/report/finalize.py:161-179` |
| HTML 标题匹配 | `src/turtlefw/report/html.py:151-161,226` |
| CLI 巨函数 | `src/turtlefw/cli.py:2382,2783-2806,3537` |
| 循环依赖 | `src/turtlefw/site.py:25` ↔ `src/turtlefw/daily.py:1051` |
| `_pct` 四份实现 | `src/turtlefw/report/format.py:18`、`src/turtlefw/factors/engine.py:70`、`src/turtlefw/report/market.py:38` vs `src/turtlefw/cli.py:28` |
