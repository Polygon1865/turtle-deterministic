# Live smoke 与 golden set

## 1. Golden set（离线）

仓库已有两类离线 golden：

- `tests/fixtures/pdf_gold_*.json`：11 份官方年报的 PDF 数字/页码断言，由
  `tests/test_pdf_gold.py` 参数化执行。PDF 不进仓库；没有 PDF 时测试跳过。
- `tests/fixtures/*` / `tests/test_*`：确定性指标、snapshot、numeric audit、
  research validator 等固定 fixture。

运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -o addopts="" -q tests\test_pdf_gold.py
```

CI 没有 PDF 文件时会 skip，不把“skip”误报为通过。

## 2. Live smoke（联网）

`scripts/live_smoke.py` 对真实 Tushare 数据跑完整 `run`，检查的是**管线不变量**，
不是固定数字（行情/公告每天变化）：

- CLI 退出码；
- `qa.json` 总体状态与 FAIL 行；
- `snapshot/manifest.json` 的 code、32 位 snapshot_id；
- `numeric_status=pass`、`numeric_coverage >= 0.9999`；
- `analysis_report.md` / `data_pack.md` 存在。

```powershell
$env:TUSHARE_TOKEN = "..."
.\.venv\Scripts\python.exe scripts\live_smoke.py `
  --codes 600887.SH,000858.SZ,600519.SH `
  --output-dir .runs\nightly `
  --json-out .runs\nightly\summary.json
```

只校验已有产物、不重新取数：

```powershell
.\.venv\Scripts\python.exe scripts\live_smoke.py `
  --codes 600887.SH --output-dir .runs\nightly --no-run
```

没有 `TUSHARE_TOKEN` 时脚本打印 skip 并返回 0，便于在本地/CI 安全运行。

## 3. Nightly CI

`.github/workflows/nightly.yml` 每天 18:00 UTC 运行；只有配置了仓库 secret
`TUSHARE_TOKEN` 才执行，否则跳过。产物上传 `live-smoke` artifact，保留 14 天。

## 4. 边界

- Live smoke 失败可能是数据源/权限/网络导致，不一定是代码回归；先看
  `qa.json` 的 FAIL 行和 summary 的 detail。
- `report_rc` 试用权限约 10 次/日；nightly 默认 3 个 code、每个一次，仍应避免在
  本地反复重跑。
- 该 harness 不覆盖真实 LLM 输出质量；LLM 回归用
  `research-agent --response` 离线回放，见 [研究层](research-layer.md)。
