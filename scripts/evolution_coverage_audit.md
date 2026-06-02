# 进化引擎覆盖度审计报告

**生成时间**: 2026-06-01  
**审计人**: Hermes Agent  
**进化引擎版本**: v2.0.0  

---

## 一、当前进化参数总数

**EVOLVABLE_PARAMS 共计 37 个参数**，分布在 8 个模块：

| 模块 | 参数数 | 参数列表 |
|------|--------|----------|
| stock_recommender | 3 | lianban_min, market_cap_min, market_cap_max |
| scout | 7 | flow_base, change_min, change_max, INTRA_FUND/INTRA_TECH/INTRA_SENT/INTRA_SECTOR |
| sniperd | 11 | STOP_PROXIMITY_PCT, P2_CHANGE_THRESHOLD, P2_VOL_RATIO, ENTRY_VOL_RATIO, ENTRY_MA_DEV_MAX, L1_INTERVAL, ALERT_COOLDOWN_P1/P2/ENTRY/MARKET, MARKET_SWING_THRESHOLD |
| ammo_risk | 5 | kelly_coefficient, single_stock_max_pct, total_positions_max, trailing_start_pct, trailing_step_pct |
| mega_collector | 1 | kb_collect_interval |
| knowledge_base | 1 | kb_dedup_window |
| auction_features | 5 | weight_price_slope, volume_accel, imbalance, premium, sector_dev |
| auction_learner | 2 | prior_alpha, prior_beta |
| review | 2 | gainer_min_pct, gainer_top_n |

**当前分类覆盖**:
- FILTER_PARAMS: 14 个
- WEIGHT_PARAMS: 7 个 
- RISK_PARAMS: 5 个
- INTRA_WEIGHT_PARAMS: 4 个
- INFRA_PARAMS: 7 个

---

## 二、仍为硬编码但应进化的参数清单

### 🔴 P0 — 影响收益/风控（10个）

| # | 参数名 | 文件 | 行号 | 当前值 | 建议范围 | 说明 |
|---|--------|------|------|--------|----------|------|
| 1 | `recommender_factor_event_weight` | stock_recommender.py | L344 | 0.30 | [0.10, 0.50] | 事件因子权重，影响选股偏向 |
| 2 | `recommender_factor_fund_weight` | stock_recommender.py | L345 | 0.25 | [0.10, 0.50] | 资金流因子权重 |
| 3 | `recommender_factor_sentiment_weight` | stock_recommender.py | L346 | 0.20 | [0.05, 0.40] | 情绪因子权重 |
| 4 | `recommender_factor_technical_weight` | stock_recommender.py | L347 | 0.15 | [0.05, 0.35] | 技术面因子权重 |
| 5 | `recommender_factor_research_weight` | stock_recommender.py | L348 | 0.10 | [0.00, 0.25] | 研究因子权重 |
| 6 | `recommender_stop_loss_ratio` | stock_recommender.py | L462 | -5.0 | [-10.0, -2.0] | 默认止损比例(%) |
| 7 | `recommender_stop_ma20_close_dev` | stock_recommender.py | L475 | 0.08 | [0.03, 0.15] | 启用MA20止损的偏离阈值 (8%) |
| 8 | `recommender_stop_ma20_multiplier` | stock_recommender.py | L476 | 0.98 | [0.95, 0.99] | MA20止损价格乘数 |
| 9 | `recommender_risk_small_cap` | stock_recommender.py | L108 | 80 | [30, 200] | 小市值高风险阈值(亿) |
| 10 | `recommender_risk_high_change` | stock_recommender.py | L108 | 8 | [5, 15] | 高涨幅高风险阈值(%) |
| 11 | `scout_stop_kcb_ratio` | scout.py | L131 | -7.0 | [-12.0, -3.0] | 科创板止损比例(%) |
| 12 | `scout_stop_main_ratio` | scout.py | L131 | -5.0 | [-10.0, -2.0] | 主板止损比例(%) |
| 13 | `scout_risk_high_change` | scout.py | L140 | 8 | [5, 15] | 高风险涨跌阈值(%) |
| 14 | `scout_risk_mid_change` | scout.py | L142 | 5 | [3, 10] | 中高风险涨跌阈值(%) |
| 15 | `scout_adaptive_strong_mult` | scout.py | L118 | 3000 | [1500, 5000] | 强势市场资金门槛(万) |
| 16 | `scout_adaptive_weak_mult` | scout.py | L120 | 8000 | [5000, 20000] | 弱势市场资金门槛(万) |
| 17 | `scout_adaptive_market_threshold` | scout.py | L117 | 1.0 | [0.5, 3.0] | 市场强弱分界阈值(%) |
| 18 | `ammo_r_value_denominator` | ammo_risk.py | L118 | 8 | [4, 20] | R值计算分母(分散度) |
| 19 | `ammo_trailing_min_buffer_pct` | ammo_risk.py | L283 | 3.0 | [1.0, 8.0] | 移动止盈动态缓冲% |
| 20 | `ammo_sector_concentration_max` | ammo_risk.py | L545 | 30 | [20, 50] | 行业集中度告警阈值(%) |

### 🟡 P1 — 影响效率（13个）

| # | 参数名 | 文件 | 行号 | 当前值 | 建议范围 | 说明 |
|---|--------|------|------|--------|----------|------|
| 21 | `auction_poll_interval` | auction_collector.py | L44 | 3 | [1, 10] | 竞价轮询间隔(秒) |
| 22 | `auction_request_timeout` | auction_collector.py | L134 | 8 | [3, 20] | API请求超时(秒) |
| 23 | `auction_request_delay` | auction_collector.py | L161 | 0.15 | [0.05, 0.5] | 请求间延迟(秒,防限流) |
| 24 | `kb_retention_days` | knowledge_base.py | L57 | 7 | [1, 30] | 知识库保留天数 |
| 25 | `datapipeline_cache_expire` | data_pipeline.py | L44 | 300 | [60, 1800] | 默认缓存过期(秒) |
| 26 | `datapipeline_index_cache_expire` | data_pipeline.py | L108 | 120 | [30, 600] | 指数数据缓存(秒) |
| 27 | `datapipeline_request_timeout` | data_pipeline.py | L123 | 15 | [5, 30] | requests请求超时(秒) |
| 28 | `sniper_l3_interval` | sniperd.py | L50 | 30 | [15, 120] | 大盘轮询间隔(秒) |
| 29 | `sniper_l4_interval` | sniperd.py | L51 | 60 | [30, 300] | 板块轮询间隔(秒) |
| 30 | `sniper_state_stale_seconds` | sniperd.py | L68 | 3600 | [1800, 14400] | 状态过期时间(秒) |
| 31 | `sniper_max_consecutive_errors` | sniperd.py | L69 | 10 | [3, 30] | 连续错误重置阈值 |
| 32 | `sniper_ma_refresh_interval` | sniperd.py | L323 | 1800 | [600, 7200] | MA数据刷新间隔(秒) |
| 33 | `scout_top_flow_count` | scout.py | L186 | 40 | [20, 100] | 获取Top资金流股数 |

### 🟢 P2 — 锦上添花（9个）

| # | 参数名 | 文件 | 行号 | 当前值 | 建议范围 | 说明 |
|---|--------|------|------|--------|----------|------|
| 34 | `recommender_candidate_flow_count` | stock_recommender.py | L180 | 50 | [30, 100] | 候选池资金流取数 |
| 35 | `ammo_nv_history_max` | ammo_risk.py | L41 | 30 | [10, 90] | 净值历史保留天数 |
| 36 | `ammo_weekly_window` | ammo_risk.py | L144 | 5 | [3, 10] | 周度变化计算窗口(天) |
| 37 | `ammo_liquidity_subprocess_timeout` | ammo_risk.py | L338 | 20 | [10, 60] | 流动性子进程超时(秒) |
| 38 | `ammo_liquidity_impact_threshold` | ammo_risk.py | L375 | 5 | [2, 15] | 流动性冲击告警阈值(%) |
| 39 | `kb_freshness_bonus` | knowledge_base.py | L216 | 1.5 | [1.0, 3.0] | 当日事件权重加成倍数 |
| 40 | `ammo_concentration_warning_level` | ammo_risk.py | L545 | 15 | [10, 30] | 集中度关注级别(%) |
| 41 | `scout_flow_normalize_cap` | scout.py | L318-322 | 50000 | [20000, 100000] | 资金流评分归一化上限(万) |
| 42 | `recommender_score_floor` | stock_recommender.py | L353 | 50 | [30, 70] | 评分基础分 |

---

## 三、关键发现

### 3.1 最大遗漏：推荐引擎五因子权重

`stock_recommender.py` 的 `_score_candidates()` 方法中五个因子权重 (0.30/0.25/0.20/0.15/0.10) 是完全硬编码的。这是整个推荐系统最核心的调参点，直接影响选股质量。

**代码位置**: L343-348
```python
c['total_score'] = round(
    scores['event'] * 0.30 +
    scores['fund'] * 0.25 +
    scores['sentiment'] * 0.20 +
    scores['technical'] * 0.15 +
    scores['research'] * 0.10, 1
)
```

### 3.2 scout市值过滤重复硬编码

`scout.py` 的 `is_market_cap_ok()` (L93) 和 `stock_recommender.py` 的 `_apply_filters()` (L263) 各自硬编码了 50/3000 的市值范围，而非读取进化参数。如需调整需同时改两处。

### 3.3 自适应资金门槛的辅助参数缺失

`scout_flow_base` (5000万) 已纳入进化，但 `adaptive_flow_threshold()` 中决定何时切换到 3000/8000 的市场涨跌阈值(1.0%) 和极端值(3000/8000) 仍是硬编码。仅调整 base 值不会改变自适应行为。

### 3.4 sniperd 守护进程漏参数

`sniperd.py` Config 类 18 个参数中仅 11 个进化。遗漏: L3_INTERVAL(30s), L4_INTERVAL(60s), STATE_STALE_SECONDS(3600s), MAX_CONSECUTIVE_ERRORS(10), _MA_REFRESH_INTERVAL(1800s)。

---

## 四、覆盖率统计

| 类别 | 已进化 | 未进化 | 覆盖率 |
|------|--------|--------|--------|
| P0 收益/风控 | 15 | 20 | 42.9% |
| P1 效率 | 10 | 13 | 43.5% |
| P2 辅助 | 12 | 9 | 57.1% |
| **总计** | **37** | **42** | **46.8%** |

> 结论：当前进化引擎仅覆盖了约 **47%** 的可进化参数。P0 级缺失 20 个参数中，推荐引擎五因子权重、R值分母和止损参数是最高优先级的短板。

---

## 五、建议的优先级路线图

### 立即补入（本周）
1. 推荐引擎五因子权重 (P0 #1-5) — 影响选股排序的核心参数
2. R值计算分母 (P0 #18) — 影响仓位分配
3. 移动止盈缓冲% (P0 #19) — 影响止盈执行
4. 行业集中度阈值 (P0 #20) — 风控告警

### 近期补入（下周）
5. 止损相关参数 (P0 #6-8, #11-12) — 影响风控
6. 风险评级阈值 (P0 #9-10, #13-14) — 影响风险标签
7. 自适应门槛辅助参数 (P0 #15-17) — 完善scout自适应

### 后续补入
8. P1 效率参数 (采集/轮询/缓存间隔)
9. P2 辅助参数

---

*审计完成。共扫描 9 个核心脚本，识别 42 个待进化硬编码参数。*
