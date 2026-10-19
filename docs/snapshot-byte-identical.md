# Snapshot + Content Hash：如何做到“同一 snapshot 报告逐字节一致”

> 结论先说：**“逐字节一致”不是“同一只股票永远同一份报告”，而是“同一个 ReportSnapshot（数据 + 研究产物 + 配置 + 模板 + 渲染器版本）重新渲染，输出字节完全相同”。**  
> 任何输入变化都必须产生新 snapshot；旧 snapshot 不允许原地修改。

## 1. 先定义三种 snapshot

| 层 | 内容 | 作用 |
|:--|:--|:--|
| `SourceSnapshot` | Tushare/HKEX/SEC 原始响应、PDF 文件、抓取元数据 | 审计“数据从哪来” |
| `FactsSnapshot` | 标准化报表、`MetricPoint`、`DocumentFact`、discrepancies | 审计“数字怎么算” |
| `ReportSnapshot` | Facts + 已批准的 research artifact + 配置 + 模板 + 渲染器/公式版本 | 审计“报告怎么生成” |

只有 `ReportSnapshot` 能承诺逐字节一致。  
`SourceSnapshot` 相同但 `FactsSnapshot` 算法变了，报告可以不同；`FactsSnapshot` 相同但 research/模板变了，报告也会不同。

## 2. Hash 链

```text
source_id       = SHA256(原始 API 响应 / PDF 字节)          # 溯源用
facts_hash      = SHA256(canonical_json(标准化 facts + metrics))
config_hash     = SHA256(canonical_json(有效配置))
research_hash   = SHA256(canonical_json(已批准的 research claims + evidence))
template_hash   = SHA256(模板文件字节)
snapshot_id     = SHA256(canonical_json({
                    as_of, code, currency,
                    facts_hash, config_hash,
                    research_hash, template_hash,
                    engine_version, formula_version,
                    report_format_version
                  }))[:32]
report_hash     = SHA256(最终报告字节)
```

注意两个 ID 的分工：

- `source_id` 只用于**溯源**：同样的逻辑数据，如果供应商返回的 JSON 字节不同（请求 ID、字段顺序），`source_id` 会变，但报告不一定需要变；
- `snapshot_id` 只覆盖**语义输入**：facts/config/research/templates/version；同一份 facts 重新抓取，`snapshot_id` 不变，报告仍可逐字节复现；
- 如果确实需要“原始响应也必须一致”，再加一个 `strict_source_snapshot_id`，不要和报告 ID 混在一起。

关键点：

- `snapshot_id` 是**内容 ID**，不是时间 ID；
- `created_at`、抓取时间、机器名、临时路径不进入 `snapshot_id`；
- `snapshot_id` 不包含自身，避免自引用；
- `report_hash` 放在 sidecar manifest，不写进报告正文（否则自引用）；
- 同一个 `snapshot_id` 必须能定位到不可变的 facts/research/template 文件。

## 3. Canonical JSON：hash 稳定的前提

同一个逻辑对象，序列化必须唯一：

```json
{
  "as_of": "2025-12-31",
  "currency": "CNY",
  "metrics": [{"id": "revenue", "value": "115636231250.05", "unit": "元"}]
}
```

规则：

1. 对象 key 按字典序排序；
2. UTF-8、无 BOM、`ensure_ascii=False`；
3. 固定分隔符（如 `(",", ":")`），无多余空格；
4. `Decimal` 统一为字符串，固定精度；禁止二进制 float 进入 hash；
5. 日期统一 ISO `YYYY-MM-DD`；
6. `null` 显式保留，不用缺失 key；
7. 列表顺序必须由业务键决定（如 year、statement、item），不能依赖 dict/set 迭代；
8. 排除 `retrieved_at`、`hostname`、`tmp_path`、token、日志；
9. 配置必须“有效配置快照”，不是 TOML 原文（默认值展开、环境变量已解析）。

否则同一数据在不同进程/机器上 hash 不同。

### Manifest 示例

```json
{
  "snapshot_id": "9f2c...",
  "source_id": "a31b...",
  "as_of": "2025-12-31",
  "code": "600887.SH",
  "currency": "CNY",
  "facts_hash": "b7e1...",
  "config_hash": "c042...",
  "research_hash": "d9a8...",
  "template_hash": "e113...",
  "engine_version": "turtlefw 0.1.0",
  "formula_version": "2026-10-19.1",
  "report_format_version": 1,
  "report_hash": "7f4d...",
  "created_at": "2026-10-19T12:00:00+08:00"
}
```

`created_at` 只放 manifest/sidecar，不进入 `snapshot_id`，也不写进报告正文；否则同一内容在不同时间渲染会字节不同。

## 4. 渲染器必须“无环境”

报告渲染只读 `ReportSnapshot`，禁止：

- 网络请求、重新取 Tushare/yfinance；
- `datetime.now()` / `date.today()`；
- 随机数/UUID/临时目录；
- 依赖 locale 的格式化；
- 依赖 dict/set 迭代顺序；
- 从环境变量/当前工作目录读配置。

当前需要改的两个真实点：

- `pack.py` 的 52 周窗口使用 `date.today()`；应改为 snapshot 的 `as_of`；
- `pack.py` / `analysis.py` 的 `generated_at=datetime.now()`；应改为 snapshot 的固定 `as_of` 或 `snapshot_id`，或干脆不显示时间。

Jinja/Markdown 固定：

- `newline_sequence="\n"`、UTF-8、无 BOM；
- `trim_blocks/lstrip_blocks` 固定；
- 表格排序有稳定 tie-breaker（如代码、年份、名称）；
- Decimal 用固定 `quantize` 和 `ROUND_HALF_UP`；
- HTML 转换器同样禁止时间/随机/环境依赖。

## 5. Agent 研究产物也要冻结

LLM 本身不确定。要逐字节一致，不能每次渲染都重新跑 LLM，而是：

1. Agent 生成 `research.json`（claims + evidence）；
2. 人工/审计批准；
3. 冻结为不可变 artifact，算 `research_hash`；
4. 渲染器只读这个 artifact。

因此：

- 重跑 LLM → 新 `research_hash` → 新 snapshot；
- 同一 `research_hash` + 同一 facts/template → 报告字节一致；
- 没有 research artifact 时，研究段落输出 `unknown`，确定性部分仍完整。

这不是“让 LLM 变确定”，而是**把 LLM 输出变成可审计、可复现的输入**。

## 6. 报告里哪些东西必须去掉/固定

| 字段 | 处理 |
|:--|:--|
| `generated_at` | 用 `as_of` 或 `snapshot.created_at`（sidecar），报告正文不写 `now()` |
| 当前价/52 周窗口 | 用 snapshot 的 `as_of`，不用 `date.today()` |
| 数据快照 ID | 用 `snapshot_id`，不用随机/时间 ID |
| 文件路径 | 不写绝对路径；写逻辑 artifact 名 |
| 排序 | 明确业务键；禁止依赖数据库返回顺序 |
| 币种/单位 | 固定 ISO 币种 + 固定单位 |
| CSS/模板 | 内容 hash；版本变更需 bump `report_format_version` |

## 7. 如何验证“逐字节一致”

```powershell
# 1. 冻结 snapshot（未来命令）
turtle snapshot freeze 600887 --as-of 2025-12-31 --out snapshots/600887-2025

# 2. 从 snapshot 离线渲染两次
turtle report --snapshot snapshots/600887-2025 --out out/a.md
turtle report --snapshot snapshots/600887-2025 --out out/b.md

# 3. 比较字节
Get-FileHash out/a.md -Algorithm SHA256
Get-FileHash out/b.md -Algorithm SHA256
cmp out/a.md out/b.md   # Linux/macOS
```

验收：

- 两个文件 SHA256 相同；
- 换进程、换工作目录、断网后仍相同；
- 同一 snapshot 在 CI 上生成 golden hash，报告变化必须显式更新 snapshot/版本，不能“偷偷变”。

## 8. “逐字节一致”不保证什么

- 不保证数字正确：只保证“同样输入同样输出”，正确性仍靠 audit；
- 不保证 LLM 判断正确：只保证研究产物被冻结；
- 不保证跨 Python/pdfplumber 版本一致：事实应从 `FactsSnapshot` 读取，不要渲染时重新解析 PDF；
- 不保证不同 snapshot 一样：新数据/新研究/新模板 = 新 snapshot；
- 不保证 PDF 本身是正确版本：需要 document hash + 公告 URL/日期。

## 9. 当前代码差距

| 现状 | 目标/状态 |
|:--|:--|
| `_snapshot_id(rows)` 只 hash 报表行 | `ReportManifest` 已覆盖 facts/config/research/template；报告头仍用 rows ID，待统一 |
| 报告用 `datetime.now()` | 已移除，使用 `as_of` |
| 52 周窗口用 `date.today()` | 已改为 `as_of` |
| `report` 每次实时取数 | 已支持 `report --save-snapshot` + `report --snapshot` 离线渲染 |
| research 是可选 JSON，无 hash | 已冻结 `research.json` 并计算 `research_hash` |
| 无 report manifest | 已生成 `manifest.json` |
| 无 golden hash | 未做；Phase 4 接 CI |

已实测：live 与 offline snapshot 渲染 SHA256 相同；同一输入两次报告相同。

## 10. 推荐实现顺序

1. 先做 `ReportSnapshot` manifest + `--snapshot` 离线渲染；
2. 移除 `now()/today()`，固定 `as_of` 和排序；
3. facts/config/template 全部 hash；
4. research 冻结 + `research_hash`；
5. CI golden：同一 snapshot 渲染两次 + 跨进程/断网校验；
6. 最后再接 Agent 自动化；Agent 只写 research artifact，不碰渲染。

## 11. 一句话

**Snapshot 是“输入闭包”，content hash 是“输入指纹”，逐字节一致是“同一闭包 + 同一渲染器”的输出契约。**  
它保护的不是“报告永远不变”，而是“报告为什么变成这样，可以精确重放”。
