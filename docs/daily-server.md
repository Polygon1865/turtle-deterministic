# 每日生产：Windows 本机 + Cloudflare Tunnel

目标不是“再跑一个脚本”，而是让一台普通 Windows 电脑每天自动产出可访问的
A 股研究报告，并且失败时按配置保留上一版站点或发布部分结果。默认策略是 **Top 10：前 3 只启用 LLM
研究，其余 7 只走确定性报告**。

## 架构

```text
Task Scheduler 19:00
  -> scripts/run_daily.ps1
  -> scripts/daily_pipeline.py
       screen --fast --deep
       Top N
       per-stock: pdf-index (optional) -> run --strict
       QA/status -> build_site -> publish current
  -> Caddy 127.0.0.1:8080
  -> cloudflared named tunnel
  -> Cloudflare Access
```

关键原则：

- 数字只来自确定性 CLI；LLM 只写定性研究，不写报告数字；
- LLM 失败自动回退确定性报告，不阻塞当天发布；
- 新站点先构建到 `site/releases/<date>/`，成功后再切换 `site/current`；
- 全部股票失败或站点构建失败时 `site/current` 保持旧版本；部分失败按
  `publish_partial` 配置处理；
- Caddy 只监听 `127.0.0.1`，公网入口只经过 Cloudflare Access。

## 目录

```text
configs/daily.toml
scripts/run_daily.ps1
scripts/daily_pipeline.py
scripts/build_site.py
.runs/daily/<YYYY-MM-DD>/
  status.json
  ranking.csv
  ranking_deep.csv
  <code>/
    qa.json
    snapshot/manifest.json
    analysis_report.html
    pdf_index.json / pdf_notes.json
site/
  releases/<YYYY-MM-DD>/
  current -> releases/<YYYY-MM-DD>
data/pdfs/<code>/*.pdf
logs/
```

## 前置条件

1. 仓库已安装：`.venv\Scripts\python.exe -m pip install -e .`
2. `.env` 中有 `TUSHARE_TOKEN`；若要启用 LLM，再加
   `TURTLE_LLM_API_KEY`、`TURTLE_LLM_MODEL`（兼容 OpenAI 接口）。
3. 可选：把年报 PDF 放到 `data/pdfs/600887.SH/`，pipeline 会自动建页级索引；
   不放 PDF 也能正常出确定性报告。
4. Caddy、cloudflared 可放在 `C:\Tools\`，不必加入系统 PATH。

## 手工跑一次

```powershell
# 完整 screen + Top 10（会调用 Tushare，耗时取决于网络）
.\.venv\Scripts\python.exe scripts\daily_pipeline.py

# 跳过 screen，用指定代码做 Top 3 dry run
.\.venv\Scripts\python.exe scripts\daily_pipeline.py `
  --codes 600887.SH,000858.SZ,600519.SH `
  --top 3 --llm-top 0 `
  --runs-root .runs\daily-dry --site-root .runs\site-dry

# 只重建站点，不重新跑股票
.\.venv\Scripts\python.exe scripts\build_site.py `
  --day-dir .runs\daily\2026-10-21 --site-root site
```

`run --with-research` 需要 LLM key；没有 key 时只跑确定性报告。`--llm-top 0`
可以在验收阶段完全关闭 LLM。

`screen` 输出会带 `交易日: YYYYMMDD`。pipeline 要求它等于当天，否则每 30 分钟
重试，最多 3 次；仍不匹配则失败并保留旧站点。节假日可加 `--allow-stale` 手工验收，
但定时任务不要开。

## 配置

`configs/daily.toml` 只放策略，不放密钥：

```toml
top_n = 10
llm_top_n = 3
fast_limit = 80
deep_limit = 30
rf = ""
research_max_input_tokens = 60000
screen_attempts = 3
retry_seconds = 1800
refresh_market = true
publish_partial = true
```

- `top_n`：进入逐票分析的排名数量；
- `llm_top_n`：前 N 只调用 `--with-research`；其余确定性；
- `rf`：留空使用 provider；固定值用字符串，例如 `"2.0"`；
- `refresh_market`：每日绕过 7 天行情缓存；
- `screen_attempts/retry_seconds`：交易日未更新时的重试策略。

## Task Scheduler

创建每天 19:00 的任务（或收盘后你的固定时间）：

- 程序：`powershell.exe`
- 参数：`-NoProfile -ExecutionPolicy Bypass -File "C:\PyProject\turtle-framework\scripts\run_daily.ps1"`
- 起始于：`C:\PyProject\turtle-framework`
- 勾选“不管用户是否登录都运行”（需要保存凭据）；
- 电源：允许唤醒计算机执行任务，任务结束后可睡眠；
- 失败告警：在“操作”里追加一个发送邮件/HTTP 的步骤，或使用
  `TURTLE_NOTIFY_WEBHOOK`（pipeline 会 POST 精简 JSON）。

PowerShell 脚本会把输出写到 `logs/daily-<timestamp>.log`，退出码非 0 时
Task Scheduler 会显示失败。

## Caddy

`Caddyfile`：

```caddyfile
:8080 {
    bind 127.0.0.1
    root * C:\PyProject\turtle-framework\site\current
    file_server
    encode gzip
}
```

启动：

```powershell
C:\Tools\caddy\caddy.exe run --config C:\Tools\caddy\Caddyfile
```

建议用 `nssm` 或 Windows 服务包装 Caddy，让它开机自启；不要把它绑定到
`0.0.0.0`。

## Cloudflare Tunnel

Day 0 临时隧道（先验证链路，不改 DNS）：

```powershell
cloudflared tunnel --url http://127.0.0.1:8080
```

它会输出一个 `https://<random>.trycloudflare.com` 地址。确认手机能打开后，
再做命名隧道：

```powershell
cloudflared tunnel login
cloudflared tunnel create turtle-daily
cloudflared tunnel route dns turtle-daily daily.example.com
```

`%USERPROFILE%\.cloudflared\config.yml`：

```yaml
tunnel: turtle-daily
credentials-file: C:\Users\<you>\.cloudflared\<tunnel-id>.json
ingress:
  - hostname: daily.example.com
    service: http://127.0.0.1:8080
  - service: http_status:404
```

安装为 Windows 服务：

```powershell
cloudflared service install
```

## Cloudflare Access

在 Zero Trust → Access → Applications 为 `daily.example.com` 建应用：

- 只允许你的邮箱/Google/GitHub 身份；
- 会话时长 7 天；
- 不暴露 `site/` 目录列表，Caddy 只读 `current`；
- 若只想自己看，保留 Access；若要公开，至少去掉私有财务数据并评估合规。

## 3 天验收

**Day 0**

- 手工跑 `--codes ... --llm-top 0`，确认 3 个代码都 `qa=PASS`；
- 打开 `site/current/index.html`，点开每只股票报告；
- 临时 cloudflared 隧道 + 手机访问；
- 断开 Caddy/隧道，确认旧站点仍可访问。

**Day 1**

- 配好命名隧道 + Access；
- Task Scheduler 跑一次，确认 19:00 自动执行；
- 人为让 `screen` 返回旧交易日（或用 `--allow-stale` 的测试日期），确认重试和失败保留旧站点；
- 检查 `status.json`、`qa.json`、日志和 `health.txt`。

**Day 2**

- 恢复交易日检测，跑完整 Top 10；
- 删掉一只股票的 PDF，确认“无 PDF 不阻塞”；
- 临时移除 LLM key，确认前 3 只回退确定性且站点仍发布；
- 记录耗时、失败率和磁盘占用。

## 发布与回滚

- 每次成功构建写 `site/releases/<date>/`；当天重复构建会写 `<date>-1` 等后缀，
  不删除旧 release；`site/current` 是 junction/symlink；
- 默认 `publish_partial = true`：部分股票失败时仍发布成功股票，首页/health 标出
  失败；设 `publish_partial = false` 则任一股票失败都保留旧站点；
- 全部股票失败或构建失败时不切换 `current`；
- 手工回滚：删除 `current`，对目标 release 重建 junction，或运行
  `build_site.py` 从旧 day 目录重建；
- 建议保留 90 天 release，定期清理 `.runs/daily` 和 `site/releases`。

## 边界

- 只覆盖 A 股；港股/美股不在每日流水线内；
- PDF 是文本层 PDF，扫描件需要 OCR（当前不做）；
- `anns_d`/`news` 权限、vendor PIT、分部自动提取仍是外部边界；
- LLM 只写定性研究；没有 key 或调用失败时回退确定性；
- 单机方案不是高可用：断电/睡眠/网络故障会跳过当天，旧站点保留。
