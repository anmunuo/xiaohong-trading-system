# 瞭望塔 v8.0 架构

> v7→v8 核心变化：推荐引擎升级（50-2000亿 + 排除全部连板）、晨报「单一真相源」原则、自然三段式输出，选股逻辑与操作策略优先于评分罗列。

## 架构全景

```
08:00  知识库 每小时采集 (mega_collector.py)  ← 不变
         ↓
       data/kb/mega_latest.json

08:25  选股推荐引擎 v2.0 (stock_recommender.py)  ← 升级
         输入: 知识库事件 + 资金流向 + 技术形态
         排除: ST · 连板(含首板) · 市值<50亿 · 市值>2000亿
         五因子: 事件30% + 资金25% + 情绪20% + 技术15% + 研报10%
         新增: 板块归类 + 操作策略生成 + 风险等级评估
         输出: scripts/data/daily_pool.json (每日重置，最多9只)
         ↓
       飞书推送精简推荐池

08:30  瞭望塔晨报 v8.0 (LLM cron)  ← 重写
         【禁止自选股】daily_pool.json 为唯一推荐源
         读取: daily_pool.json + mega_latest.json + data_pipeline
         输出: 自然三段报告 → 飞书推送
           一个判断  → 今天什么逻辑（1段话）
           今天看什么 → 板块分组 + 每只股逻辑+操作+风险
           今天怎么做 → 持仓分类 + 纠错纪律 + 时间窗口
```

## v7 → v8 变更对比

| 维度 | v7.0 | v8.0 |
|------|------|------|
| 推荐引擎 | v1.0，排除 >3000亿/连板≥2 | v2.0，排除 <50亿/>2000亿/任何连板 |
| 推荐上限 | 8只 | 9只 |
| 输出字段 | code/name/score/stop_loss | +sector/operation/risk_level |
| 晨报选股 | LLM 可能自选 | 只读 daily_pool.json |
| 报告结构 | 7-9段编号 | 自然三段，无强制编号 |
| 报告重点 | 多因子评分罗列 | 选股逻辑 + 操作策略 |

## 关键数据流

### stock_recommender v2.0 → 推荐池

```
08:25 cron 触发
  ↓
StockRecommender.run(top_n=9)
  ├─ _get_candidates()     ← kb + fund_flow + hot_events + broker
  ├─ _apply_filters()      ← ST / 连板(含首板) / <50亿 / >2000亿
  ├─ _score_candidates()   ← 五因子加权打分
  ├─ _enrich_recommendations()  ← 板块归类 + 操作策略 + 风险等级（v2.0新增）
  └─ _save_pool()          → scripts/data/daily_pool.json（覆盖式重置）
```

### daily_pool.json 数据契约

```json
{
  "date": "20260601",
  "version": "v2.0",
  "recommendations": [
    {
      "code": "600487",
      "name": "亨通光电",
      "sector": "通信光缆",
      "total_score": 72.5,
      "factor_scores": {"event": 65, "fund": 85, "sentiment": 70, "technical": 68, "research": 60},
      "market_cap": 320,
      "change_pct": 9.42,
      "net_flow": 398000000,
      "operation": "回踩5日线确认后轻仓介入，止损-5%",
      "risk_level": "中高",
      "stop_loss": {"method": "default", "price": 18.05, "ratio": -5.0}
    }
  ],
  "excluded": {"st": 3, "lianban": 12, "small_cap": 8, "large_cap": 5},
  "methodology": {
    "factors": {"event": 0.30, "fund": 0.25, "sentiment": 0.20, "technical": 0.15, "research": 0.10},
    "filters": ["ST/*ST", "连板(含首板)", "市值<50亿", "市值>2000亿"],
    "max_picks": 9,
    "reset": "daily"
  }
}
```

### 板块归类规则

`_guess_sector()` 按两级策略匹配：
1. 从知识库公告/研报标题中匹配 16 个行业关键词
2. 回退到股票名称关键词匹配
3. 兜底返回「综合」

### 操作策略生成

`_gen_operation()` 按技术面+资金面组合生成：
- 涨>7%：高开不追，等回踩
- 技术≥65且资金≥60：回踩MA20建底仓
- 技术≥50：缩量回踩10日线低吸
- 资金≥65：等分时回调介入
- 其他：观望，等放量突破确认

### 风险等级评估

`_assess_risk()` 按市值+波动判定：
- 市值<80亿 或 涨跌>8%：高
- 市值>500亿 且 资金≥60：低
- 其他：中

## 晨报 LLM 约束

| 约束 | 详情 |
|------|------|
| ⛔ 推荐源 | **只能使用 daily_pool.json**，不另选代码 |
| ⛔ 空池处理 | 输出简短休市通知，不编造 |
| 📝 市场判断 | 1段话，数据只做佐证 |
| 📝 推荐池 | 按板块自然分组，每只股必含逻辑+操作+风险 |
| 📝 操作框架 | 按仓位分类 + 纠错纪律 + 时间窗口 |

## 排除规则对比

| 维度 | v7.0 | v8.0 |
|------|------|------|
| ST | ✅ 排除 | ✅ 排除 |
| 连板 | 排除 ≥2板 | **排除全部**（含首板） |
| 市值下限 | 无 | **排除 <50亿** |
| 市值上限 | >3000亿 | **>2000亿** |

## Cron 时间线

| 时间 | 任务 | 模式 | 变化 |
|------|------|:--:|:--:|
| 每小时 | 知识库采集 | no_agent | 不变 |
| 08:25 | 🎯 选股推荐引擎 v2.0 | no_agent | **升级** |
| 08:30 | 🌅 瞭望塔晨报 v8.0 | LLM | **重写** |
| 09:25 | 🔍 侦察兵 | no_agent | 不变 |
| 09:35-14:30 | 🎯 狙击手 | no_agent | 不变 |
| 14:30 | 🌹 决策官 | LLM | 不变 |
| 15:30 | 🛡️ 弹药库 | no_agent | 不变 |
| 17:00 | 🏥 文工团 | no_agent | 不变 |

## 文件变更清单

| 文件 | 变更 | 说明 |
|------|:--:|------|
| `scripts/stock_recommender.py` | **重写** | v1.0→v2.0，排除规则+板块归类+操作策略 |
| `scripts/data/daily_pool.json` | 格式升级 | 新增sector/operation/risk_level字段 |
| Cron `afbbfe5a101e` | **重写** | prompt 全面改写为v8.0 |
| `references/watchtower-v8-model.md` | **新建** | 本文档 |
