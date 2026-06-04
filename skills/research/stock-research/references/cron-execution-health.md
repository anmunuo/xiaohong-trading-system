# Cron 执行健康检测 — 监控反模式修复

> 日期：2026-06-04 | 版本：system_health_check.py v1.2.0

## 问题

旧版 `check_scout_sniper()` 只检查 cron **产出物**（输出文件是否存在、时间是否新鲜），不检查 cron **执行状态**（退出码、stderr）。22/26 脚本被行号污染后，bash 报 `未找到命令` 但管道后半段 `exec python3` 仍能产出报告——健康检查永远发现不了。

## 监控反模式

```
旧逻辑:
  📁 输出文件存在？→ ✅ → status=ok
  ⏰ 时间新鲜？    → ✅
  📝 内容有数据？  → ✅
  
  没看到:
  ❌ exit code = 2
  ❌ stderr 6行报错
  ❌ 22/26 脚本语法损坏
```

## v1.2 修复

### 维度6重构：⚙️ Cron执行

```python
def check_cron_execution_health():
    # 扫描所有 cron output 目录
    for job_dir in output_root.iterdir():
        latest = 最新输出文件
        content = latest.read_text()[:2000]
        
        # 🆕 检测脚本执行失败
        if 'script failed' in content or 'exited with code' in content:
            failed_jobs.append(...)
    
    if failed_jobs:
        status = 'down'  # 真正需要报警的状态
```

### 维度12新增：📜 Cron脚本

```python
def check_cron_scripts():
    for f in scripts_dir.glob('cron_*.sh'):
        raw = f.read_bytes()
        # 前20字节必须以 #! 开头
        if not first_bytes.startswith('#!'):
            corrupted.append(f.name)
```

## 教训

**监控产出物 ≠ 监控管道。** 产出物可能从破裂管道漏出来，但只有查退出码才知道管道破了。
