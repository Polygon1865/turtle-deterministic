# 00700.HK 已知差异（2025 年报）

## 1. 营业收入：PDF 751,766 vs Tushare 743,689

| 来源 | 数值（RMB million） |
|:--|--:|
| 年报合并报表 / MD&A | 751,766 |
| Tushare HK line item | 743,689 |
| 差额 | 8,077 |

差额等于年报分部表中的 **Others** 收入：

| 分部 | 2025 |
|:--|--:|
| VAS | 369,281 |
| Marketing Services | 144,973 |
| FinTech and Business Services | 229,435 |
| **Others** | **8,077** |
| **The Group** | **751,766** |

Tushare 的 `revenue` 行没有把 Others 并入总额，导致约 **1.09%** 的差异，略高于默认 1% 审计阈值。

### 处理决定

- **不手工修正 Tushare 数值**，避免引入不可追溯的调整；
- 在 audit 中保留该差异；
- 报告/数据包必须能解释：差额 = Others 分部；
- 如果后续要调整，应通过独立字段 `segment_others` 或 PDF override，并记录来源页码。

## 2. PDF 分区 4/7：不是“少抽了三节”

`00700.pdf` 当前识别到：

- P2：restricted cash 相关页（含合并报表附近文本）
- P4：related party / substantial shareholders
- MDA：管理层讨论与分析
- SUB：附注/会计政策附近文本

未识别：

- P3：应收账款账龄
- P6：或有负债
- P13：非经常性损益

腾讯这份 HK 年报没有按 A 股模板提供这三个独立章节；因此“4/7”是**报告结构差异**，不是单纯抽取 bug。当前 `pdf_sections.json` 会把这些位置留空，Agent 应把它们标为 `unknown`，不能猜。

## 4. 已实现的语义抽取

```powershell
turtle pack 00700.HK --pdf-sections output\00700.HK\pdf_sections.json
```

输出：

- 前十大股东：MIH Internet Holdings B.V. 22.80%、Advance Data Services 8.82%；
- 分部收入：VAS 369,281、Marketing Services 144,973、FinTech and Business Services 229,435、Others 8,077；
- 校验：分部合计 751,766 = The Group；
- 不手工修正 Tushare 的 743,689。

## 5. 后续改进

1. 分区识别增加“章节标题 + 表格形状”双条件，减少 P2/P4 误命中；
2. 港股股东从 P4 的 “INTERESTS OF SUBSTANTIAL SHAREHOLDERS” 表做语义抽取；
3. 港股分部收入从 MDA 的 segment table 做语义抽取，并保留 “The Group” 合计校验；
4. 对已知的 Others 差异建立 `known_differences` 记录，避免每次审计重复告警。
