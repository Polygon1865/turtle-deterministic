# 每日站点设计方案

> 目标：在“纯静态 HTML + Caddy + Cloudflare Access”的约束下，让每天
> **200 只候选（A 股 100 + 港股 100）**、**40 份报告（A 股 20 + 港股 20）** 都能被快速扫描、
> 筛选和阅读，而不是把 200 只都做成完整报告，也不是只展示 20 行摘要。

## 0. 当前实现（2026-10-29 改版）

站点已从“首页 + 40 份报告 + 每天整站复刻”改为按页面类型拆分：

```text
/index.html                 今日研究（唯一决策主表 + 今日变化 + 统计）
/screener.html              候选池（A 股 / 港股分面板，?market= 可分享）
/stock/<code>.html          个股页（决策摘要 + 关键指标 + 研究结论 + 跨日历史）
/report/<code>.html         报告全文（统一外壳，返回指向个股页）
/archive/index.html         存档索引（按数据日，含结论分布）
/archive/<date>/index.html  单日记录
/archive/<date>/<code>.html 历史报告副本
/method.html                方法说明（R/GG/II、底价、四因子、数据来源、限制）
/assets/site.css|site.js|favicon.svg
/ranking.csv|ranking_deep.csv|ranking_hk.csv
/health.txt|site_data.json
```

- 一级导航固定四项：**首页 · 筛选 · 存档 · 方法**；数据下载与健康状态只在页脚。
- 首页只有一张表（结论/标的/市场/R/GG/安全边际/底价/当前价/溢价/报告），
  候选池不再与报告混排；同一股票在一页最多出现一次。
- 个股 URL 稳定（不随日期变化），`?asof=` 可切到历史数据日；历史点来自
  `site_data.json` 的 `history`。
- CSS/JS/favicon 外置，页面不再内联样式；每页有 `canonical`、`og:*`、`twitter:card`。
- 归档报告优先用硬链复用上一 release 的字节，只有 back link 变化时才重写。

尚未完成：`site.json`（现用 `site_data.json`）、自选/笔记、上一只/下一只导航、图表、搜索后端。

## 1. 改版前的问题（2026-10-28 审计）

完整审计见 [docs/audits/2026-10-29-site-structure-review.md](audits/2026-10-29-site-structure-review.md)。摘要：

- 首页同时承担“今日概览 / 报告仓库 / 候选池”三种页面职责，三张表重叠三套排序；
- A 股与港股混在一张表里，列语义不同（A 股 PE/PB 全空、港股结论列全为「观察」）；
- 市场筛选只在前端 JS，切日期后市场选择丢失；
- 个股没有稳定 URL，跨日无法关联；报告被复制到根目录和 `archive/` 两套地址；
- 每个 release 复刻全部历史（单 release 250 个 HTML、34 个 release / 171MB）；
- 导航讲内部实现（候选 CSV / 深度 CSV / 健康检查），缺少“方法”入口。

## 2. 调研结论

参考方向（只借鉴原则，不照搬视觉）：

- 财富管理/投资门户通常按“总览 → 组合/标的 → 详情”分层，首页只放决策所需摘要，
  细节下沉到详情页。[Devexperts 案例](https://devexperts.com/case-studies/designing-a-wealth-management-platform-investor-advisor-portals/)
- 金融数据仪表盘的关键不是堆图表，而是层级、可比性和可扫描性；表格、筛选、
  一致的数值格式比装饰性图表更重要。[Highcharts + Morningstar 仪表盘实践](https://www.highcharts.com/blog/tutorials/saas-analytics-dashboards-with-highcharts-and-morningstar/)
- 金融界面适合高 x-height、清晰数字字形的字体，并启用 tabular numerals，
  让表格数字对齐。[Fonts in Financial Services](https://www.gate39media.com/blog/design-spotlight-fonts-in-financial-services)

对本地场景的推论：

1. **一个实体一个 URL。** 股票页与报告页分开，列表页不承担实体页职责。
2. **首页先结论，后证据。** 首屏回答“今天结论怎么分布、哪几只要先看、相比昨天变了什么”。
3. **候选池是独立产品面。** 200 行扫描与 40 行决策是两种任务，不应挤在同一页。
4. **历史是时间轴，不是目录。** 日期选择器只改变“看哪一天”，不改变站点结构。
5. **不要做“实时行情终端”。** 数据是收盘后日更，页面明确“数据日”，不伪装实时。

## 3. 信息架构

```text
/                     今日研究
/screener.html        候选池（A 股 | 港股）
/stock/<code>.html    个股页（?asof=<date> 切换历史）
/report/<code>.html   报告全文
/archive/             存档索引
/archive/<date>/      单日记录
/method.html          方法说明
/assets/*             样式、脚本、favicon
/ranking*.csv|health.txt|site_data.json
```

导航回答用户任务，不讲内部实现：

| 导航 | 回答的问题 | 页面 |
|---|---|---|
| 首页 | 今天结论是什么、变了什么 | `/index.html` |
| 筛选 | 全市场筛出了哪些、按什么排 | `/screener.html` |
| 存档 | 过去几天分别发生了什么 | `/archive/` |
| 方法 | R/GG/II、底价、四因子怎么算 | `/method.html` |

## 4. 页面职责

### 4.1 首页

- 标题「今日研究」+ 副题（数据日、A 股/港股报告数、LLM 研究开启数）；
- 统计条：报告 / 通过 / 未通过 / 候选（A·HK）/ LLM 开启；
- 「今日变化」：新进 / 移出 / 结论变化（对比上一数据日）；
- 唯一主表「今日报告」：`# / 结论 / 标的 / 市场 / R / GG / 安全边际 / 底价 / 当前价 / 溢价 / 报告`，
  前 5 行标星；失败行显示「失败」badge，LLM 回退显示「LLM 研究回退」；
- 页脚：方法、存档、CSV、健康状态、生成时间。

### 4.2 候选池

- 工具栏：市场切换（A 股 / 港股，写入 `?market=`）、搜索、排序（安全边际 / 排名）、CSV 下载；
- A 股面板列：`# / 代码 / 名称 / 通道 / R / GG / II / 安全边际 / 深度结论`；
- 港股面板列：`# / 代码 / 名称 / R / GG / II / 安全边际 / PE / PB / 报告结论`；
- 无 JS 时两个面板都展开，仍可逐行阅读。

### 4.3 个股页

- 标题：名称 + 市场徽章 + 结论徽章；副题：代码 / 行业 / QA / 覆盖率；
- 关键指标：当前价、综合底价、溢价、安全边际、R、GG、II、支付率；
- 研究结论：`thesis` 摘要；
- 历史：数据日 / 结论 / 当前价 / 底价 / 安全边际 / 报告，按日期倒序；
- 相关：报告全文、当日页面、CSV、health、方法说明。

### 4.4 报告页

报告全文由 Markdown→HTML 渲染器生成，站点只负责注入统一外壳（品牌、返回个股页、
数据口径提示）。渲染器不重算任何数字，正文数字与 Markdown 源一一对应。

### 4.5 存档

- 索引列出每个数据日：报告数 / 通过 / 失败 / 买入 / 观察 / 排除 / 候选数；
- 日页保留当日报告表与 CSV 入口，并提供上一日 / 下一日 / 全部存档导航。

## 5. 页面字段

### 5.1 候选池

来自 `ranking.csv`（A 股）与 `ranking_hk.csv`（港股，含 `R%/GG%/II%/margin`）：

| 字段 | 来源 | 说明 |
|---|---|---|
| `rank` | 行序 | 市场内排名 |
| `code/name` | ranking | 代码、名称 |
| `channel` | ranking | A 股主/观察通道；港股为 `HK` |
| `roe` `payout` | ranking | 港股 `payout` 来自年度 `divi_ratio` |
| `r` `gg` `ii` `margin` | ranking | 穿透回报率三件套与安全边际 |
| `pe` `pb` | ranking | 仅港股有值；A 股留空 |
| `verdict` | 报告 | 深度分析结论；未分析留空 |

### 5.2 今日报告

来自 `status.json`、`snapshot/manifest.json`、`metrics.json` 与报告首行：

- 代码、名称、市场、行业、结论、QA、研究模式、覆盖率；
- 综合底价、当前价、溢价、安全边际、R、GG；
- 报告链接；失败时保留错误原文；研究回退时保留原因码。

### 5.3 站点元数据

`site_data.json` 保存当日记录与历史（`history` 列表），`health.txt` 保存
`status/date/trade_date/reports/candidates/days/qa_pass/qa_fail/llm_on/llm_fallback/
llm_off/pdf_ok/pdf_none/screen_source/generated_at`。两者只做展示与检查，不参与计算。

## 6. 生成器

`src/turtlefw/site.py` 负责构建；模板位于 `src/turtlefw/report/templates/`：

| 模板 | 用途 |
|---|---|
| `site_layout.html.j2` | 公共 head/顶栏/页脚 |
| `site_home.html.j2` | 首页 |
| `site_screener.html.j2` | 候选池 |
| `site_stock.html.j2` | 个股页 |
| `site_day.html.j2` | 单日记录 |
| `site_archive.html.j2` | 存档索引 |
| `site_method.html.j2` | 方法说明 |

样式与脚本在 `src/turtlefw/site_assets.py`（`SITE_CSS` / `SITE_JS`），构建时写入
`assets/`。`build_site(day_dir, site_root, *, date_label=None, reports=None,
candidates=None, base_url=None)` 的流程：

1. 读当日 `status.json` / `ranking*.csv` / 历史 `site_data.json`，合并为按日记录；
2. 写 `releases/<label>`（同日重跑自动加 `-N`）；
3. 复制当日报告到 `report/<code>.html` 与 `archive/<day>/<code>.html`，按目标位置重写返回链接；
4. 历史日报表优先硬链上一 release 的字节，back link 不同才重写；
5. 渲染首页、候选池、方法、存档索引、单日页、个股页；
6. 写 `health.txt` / `status.json` / `site_data.json`；
7. `publish_site` 切换 `site/current` junction（失败时 copytree 兜底）。

`canonical` 使用 `base_url`（默认生产域名，可用 `TURTLE_SITE_BASE_URL` 覆盖）。

## 7. 视觉与交互

- 布局最大宽度 1240px；桌面表格密度优先，手机单列并允许横向滚动；
- 米白/深墨为主，结论徽章用三色（买入/观察/排除），不用红绿表示涨跌；
- 数字启用 `font-variant-numeric: tabular-nums`；表格 13px，正文 15px；
- 交互只用原生 JS：候选池搜索/排序/市场切换，状态写入 URL query；
- 无 JS 时所有表格仍完整可读；颜色不是唯一状态标识。

## 8. 发布与归档

- 每次成功构建写 `site/releases/<label>`，切换 `site/current` junction；
- 旧 release 不删除；同日重跑产生 `-1`、`-2` 后缀；
- 站点构建失败时 `site/current` 保持旧版本；
- 历史报告用硬链复用，稳态每日新增应小于 5MB（迁移轮因重写 back link 会偏高）。

## 9. 验收标准

- 首页只有一张决策主表，且同一股票在同一页最多出现一次；
- A 股与港股不混排（首页有市场列、候选池分面板）；
- URL 只由「页面类型 + 实体 + 参数」组成：`/stock/<code>.html`、`/archive/<date>/`、`?market=`、`?asof=`；
- `/stock/<code>.html` 能显示该股票的历史数据日；
- 每页都有返回上一层的入口，一级导航固定四项；
- 单日新增页面 < 50 个、新增字节 < 5MB；
- `</style>` 每页只出现一次（样式外置），每页有 canonical / OG / favicon；
- 发布失败时 `site/current` 仍指向上一版；
- 首页不出现报告正文中的数字，除非来自同一份 `metrics/data_pack` 数据源。

## 10. 不做的事

- 不做实时行情/分钟线；数据是日更。
- 不把 200 只都生成完整报告；深度报告只给前 20+20。
- 不引入 React/Vue/数据库；静态 HTML + 少量原生 JS 足够。
- 不在浏览器存 API key；所有数据在构建时生成。
- 不用颜色暗示买卖建议；页面只展示事实、估值区间和 QA 状态。

## 11. 后续（P2）

- 图表（复用报告里的 SVG）；
- 行业维度聚合页；
- 站内搜索（按代码/名称）；
- 自选/笔记（需要本地存储或后端，暂不做）；
- 候选池与报告联动：无报告时显示“未深度分析”而不是空白。
