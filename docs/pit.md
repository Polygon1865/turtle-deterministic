# PIT 快照库

## 目标

同一份报表在不同日期可能被修订、重述或补发。普通 `--as-of` 只是拿“今天取到的最新报表”按公告日过滤，无法区分：

- 2025-04-30 第一次公告的 2024 年报；
- 2026-04-30 重述后的 2024 年报；
- 2025-08-30 才公告的 2025 中报。

PIT 库把“某天知道的完整报表集合”冻结成不可变 snapshot，查询 `as_of` 时选择该日期之前最新的知识快照。

## 存储

默认根目录：

```text
.runs/pit/<code>/
  index.json
  2025-04-30_<snapshot_id>.json
  2026-04-30_<snapshot_id>.json
```

每份 snapshot：

- `code`、`knowledge_date`、`source`、`backfill`；
- 完整 `StatementRow` 列表（含 `ann_date`）；
- `snapshot_id` = canonical rows + metadata 的 content hash；
- `created_at` 只在 index 中，不参与 snapshot ID。

## 命令

```powershell
$env:TURTLE_OUTPUT_DIR = ".runs"

# 当前数据冻成一个快照
turtle pit freeze --code 600887 --known-at 2026-10-19

# 用当前可得的 ann_date 回填 21 个累计快照
turtle pit freeze --code 600887 --backfill

turtle pit list --code 600887
turtle pit show --code 600887 --as-of 2025-06-30
turtle pit export --code 600887 --as-of 2025-06-30 --out .runs/pit/600887_20250630.json
```

查询：

```powershell
turtle report 600887 --as-of 2025-06-30 --pit
turtle pack 600887 --as-of 2025-06-30 --pit
```

## 查询语义

1. 只考虑 `knowledge_date <= as_of` 的 snapshot；
2. 取其中 knowledge date 最新的一份；
3. 同一 `(period_end, statement, item)` 多条记录时，取 `ann_date` 最新的一条；
4. 再按 `ann_date <= as_of` 过滤。

## backfill 的边界

`--backfill` 用**当前数据 + ann_date** 造累计快照，能模拟“当时已知哪些报表”，但：

- 不能还原真正被覆盖的旧版本；
- 不能还原重述前的数字；
- 不能还原供应商历史快照。

所以：

- 新数据从今天开始 `pit freeze`，才能捕获真实 restatement；
- 历史回测只能用 backfill，报告中必须标注是回填；
- 不能把 backfill 当成完整 vendor PIT。

## 报告显示

- `report --pit` 会在数据问题中显示：
  `PIT snapshot <id> known=<date>；市值近似`
- 无对应 snapshot 时回退公告日过滤，并明确提示。
