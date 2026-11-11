# 每日简报推送到微信：方案调研（2026-11-02）

目标：每天 19:00 的 daily 跑完后，把 `briefing.txt` 自动推到**个人微信**，不需要人工点发送。

现状：
- 流水线已经会自动生成 `.runs/daily/<date>/briefing.md` / `briefing.txt`（`src/turtlefw/briefing.py`，`daily.py` 在发布站点后调用）。
- 推送函数 `notify_briefing()` 已存在，读环境变量 `TURTLE_BRIEFING_WEBHOOK`，payload 是**企业微信群机器人**格式 `{"msgtype":"text","text":{"content":...}}`。
- 另有 `TURTLE_NOTIFY_WEBHOOK`（`daily.py:_notify`），POST 原始 status JSON，不适合人读。
- DSH 的 IM 通道（`dsh_im_return_file`）只在**交互回合**内可用；定时提醒/后台任务没有 IM consumer，会返回 `No active IM delivery consumer`。

## 先说结论

“webhook” 不是唯一办法，但在“无人值守 + 当天自动到微信”这个约束下，**所有可行方案最终都是一次 HTTP 调用**，区别只是：
1. 由谁提供这个 HTTP 端点（自己搭 / 用企业微信 / 用第三方中转）；
2. 消息最终以什么形态进入微信（企业微信群、企业微信应用、服务号通知、好友消息）。

真正不用 HTTP 的只有「个人微信 UI 自动化」这一类，代价是封号风险，不推荐。

## 方案对比

| 方案 | 消息落到哪 | 前置条件 | 费用/额度 | 接入工作量 | 风险 |
| --- | --- | --- | --- | --- | --- |
| A. 企业微信群机器人 webhook | 企业微信群 | 有企业微信、建群、建机器人拿 URL | 免费；官方限制 20 条/分钟 | **已支持，填 URL 即用** | 低；需要企业微信（微信可在“微信插件”里看企业微信消息） |
| B. 企业微信自建应用消息 | 个人企业微信 | 管理员建应用，取 corpid / corpsecret / agentid；定时取 access_token | 免费 | 中（多一步 token 缓存） | 低 |
| C. Server酱 Turbo | 微信（“方糖”服务号会话） | 微信扫码注册，拿 `SCT...` SendKey | 免费 **5 条/天**（新用户 7 天全功能） | 低（form 提交 title/desp） | 中低；第三方，key 泄露可被冒充发消息 |
| D. PushPlus（推送加） | 微信（“推送加”服务号） | 注册 + **实名**，关注公众号 | 免费 200 次/天（1 分钟 5 次、同内容 1 小时 3 条） | 低 | 中低；第三方 |
| E. WxPusher | 微信 ClawBot / 其 App | 扫码拿 SPT，或建应用拿 appToken+uid | 官方称永久免费 | 低 | 中低；第三方 |
| F. 自有公众号模板消息/订阅通知 | 微信服务号通知 | 认证服务号（企业主体，需年审）、用户订阅 | 认证费约 300 元/年 | 高（认证 + 模板 + 订阅流程） | 低，但门槛最高 |
| G. 个人微信 UI 自动化（wxauto / Wechaty 等） | 微信好友/群 | 桌面微信常驻且登录 | 免费 | 高（易碎、要保活） | **高：违反微信使用规范，有封号风险** |
| H. 邮件 → 微信 | 微信里的邮件提醒 | 邮箱 + 微信绑定“QQ邮箱提醒”等 | 免费 | 中 | 延迟大、噪音大，不像“推送” |

额度判断：本项目每天 **1 条**简报（个别情况补发 1 条），C 的 5 条/天、D 的 200 次/天、A/B/E 都绰绰有余。

## 推荐顺序

1. **有企业微信 → A（群机器人）**：零第三方、零费用，代码已按这个格式写好，把 webhook URL 填进 `TURTLE_BRIEFING_WEBHOOK` 就完成。
2. **没有企业微信、只想在个人微信里收 → C（Server酱）**：注册最快、5 条/天刚好够；需要把 `notify_briefing()` 加一个 form 提交分支。
3. **C 的额度/第三方有顾虑 → D（PushPlus，实名 200 次/天）或 E（WxPusher）**：都需要写各自的小适配。
4. **不推荐 G**（个人号自动化）：为了每天一条简报承担封号风险不划算。

## 落地改造（建议）

把 `notify_briefing()` 改成按 endpoint 自动识别的小适配层：

- `qyapi.weixin.qq.com` / 含 `key=` 的企业微信 URL → 现有 JSON 格式（A）
- `sctapi.ftqq.com` 或 `SCT` 前缀 → `POST title=<标题>&desp=<正文>`（C）
- `pushplus` → `POST {"token": ..., "title": ..., "content": ..., "template": "txt"}`（D）
- `wxpusher` → `POST {"appToken": ..., "content": ..., "uids": [...]}`（E）
- 其他 → 沿用企业微信 JSON（通用中转）

配置优先级：`configs/daily.toml` 的 `briefing_webhook`（可选，便于随仓库配置）> 环境变量 `TURTLE_BRIEFING_WEBHOOK` > 不发。
并把发送结果写进 `status.json` 的 `briefing_sent`（已实现），失败不影响 daily 结果。

## 待用户决定

- 选 A / C / D / E 中的哪一个（或先不接，继续用现在的“到点我贴全文”）；
- 若选 A：需要一个企业微信群机器人 URL；
- 若选 C：需要 `SCT...` 开头的 SendKey；
- 若选 D：需要 PushPlus token；
- 若选 E：需要 SPT 或 appToken+uid。
