# 进化引擎 v2.0 · 全域参数映射

27 可进化参数，7 模块全覆盖。LLM 复盘通过 `review_diagnosis.json` 的 `rule_changes_suggested` 驱动。

## 诊断 → 参数映射

LLM 复盘 `rule` 关键词 → 进化引擎 `param_id`：

| rule 关键词 | param_id | 模块 | 默认值 | 范围 | 沙箱策略 |
|:--|:--|:--|:--|:--|:--|
| `连板排除` | `recommender_lianban_min` | 推荐引擎 | 1 | 1-4 | lightweight_sim |
| `市值下限` | `recommender_market_cap_min` | 推荐引擎 | 50 | 20-100 | lightweight_sim |
| `市值上限` | `recommender_market_cap_max` | 推荐引擎 | 2000 | 500-5000 | lightweight_sim |
| `资金门槛` | `scout_flow_base` | 侦察兵 | 5000 | 2000-15000 | lightweight_sim |
| `盘中资金` | `intra_fund_weight` | 侦察兵盘中 | 0.40 | 0.20-0.60 | reflection_log |
| `盘中技术` | `intra_tech_weight` | 侦察兵盘中 | 0.30 | 0.10-0.50 | reflection_log |
| `盘中情绪` | `intra_sent_weight` | 侦察兵盘中 | 0.20 | 0.05-0.40 | reflection_log |
| `盘中板块` | `intra_sector_weight` | 侦察兵盘中 | 0.10 | 0.00-0.30 | reflection_log |
| `P1逼近` | `sniper_stop_approach_pct` | 狙击手 | 3.0 | 1.0-8.0 | lightweight_sim |
| `P2涨跌` | `sniper_p2_change_threshold` | 狙击手 | 5.0 | 3.0-10.0 | lightweight_sim |
| `P2量比` | `sniper_p2_vol_ratio` | 狙击手 | 3.0 | 1.5-6.0 | lightweight_sim |
| `入场量比` | `sniper_entry_vol_ratio` | 狙击手 | 1.5 | 1.0-3.0 | lightweight_sim |
| `入场偏离` | `sniper_entry_ma_dev_max` | 狙击手 | 5.0 | 2.0-10.0 | lightweight_sim |
| `凯利系数` | `ammo_kelly_coefficient` | 弹药库 | 0.2 | 0.05-0.5 | boundary_only |
| `单股上限` | `ammo_single_stock_max` | 弹药库 | 33.3 | 15.0-50.0 | boundary_only |
| `持仓上限` | `ammo_total_positions_max` | 弹药库 | 9 | 5-15 | boundary_only |
| `止盈启动` | `ammo_trailing_start` | 弹药库 | 20.0 | 10.0-40.0 | boundary_only |
| `止盈步长` | `ammo_trailing_step` | 弹药库 | 10.0 | 5.0-20.0 | boundary_only |
| `采集间隔` | `kb_collect_interval` | 知识库 | 60 | 15-240 | boundary_only |
| `去重窗口` | `kb_dedup_window` | 知识库 | 7 | 1-30 | boundary_only |
| `涨幅阈值` | `review_gainer_min_pct` | 文工团 | 6.0 | 3.0-10.0 | lightweight_sim |
| `涨幅数量` | `review_gainer_top_n` | 文工团 | 50 | 20-100 | lightweight_sim |

竞价五维权重 + 先验α/β 由独立 `auction_diagnosis.json` 处理（7参数），不在此表重复。

## 沙箱策略分层

| 策略 | 适用参数类 | 方法 | 耗时 |
|:--|:--|:--|:--|
| `lightweight_sim` | 过滤器/阈值参数 | 读 daily_pool.json excluded 统计，估算影响 | <0.1s |
| `reflection_log` | 权重/评分参数 | 读 reflection_log 3天 pool_rate 趋势 | <0.1s |
| `boundary_only` | 风控/基础设施参数 | 仅安全边界校验，通过即落地 | <0.1s |

## review_diagnosis.json 规范

```json
{
  "date": "YYYYMMDD",
  "diagnosis": "一句话全局诊断",
  "rule_changes_suggested": [
    {
      "rule": "市值下限",           // 必须精确匹配上表关键词
      "change": "下限从50亿降低到40亿",  // 最后一个数字 = 目标新值
      "reason": "99只<50亿被排除导致空池",
      "confidence": "medium"          // high/medium/low; low 不写入
    }
  ],
  "no_change": false
}
```

## 安全边界 (v3.0: 取消硬上限)

- ~~单次参数调整 ≤ ±20%~~ **已取消**。系统自主评估合理性，无幅度限制。
- 变更幅度较大的参数建议分步执行（通过 `step` 字段标记当日进度）
- 所有变更记录 `evolution_log.json`，可追溯可回滚
- `evolution_backups/` 保存每个文件的修改前版本

### 跨日渐进变更

action_item 新增 `step` 和 `total_steps` 字段：

```json
{
  "rule": "市值下限",
  "param_id": "recommender_market_cap_min",
  "target_value": 30,         // 最终目标
  "current_value": 50,        // 当日当前值
  "step": 1,                   // 当日执行第几步
  "total_steps": 3,            // 共分几步
  "change_today": "50→40",    // 当日变更
  "reason": "105只小市值被排除",
  "confidence": "high"
}
```

引擎处理逻辑：如果 `step < total_steps`，执行当日变更后将 `step+1`，状态保持 `pending` 而非 `applied`，次日继续执行下一步。
