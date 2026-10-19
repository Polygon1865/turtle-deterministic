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
| 美股 | 三表/行情 | Tushare `us_*` + yfinance |
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

## 仍未完成

### 10-K 分部

- companyfacts 不含 XBRL dimensions；
- 需要 10-K 正文或 `edgartools` 等维度解析；
- 当前 `segments` 仍 missing。

### 13F

- 需要 SEC 13F bulk dataset 或第三方 API；
- 工作量和数据体积大；
- 当前 `holders` 仍 missing。

### P1 剩余边界

这两项不是“免费 API 一接就有”，需要外部数据样本/供应商。当前没有把缺失数据伪装成 available。

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
