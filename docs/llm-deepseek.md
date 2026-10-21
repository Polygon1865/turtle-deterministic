# DeepSeek LLM 接入

项目不绑定 DeepSeek SDK。`src/turtlefw/agent/llm.py` 是 OpenAI-compatible
客户端，请求 `${TURTLE_LLM_BASE_URL}/chat/completions`，所以 DeepSeek 只需要
配置 API key、base URL 和 API 模型名。

## 1. 配置

```powershell
$env:TURTLE_LLM_API_KEY = "sk-..."
$env:TURTLE_LLM_BASE_URL = "https://api.deepseek.com"
$env:TURTLE_LLM_MODEL = "deepseek-flash"
```

API 模型名以 DeepSeek 控制台/接口返回为准。当前接口接受：

- `deepseek-flash`
- `deepseek-v4-pro`

控制台里的展示名（例如 `DeepSeek-V4.1-Flash1017`）不是 API 的 `model` 值；
传展示名会返回 `400 invalid_request_error`。`src/turtlefw/agent/llm.py` 现在会
把该错误响应体带进 `AgentError`，不再只显示 `HTTP 400`。

`deepseek-chat` / `deepseek-reasoner` 是其他部署/版本的别名，是否可用取决于
账号；接入前先用一次最小请求验证：

```powershell
.\.venv\Scripts\python.exe -c "from turtlefw.agent.llm import OpenAICompatibleLLM; print(OpenAICompatibleLLM(base_url='https://api.deepseek.com', model='deepseek-flash', api_key='...').complete('Return only a JSON object.', {'ping': 'pong'}))"
```

## 2. 单票自动研究

```powershell
.\.venv\Scripts\python.exe -m turtlefw run 600887 `
  --with-research `
  --pdf-index .runs\600887.SH\pdf_index.json `
  --research-max-input-tokens 60000 `
  --research-retries 1
```

- 不传 `--pdf-index` 时，研究上下文只有数据包/facts，没有 `pdf_deep`/`pdf_notes`；
- 传 PDF 索引后上下文会明显变大，600887 实测约 43,741 tokens；预算低于该值时
  会直接拒绝调用，不会截断后静默降级；
- `--research-retries 1` 会在 schema/质量失败时带反馈重试一次。

## 3. 每日流水线

`run_daily.ps1` 的计划任务参数目前含 `--llm-top 0`，会覆盖
`configs/daily.toml` 的 `llm_top_n`。要每天对前 3 只启用：

```powershell
# 计划任务参数改为 --llm-top 3
# 并在运行任务的用户环境里设置 TURTLE_LLM_API_KEY/BASE_URL/MODEL
```

没有 key/额度时，`run_stock` 会回退为确定性报告，不会让整个站点失败；但每次
LLM 失败仍会消耗时间，正式启用前先手工验证一次。

## 4. 输出契约

模型必须返回严格的 ResearchDocument JSON：

```json
{
  "evidence": [{"id": "ev_...", "source_type": "pdf|data|web", "quote": "..."}],
  "claims": [{"claim_id": "D1....", "dimension": "D1", "statement": "...", "evidence_ids": ["ev_..."]}],
  "params": [{"param_id": "...", "value": "...", "evidence_ids": ["ev_..."]}],
  "decisions": []
}
```

`claim_id`/`param_id`/`decision_id` 不能写成裸 `id`；`evidence_ids` 必须逐字复制
`evidence[].id`，不能用 E1/E2 这类数组别名。提示词在
`src/turtlefw/agent/research_prompt.py`，校验在 `src/turtlefw/research.py`。

## 5. 已验证结果

2026-10-22 使用 `deepseek-flash` + 600887 官方 PDF 索引实测：

- 28 claims、18 params、36 evidence（含 PDF 页证据）；
- 输入约 43,741 tokens，耗时 85 秒；
- `research_audit` PASS，QA 13/13 PASS，strict numeric 1.0000；
- final snapshot `b0aed8e8d34ae083d04460b29445b831`，`verify_manifest` 返回空。

产物在 `.runs/deepseek-600887-pdf/600887.SH/`，已被 `.gitignore` 忽略。
