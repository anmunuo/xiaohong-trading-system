# 全流程架构审计工作流 v1.1

> 基于 2026-06-11 Phase 优化实战 + ttmens-skills Pipeline 范式提炼。
> 适用场景：系统稳定性下降、多 cron 失败、数据管线产出异常时。

## Phase-Gate 执行范式（源自 ttmens-skills）

```
每Phase: Plan → Execute → Verify → Gate → Next
  ├─ 同Phase内独立子任务可并行(subagent)
  ├─ 每Phase结束设硬性Gate检查
  └─ Gate不通不前进——必须验证通过才进入下一Phase
```

**典型 Phase 划分**：
- P0 修复：致命 bug（数据产出断裂 / cron 全线失败 / 崩溃）
- P1 加固：辅助模块修复 + 新增监控
- P2 缝合：全链路端到端验证
- P3 防御：自动修复增强 + 告警
- P4 Gate：全量健康检查 + 文档记录

> 每个 Phase 的 Gate 检查项必须可量化（如 Silver 行数 > 5000、cron error count = 0），不可「看上去好了」。

```
Step 1: 全维度健康扫描
  python3 system_health_check.py
  → 拿到 overall 状态 + 各维度问题清单

Step 2: Cron 全面排查
  cronjob action=list
  → 看 4 个信号：
    1) last_status=error 的 job
    2) last_run 时间异常（超过应运行时间未跑）
    3) no_agent script 的 timeout 风险
    4) 关键链路的 context_from 依赖断裂

Step 3: 故障输出取证
  for job_id in 失败的jobs:
    cat cron/output/$job_id/最新文件
  → 读 Script exited with code / Script timed out / stderr
  → 提取 Traceback 行号 → 根因定位

Step 4: 分类分级修复
  P0: 影响数据产出或决策链路的 → 立即修复
  P1: 影响辅助模块但不阻塞主链 → 当日修复
  P2: 美化/推送/展示问题 → 排期修复
```

## 关键诊断路径

### Cron 健康状况速查
```bash
# 统计失败率
grep -l "script failed\|Script timed out" cron/output/*/最新文件 | wc -l

# 定位具体失败
for d in cron/output/*/; do
  latest=$(ls -t "$d" | head -1)
  if grep -q "script failed\|timed out" "$d/$latest" 2>/dev/null; then
    echo "$(basename $d): FAIL ($latest)"
  fi
done
```

### 数据管线完整性
```bash
# Bronze
python3 bronze_ingest.py --verify

# Silver
python3 silver_pipeline.py --dry-run  # 看消费的 Bronze 路径
python3 -c "from silver_pipeline import SilverPipeline; p=SilverPipeline(); print(p.get_stats())"

# Gold
python3 gold_pipeline.py --stats  # 因子数/ML状态/Pool状态
```

### 议会/研究员链路
```bash
# 议会日志是否存在+有意义条目
python3 -c "
import json
log = json.load(open('scripts/data/research/parliament_log.json'))
meaningful = [e for e in log if e.get('bull_signals',0)>0 or e.get('bear_signals',0)>0]
print(f'总条目:{len(log)} 有意义:{len(meaningful)}')
"

# 研究报告空壳检测
python3 -c "
import json
d = json.load(open('scripts/data/daily_pool.json'))
for r in d.get('recommendations', []):
    ra = r.get('researcher_analysis', {})
    has_content = any(ra.get(k) for k in ['fund','tech','event','risk','capital','data'])
    print(f'{r[\"code\"]}: {\"有内容\" if has_content else \"空壳\"} ')
"
```

## 常见故障矩阵

| 症状 | 第一步排查 | 常见根因 |
|------|-----------|---------|
| Script timed out after 120s | cronjob list 查 job 类型 | no_agent 脚本需300s或转LLM模式 |
| Script failed exit=1 | cat output 看 stderr | NoneType / ZeroDivisionError / ImportError |
| exit=? | config.yaml script_timeout 未对已有job生效 | 通过 cronjob update 重新写入 timeout |
| daily_pool 15h+ stale | 推荐引擎 cron 是否运行 | $HOME profile 覆盖 + 路径错误 |
| Silver <100 行 | Bronze→Silver 链路 | Bronze ingest 产出 + Silver 消费路径 |
| parliament_log 不存在 | 议会 cron 是否有调度 | crontab 缺少 parliament cron |
| push_text() 崩溃 | notifier.py 签名 | API 升级后 keyword-only 参数变化 |

## 修复后验证

```bash
# 1. 逐模块手动触发
python3 stock_tracker.py --snapshot --stats    # P0-1
python3 auction_collector.py --live            # P0-2
python3 researchers.py --winners               # P0-3
python3 system_health_check.py --fix --push    # P0-4
python3 silver_pipeline.py                     # P0-5

# 2. 全量健康检查
python3 system_health_check.py

# 3. Cron 对齐
cronjob list | grep -E "error|failed"
```
