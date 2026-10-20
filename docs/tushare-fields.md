# Tushare 字段与权限核对

> 观测日期：2026-10-19  
> 样本：`600887.SH`（A 股）、`00700.HK`（港股）  
> 说明：以下是**本机账号实际返回**的字段，不代表所有 Tushare 账号都有相同权限。换账号后请用文末探测脚本重跑。

## 结论摘要

| 能力 | 状态 | 对分析的影响 |
|:--|:--|:--|
| A 股三大报表核心字段 | 可用 | 因子 1–3、底价、估值正常 |
| A 股财务费用 | 已修正为 `fin_exp` | 之前 `finance_exp` 返回空，债务成本回退 5% |
| A 股现金桥明细 | 部分缺失 | `c_paid_goods_srv`、`c_pay_oth_act` 未返回；用“经营流入小计 − OCF”推导总流出 |
| 母公司报表 | 可用（`report_type=6`） | 因子 1B 现金上游检查 |
| 质押 | 可用（`pledge_stat`） | 因子 1A >70% 否决 |
| 回购 | 可用（`repurchase`） | 因子 2 的 O |
| 审计意见 | 可用（`fina_audit`） | 因子 1A |
| 港股三大报表 | 可用（line-item） | 缺毛利现金收付明细，只能做“间接现金桥” |
| 港股 D&A | 已修正为 `加:折旧及摊销` | G 网格不再因缺 D&A 回退 |
| 港股 DPS | 可用但可能重复 | 重复时标记不可靠，股息隐含价跳过 |
| `hk_daily` | 限频 1 次/小时 | 行情优先 yfinance，失败才回退 |
| `yc_cb` | 本账号无权限 | 需用 `--rf/--rf-source` 或配置默认 Rf |

## A 股字段（`income` / `balancesheet` / `cashflow`）

### income

| 字段 | 用途 | 本账号状态 | 缺失时 |
|:--|:--|:--|:--|
| `revenue` | 营收、CAGR、现金桥 | ✅ | 因子 1B/3 缺失 |
| `oper_cost` | 毛利率 | ✅ | 毛利率空 |
| `sell_exp` / `admin_exp` / `rd_exp` | 费用率 | ✅ | 对应指标空 |
| `fin_exp` | 财务费用、债务成本 | ✅（原 `finance_exp` 错误） | WACC 债务成本回退 5% |
| `operate_profit` | EV/EBITDA、利润率 | ✅ | 对应指标空 |
| `total_profit` / `income_tax` | 有效税率 | ✅ | 税率回退默认 |
| `n_income` / `n_income_attr_p` | 净利润、ROE、支付率 | ✅ | 核心指标缺失 |
| `minority_gain` | 少数股东损益 | ✅ | 现金桥/净利润口径受限 |
| `basic_eps` | EPS、PE、PEG | ✅ | PE/PEG 不可用 |
| `asset_disp_income` / `non_oper_income` / `oth_income` | 非经常性项目 | ✅ | 提示“未接入” |
| `invest_income` | 投资收益 | ✅ | 现金桥 V1 空 |

### balancesheet

| 字段 | 用途 | 状态 | 缺失时 |
|:--|:--|:--|:--|
| `money_cap` | 净现金、底价 | ✅ | 净现金/底价缺失 |
| `trad_asset` | 净流动资产底价 | ✅ | 该底价锚点缺失 |
| `accounts_receiv` | 应收/营收、现金桥 | ✅ | 现金桥回退 |
| `inventories` | 营运资本 | ✅ | 现金桥/质量指标受限 |
| `total_assets` | 商誉占比、PS | ✅ | 对应指标空 |
| `st_borr` / `lt_borr` / `bond_payable` / `non_cur_liab_due_1y` | 有息负债 | ✅ | 净现金/杠杆空 |
| `total_liab` | 资产负债率 | ✅ | 杠杆指标空 |
| `total_hldr_eqy_exc_min_int` | 归母权益、ROE、PB | ✅ | 底价/ROE 空 |
| `minority_int` | 少数股东权益 | ✅ | 现金桥/权益口径受限 |
| `goodwill` | 商誉/总资产 | ✅ | 商誉指标空 |
| `contract_liab` | 预收/合同负债 | ✅ | 现金桥预收项缺失 |
| `adv_receipts` | 预收款项 | ✅ | 回退 `contract_liab` |

### cashflow

| 字段 | 用途 | 状态 | 缺失时 |
|:--|:--|:--|:--|
| `n_cashflow_act` | OCF、FCF、现金桥 | ✅ | 因子 3 缺失 |
| `n_cashflow_inv_act` / `n_cash_flows_fnc_act` | 现金流结构 | ✅ | 仅展示空 |
| `c_pay_acq_const_fiolta` | Capex、FCF | ✅ | FCF/现金桥缺失 |
| `depr_fa_coga_dpba` | D&A、G 网格 | ✅ | G 回退 1.0 |
| `amort_intang_assets` / `lt_amort_deferred_exp` | D&A 补充 | ✅ | D&A 偏低 |
| `c_pay_dist_dpcp_int_exp` | 已付股利（上界） | ✅ | 支付率法 2 缺失 |
| `c_paid_for_taxes` | 税费现金流 | ✅ | 现金桥明细缺失 |
| `c_fr_sale_sg` | 销售收现 | ✅ | 真实现金收入回退营收调整 |
| `c_inf_fr_operate_a` | 经营流入小计 | ✅ | 总流出无法推导 |
| `c_paid_to_for_empl` | 职工现金 | ✅ | 现金桥明细缺失 |
| `c_paid_goods_srv` | 购买商品/劳务现金 | ❌ 本账号不返回 | 用“流入小计 − OCF”推导总流出 |
| `c_pay_oth_act` | 其他经营支付 | ❌ 本账号不返回 | 同上 |

> 这两个字段缺失时，现金桥保留实际销售收现，并标记为
> `source=derived_bridge`、`complete=False`、`推导现金桥（部分）`；
> 不会把推导值伪装成完整明细。只有实际销售收现与完整流出组件都存在时
> 才标为 `cash_bridge / complete=True`。

## A 股扩展接口

| 接口 | 字段 | 用途 | 状态 | 缺失时 |
|:--|:--|:--|:--|:--|
| `dividend` | `cash_div_tax,base_share,div_proc` | DPS、支付率 | ✅ | 分红缺失 |
| `daily_basic` | `close,pe_ttm,pb,total_mv,circ_mv,dv_ttm,turnover_rate,total_share` | 价格/市值/估值 | ✅ | 行情缺失 |
| `weekly` | `open,high,low,close` | 52 周/10 年最低 | ✅ | 价格历史缺失 |
| `fina_audit` | `audit_agency,audit_result` | 审计意见 | ✅ | 因子 1A unknown |
| `pledge_stat` | `pledge_ratio` | 质押率 | ✅ | 因子 1A unknown，不否决 |
| `repurchase` | `amount,vol,proc` | 回购 O | ✅（金额单位：元） | O=0 |
| `top10_holders` | `holder_name,hold_amount,hold_ratio` | 股东结构 | ✅ | 数据包“未接入” |
| `fina_mainbz` | `bz_item,bz_sales,bz_profit` | 主营/分部 | ✅ | 数据包“未接入” |
| `adj_factor` | `adj_factor` | A 股后复权 | ✅ | 价格不复权 |
| `stock_basic` | `name,industry,area,market,exchange,list_date,delist_date` | 股票元数据/上市状态 | ✅ | 名称/行业空 |
| `trade_cal` | `cal_date,is_open` | 最新交易日 | ✅ | 行情日期回退今天 |
| `yc_cb` | 国债收益率 | Rf | ❌ 无权限 | `--rf` 或 `default_rf` |
| `fina_indicator_vip` | `roe_waa,grossprofit_margin,debt_to_assets` | 批量筛选 | 视权限 | Tier1 指标空 |

## 港股字段（line-item）

港股报表不是列式，而是 `ind_name/ind_value` 长表；字段缺失表现为某条 line item 不存在。

| 接口 | 本账号状态 | 说明 |
|:--|:--|:--|
| `hk_income` | ✅ 映射全部命中 | 营业额/营运支出/股东应占溢利/EPS 等 |
| `hk_balancesheet` | ✅ 映射全部命中 | 现金/应收/预付款项/递延收入/股东权益等 |
| `hk_cashflow` | ✅ 核心项命中；D&A 已修正 | 无“销售收现/购买商品付现”明细；Capex 由 PPE + 无形资产两项相加 |
| `hk_fina_indicator` | ✅ `dps_hkd,divi_ratio` | DPS 可能多年重复，需标记不可靠 |
| `hk_daily` | ⚠️ 1 次/小时 | yfinance 优先；限流时跳过行情 |

### 港股现金桥为什么是“间接”

港股 cashflow 没有：

- 销售商品、提供劳务收到的现金；
- 购买商品、接受劳务支付的现金；
- 支付给职工的现金；
- 其他经营支付。

因此本地只能用：

```text
真实现金收入 = 营收 − 应收增加 − 预付增加 + 预收/合同负债增加
经营流出（推导） = 真实现金收入 − OCF
现金结余 = OCF − Capex
```

报告会标为 `间接现金桥`/`PDF间接现金桥`，不会标成完整直接现金桥。港股 AA 仍等于 `OCF−Capex`，但工作资本拖累和完整性可见。传入 `--pdf-numbers` 时，最新一年改用 PDF 的净利润/D&A/营运资本/经营产生现金/税/OCF/Capex，标签为 `PDF间接现金桥+历史口径`。

### 真实年报核对（2025）

- 00700 的 PDF 营业收入 751,766 百万 vs Tushare `营业额` 743,689 百万，差 8,077 百万（PDF `Others` 分部）；这是供应商口径差异，`audit` 会报 1.09%。
- 00700 的 Capex：PDF PPE 87,482 + 无形 25,399 = 112,881 百万；修复前 Tushare 只映射无形 25,393，FCF 被高估。现已相加。
- 详见 [pdf-extraction-validation.md](pdf-extraction-validation.md)。

## 美股（yfinance 实验）

| 项 | 来源/字段 | 状态 |
|:--|:--|:--|
| 三大报表 | `Ticker.financials/balance_sheet/cashflow` 标签映射 | 实验可用 |
| 行情/股本 | `info.marketCap/sharesOutstanding/currentPrice` + 1y history | 实验可用 |
| 分红 | `Ticker.dividends` | 实验可用 |
| 审计/质押/股东/主营 | 无 | 返回空 |

注意：yfinance 报表只有最近 4 个年度、字段命名可能变化；US 报告不应当当作与 A/HK 同等覆盖。

## 换账号后如何复测

```powershell
.\.venv\Scripts\python.exe -c @"
from turtlefw.config import get_token
from turtlefw.data.tushare_provider import TushareProvider
from turtlefw.data import tushare_maps as m
p = TushareProvider(get_token())
for endpoint, fields in [
    ('income', m.CN_INCOME_MAP.values()),
    ('balancesheet', m.CN_BALANCE_MAP.values()),
    ('cashflow', m.CN_CASHFLOW_MAP.values()),
]:
    df = p._safe(endpoint, ts_code='600887.SH', fields='ts_code,end_date,' + ','.join(fields))
    print(endpoint, 'missing:', [f for f in fields if f not in df.columns])
"@
```

港股用 `hk_income/hk_balancesheet/hk_cashflow` + `ind_name` 检查映射值是否存在；不要用列名检查。

## 代码位置

- 字段映射：[tushare_maps.py](../src/turtlefw/data/tushare_maps.py)
- 取数与降级：[tushare_provider.py](../src/turtlefw/data/tushare_provider.py)
- 现金桥：[cashflow.py](../src/turtlefw/metrics/cashflow.py)
- 缓存 schema：`TushareProvider.SCHEMA_VERSION = "turtle-7"`；升级字段后需换版本避免旧缓存。
