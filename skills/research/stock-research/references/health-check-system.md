# 系统健康自检 v1.0 — 实现文档

> 2026-06-03 落地。每日 3 次自动扫描（08:15/15:15/22:15），7 维检查+飞书推送。

---

## 触发机制

```
cron: 🩺 系统健康检查 (ea214c0b036b)
  └─ schedule: 15 8,15,22 * * *
       └─ system_health_check.py (no_agent)
            ├─ 7维扫描
            ├─ 异常 → 非零 exit code → cron 自动推送飞书
            └─ 终端输出格式化报告
```

手动运行：
```bash
cd ~/.hermes/profiles/xiaohong/scripts
python3 system_health_check.py           # 终端格式化输出
python3 system_health_check.py --json    # JSON 输出
python3 system_health_check.py --push    # 推送飞书
```

---

## 7维扫描

| # | 维度 | 函数 | 核心检查 |
|:--|:--|:--|:--|
| 1 | 数据新鲜度 | `check_data_freshness()` | mega_latest/daily_pool/kb_insights/holdings/market_snapshot 的年龄和存在性 |
| 2 | 持仓估值 | `check_valuation_sync()` | holdings.json 中 lastPrice 是否为空，盈亏数据完整度 |
| 3 | 议会链路 | `check_parliament_flow()` | daily_pool.json 中 parliament.bias 是否存在，parliament_log.json |
| 4 | 弹药库风控 | `check_ammo_risk()` | R 值/回撤/净值是否已计算和更新 |
| 5 | 数据管线 | `check_data_pipeline()` | push2/sina/tushare/baostock 四路 API 连通性 |
| 6 | 侦察兵状态 | `check_scout_sniper()` | 最近运行时间、输出中是否有「数据源降级」标记 |
| 7 | 研究员质量 | `check_researcher_reports()` | 研学报告是否有实质内容，议会报告是否有小红终审 |

---

## 路径规范

所有路径相对于 `WORKSPACE = SCRIPT_DIR.parent`（`~/.hermes/profiles/xiaohong/`）：

```
WORKSPACE/
├── data/
│   ├── kb/              ← mega_latest.json, kb_insights.json
│   ├── holdings.json    ← 持仓+风控
│   └── research/        ← parliament_log.json
├── scripts/
│   └── data/daily_pool.json
├── reports/research/    ← 研学报告-*.md, 议会报告-*.md
└── cron/output/a6b4e31d3919/  ← 侦察兵输出
```

---

## 研究员研学报告空壳检测

**根因**：`researchers.py` v1.0 的 `run_study_session()` 只写 `_自主学习完成_` 模板，未捕获 `r.analyze()` 结果。

**修复（v2.0）**：报告写入循环中重新调用 `r.analyze(ctx)`，将 `key_findings`/`data_evidence`/`red_flags` 写入 markdown，输出 `reports_written` 计数。
