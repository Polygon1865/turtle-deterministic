# Phase 5：QA 与交付

目标：在交付前确认所有产物齐全、可追溯、未验证项已披露。

## 门控命令

```powershell
python -m turtlefw.cli qa <code> --write
```

检查项：

| 项 | 要求 |
|:---|:---|
| run_state | 存在 |
| report | `analysis_report.md` 存在 |
| qualitative | JSON 合法，且不全为 unknown |
| discrepancies | 冲突已记录到 qualitative.json |
| narrative | 若提供，数字必须全部可追溯 |

全部 PASS 时 `--write` 把状态推进到 `done`；任何 FAIL 都不得声称完成。

## 人工复核清单

- [ ] 结论与 CLI 报告一致（买入/观察/排除及原因）
- [ ] Thesis Card 的仓位、止损条件与最终结论一致
- [ ] 抽查 2 条证据链接，确认引文可找到
- [ ] unknown 模块在交付说明中列出
- [ ] 数字冲突（discrepancies）已解释
- [ ] 报告含免责声明
- [ ] 未把网页数字写入数字层

## 失败处理

- FAIL 项回到对应阶段修复，**不得绕过门控**；
- 网络不可达导致 `verify` 无法完成：记录 warning，交付时说明"事实校验未完成"。
