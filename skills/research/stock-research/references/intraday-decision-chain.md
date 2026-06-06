# 盘中实时决策链 v1.0

> 侦察兵发现 → 三级认证 → 推荐池/目标池 → 狙击手开仓

## 数据流

```
09:30  侦察兵盘中扫描 (scout.py --intraday)
         │
         ├─ 扫描资金流 TOP 40
         ├─ 发现不在推荐池的标的
         │
         ├─ Gate 1: 研究员快速议会 (run_quick_parliament)
         │     · 4位核心研究员（多方/空方/技术面/基本面）
         │     · 2轮研判（独立→小红终审）
         │     · 通过: bias≠"偏空" 且 confidence≥0.5
         │     · 耗时: ~10s
         │
         ├─ Gate 2: 多因子认证 (score_single_stock)
         │     · 拉取K线 → 构建候选 → 五因子评分
         │     · 通过: total_score ≥ 60
         │     · 耗时: ~2s
         │
         └─ Gate 3: 基本面快筛
               · PE>0, PB>0, ROE≥5%, 负债率<70%
               · 耗时: <1s
               │
         三级全过 ──→ daily_pool (评分竞争, ≤9席)
               └──→ target_pool (评分竞争, 固定3席)
                      │
                      ├─ 09:30 初始选池
                      │     · 综合评分: 议会35% + 因子35% + 基本面15% + 流动性15%
                      │     · 从 daily_pool 中选 Top 3
                      │
                      └─ 盘中动态更新
                            · 新标的评分 > 池内最低分 → 替换
                            · 保持3只不变
                            │
                    狙击手 (sniper.py v3.1)
                      │
                      ├─ 加载 target_pool.json
                      ├─ 量比分析 (_get_volume_ratio)
                      │     · 量比 > 1.5 → 放量
                      │     · 量比 > 2.0 → 强放量
                      │
                      ├─ 分时K线分析 (_analyze_intraday_kline)
                      │     · 拉取5分钟K线 (48根=4h)
                      │     · 趋势: MA5 vs MA10
                      │     · 形态: V型反转/连续上攻/连续回落
                      │     · 量价: 近3根 vs 均量
                      │
                      └─ 综合入场判断 (_build_entry_signal)
                            · 分时ready + 量比>1.2 + 涨跌>-3%
                            → 🟢 开仓信号
```

## 模块版本

| 模块 | 版本 | 新增能力 |
|:--|:--|:--|
| researchers.py | v2.3+v2.4 | run_quick_parliament() + run_winner_study() |
| stock_recommender.py | v2.4 | score_single_stock() |
| **target_pool.py** | **v1.0** | **新模块** select/update/load/mark_entry |
| scout.py | v4.2 | _intraday_gate() + target_pool 集成 |
| sniper.py | v3.1 | 目标池驱动 + 量比 + 分时K线入口 |

## 关键参数

| 参数 | 值 | 位置 |
|:--|:--|:--|
| 目标池容量 | 3 | target_pool.py |
| 议会通过门槛 | bias≠"偏空" + confidence≥0.5 | _intraday_gate() |
| 多因子通过门槛 | total_score ≥ 60 | _intraday_gate() |
| 基本面通过门槛 | PE>0, PB>0, ROE≥5%, debt<70% | _intraday_gate() |
| 目标池评分权重 | 议会35% + 因子35% + 基本面15% + 流动性15% | _score_for_target() |
| 狙击手入场 | 分时ready + 量比>1.2 + change>-3% | _build_entry_signal() |

## 目标池 JSON Schema

```json
{
  "date": "20260606",
  "selected_at": "09:30",
  "capacity": 3,
  "stocks": [
    {
      "code": "300750",
      "name": "宁德时代",
      "score": 78.5,
      "parliament": {"bias": "偏多", "confidence": 0.72, "bull_signals": 3},
      "factor_scores": {"event": 65, "fund": 82, "sentiment": 70},
      "fundamental": {"pe": 28.5, "pb": 4.2, "roe": 18.3, "debt_ratio": 55.2},
      "entry_ready": false,
      "entry_signal": null
    }
  ],
  "history": []
}
```

## 数据文件

| 文件 | 位置 | 写入者 | 读者 |
|:--|:--|:--|:--|
| daily_pool.json | scripts/data/ | stock_recommender + scout | 瞭望塔/决策官/侦察兵/target_pool |
| target_pool.json | scripts/data/ | scout + target_pool | 狙击手/决策官 |
| fix_log.json | scripts/data/ | auto_repair | system_health_check |

## 开关控制

- `scout.py`: `TARGET_POOL_ENABLED = True` → 设 False 禁用目标池
- `target_pool.py`: `--select --force` 强制重选
- `sniper.py`: 自动从 target_pool.json 读取，无需配置

## 涨幅榜学习 (新)

收盘后研究员对6%+个股做领域专项分析:

```bash
python3 researchers.py --winners
```

输出: `reports/research/涨幅榜学习-{date}.md`
Cron: 每周一至五 15:50 `ac4772979e24`
