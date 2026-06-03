# Cron 全面审计与修复模式

## 审计触发

当系统出现多个 cron error 或用户要求「全面复盘」「确保明天正常工作」时，执行以下审计流程。

## 审计四步法

### 1. 全量 cron 健康扫描

```bash
# 列出所有 cron，标记 error/paused
hermes cron list | python3 -c "import json,sys; ...[解析status]..."
```

关注维度：
- `last_status=error` → 根因诊断
- `enabled=false` / `state=paused` → 是否应清理
- `next_run_at` 过期未跑 → 调度问题
- `no_agent=True` 脚本 → PATH/依赖完整性

### 2. 错误 cron 根因诊断

按优先级分类：
- **P0 永久性**: 脚本错误、PATH 缺失、调度时间矛盾
- **P1 间歇性**: API 冷启动、超时、限流
- **P2 设计缺陷**: 退出逻辑过于激进、预期行为被当错误

### 3. 批量修复

**PATH 修复（最常遇到）**：
```bash
# 将所有 cron_*.sh 中的 'python3' 替换为绝对路径
PYTHON3="/home/pc/.hermes/hermes-agent/venv/bin/python3"
# 注意：不要碰 #!/ 行，不要重复替换
```

**调度修复**：
- 数据管线就绪后才执行依赖任务（如推荐引擎要在数据管线后）
- 时间窗口足够（竞价采集器需要预热时间）

**退出逻辑修复**：
- 健康检查类：degraded ≠ error，仅 down/critical 应非零退出

### 4. 并行清理

- 移除暂停 cron（过时/被替代的 v1.0 任务）
- 清理重复数据目录（如双 KB）
- 删除 `__pycache__`
- 旧 workspace 中的过期脚本

## 常见的根因清单

| 症状 | 根因 | 修复 |
|:--|:--|:--|
| 26 个 cron 脚本全部失败 | cron PATH 不含 venv，`python3` 找不到 | 全量替换绝对路径 |
| 推荐引擎每日 error | 调度 08:25 早于数据管线 (08:30 准备) | 改为 08:35 |
| 健康检查每日 error | `degraded` → `exit 1`，「黄灯当红灯」 | 改为仅 `down/critical` 非零 |
| 竞价/侦察兵偶发 error | 东方财富 API 冷启动 + cron 超时 | PATH 修复 + 超时延长 |
| 大量暂停 cron 堆积 | v1.0 系统残留（已被 v2.0 替代） | 确认后直接删除 |

## 验证

```bash
# 验证所有脚本 PATH 正确
grep -l 'venv/bin/python3' cron_*.sh | wc -l
# 验证健康检查正常退出
python3 system_health_check.py --json; echo $?
# → 即使 overall=degraded，exit code 也应为 0
```
