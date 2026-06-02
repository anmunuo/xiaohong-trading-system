# 数据资产注册表

> 维护者: 📊 数据研究员 (data_hub.py)
> 最后更新: 2026-06-02 v8.1

## 系统数据资产全景 (21项)

| 数据名 | 来源 | 消费者 | 状态 |
|:--|:--|:--|:--:|
| global_indices | data_pipeline → mega_collector → external_futures | market_snapshot/瞭望塔/决策官/推荐引擎 | ✅ |
| north_flow | data_pipeline → mega_collector → north_flow | market_snapshot/瞭望塔/推荐引擎 | ✅ |
| sector_flow | data_pipeline → market_snapshot + scout | market_snapshot/scout/推荐引擎 | ✅ |
| market_money | data_pipeline → ammo_risk + market_snapshot | market_snapshot/ammo_risk | ✅ |
| stock_realtime | data_pipeline (Sina 批量, <0.05s) | 推荐引擎/弹药库/狙击手/跟踪器/竞价学习器 | ✅ |
| fundamentals | tushare daily_basic (PE/PB/total_mv) | 推荐引擎/弹药库 | ✅ |
| announcements | mega_collector (akshare 公告) | 推荐引擎/研究员议会/kb_insights | ✅ |
| dragon_tiger | mega_collector (akshare 龙虎榜) | 推荐引擎/研究员议会 | ✅ |
| broker_views | mega_collector (akshare 研报) | 推荐引擎/研究员议会 | ✅ |
| hot_events | mega_collector (东方财富热搜) | 推荐引擎 | ⚠️ 弱 |
| auction_data | auction_collector (东方财富竞价) | 竞价学习器/侦察兵 | ✅ |
| industry_news | mega_collector → 推荐引擎 event | 推荐引擎/kb_insights | ✅ |
| policy_macro | mega_collector → 推荐引擎 event | 推荐引擎/kb_insights | ✅ |
| margin_trading | akshare → market_snapshot | market_snapshot/瞭望塔/决策官 | ✅ 🆕 |
| index_valuation | tushare → index_valuation.py → market_snapshot | market_snapshot/弹药库/瞭望塔 | ✅ 🆕 |
| market_snapshot | 聚合上述所有 → snapshot.json | 瞭望塔/决策官 LLM | ✅ 🆕 |
| data_packages | data_hub.distribute → 3 packages | 各模块 | ✅ 🆕 |
| tracked_pool | stock_tracker → tracked_pool.json | 跟踪系统/进化引擎 | ✅ 🆕 |
| research_weekly | research_weekly.py → 5研究员 reports | 进化引擎(action_items) | ✅ 🆕 |
| limit_up_pool | akshare.stock_zt_pool_em | 推荐引擎(首板候选) | ⚠️ 部分 |
| short_selling | akshare (未接入) | — | ❌ 待接 |
| institutional_holdings | tushare (未接入) | — | ❌ 待接 |
| volatility_index | akshare (未接入) | — | ❌ 待接 |

## 数据流架构

```
data_pipeline.py ────→ mega_collector.py ──→ mega_latest.json ──→ 推荐引擎(scoring)
       │                      │                    │
       │                      │              market_snapshot.py (08:28)
       │                      │                    │
       │                      │              market_snapshot.json ──→ 瞭望塔/决策官 LLM prompt
       │                      │                    │
       │                      │              data_hub.distribute() ──→ 3 数据包
       │                      │
       ├──→ 侦察兵/弹药库/狙击手/跟踪器 (实时直调)
       └──→ 竞价采集器/学习器
```

## 数据研究员 v2.0 能力

- `data_hub --health` → 5项数据新鲜度检查
- `data_hub --discover` → 缺口发现 + 接入建议
- `data_hub --distribute` → 3个数据包自动分发
- 每日 02:00 cron 自动执行 health + discover
- 数据包在 08:28 market_snapshot 中自动生成
