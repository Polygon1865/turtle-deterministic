# 本地更新后 vs v2：真实差距（2026-10-19）

> v2 基线：`terancejiang/Turtle_investment_framework` HEAD `c61419c`（2026-07-04，v2.1-beta，未变）。  
> 本地基线：本轮完成 SBC/稀释/复权/PIT、税档/OE、PDF 附注/股东分部之后。

## 一句话

**本地已经把“数字正确、可复现、可审计”这条线做完了；v2 仍然领先的是“信息密度、覆盖广度、自动化深度”。**  
两者不是同一类产品：v2 是 LLM-first 的全流程研究 Agent，本地是确定性数字内核 + 可选 Agent 层。

## v2 仍然领先的地方

| 维度 | v2 | 本地现状 | 差距性质 |
|:--|:--|:--|:--|
| PDF-first 定性 | 单 Agent 读 1M 上下文 PDF，D1–D6、MD&A/治理/附注、38 参数输出 | PDF 能抽 6 项数字、SBC、HK 间接桥、附注表格结构；定性仍是 6 模块 JSON + 提示词 | **最大真实差距** |
| 数据覆盖 | 28 个 Tushare 接口；A/HK/US、母公司、质押、回购、股东、主营 | A/HK；A 股母公司/质押/回购/股东/主营已接；US、港股股东/分部、部分历史数据仍缺 | 广度差距 |
| 中报/季度 | 支持中报/季度年化、双 PDF | 中报/季报只进数据包“年化参考”，因子/估值/报告仍用年报 | 口径差距 |
| 报告厚度 | 9 章、1000+ 行、行业/竞对/管理层/控股结构 | Markdown ~10k 字节、约 200 行；Thesis Card 基础版；HTML 无图表 | 信息密度差距 |
| clean-room/质量门 | quality_control、report_consistency、clean-room、numeric audit | 机械 verify/qa + deterministic report；clean-room 只有设计文档 | 质量基础设施差距 |
| 因子 3 调整项 | 11 步现金桥（S/T/U、W1–W4、V1/V5、X1/X2） | 核心现金桥（真实现金收入、经营流出、Capex、WC）；PDF 间接桥；未覆盖全部 V/X 调整 | 方法论细节差距 |
| 估值广度 | 1,516 行 valuation_engine；方法选择/假设更多 | 纯函数 DCF/DDM/PE/PEG/PS + 分类/权重/5×5/反推；无 peer comps、SOTP、公司特定 WACC | 广度差距 |
| 缓存/刷新 | TTL + `--refresh-market` | 内容寻址缓存，无 refresh 命令 | 运维差距 |
| 测试规模 | 875 个测试函数 / ~923 收集 | 362 收集 / 362 通过 / 0 setup error | 覆盖差距，但不是纯数量可比 |
| Agent 自动化 | 41 个 prompt、8k 行、slash command/skill | 17 个 prompt + `.claude` 入口；流程仍需手动/Claude 驱动 | 自动化差距 |

## 本地已经追平或反超的地方

- **确定性数字内核**：Money/Currency、Tri-state、snapshot、内容寻址缓存；v2 仍以 LLM 选表/抄数为主。
- **A/HK 币种与分红修复**：港股 FX、reporting currency、DPS 重复、分红 `—`；v2 仍有硬编码/静默降级。
- **现金桥/底价/G/M**：确定性 grids、负锚点剔除、composite、税档情景、5 年正常化 OE。
- **SBC/稀释/复权/PIT（部分）**：PDF SBC、稀释股数、A 股后复权、`--as-of` 行情/上市状态；v2 未见同等级确定性实现。
- **PDF 审计**：6 项数字 + 港股 PDF 间接桥 + 附注表格结构；600887/00700 实盘通过。
- **A 股治理数据**：母公司现金、质押、回购、股东、主营；v2 有但本地是确定性接入。
- **机械证据门**：URL/引文校验、narrative whitelist、QA state machine；比 v2 的 LLM 自报审计更硬。
- **测试可复现**：纯函数估值/现金桥/税档测试，不依赖 token。
- **入口/交付**：CLI、HTML、`.claude` commands/skill、Windows 安装。

## 不值得照抄的 v2 部分

- 让 LLM 重算 R/GG/底价；
- v2 的 prompt 文本测试（大量子串断言，部分指向旧版存档）；
- LLM 自报 `AUDIT_RESULT` / clean-room 结论；
- 个人站式 HTML 硬编码；
- 为了“参数数量”而扩 38 参数，却没有证据链/表格结构。

## 真实优先级

### P0（会改判断）
1. **PDF-first 定性**：把附注表格/证据接到 D1–D6，输出可校验的 38 参数或等价 schema；本地现在只到“表格结构”。
2. **数据广度**：US、港股股东/分部、中报/季度进入因子与估值、完整 PIT 财务快照。
3. **因子 3 全调整**：补齐 V1/V5、X1/X2、税档真实进入结论（现在税档只展示）。
4. **报告深度**：行业/竞对/管理层/控股结构，不是简单加长，而是把 PDF 证据落到章节。

### P1（会改效率/可信度）
5. clean-room runner + live CI + golden set（设计已有，未实现）；
6. 估值 peer comps/SOTP/公司特定 WACC；
7. 缓存 TTL/refresh、报告图表/PDF 导出；
8. 回购注销净股数、SBC treasury-stock method、期权/可转债稀释。

### 已经不用追
- 数字确定性、A/HK 币种/分红、底价负锚点、税档/OE 基本盘、PDF 6 项审计、A 股治理数据、HTML/Claude 入口。

## 结论

**本地现在不落后于 v2 的“数字可信度”，落后的是“研究信息密度 + 数据覆盖 + Agent 自动化”。**  
如果只继续做一件事，做 **PDF-first 定性 + 数据广度**；如果只做工程，做 **clean-room/live CI**。不要再为了追 v2 把数字交回 LLM。
