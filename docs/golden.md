# Golden 基线（W6.1）

## 这是什么

`tests/fixtures/golden-daily-<date>.json` 是某个 daily run 的**结论快照**：每只股票的
verdict、R/GG/II/安全边际/底价/溢价/支付率/价格/PB/FCF 收益率、QA/研究状态、claims 数。
它刻意不含排版，所以改模板不会让基线失败；只有**结论或数字变了**才算漂移。

当前覆盖 6 天（2026-11-08 → 2026-11-13，各 40 只，总计约 240 个股票日），冻结命令：

```powershell
.\.venv\Scripts\python.exe scripts\golden.py freeze --days 6   # 冻结最新的 6 个归档日
.\.venv\Scripts\python.exe scripts\golden.py check --all        # 回放全部冻结日
```

单日：

```powershell
.\.venv\Scripts\python.exe scripts\golden.py freeze --date 2026-11-13
.\.venv\Scripts\python.exe scripts\golden.py check --date 2026-11-13 --tol 0.01
```

`check` 逐字段打印差异（`00270.HK metrics.r 6.29 -> 6.79`），有差异时退出码 1；
`--no-fail` 只报告不失败。

## 更新协议（ADR-11）

1. **只在变化被解释后重新冻结**：先 `check --all`，把差异按「预期/意外」分类；预期
   变化（例如修了某个口径）在 PR/提交说明里写清楚哪只、哪个字段、为什么。
2. **格式/模板/前端改动不需要更新 golden**；如果 `check --all` 报告的是 `structure`
   或 `qa_fail`，先确认不是回归。
3. **不允许为了让 check 通过而手改 JSON**；重新 `freeze` 之前必须先解释差异。
4. **新增冻结日**：`freeze --days N` 只会补缺失日期，不会覆盖已有文件；要重冻某天，
   先删除该文件再跑。
5. 容差默认 `--tol 0.01`（百分比字段 0.01pp，价格/倍数 0.01）。跨库/换数据源时用
   `--tol 0.05` 并说明原因。

## 为什么要「全市场」

单日 golden 只覆盖当天被筛中的 40 只；同一批标的每天几乎不变，一次模板/口径改动
可能只影响没被覆盖的股票（例如港股 vs A 股的分支）。冻结多天能把「A 股/港股、
买入/观察/排除、研究 on/fallback」几类样本都固定下来——当前 6 天里就有 38/40 与
40/40 两种研究覆盖状态，以及买入 1–3 只的分布。

## CI 与本地

- CI 不跑 `check --all`（仓库里没有 `.runs/daily`），只跑 `tests/test_golden_baseline.py`
  对 `collect/compare/freeze/check_all` 的离线单测。
- 本地/夜间任务在跑完 daily 后执行 `check --all`，差异进日报或直接失败，避免「结论
  悄悄翻转」再次发生（2026-11-04 的 00270 就是这样从买入变排除的）。
