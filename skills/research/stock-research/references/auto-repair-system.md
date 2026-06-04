# 自主修复系统 v1.3

## 入口

```bash
python3 system_health_check.py --fix        # 扫描 + 修复
python3 system_health_check.py --fix --push # + 飞书推送
```

## 修复维度

| 维度 | 问题 | 修复动作 | 幂等 |
|:--|:--|:--|:--|
| D2 持仓估值 | 估值未同步 | `ammo_risk.py --update` | ✅ |
| D3 议会链路 | parliament_log 缺失 | `researchers.py --parliament` | ✅ |
| D5 数据管线 | 缓存过期 | 删除 >30min 缓存文件 | ✅ |
| D6 Cron执行 | sniperd 宕机 | `systemctl restart sniperd` | ✅ |
| D6 Cron执行 | 脚本行号污染 | 正则 `^\d+\|` 清理 | ✅ |
| D7 研究员质量 | 空壳报告 | `researchers.py --study` | ✅ |
| D10-11 管线 | 分层数据缺失 | bronze→silver→gold 重新生成 | ⚠️ |
| D12 Cron脚本 | 行号污染 | 同上正则清理 | ✅ |

## 日志

`data/fix_log.json` — 每次修复操作记录:
```json
[{"ts":"...", "action":"valuation_sync", "detail":"rc=0", "ok":true}]
```

## 调度

Cron: `15 8,15,22 * * *` → `system_health_check.py --fix`
每次 scan 后自动 repair，修复报告附在健康报告末尾。
