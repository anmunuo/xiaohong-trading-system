# 工作区路径发现与版本映射

> 2026-06-02 实测：skill 文档引用路径与实际部署存在断层。本文档记录发现流程和映射关系。

## 路径发现优先级

LLM 复盘 cron 启动时按以下顺序定位工作区：

```
1. ~/.openclaw/workspace/anmunuo-family/xiaohong/  ← 主工作区（首选）
   ├── holdings.json       ← 实际持仓文件
   ├── scripts/            ← 脚本（v1.0 命名）
   ├── data/data/          ← 运行时数据（双层嵌套）
   ├── reports/daily/      ← 每日报告
   └── data/watchlist.json

2. ~/.hermes/profiles/xiaohong/data/               ← 备选（holdings.json 副本）
   └── holdings.json       ← 可能与主工作区不同步

3. ~/wiki/交易系统/                                ← 文档/架构图
```

## 发现命令

```bash
# 快速定位
find ~/.openclaw -name 'holdings.json' -type f 2>/dev/null
find ~/.hermes -name 'holdings.json' -type f 2>/dev/null

# 确认主工作区
ls ~/.openclaw/workspace/anmunuo-family/xiaohong/holdings.json
```

## v1.0 vs v2.0 脚本命名映射

skill 文档（v2.0+） | 实际部署（v1.0） | 功能
---|---|---
`evolution_engine.py` | `self_evolution.py` | 进化引擎（SelfEvolution 类，角色分离，不消费 review_diagnosis.json）
`stock_recommender.py` | `scout_recommender.py` | 推荐引擎（不同入口）
`mega_collector.py` | ❌ 不存在 | 统一采集器（v1.0 无此模块）
`ammo_risk.py` | `ammo_risk_check.py` / `ammo_agent.py` / `ammo_report_pro.py` | 弹药库（拆分为多文件）
`scout.py` | `scout_agent.py` / `strategic_scout.py` | 侦察兵
`sniper.py` | `sniper_agent.py` / `sniper_analyzer.py` | 狙击手
`review.py` | `review.py` | 文工团（同名但功能不同——v1.0 仅读模板字段）
`auction_collector.py` | `jingjia_scout.py` | 竞价（v1.0 命名）
`kb_insights.json` | ❌ 不存在 | 知识库洞察（v1.0 无此管道）
`parliament_log.json` | ❌ 不存在 | 议会日志（v1.0 未集成）
`daily_pool.json` | `stock_pool.json` / `watchtower_pool.json` | 选股池（v1.0 使用不同 schema）
`data/data/evolution/review_decisions.json` | 存在 | 进化决策记录
`data/data/evolution/review_stats.json` | 存在 | 进化统计

## 数据目录结构（v1.0 实测）

```
workspace/
├── holdings.json                    ← 持仓+账户信息
├── data/
│   ├── watchlist.json
│   ├── push_config.json
│   ├── data_pipeline.py             ← 注意：pipeline 在 data/ 下，非 scripts/
│   └── data/                        ← 双层嵌套
│       ├── stock_pool.json          ← 自选池（停更于 2026-04-04）
│       ├── watchtower_pool.json     ← 瞭望塔池（停更于 2026-04-04）
│       ├── trading_log.json         ← 交易日志（最后 2026-03-14）
│       ├── system_stats.json        ← 系统统计（最后 2026-04-10）
│       ├── account_info.json
│       ├── verification_history.json
│       └── evolution/               ← 进化引擎数据
│           ├── ammo_decisions.json
│           ├── ammo_stats.json
│           ├── review_decisions.json
│           ├── review_stats.json
│           ├── scout_decisions.json
│           ├── scout_stats.json
│           ├── watchtower_decisions.json
│           └── watchtower_stats.json
├── scripts/
│   ├── self_evolution.py            ← 进化引擎（v1.0）
│   ├── scout_recommender.py         ← 推荐引擎入口
│   ├── review.py                    ← 文工团
│   ├── ammo_risk_check.py           ← 弹药库
│   ├── ammo_report_pro.py
│   ├── ammo_agent.py
│   ├── scout_agent.py
│   ├── strategic_scout.py
│   ├── sniper_agent.py
│   ├── sniper_analyzer.py
│   ├── bearish_researcher.py        ← 研究员脚本（存在但未编排为议会）
│   ├── bullish_researcher.py
│   ├── debate_flow.py               ← 辩论流（存在但未集成 cron）
│   └── data/
│       ├── push_history.json
│       └── watchlist.json
└── reports/
    └── daily/
        ├── 瞭望塔-YYYY-MM-DD.md     ← 08:30 cron
        ├── 弹药库风控-YYYY-MM-DD.md  ← 15:30 cron
        └── 文工团复盘-YYYY-MM-DD.md  ← 17:00 cron
```

## LLM 复盘时的关键判断

1. **如果 `daily_pool.json` 不存在** → 检查 `stock_pool.json` 和 `watchtower_pool.json`（v1.0 格式）
2. **如果 `parliament_log.json` 不存在** → 议会未部署，状态 error
3. **如果 `evolution_engine.py` 不存在** → 用 `self_evolution.py` 替代，但注意不消费 `review_diagnosis.json`
4. **如果 `holdings.json` 中 `lastPrice=None`** → 盘后估值未同步，标记 warn 而非 error
5. **如果每日报告连续两天完全相同** → 模板化输出，标记文工团 warn
6. **review_diagnosis.json 写入路径** → `data/data/kb/review_diagnosis.json`（需先 mkdir -p）
