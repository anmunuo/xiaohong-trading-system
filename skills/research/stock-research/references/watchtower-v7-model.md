# 瞭望塔 v7.0 架构

> v6→v7 核心变化：瞭望塔(no_agent) + 每日晨报(LLM) 合并 → 单一 LLM 瞭望塔晨报。新增选股推荐引擎 + 知识库升级至 14 数据源。

## 架构全景

```
08:00  知识库 v7.0 每小时采集 (mega_collector.py)
         ├─ 🔥 热点事件 TOP20    (东方财富热搜 + 市场新闻)
         ├─ 🏛️ 宏观政策/央行     (经济日历 + 政策关键词过滤)
         ├─ 📊 行业重大新闻       (资源池交叉验证)
         ├─ ⭐ 公司公告           (持仓股优先排序)
         ├─ 📈 券商晨会观点       (东方财富研报买入评级)
         ├─ 🐉 龙虎榜复盘         (前日龙虎榜 + 净买卖排序)
         ├─ ⚠️ ST/退市风险        (公告关键词过滤)
         ├─ 📥 北向资金详情       (data_pipeline + 活跃股)
         └─ 🌍 隔夜外盘+期货     (美股/欧股/亚太 + 原油±3%→能源 / 黄金±2%→贵金属)
         ↓
       data/kb/mega_latest.json

08:25  选股推荐引擎 (stock_recommender.py)
         输入: 知识库事件 + 资金流向 + 技术形态
         排除: ST · 连板(≥2) · 市值>3000亿
         五因子: 事件30% + 资金25% + 情绪20% + 技术15% + 研报10%
         输出: scripts/data/daily_pool.json (每日重置)
         ↓
       飞书推送推荐池

08:30  瞭望塔晨报 (LLM cron)
         读取: mega_latest.json + daily_pool.json + data_pipeline
         输出: 9段完整报告 → 飞书推送
           一·隔夜外围   二·前日复盘   三·资金面   四·多因子评分
           五·事件矩阵   六·要闻速览   七·外盘期货 八·推荐池 九·综合研判
```

## v6 → v7 变更对比

| 维度 | v6.0 | v7.0 |
|------|------|------|
| 早晨 cron | 瞭望塔(no_agent)+晨报(LLM) | 瞭望塔晨报(LLM 合并) |
| 数据采集 | resource_pool(3源) | mega_collector(14源) |
| 选股推荐 | 无 | stock_recommender(5因子) |
| 外盘监测 | 仅收盘价 | +传导规则 ±2%/+3% |
| 期货联动 | 无 | 原油±3%/黄金±2%标记 |
| 早晨飞书 | 2条 | 2条(推荐池+瞭望塔) |
| LLM任务 | 3→2 | 3(瞭望塔+决策官+周报暂停) |

## 关键数据流

### mega_collector.py → 知识库
```
每小时整点 cron 触发
  ↓
MegaCollector.collect_all()
  ├─ 9模块独立 try/except（单模块失败不影响其他）
  ├─ 输出 → data/kb/mega_YYYYMMDD_HHMM.json
  └─ 同时写入 data/kb/mega_latest.json（覆盖）
```

### stock_recommender.py → 推荐池
```
08:25 cron 触发
  ↓
StockRecommender.run(top_n=8)
  ├─ _get_candidates()     ← kb + fund_flow + hot_events + broker
  ├─ _apply_filters()      ← ST/连板/市值 三重排除
  ├─ _score_candidates()   ← 五因子加权打分
  └─ _save_pool()          → scripts/data/daily_pool.json（覆盖式重置）
```

### 瞭望塔晨报 LLM prompt
```
加载 stock-research skill
  ↓
1. 终端: data_pipeline 拉取全球指数/北向/板块/个股资金
2. 终端: akshare 拉取涨停/跌停/连板
3. 文件: 读取 data/kb/mega_latest.json
4. 文件: 读取 scripts/data/daily_pool.json
  ↓
LLM 综合研判 → 9段 Markdown 报告 → 飞书推送
```

## Cron 时间线（交易日）

| 时间 | 任务 | 模式 | 输出 |
|------|------|:--:|------|
| 每小时 | 知识库采集 | no_agent | local |
| 08:25 | 选股推荐引擎 | no_agent | 飞书(推荐池) |
| 08:30 | 瞭望塔晨报 | **LLM** | 飞书(完整报告) |
| 09:25 | 侦察兵 | no_agent | 飞书(选股) |
| 09:35-14:30 | 狙击手 | no_agent | 飞书(监控) |
| 10:30 | 盘中扫描 | no_agent | 飞书 |
| 14:30 | 决策官 | **LLM** | 飞书(决策) |
| 15:30 | 弹药库 | no_agent | 飞书(风控) |
| 17:00 | 文工团 | no_agent | 飞书(复盘) |

## 选股推荐引擎排除规则

```
候选池 (资金TOP50 + 事件驱动 + 券商买入)
  ↓
排除 ST / *ST       ← 名称含ST 或 公告过滤
排除 连板 ≥ 2       ← akshare stock_zt_pool_em 前日涨停板
排除 市值 > 3000亿  ← tushare daily_basic / data_pipeline
  ↓
有效池 → 五因子打分 → Top 8 推荐
```

## 外盘期货传导规则

| 触发条件 | 标记 | 影响板块 |
|------|:--:|------|
| 纳指涨跌 > ±2% | 🔴 强外盘影响日 | 科技/AI/互联网 |
| 中概金龙集体涨跌 | 🟡 中概联动 | 对应A股ADR板块 |
| 原油涨跌 > ±3% | 🟡 能源化工影响 | 石化/化工/航运 |
| 黄金涨跌 > ±2% | 🟡 贵金属影响 | 黄金/白银/有色 |

## 新增模块

| 文件 | 用途 | 大小 |
|------|------|:--:|
| `scripts/mega_collector.py` | 统一采集器（9模块14源） | ~22K |
| `scripts/stock_recommender.py` | 选股推荐引擎 | ~19K |
| `scripts/cron_recommender.sh` | 推荐引擎 cron 包装器 | ~250B |
| `scripts/data/daily_pool.json` | 每日推荐池（覆盖式） | ~4K |
