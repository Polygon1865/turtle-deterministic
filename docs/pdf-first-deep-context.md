# PDF-first 深度链路

本页描述 `pdf-index` 与 `research-context --pdf-index`。目标不是让 LLM 写数字，而是让研究层能读到**整本年报的页级证据**，并把结论绑定到稳定的 `pdf://` 引用。

## 为什么需要第二层 PDF 上下文

旧链路只有：

- `pdf`：识别目录/章节，输出 `pdf_sections.json`；
- `pdf-numbers`：抽取少量审计数字；
- `pdf-evidence`：章节、股东、分部、母公司等结构化 evidence；
- `research-context`：把每节截断到 12,000 字符、附注摘录截断到 2,000 字符。

这对数字核验够用，但研究层只能看到节选，无法回答“这句话在 PDF 哪一页”“管理层对下一个季度的原话是什么”“治理章节里的关联交易细节”。`pdf-index` 增加一层**页级索引**，`research-context` 再把预算内的页面组织为 `pdf_deep`。

## 命令

```powershell
# 1. 为整本 PDF 建页级索引（输出默认是 <pdf>.pdf_index.json）
turtle pdf-index `
  --pdf .runs\600887.SH\2025年报.pdf `
  --output .runs\600887.SH\pdf_index.json

# 2. 生成研究上下文；会自动读取 snapshot/pdf_index.json，
#    也可以用 --pdf-index 显式指定
turtle research-context `
  --snapshot .runs\600887.SH\snapshot `
  --out .runs\600887.SH\snapshot\research_context.json `
  --pdf-index .runs\600887.SH\pdf_index.json `
  --pdf-max-chars 160000
```

可选的 `--pdf-focus` 是逗号分隔的检索主题；不传时使用默认 16 个主题（管理层讨论、经营、毛利率、现金流、研发、治理、关联交易、附注、分部、股东、分红、资本开支等）。

## 索引格式

`pdf_index.json` 是确定性的 JSON：

```json
{
  "version": 1,
  "document": {
    "sha256": "d17b8c541c42f65d...",
    "source_name": "2025年报.pdf",
    "page_count": 259,
    "chars": 407812
  },
  "sections": [
    {"id": "sec-004", "title": "第三节 管理层讨论与分析", "kind": "mda", "start_page": 10, "end_page": 39}
  ],
  "pages": [
    {"page": 10, "text": "...", "chars": 1800, "citation": "pdf://d17b8c541c42f65d/p10", "section_id": "sec-004"}
  ]
}
```

- `sha256` 是 PDF 文件哈希；citation 只取前 16 位，形如 `pdf://d17b8c541c42f65d/p10`。
- 页码是 PDF 的物理页，不是印刷页码。
- 章节识别优先使用 `第X节`，再使用 MDA/治理/审计/附注/风险/业务/ESG 等标题；财务报表内部的粗体小标题不会被拆成新章节。
- 目录页会跳过；无章节标题时仍保留页级索引。

## `pdf_deep` 上下文

`research-context` 在索引存在时增加 `pdf_deep`：

```json
{
  "document": {"sha256": "...", "page_count": 259},
  "sections": [{"id": "sec-004", "title": "...", "kind": "mda", "start_page": 10, "end_page": 39}],
  "pages": [
    {
      "page": 10,
      "section_id": "sec-004",
      "citation": "pdf://d17b8c541c42f65d/p10",
      "text": "...",
      "truncated": false,
      "score": 12
    }
  ],
  "citations": {
    "pdf://d17b8c541c42f65d/p10": {
      "page": 10,
      "section": "第三节 管理层讨论与分析",
      "quote": "……"
    }
  },
  "stats": {
    "pages_total": 259,
    "pages_selected": 60,
    "chars_selected": 90180,
    "max_chars": 160000,
    "max_pages": 60,
    "truncated_pages": 0,
    "focus_terms": ["管理层讨论", "..."]
  }
}
```

选择逻辑：

1. 按章节类型给权重（MDA、治理、业务、财务/附注较高）；
2. 同类型内按页码顺序；
3. 命中 focus 词的页面加分；
4. 在 `max_chars`（默认 160,000）和 `max_pages`（默认 60）内取页；
5. 单页超预算时截断，`truncated` 标为 `true`，`citations` 只保留实际进入上下文的文本。

## `pdf_notes` 结构化附注表

`pdf-index` 同时写一个 companion 文件（例如 `600887.pdf_notes.json`）。它从已抽取的
页级文本里挑选高价值表格，不重新解析报表数字：

- 营业收入构成/分行业/分产品/分地区；
- 研发投入/研发费用；
- 客户与供应商集中度；
- 受限资产；
- 有息负债/到期结构；
- 关联交易；
- 存货/跌价准备；
- 应收账款/账龄/坏账准备。

每张表保留 `page`、`citation`、`headers`、`rows`，最多 12 行、每组最多 2–4 张。
同组、同表头、标题相同（忽略“续”）、下一页且前表接近满行时，会合并为一张
跨页续表；citation 保留首页，合并后仍只保留前 12 行。这是启发式规则，不保证
所有复杂跨页表都能正确合并；600887/600519 当前各 12/10 张，未强行合并短表。
`research-context` 自动读取 `pdf_index.json` 旁边的 `pdf_notes.json` 并写入
`context["pdf_notes"]`；没有该文件时字段不出现。

```json
{
  "group": "revenue",
  "title": "主营业务分行业情况",
  "page": 22,
  "citation": "pdf://d17b8c541c42f65d/p22",
  "headers": ["分行业", "营业收入", "营业成本", "毛利率（%）"],
  "rows": [["液体乳", "...", "...", "..."]]
}
```

研究层可以把表格行作为 evidence 的 quote，但必须逐字来自该页，且不能自己
加总、年化或重算。结构化表只是**证据候选**；计算仍由 `metrics` 完成。

## 研究层引用规则

研究 JSON 的 evidence 可以这样写：

```json
{
  "id": "pdf:600887:mda-p10",
  "source_type": "pdf",
  "url": "pdf://d17b8c541c42f65d/p10",
  "page": 10,
  "quote": "必须逐字来自该页原文，最多 400 字符"
}
```

`research.validate_evidence` 接受 `source_type="pdf"` + `pdf://` URL；普通 web evidence 仍必须是 `http(s)://`。Agent prompt 要求：

- 优先使用 `pdf_deep` 的页面回答 D1/D4/D5/D6；
- 只能引用实际出现在 `pdf_deep` 里的页面；
- 不得把页码/引用当成数字指标；数字仍用 `{{metric:...}}` / `{{fact:...}}`；
- 不得为未选中的页面编造 citation。

## 边界

- 默认只处理文本型 PDF；扫描件仍需 OCR/外部工具。
- 页级上下文**不是** `StatementRow`，不进入估值；它只服务研究叙述和证据。
- 章节标题是启发式；年报排版差异可能导致章节合并/拆分，但 citation 仍按物理页稳定。
- 60 页/160,000 字符是预算默认值；可通过 `--pdf-max-chars` 调整。大 PDF 的 `pdf_deep` 会让上下文 JSON 明显变大。
- 页级 evidence 的 quote 上限 400 字符；长段落需截取关键句，不能拼接不存在的文本。
- 该层与 `reported_numbers.json` 的确定性审计数字是互补关系：数字核验仍以 `pdf-numbers` / facts 为准。

## 验证

```powershell
.\.venv\Scripts\python.exe -m pytest -o addopts="" -q tests\test_pdf_deep_index.py tests\test_pdf_notes.py tests\test_research_context.py
```

测试覆盖：章节识别、citation、字符预算、页选择优先级、搜索排序、JSON 往返、
结构化附注表选择/行预算、`research-context` 自动读取索引和附注、`pdf://` evidence 校验。
