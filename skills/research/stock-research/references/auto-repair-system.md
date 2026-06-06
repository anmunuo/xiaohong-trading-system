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

Cron: `15 8,15,22 * * *`，脚本路径 `cron_health_fix.sh`

**🚨 致命陷阱：cron 的 `script` 参数不支持命令行参数**

`system_health_check.py --fix` 会被当成**完整文件名**去查找——文件系统里不存在 `system_health_check.py --fix` 这个文件 → 永远 `Script not found`。修复：创建 wrapper shell 脚本包装参数传递：

```bash
#!/bin/bash
# cron_health_fix.sh
exec /path/to/venv/bin/python3 system_health_check.py --fix --push
```

cron 调度器指向 `cron_health_fix.sh` 而不是带参数的 python 命令。**任何需要参数的 cron 脚本都必须用 wrapper 模式。**

## 🚨 陷阱: profile $HOME 覆盖导致修复全管线静默失败 (v8.12)

**症状**: fix_log.json 中所有管线修复返回 rc=-1，但脚本文件实际存在且可独立运行。

**根因**: hermes profile 将 `$HOME` 设为 `/home/pc/.hermes/profiles/xiaohong/home`，`auto_repair.py:22` 使用 `Path.home()`（依赖 `$HOME`）拼接 VENV_PYTHON 路径，指向不存在的 venv。`subprocess.run()` 找不到解释器 → 返回 rc=-1。

**修复**: `VENV_PYTHON = "/home/pc/.hermes/hermes-agent/venv/bin/python3"`（绝对路径，不依赖 `$HOME`）。

**检测**: 
```bash
echo $HOME  # 应是 /home/pc，非 profile home
python3 -c "from auto_repair import _run_script; print(_run_script('bronze_ingest.py', ['--help']))"
# 应返回 rc=0
```
