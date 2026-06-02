# 股票跟踪系统设计 v1.0

> 创建: 2026-06-02

## 目的

推荐引擎产出后，持续跟踪每只推荐股 60 个交易日的走势，记录每日快照，检测止损失效和到期退场，积累胜率数据供进化引擎使用。

## 数据模型

```json
{
  "pools": [{ "date": "20260602", "stock_count": 8, "stocks": ["601969",...] }],
  "stocks": [{
    "code": "601969",
    "name": "海南矿业",
    "entry_date": "20260602",
    "entry_close": 9.70,
    "entry_score": 53.8,
    "entry_factors": {"event": 60, "fund": 45, ...},
    "entry_sector": "普钢",
    "stop_loss_price": 9.21,
    "target_period": 60,
    "status": "active",
    "snapshots": [
      {"date": "20260602", "close": 9.70, "vs_entry_pct": 0, "volume": 6694000}
    ],
    "exit": {}
  }]
}
```

## 生命周期

```
推荐引擎 _save_pool() ──→ tracker.add_pool() ──→ tracked_pool.json
                                                      │
每日 15:35  ──→ tracker.update_snapshots() ──→ 快照追加
                 │
                 ├── close ≤ stop_loss_price → status=stopped_out, exit 写入
                 ├── days ≥ 60 → status=expired, exit 写入
                 └── 否则 → 继续跟踪
```

## 去重规则

同一 code 3 个月内不重复追踪：
- status=active → 跳过
- 已退场(stopped_out/expired)且 exit_date 距今 < 90 天 → 跳过

## 统计指标

- 总跟踪数 / 活跃数 / 止损失效数 / 到期数
- 止损组平均收益 + 胜率
- 到期组平均收益 + 胜率
- 综合胜率

## 文件

- `scripts/stock_tracker.py` — 核心跟踪器
- `scripts/data/tracked_pool.json` — 跟踪数据
- `cron 📊 股票跟踪器` (15:35 工作日) — 每日快照 cron

## 进化引擎接入

三个月后累计足够样本(≥20只到期)，接入进化引擎：因子回溯 → 哪些因子组合胜率最高 → 参数自动优化。
