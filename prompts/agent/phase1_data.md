# Phase 1：数据采集

目标：拿到确定性数据包，并锁定快照。

## 步骤

```powershell
python -m turtlefw.cli state <code> --phase data
python -m turtlefw.cli pack <code>
```

`pack` 默认写 `output/<标准化代码>/data_pack.md`。

## 验收

- 文件存在且包含 `## 1.`、`## 2.`、`## 3.`、`## 5.` 四个区块；
- 记录头部 `数据快照` 的哈希；
- 缺段（如港股无 `§3P`）记 warning，不视为失败。

## 状态更新

```powershell
python -m turtlefw.cli state <code> --phase data `
  --artifact data_pack=output/<code>/data_pack.md `
  --artifact snapshot=<快照哈希>
```

## 失败处理

| 情况 | 处理 |
|:---|:---|
| 无 TUSHARE_TOKEN | 停止，提示配置 .env |
| 接口权限不足 | 记 warning，继续（报告会显示数据缺口） |
| 完全无数据 | 停止，输出错误码 2 |
