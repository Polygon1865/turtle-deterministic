# Phase 2 行业模板

当前已实现三套声明式模板：

| key | 名称 | 示例代码 | Peer 组 |
|:--|:--|:--|:--|
| telecom | 运营商 | 600941.SH / 601728.SH / 600050.SH | 中国移动 / 中国电信 / 中国联通 |
| food | 食品饮料 | 600887.SH / 600519.SH / 000858.SZ | 伊利 / 茅台 / 五粮液 |
| internet | 互联网 | 00700.HK / 09988.HK / 03690.HK | 腾讯 / 阿里 / 美团 |

## 设计原则

- 模板只声明 KPI 与 peer 范围，不写死数字；
- 指标存在则用 `MetricRegistry.display` 渲染；
- 指标缺失显示 `—` 并写原因；
- Peer 表在 A 股动态分类下填入经确定性公式计算的财务数字；静态模板或抓取失败时显示 `—`；
- 不抓取/猜测未验证的行业数据。

## 已接入

- `src/turtlefw/report/industry.py`
- 报告「行业模板」章节
- 三套模板测试
- 报告渲染测试

## 未完成

- 行业专属数据源（ARPU、MAU/DAU、渠道库存）；
- 模板选择已接入 Tushare 申万分类（`index_classify` + `index_member_all`），静态模板保留 fallback；
- 行业 KPI 的期间/币种统一；
- HK/US peer 暂无结构化数据源。

## Peer 财务对比

A 股 peer 会通过 provider 抓取：

```text
营收 CAGR
净利率
ROE
```

抓取失败或港股 peer 显示 `—`，不填未核实数字。
