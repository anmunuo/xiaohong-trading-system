# Cron 交易报告系统 v7.0

15 个 cron 任务（12 no_agent + 3 LLM 驱动），覆盖盘前→盘中→盘后全时段。

## 架构

```
~/.hermes/profiles/xiaohong/scripts/
├── data_pipeline.py          ← 统一数据管道（Tushare/AKShare/东方财富/Sina）
├── mega_collector.py         ← 🆕 v7.0 统一采集器（9模块14数据源）
├── stock_recommender.py      ← 🆕 v7.0 选股推荐引擎（五因子+三重排除）
├── resource_pool.py          ← 事件智能池（四维交叉验证）
├── knowledge_base.py         ← 知识库（增量采集+去重+索引）
├── strategy_bridge.py        ← 策略引擎桥接器
├── ammo_risk.py              ← 弹药库风控（实时止损+估值）
├── scout.py / sniper.py      ← 侦察兵/狙击手
├── review.py                 ← 文工团复盘
│
├── cron_kb_collector.sh      ← 知识库每小时 (mega_collector)
├── cron_recommender.sh       ← 🆕 选股推荐引擎 08:25
├── cron_pre.sh               ← 盘前采集 08:30
├── cron_scout.sh             ← 侦察兵 09:25
├── cron_sniper.sh            ← 狙击手 09:35-14:30
├── cron_intra.sh             ← 盘中扫描 10:30
├── cron_ammo.sh              ← 弹药库 15:30
├── cron_review.sh            ← 文工团每日 17:00
└── cron_weekly.sh            ← 文工团周度 周六
```

## Cron 任务矩阵

| 时间 | 角色 | 脚本 | 模式 | 投递 |
|------|------|------|:--:|:--:|
| 每小时 | 📚 知识库 v7.0 | cron_kb_collector | no_agent | local |
| 08:25 | 🎯 选股推荐引擎 | cron_recommender | no_agent | 飞书 |
| 08:30 | 🌅 瞭望塔晨报 | (LLM prompt) | **LLM** | 飞书 |
| 09:25 | 🔍 侦察兵 | cron_scout | no_agent | 飞书 |
| 09:35-14:30 | 🎯 狙击手 | cron_sniper | no_agent | 飞书 |
| 10:30 | 📊 盘中扫描 | cron_intra | no_agent | 飞书 |
| 14:30 | 🌹 决策官 | (LLM prompt) | **LLM** | 飞书 |
| 15:30 | 🛡️ 弹药库 | cron_ammo | no_agent | 飞书 |
| 17:00 | 🏥 文工团 | cron_review | no_agent | 飞书 |
| 周六 09:00 | 📊 文工团周度 | cron_weekly | no_agent | 飞书 |

> 仅 2 个活跃 LLM cron 消耗 token（瞭望塔晨报 / 决策官）。周报分析暂停中。

## no_agent cron 模板

```bash
#!/bin/bash
cd /home/pc/.hermes/profiles/xiaohong/scripts
export TQDM_DISABLE=1
exec python3 <script>.py
```

创建命令：
```
cronjob action=create name="角色名" schedule="CRON" 
  script="cron_xxx.sh" no_agent=true profile=xiaohong
  workdir=/home/pc/.hermes/profiles/xiaohong/scripts deliver=origin
```

## LLM cron 模板

瞭望塔晨报和决策官通过 prompt 驱动，加载 stock-research skill，读取知识库/推荐池数据后进行综合研判。

## 弹药库 v3.1

```bash
python3 ammo_risk.py            # 风控报告
python3 ammo_risk.py --push     # 报告+飞书推送
python3 ammo_risk.py --update   # 同步持仓实时估值
```

## 数据来源优先级

1. `stock_recommender.py` 调用 `data_pipeline` → Tushare/AKShare/Sina fallback
2. `mega_collector.py` 调用 `resource_pool` + `akshare` + `data_pipeline`
3. `ammo_risk.py` 调用 `data fetch` CLI → Hermes 平台凭证管理
