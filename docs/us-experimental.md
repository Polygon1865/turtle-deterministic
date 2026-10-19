# 美股支持边界（实验）

## 已实现

- yfinance 年报三表映射：营收、净利、营业利润、EPS、总资产、权益、现金、债务、商誉、OCF、Capex、D&A、SBC；
- 行情/股本/市值；
- 分红；
- 报告/估值/snapshot/cleanroom 复用 A/HK 路径。

## 明确未实现

- SEC companyfacts/companyconcept 直连；
- 10-K/10-Q 文件级 DocumentFact；
- 股东、质押、回购、主营分部；
- 历史财务 vintage/PIT；
- 完整 4 年以上财年。

## 为什么

yfinance 不是交易所原始披露源，字段标签会变，且只有最近 4 个财年。  
在没有 SEC CIK 映射、币种/期间 schema 和 filing-vintage 存储之前，不能把美股标成与 A/HK 同等覆盖。

## 报告中的标记

美股报告应保留：

```text
报表币种：USD
数据源：yfinance（实验）
```

如果后续接入 SEC，应通过独立 provider，不直接把 companyfacts 混进 TushareProvider。
