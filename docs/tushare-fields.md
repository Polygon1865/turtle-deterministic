# Tushare 字段与权限核对

> 观测日期：2026-10-21
>
> 样本：`600887.SH`（A 股）、`00700.HK`（港股）、`AAPL.US`（美股）
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
| 港股/美股财务指标 | 可用（`hk_fina_indicator` / `us_fina_indicator`） | 仅作交叉核对，不覆盖三表 |
| 补充基本面 | A 股 13 个接口已接入 | 指标、预告/快报/披露、公司、管理层、股东、申万分类 |
| 市场/宏观 | A 股 8 类 + 宏观 6 项已接入 | `market_extras`；卖方预期、资金流、两融、涨跌停、指数、公告/新闻 |
| A 股申万分类 | 可用（`index_classify` + `index_member_all`） | 用于选择行业模板；动态 peer 按申万一级+总市值 |
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
| `top10_holders` | `holder_name,hold_amount,hold_ratio` | 股东结构 | ✅ | 数据包股东段为空 |
| `fina_mainbz` | `bz_item,bz_sales,bz_profit` | 主营/分部 | ✅ | 数据包主营段为空 |
| `adj_factor` | `adj_factor` | A 股后复权 | ✅ | 价格不复权 |
| `stock_basic` | `name,industry,area,market,exchange,list_date,delist_date` | 股票元数据/上市状态 | ✅ | 名称/行业空 |
| `trade_cal` | `cal_date,is_open` | 最新交易日 | ✅ | 行情日期回退今天 |
| `yc_cb` | 国债收益率 | Rf | ❌ 无权限 | `--rf` 或 `default_rf` |
| `fina_indicator_vip` | `roe_waa,grossprofit_margin,debt_to_assets` | 批量筛选 | 视权限 | Tier1 指标空 |
| `fina_indicator` | `roe_waa,grossprofit_margin,netprofit_margin,debt_to_assets,ocf_to_or,eps,bps` | 单票财务指标 | ✅（本机） | 仅补充章节，不并入三表 |
| `forecast` | `type,p_change_min/max,net_profit_min/max,summary,change_reason` | 业绩预告 | ✅（本机） | 空响应标注未取得 |
| `express` | `revenue,n_income,total_assets,total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe` | 业绩快报 | ✅（本机） | 空响应标注未取得 |
| `disclosure_date` | `pre_date,actual_date,modify_date` | 预约披露 | ✅（本机） | 空响应标注未取得 |
| `stock_company` | `com_name,chairman,manager,reg_capital,main_business` | 公司信息 | ✅（120 积分） | 仅展示，不参与估值 |
| `stk_managers` | `name,title,begin_date,end_date` | 管理层 | ✅（本机） | 仅展示 |
| `stk_rewards` | `name,title,reward,hold_vol` | 管理层薪酬 | ✅（本机） | `reward` 单位元，报告按百万元展示 |
| `top10_floatholders` | `holder_name,hold_amount,hold_ratio,hold_change` | 十大流通股东 | ✅（本机） | 补充章节展示 |
| `stk_holdernumber` | `holder_num` | 股东户数 | ✅（本机） | 补充章节展示 |
| `stk_holdertrade` | `in_de,change_vol,change_ratio,avg_price` | 增减持 | ✅（本机） | 补充章节展示 |
| `share_float` | `float_date,float_share,float_ratio` | 限售解禁 | ✅（本机） | 补充章节展示 |
| `index_classify` | `index_code,industry_name,level` | 申万分类 | ✅（本机） | 用于模板选择 |
| `index_member_all` | `l1_code,l1_name,l2_name,l3_name,in_date,is_new` | 申万成分 | ✅（本机） | 用于模板选择 |

## 补充基本面（2026-10-21 接入）

这些数据走 `TushareProvider.fundamental_extras()`，只进入报告/data pack 的
“补充基本面”章节，**不进入 `StatementRow`，不改变确定性指标**。空响应写入
`missing`，权限/网络失败写入 `FetchIssue`；两者都不会被零填充。

| 数据 | 接口 | 标准化 | 单位/口径 |
|:--|:--|:--|:--|
| A 股财务指标 | `fina_indicator` | `normalize_fina_indicator` | 比例字段为百分点；`ocf_to_or` 是比率，×100 转百分点 |
| 港股财务指标 | `hk_fina_indicator` | 同上 | `ocf_sales` 已是百分点，不再乘 100 |
| 美股财务指标 | `us_fina_indicator` | 同上 | 无 `ocf_sales`/`bps` 时保持 `None` |
| 业绩预告 | `forecast` | `normalize_forecast` | `net_profit_min/max` 单位万元，×10000 转元 |
| 业绩快报 | `express` | `normalize_express` | 金额为元；EPS/ROE 兼容 `diluted_*` |
| 预约披露 | `disclosure_date` | `normalize_disclosures` | 保留预约/实际/修改日期 |
| 公司信息 | `stock_company` | `normalize_company` | 仅展示，不参与估值 |
| 管理层/薪酬 | `stk_managers` / `stk_rewards` | `normalize_managers` / `normalize_rewards` | 按起始/公告日期倒序 |
| 股东结构 | `top10_floatholders` / `stk_holdernumber` / `stk_holdertrade` / `share_float` | `normalize_float_holders` 等 | 最新一期/最近记录；比例字段为百分点 |
| 申万分类 | `index_classify` + `index_member_all` | `normalize_industry` | 取当前 `is_new=Y` 的最新 `in_date`；用于选择行业模板 |

实现位置：

- `src/turtlefw/data/tushare_provider.py`（schema `turtle-9`）
- `src/turtlefw/data/extras.py`（标准化）
- `src/turtlefw/report/extras.py`（报告/data pack 共用渲染）
- `src/turtlefw/report/snapshot.py`（`ReportInputs.fundamental_extras`、`industry_name`、`extras_hash` 校验）

边界：

- 预告/快报未经审计，不覆盖正式报表；报告中明确标注。
- 财务指标是供应商口径，季度/中报未年化。
- 申万分类决定行业模板；动态 peer 已接入，按申万一级、总市值取前 8。
- A 股接口多需约 2000 积分；`stock_company` 门槛较低。实际权限以账号为准。

## 市场、宏观与治理（2026-10-21 接入）

这些数据走 `TushareProvider.market_extras()`，只进入报告/data pack 的
“市场与宏观”章节，**不进入 `StatementRow`，不改变估值**。数值单位在
`data/market_extras.py` 统一：金额为元，百分比为百分点。

| 数据 | 接口 | 标准化 | 单位/口径 |
|:--|:--|:--|:--|
| 卖方盈利预测 | `report_rc` | `normalize_research` | `op_rt`/`np` 万元→元；取最新 8 条；试用 10 次/日 |
| 个股资金流 | `moneyflow` | `normalize_moneyflow` | 大单+特大单净额，万元→元；最新 5 日 |
| 融资融券 | `margin_detail` | `normalize_margin` | 元；最新 5 日 |
| 涨跌停价格 | `stk_limit` | `normalize_limits` | 元；最新 3 日 |
| 指数估值 | `index_dailybasic` | `normalize_index_valuation` | 沪深300 PE/PB + 3 年分位 |
| 指数成分 | `index_weight` | `normalize_index_weights` | 权重为百分点；前 10 |
| 宏观 | `cn_cpi`/`cn_ppi`/`cn_gdp`/`cn_pmi`/`shibor`/`shibor_lpr` | `normalize_macro` | 指标各 2 期；GDP 亿元；PMI 用 `pmi010000` |
| 公告/新闻 | `anns_d`/`news` | `normalize_announcements`/`normalize_news` | 本账号无权限时 `missing` |
| HK/US 机构股东 | Yahoo `institutional_holders` | `normalize_governance` | 第三方数据；失败 `missing` |

动态 peer：`peer_candidates()` 先按 `index_member_all` 找申万一级，再用
`daily_basic.total_mv` 取前 8；报告优先展示动态 peers，静态模板只作无分类时回退。
快照新增 `ReportManifest.market_hash`，`verify_manifest` 会校验原始 payload。

边界：

- `report_rc` 是卖方预测，不是公司指引；不覆盖正式报表。
- `anns_d` 与 `news` 需要单独公告/新闻权限，当前账号无权限；不伪造。
- 资金流/两融/涨跌停只作背景，不进入确定性估值。
- 宏观数据与个股无直接映射，不能据此调整折现率。

## 港股字段（line-item）

港股报表不是列式，而是 `ind_name/ind_value` 长表；字段缺失表现为某条 line item 不存在。

| 接口 | 本账号状态 | 说明 |
|:--|:--|:--|
| `hk_income` | ✅ 映射全部命中 | 营业额/营运支出/股东应占溢利/EPS 等 |
| `hk_balancesheet` | ✅ 映射全部命中 | 现金/应收/预付款项/递延收入/股东权益等 |
| `hk_cashflow` | ✅ 核心项命中；D&A 已修正 | 无“销售收现/购买商品付现”明细；Capex 由 PPE + 无形资产两项相加 |
| `hk_fina_indicator` | ✅ `dps_hkd,divi_ratio` + ROE/毛利率/净利率/负债率/OCF 占比 | 指标用于补充基本面；DPS 可能多年重复 |
| `hk_daily` | ⚠️ 1 次/小时 | 全市场快照；`amount` 单位为元；限流时回退 Yahoo 日线并标注 source |
| `hk_basic` | ✅ 2787 只在市 | 主板/创业板、上市日期、币种；用于全市场筛选 |
| `hk_fina_indicator` | ✅ 逐票 | 无批量接口；ROE/毛利率/净利率/负债率/营收增速/EPS/BPS/PE/PB 用于质量分；`report_type` 校验年报，`currency` 非 HKD/CNY 跳过 |

港股 screen 先用 `hk_basic` 过滤创业板、上市不足 3 年、当日无行情的标的，
并跳过已知美元报表公司 `00005.HK`、`01299.HK`、`02378.HK`、`02888.HK`（项目不伪造 USD 折算；运行时还会按 `currency` 跳过非 HKD/CNY 报表）、
人民币柜台重复上市（`8xxxx.HK` 且名称以 `-R` 结尾，如 `82333.HK 长城汽车-R`，其港币柜台 `02333.HK` 会正常参与），
再对存活标的逐票取 `hk_fina_indicator`（财报期默认上一完整年度；`report_type=Q4` 或 `end_date` 为 1231 视为年报，非 12 月财年按年报回退，拒绝中报），
要求年报口径、`total_market_cap` ≥ 50 亿港元（`--min-market-cap-yi` 可调）、营收/净利为正，且通过与 A 股相同的质量门槛（ROE ≥ 8、负债率 ≤ 70、毛利率存在时 ≥ 15）。

排序改用与 A 股 `fast_screen` 完全一致的穿透回报率口径，而不是 ROE 加权分：

- `payout`：优先 `divi_ratio`（Tushare 存小数，0.928 = 92.8%，特别股息可 >1，超过 100% 截断并标 `payout_ok=False`），缺失回退 `dps_hkd / basic_eps`；
- `R% = 归母净利 × payout / 市值`；`GG% = 近两年 FCF 均值 × payout / 市值`；`II% = max(5.0, Rf + 3.0)`；`margin = GG% − II%`；
- 市值、净利、FCF 统一为港元（CNY 报表按 `cny_per_hkd` 折算），FCF 取 `hk_cashflow` 的 `n_cashflow_act − |c_pay_acq_const_fiolta|`，按年报财月过滤掉中报期间；
- 无现金流数据的标的直接剔除（`drop_no_cashflow`），毛利率缺失只跳过毛利质量项，不再整只丢弃（港交所 00388、中国平安 02318 曾因此被误杀）。

入选行在返回前还会用 yfinance 复核报表币种（`hk_fina_indicator.currency` 对 06862 一类内地发行人并不可靠）：确认为 USD 的标的直接剔除，
避免像 `00288.HK 万洲国际` 这样进了榜单却在分析阶段报「港股美元报表暂不支持」、白白占掉 35% 的港股报告名额。

### 港股股东与主营（2026-11-11）

- 股东：Tushare 没有港股股东接口（`hk_holders`/`hk_major_holders` 均返回「请指定正确的接口名」），
  改为 Yahoo Finance `institutional_holders` + `mutualfund_holders`（`TushareProvider._hk_holders`，进程内缓存）。
  报表第 8 节标题会写成「机构与基金持仓（Yahoo，第三方，可能滞后）」，并附披露日期；
  它不是完整股东名册，也不等同于年报披露。
- 主营：Yahoo 只有 `sector/industry/longBusinessSummary`，没有分部收入；数据包第 8 节在无分部表时输出
  「主营描述（行业）」段落，分部收入仍仅 PDF 路径（`hk_facts.segments`）可得。
- 母公司现金：港股只有合并报表，保持「未验证」，不做估算。

CSV 列含 `R%`/`GG%`/`II%`/`margin`/`payout`/`FCF yield%`，与 `ranking.csv` 对齐；`hk_daily` 单次最多 5000 行，单日全市场通常一次足够；
`hk_fina_indicator`/`hk_cashflow` 逐票调用，首次完整刷新约十几分钟，之后走 7 天文件缓存（`--refresh-market` 也不会重拉财报类接口）。

### 港股价格与币种（2026-11-05）

报告币种取 `reporting_currency`（yfinance），取不到时默认 CNY 并打印提示；HKD 报价按 `fx.cny_per_hkd`（默认 0.92，固定配置、非实时汇率）折算成报告币种，OHLC 历史与分红也乘同一因子。
为了不让读者把折算价当成行情价，三处展示都同时给出原币收盘：

- 报告头：`当前价：3.63 CNY（报价 3.95 HKD）`（`analysis._price_text`，quote 里的 `close_local/currency_local/fx` 由 `cli._quote_with_local` 写入 `inputs.quote`）；
- 数据包头：`报价 HKD 3.95（1 HKD = 0.92 CNY）`（`pack._quote_note`）；
- 站点个股页 lede：`现价 3.63 CNY（报价 3.95 HKD）`（`site._report_lede`）。

已知未统一：`ranking_hk.csv` 的 `total_market_cap` 仍是港元口径，而报告市值是人民币，同一家公司在 screener 与报告里市值数字不同；`fx.cny_per_hkd` 是配置常量，港元汇率大幅波动时需要手工改配置。

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

### 港股回购（HKEXnews，2026-11-17 接入）

港交所没有公开的回购日表接口（旧「每日股份購回報告」入口已 404），本地改为读**翌日披露報表**（Next Day Disclosure Return，FF305）：

- 检索：`search/prefix.do` 取 `stockId`，`search/titleSearchServlet.do` 按 `stockId + fromDate/toDate` 列文档，再下载 PDF 用 `pdfplumber` 解析；
- 解析：Part B 行形如 `N). Shares repurchased for cancellation but not yet cancelled 227,000 0.0025 % HKD 442.3505` + 下一行 `Date of changes 23 September 2026`，金额 = 股数 × VWAP；也兼容显式 `Buy-back date ... Aggregate price paid` 表；
- 窗口与平均：`hk_buyback_events(years=2)` 抓两年事件（最多 400 份、6 线程、7 天缓存）；`hk_buyback_amount(years=3)` 按自然年汇总且**只平均已完成年份**（当前年不计，避免部分年份拉低年化）；
- 币种：保留披露币种（多为 HKD，个别 RMB），进报告时按 `fx` 折成报表币种；
- 降级：失败记 `FetchIssue("hk_buyback", …, "HKEX 回购抓取失败：…")` 并返回空，报告照常生成（O=0）；
- 局限：ADR/美股回购不进披露易，双重上市可能低估；披露易数据再分发需授权；窗口内未回填 2024 年以前。

实测：00700 两年 **323 条**事件、年化 **81.88 亿港元**；20 只日更港股中只有 06069 有回购（292 万港元），其余确无回购记录。

## 美股（yfinance 实验）

| 项 | 来源/字段 | 状态 |
|:--|:--|:--|
| 三大报表 | `Ticker.financials/balance_sheet/cashflow` 标签映射 | 实验可用 |
| 行情/股本 | `info.marketCap/sharesOutstanding/currentPrice` + 1y history | 实验可用 |
| 分红 | `Ticker.dividends` | 实验可用 |
| 财务指标 | Tushare `us_fina_indicator` | 补充基本面；仅 ROE/毛利率/净利率/负债率/EPS |
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
- 补充基本面标准化：[extras.py](../src/turtlefw/data/extras.py)
- 补充基本面渲染：[report/extras.py](../src/turtlefw/report/extras.py)
- 现金桥：[cashflow.py](../src/turtlefw/metrics/cashflow.py)
- 缓存 schema：`TushareProvider.SCHEMA_VERSION = "turtle-9"`；升级字段后需换版本避免旧缓存。
