# 数据源调研与 P0/P1 落地

## v2 的做法

v2 HEAD：`c61419c9fb5458595c0e44458ea5798dab501d92`（README 写 v2.0-beta）。

| 市场 | 数据 | 来源 |
|:--|:--|:--|
| A 股 | 合并/母公司三表 | Tushare `income` / `balancesheet` `report_type=6` |
| A 股 | 回购 | Tushare `repurchase` |
| A 股 | 质押 | Tushare `pledge_stat` |
| A 股 | 定性 | PDF-first + WebSearch |
| 港股 | 三表 | Tushare `hk_income` / `hk_balancesheet` / `hk_cashflow` |
| 港股 | 行情/股东 | yfinance，`hk_daily` fallback |
| 港股 | 母公司 | 不提供（v2: HKFRS 不拆母公司） |
| 港股 | 回购/质押 | 占位符 |
| 美股 | 三表/行情 | yfinance + SEC companyfacts；`us_fina_indicator` 仅补充指标 |
| 美股 | 母公司 | 不提供（v2: US GAAP 不拆母公司） |
| 美股 | 回购/质押 | 占位符 |
| 全部 | PIT | 无 |

v2 的 README 写母公司 `report_type=4`，代码/测试实际用 `report_type=6`；Tushare 文档定义 6 才是母公司报表。

## 本项目 P0

### 港股回购

- `HK_CASHFLOW_MAP["buyback"] = "回购股份"`
- 生成 `StatementRow(cashflow, buyback)`
- 报告指标 `buyback.latest`
- 边界：年度现金流汇总，无股数/价格/用途，partial

### 美股回购

- SEC companyfacts:
  - `PaymentsForRepurchaseOfCommonStock`
  - `StockRepurchasedAndRetiredDuringPeriodValue`
- 生成 `StatementRow(cashflow, buyback, source=sec)`
- evidence id：`sec:buyback:YYYY`

### Coverage 重分类

- 港股母公司：`pdf_optional`
- 港股质押：`not_applicable`
- 美股母公司/质押：`not_applicable`
- 港股/美股回购：`partial`

## 本项目 P1

### HKEXnews 回购公告

`hkex-news` 通过 HKEXnews `titleSearchServlet.do` 搜索公告：

```powershell
turtle hkex-news --code 00700 --keyword "Next Day Disclosure" --out hkex_buyback.json
```

输出 evidence：

```text
hkexnews:<NEWS_ID>
source_url = PDF
quote = 公告日期 + 标题
```

不解析 PDF 金额，只提供公告级证据。

### 港股母公司 PDF evidence

`pdf-evidence` 识别 Company-level statement，输出 `pdf:parent_company`，不解析金额。

## 标记为 external

以下能力不由本地 provider 硬做：

| 能力 | 状态 | 原因 |
|:--|:--|:--|
| 美股 10-K 分部 | external | companyfacts 无 dimensions；需 XBRL 正文/维度解析或供应商 |
| 美股 13F 股东 | external | 需 SEC 13F bulk dataset 或第三方 API |

`coverage` 与 QA 会显示 `external`，不把它们伪装成 `available`，也不把它们算作本地 missing。

## 补充基本面（2026-10 接入）

Tushare P0 中不进入三表的单票数据已接入，统一由
`TushareProvider.fundamental_extras()` 拉取并标准化：

| 市场 | 已接入 | 入口 |
|:--|:--|:--|
| A 股 | `fina_indicator`、`forecast`、`express`、`disclosure_date`、`stock_company`、`stk_managers`、`stk_rewards`、`top10_floatholders`、`stk_holdernumber`、`stk_holdertrade`、`share_float`、`index_classify` + `index_member_all` | `data/extras.py` |
| 港股 | `hk_fina_indicator` | 同上 |
| 美股 | `us_fina_indicator`（去 `.US` 后缀） | 同上 |

数据流：

```text
Tushare endpoint
  → normalize_*()（单位/字段统一，缺失 None）
  → ReportInputs.fundamental_extras / industry_name
  → snapshot inputs.json + manifest.extras_hash
  → report 第十二节 + data pack 第十七节（同一段 Markdown）
```

边界：

- 只做交叉核对与前瞻提示，**不进入 `StatementRow`，不改变确定性财务指标**；
- 预告/快报未经审计，不覆盖正式报表；
- 空响应进 `missing`，权限/网络失败进 `FetchIssue`，不做零填充；
- 申万分类用于选择行业模板；动态 peer 已接入，按申万一级、总市值取前 8；
- `report_rc`、宏观、公告/新闻、资金流/两融/涨跌停、指数估值/成分已接入 `market_extras`；公告/新闻需单独权限，缺失时显式标记。
- HK/US 的机构股东优先取 Yahoo Finance `institutional_holders`；Tushare 无对应标准接口，失败时标记 missing。

## 市场、宏观与治理（2026-10 接入）

这些数据走 `TushareProvider.market_extras()`，只进入报告“市场与宏观”章节和
data pack 同名附录，**不进入 `StatementRow`，不改变确定性估值**。报告与 data pack
共用 `src/turtlefw/report/market.py`，快照通过 `ReportManifest.market_hash` 固化
原始 payload。

| 市场 | 数据 | 接口 | 单位/口径 |
|:--|:--|:--|:--|
| A 股 | 卖方盈利预测 | `report_rc` | `op_rt`/`np` 万元→元；试用 10 次/日 |
| A 股 | 个股资金流 | `moneyflow` | 大单+特大单净额，万元→元 |
| A 股 | 融资融券 | `margin_detail` | 元 |
| A 股 | 涨跌停价格 | `stk_limit` | 元 |
| A 股 | 指数估值 | `index_dailybasic(000300.SH)` | PE/PB 及 3 年分位 |
| A 股 | 指数成分权重 | `index_weight(000300.SH)` | 权重为百分点 |
| A 股 | 宏观 | `cn_cpi`、`cn_ppi`、`cn_gdp`、`cn_pmi`、`shibor`、`shibor_lpr` | 百分比为百分点；GDP 亿元 |
| A 股 | 公告/新闻 | `anns_d`、`news` | 需单独公告/新闻权限；缺失标记 missing |
| HK/US | 机构股东 | Yahoo Finance `institutional_holders` | 第三方数据；失败标记 missing |

动态 peer：`peer_candidates()` 用 `index_member_all` 定位申万一级，再按
`daily_basic.total_mv` 取前 8；`industry.render_section()` 优先展示动态 peer，
静态模板 peer 只在没有分类数据时保留。

已知边界：`report_rc` 为供应商预测，未经审计；`anns_d`/`news` 在本账号无权限；
Yahoo 机构股东可能延迟或为空；这些值均不参与估值。

## 来源分类契约

报告数字只允许三类来源：

1. **metric**：Python `Decimal` 指标，带 `MetricPoint`/`MetricRegistry` id；
2. **fact**：PDF/SEC `DocumentFact`，带文档 hash、页码/标签；
3. **vendor context**：Tushare/Yahoo 补充基本面、市场、治理。必须同时出现在 data pack，带 `source`/`missing` 标注；不进入 `StatementRow`、不改变估值、不伪装成 metric/fact。

`numeric-audit --strict` 排除 `inputs.json` 原始值；默认 audit 仍保留它做兼容，但同时打印 strict view，因此默认 `coverage=1.0` 不再被当作 strict 100%。peer 财务已进入 data pack 与 `peer.*` MetricPoint，600887 的默认与 strict view 均为 100%；evidence/治理原始值仍需按上述三类来源继续分类。

## 关键参考

- [v2 README](https://github.com/terancejiang/Turtle_investment_framework/blob/c61419c9fb5458595c0e44458ea5798dab501d92/README.md)
- [v2 assembly.py](https://github.com/terancejiang/Turtle_investment_framework/blob/c61419c9fb5458595c0e44458ea5798dab501d92/scripts/tushare_modules/assembly.py)
- [Tushare income report_type](https://tushare.pro/wctapi/documents/33.md)
- [Tushare hk_cashflow](https://tushare.pro/wctapi/documents/391.md)
- [Tushare hk_balancesheet](https://tushare.pro/wctapi/documents/390.md)
- [SEC companyfacts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json)
- [SEC EDGAR API](https://www.sec.gov/edgar/sec-api-documentation)
- [Sharadar PIT](https://sharadar.com/llms.txt)
- [AkShare 港股财务](https://github.com/akfamily/akshare/blob/main/akshare/stock_fundamental/stock_finance_hk_em.py)
