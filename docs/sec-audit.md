# SEC companyfacts 复核（美股数据覆盖）

## 定位

`sec-audit` 是**独立源复核**，不是主数据源：

- 不修改本地 `StatementRow`；
- 不覆盖 yfinance；
- 只比较 SEC companyfacts 与 snapshot 年报表值；
- 差异写入 JSON，供 cleanroom/人工判断。

## 命令

```powershell
turtle sec-audit `
  --snapshot output\AAPL.US\snapshot `
  --ticker AAPL `
  --out output\AAPL.US\sec_audit.json
```

## 映射

```text
revenue       Revenues / RevenueFromContractWithCustomerExcludingAssessedTax / SalesRevenueNet
net_income    NetIncomeLoss
total_assets  Assets
equity        StockholdersEquity
ocf           NetCashProvidedByUsedInOperatingActivities
capex         PaymentsToAcquirePropertyPlantAndEquipment
```

只接受：

- `form = 10-K / 10-K/A`
- `fy`
- `USD`

## 边界

- 只做年表复核，不提供股价/股本/分红；
- SEC tag 可能因公司而异，缺失即不比较；
- 需要 `SEC_USER_AGENT`（建议设置为联系方式）；
- 差异不是自动修正，必须经 source resolver/人工确认。
