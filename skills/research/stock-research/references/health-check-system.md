# 系统健康自检 v1.0 — 设计文档

> 2026-06-02 落地。进化引擎 live 模式完成后自动触发。7维扫描 + 6种自修复。

---

## 触发机制

```
进化引擎 evolve(live)
  └─ 变更落地后
       └─ system_health_check.py --fix
            ├─ 7维扫描
            ├─ 异常 → 自动修复
            └─ 写入 health_check_log.json
```

手动运行：
```bash
python3 system_health_check.py --fix     # 带自动修复
python3 system_health_check.py           # 只检查不修复
python3 system_health_check.py --json    # JSON输出
```

---

## 7维扫描

| # | 维度 | 检查项数 | 核心检查 |
|:--|:--|:--|:--|
| 1 | 数据文件完整性 | 5 | daily_pool/holdings/kb_insights/mega_latest/auction.db 存在+有效+时效 |
| 2 | 跨模块路径一致性 | 5 | 同一文件在各模块的读写路径是否一致（基于绝对路径解析） |
| 3 | Cron健康 | 8 | 基于文件产出时间推断每个cron是否正常（不依赖hermes CLI） |
| 4 | 服务健康 | 2 | sniperd守护进程+sniperd.timer是否运行 |
| 5 | 参数一致性 | 5 | 凯利系数/单股上限/仓位上限/止盈启动/止盈步长在进化日志和代码中是否一致 |
| 6 | 认知层闭环 | 3 | review_diagnosis→evolution_log→参数落地链路是否完整 |
| 7 | 账户一致性 | 3 | 净值一致性/R值/回撤计算自洽 |

---

## 6种自修复

| 异常 | 修复动作 | fix参数 |
|:--|:--|:--|
| JSON文件损坏 | 备份→重建空文件 | `--fix` |
| sniperd未运行 | `systemctl --user restart sniperd` | `--fix` |
| 双重净值不一致 | 以accountInfo为准修正riskManagement | `--fix` |
| 参数漂移 | 以进化日志为真相源修正代码 | `--fix` |
| 认知层文件过期 | 报告warn，不自动触发生成 | 无 |
| cron异常 | 报告error，不自动重启（防死循环） | 无 |

---

## 当前健康度：90%（28/31）

3项预期内非问题：
1. 竞价DB不存在 — 交易日才有
2. P0闭环 — 候选池盲区已手动修复，进化引擎正确识别
3. R值未计算 — 持仓0只

---

## Cron健康检查策略

不依赖 `hermes cron list` CLI（环境限制），改为基于文件产出时间推断：

| cron | 检查文件 | 预期时间 | 最大延迟 |
|:--|:--|:--|:--|
| 推荐引擎 | daily_pool.json | 08:25 | 1h |
| 竞价采集 | auction.db | 09:15 | 2h |
| 弹药库 | reports/daily/弹药库风控-*.md | 15:30 | 2h |
| 文工团 | reports/daily/文工团复盘-*.md | 17:00 | 2h |
| 进化引擎 | evolution_log.json | 17:30 | 3h |
| KB采集 | mega_latest.json | 每小时 | 2h |
| KB LLM消化 | kb_insights.json | 每小时 | 3h |
| 瞭望塔 | reports/daily/瞭望塔晨报-*.md | 08:30 | 2h |
