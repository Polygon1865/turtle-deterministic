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

## 重冻记录

- **2026-11-16（2026-11-17 重冻）**：接入港交所回购数据（W2.7）后重跑该日，`check`
  报 142 处差异——价格按当日行情刷新、研究 claims 因 LLM 重跑波动（多条 6–22 条不等）、
  `000651.SZ` research 回退（研究层写了不存在的 `{{fact:data:governance}}`）、
  `000921`/`002478` 的研究状态与 QA 互换。回购只影响有回购记录的公司（20 只港股里
  只有 06069），不改变其余标的的确定性数字。差异逐条对照后删除旧文件并重冻，现基线
  为 40 只、ok 40、QA PASS 1、研究 on 38。

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

## 方案 B 之后（2026-11-16）

- 现有 6 天 golden（2026-11-08 → 11-13）冻结的是**方案 B 之前**的产物：底价只有一个
  综合中位数、港股分红是供应商 TTM 占位值。它们是历史记录，`check --all` 仍应通过
  （只读当天写下的 status/报告，不重渲）。
- 下一次 daily（2026-11-17）会用新口径落盘：底价拆资产/收益、港股分红换成真实除息
  事件，因此**新一天的 golden 与这 6 天不可直接横向比较**。首次冻结新日期时，先在
  PR/提交说明里写清「方案 B 口径变更」；之后的差异才是回归信号。
- 若要重冻结某天：删掉对应 `tests/fixtures/golden-daily-<date>.json` 再 `freeze`，
  不要手改 JSON（ADR-11 第 3、4 条）。
- 2026-11-16 已按方案 B（含「收益组锚点不足 → 结论封顶观察」）重新运行并冻结为
  `tests/fixtures/golden-daily-2026-11-16.json`：40 只、QA 2 PASS / 38 WARN、
  研究 38 on / 2 回退，结论 买入 9 / 观察 12 / 排除 19。它是方案 B 之后的第一份
  golden，可作为后续新口径差异的起点。
