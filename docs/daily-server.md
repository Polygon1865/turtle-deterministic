# 每日生产：Windows 本机 + Cloudflare Tunnel

目标不是“再跑一个脚本”，而是让一台普通 Windows 电脑每天自动产出可访问的
A 股研究报告，并且失败时按配置保留上一版站点或发布部分结果。默认策略是
**全市场筛出 100 个候选，对前 20 名逐只生成确定性报告**；LLM 研究默认关闭，
需要时用 `--llm-top N` 只对前 N 只启用。

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
   计划任务通过 `scripts/run_daily.ps1` 启动；如果进程环境缺少这些变量，
   脚本会从当前 Windows 用户的环境变量回退读取，因此不需要把 key 写进脚本。
3. 可选：把年报 PDF 放到 `data/pdfs/600887.SH/`，pipeline 会自动建页级索引；
   不放 PDF 也能正常出确定性报告。
4. Caddy、cloudflared 可放在 `C:\Tools\`，不必加入系统 PATH。

## 手工跑一次

```powershell
# 完整 screen + 前 20 报告（会调用 Tushare，耗时取决于网络）
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
可以在验收阶段完全关闭 LLM。LLM 输出校验失败会按 `research_retries`（默认 1）
重试；仍失败则删除该股票残留的 research 产物，回退确定性报告，并在
`status.json` 的 `research_error` 记录原因。

`screen` 输出会带 `交易日: YYYYMMDD`。pipeline 要求它等于当天，否则每 30 分钟
重试，最多 3 次；仍不匹配则失败并保留旧站点。节假日可加 `--allow-stale` 手工验收，
但定时任务不要开。

`ranking.csv` 保留快速筛选的 100 只，`ranking_deep.csv` 保留进入深度分析的 20 只；
`build_site` 会把两份 CSV 一并复制到当日 release，方便下载核对。

## 配置

`configs/daily.toml` 只放策略，不放密钥：

```toml
top_n = 20
llm_top_n = 0
fast_limit = 100
deep_limit = 30
rf = ""
research_max_input_tokens = 60000
research_retries = 1
screen_attempts = 3
retry_seconds = 1800
refresh_market = true
publish_partial = true
```

- `fast_limit`：快速筛选后保留的候选数（默认 100，写入 `ranking.csv`）；
- `deep_limit`：进入深度分析的候选数（默认 30，写入 `ranking_deep.csv`；比 `top_n` 多留失败缓冲）；
- `top_n`：从深度排名中取前 N 只逐票生成报告（默认 20）；
- `llm_top_n`：前 N 只调用 `--with-research`；默认 0，全部确定性；
- `research_retries`：LLM 输出校验失败时的重试次数（默认 1）；仍失败则回退确定性；
- `rf`：留空使用 provider；固定值用字符串，例如 `"2.0"`；
- `refresh_market`：每日绕过 7 天行情缓存；
- `screen_attempts/retry_seconds`：交易日未更新时的重试策略。

## Task Scheduler

创建每天 19:00 的任务（或收盘后你的固定时间）：

- 程序：`powershell.exe`
- 参数：`-NoProfile -ExecutionPolicy Bypass -File "C:\PyProject\turtle-framework\scripts\run_daily.ps1" --llm-top 10`
- 起始于：`C:\PyProject\turtle-framework`
- 勾选“只在用户登录时运行”；脚本会回退读取该用户的 LLM 环境变量。
  若必须无人值守，需把变量放到系统环境或改用凭据存储；
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

启动（仓库内脚本，幂等：8080 已在监听时直接退出）：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\PyProject\turtle-framework\scripts\run_caddy.ps1 -Supervise
```

`-Supervise` 让脚本在 Caddy 意外退出后隔几秒自动重启（死在 5 秒内的崩溃循环会
退避 30 秒），适合登录项/常驻场景；不带 `-Supervise` 时跑一次就退出，适合手动
排障。每次调用和每次退出都追加一行到 `logs/caddy-launch.log`（含时间、PID、
no-op/重启原因），所以“到底是谁拉起/拉没拉起来”可以直接查这个文件。

Caddy 的 stderr 追加到 `logs/caddy.log`。Caddy 是隧道的**唯一原点**：它没起来时
cloudflared 服务仍然是 Running、隧道也有 connector，但

- 浏览器看到 502 / Error 1033；
- `logs/cloudflared.log` 反复出现
  `dial tcp 127.0.0.1:8080: connectex: No connection could be made because the
  target machine actively refused it`；
- `http://127.0.0.1:20242/metrics` 的 `cloudflared_tunnel_request_errors`
  持续增长。

排查顺序固定为：`netstat -ano | findstr :8080` 有没有 LISTENING →
`curl http://127.0.0.1:8080/health.txt` 是否 200 → 再怀疑隧道/Access。

Caddy 必须自启，否则重启或注销后站点只剩 502。现成做法：把
`scripts/startup/turtle-caddy.vbs` 复制进
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`（删除即停用，无需
管理员）；或管理员用 `nssm`/Windows 服务包装。不要把它绑定到 `0.0.0.0`。
`turtle-caddy.vbs` 带 `-Supervise`，Caddy 崩溃会在几秒内被拉起，登录会话内的
抖动不需要人工干预。隧道同样用登录项 `scripts/startup/turtle-tunnel.vbs`
（见下节），两者都随登录启动、不依赖管理员；代价是**开机不登录 = 站点不可达**
（Access 之后报 1033），要 7×24 就得把两者都改成 systemprofile 配置下的
LocalSystem 服务。

第二道兜底在 `scripts/run_daily.ps1`：每天 19:00 的流水线在构建前检查 8080，
没在监听就用 `-Supervise` 拉起 Caddy。所以“某天 Caddy 死了”最多撑到下一次
流水线，再叠加登录项的作用域（登录会话内崩溃会由 supervisor 立刻重启）。

验证“自启真的生效”不要只看端口，按这个顺序查 `logs/caddy-launch.log`：

```powershell
Get-Content C:\PyProject\turtle-framework\logs\caddy-launch.log -Tail 20
netstat -ano | findstr :8080        # 应有 LISTENING
curl http://127.0.0.1:8080/health.txt
```

日志里应能看到 `start (supervise=True)`；如果只有 `no-op: ... already listening`，
说明当时已有实例在服务（幂等守卫），不是失败。

两个容易踩的坑：

- `caddy stop` 会向全局 admin API（`localhost:2019`）发停止指令，**直接干掉正在
  服务的那个实例**。排障时不要拿它当“重启”用；用 `run_caddy.ps1` 的幂等启动。
  测试别的 Caddyfile 时给它单独配 `admin localhost:20xx`，别占用 2019。
- `caddy start` 在 Windows 上“子进程仍挂在当前终端”，关窗口即杀 Caddy，不适合
  隐藏窗口/计划任务；要后台常驻就用本仓库的 `run_caddy.ps1`。

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

### 本机现状（2026-10-22）：服务不可用，改用登录项

`cloudflared service install` 写出来的服务 binPath 只有 exe 本身：

```
BINARY_PATH_NAME : C:\Tools\cloudflared\cloudflared.exe
```

服务以 `LocalSystem` 运行，因此读的是
`C:\Windows\System32\config\systemprofile\.cloudflared\config.yml`，而不是当前
用户的 `%USERPROFILE%\.cloudflared\config.yml`。只配置了用户目录时，服务在
SCM 里显示 `RUNNING`，却没有 connector（2026-10-22 见过 PID 已消失、SCM 仍报
`4 RUNNING` 的僵尸状态），Access 登录后得到 **Error 1033**。排障时不要以
`Get-Service` 的 Running 为准，要看进程和日志。

零管理员的做法（本机采用）：登录项 + `run_tunnel.ps1`。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\PyProject\turtle-framework\scripts\run_tunnel.ps1 -Supervise
```

- 幂等：已有 cloudflared 进程**且该进程存活 ≥ 15 秒**时，写
  `no-op: cloudflared already running (pid N)` 并退出，登录项、手工双击、服务
  不会互相打架。15 秒这个门槛是必要的：坏服务被 SCM 反复拉起时会闪起一个裸
  `cloudflared.exe` 再秒退，只看“进程存在”的守卫会正好抓到那一下，把真正的
  连接器挡在门外（2026-10-22 发生过）；
- 僵尸服务实例（SCM 报 `4 RUNNING`、进程对当前用户不可见、`netstat -ano`
  里那个 PID **一个 socket 都没有**）同样会挡住启动。用 `-Force` 跳过守卫：

  ```powershell
  powershell -NoProfile -ExecutionPolicy Bypass -File C:\PyProject\turtle-framework\scripts\run_tunnel.ps1 -Supervise -Force
  ```

  判断“连接器是否真的在线”永远以 `Registered tunnel connection` 为准，不以进程
  存在或 SCM 状态为准；
- `-Supervise`：连接器退出后自动重连（秒退的崩溃循环退避 30 秒）；
- 启动/退出记录在 `logs\tunnel-launch.log`，cloudflared 自身日志追加到
  `logs\cloudflared.log`（cmd 重定向保持 UTF-8；不要用 `Tee-Object`，PS 5.1
  会写成 UTF-16）。

自启：把 `scripts/startup/turtle-tunnel.vbs` 复制进
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\`。注销后隧道停止，
锁屏不受影响。

验证“隧道真的连上”只看日志里的连接记录，不看进程存在性、也不看服务状态：

```powershell
Get-Content C:\PyProject\turtle-framework\logs\cloudflared.log -Tail 20
# 期望：precheck complete hard_fail=false + 多行 Registered tunnel connection
netstat -ano | Select-String ':7844'
# 连接器一定有到 Cloudflare 边缘的 socket（QUIC/UDP 或 TCP 7844）
```

注意：由 explorer 登录项拉起的进程属于用户桌面会话，从受限/低完整性会话
（如 DSH 命令沙箱）里 `Get-Process -Id` 会报“找不到进程”、`tasklist` 会报
`Access denied`，这**不代表进程没在跑**；用 `netstat` 的 PID 和 HTTP 响应判断。

如果要恢复成系统服务（开机不登录也在线）：管理员把用户配置和凭据复制到
`C:\Windows\System32\config\systemprofile\.cloudflared\`，再重启 `Cloudflared`
服务；然后删掉 Startup 里的 `turtle-tunnel.vbs`（否则只是多一个会被 guard
挡掉的登录项）。`cloudflared tunnel info <name>` 需要 `cert.pem`，本机只有
credentials file，所以用日志里的 `Registered tunnel connection` 判断。

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

- 恢复交易日检测，跑完整前 20；
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
