# 分时数据接入指南 (v8.3)

## 数据源

| 来源 | 接口 | 粒度 | 免费 | 限流 |
|:--|:--|:--|:--:|:--|
| Sina | `quotes.sina.cn` KLineData | 1/5/15/30/60min | ✅ | 无显著限制 |
| AKShare | `stock_zh_a_hist_min_em` (东方财富) | 1/5/15/30/60min | ✅ | 易被东方财富限流 |
| tushare | `stk_mins` | 1/5/15/30/60min | 🔒 | 需积分≥2000 + 1次/分钟 |
| tushare | `realtime_quote` | 快照(非序列) | ✅ | 无 |

## data_pipeline.py 新增函数

### get_intraday_minutes(stock_code, scale=5, count=48)

```python
from data_pipeline import get_intraday_minutes
bars = get_intraday_minutes('000001', scale=5, count=48)
# → [{'time': '2026-06-02 09:35:00', 'open': 10.98, 'high': 11.0, 'low': 10.98, 'close': 11.0, 'volume': 8210150, 'amount': 90311650.0}, ...]
```

- 60s 缓存 (TTL)
- 自动判断 sh/sz 前缀 (6开头→sh)
- 返回最多 count 条 (max ~240)

### get_intraday_volume_alert(stock_code, scale=5)

```python
from data_pipeline import get_intraday_volume_alert
va = get_intraday_volume_alert('000001', scale=5)
# → {'alert': True, 'signal': '放量滞涨⚠️', 'vol_ratio': 2.57, 'price_chg': 0.18}
```

检测逻辑：
- 最近 2 根 vs 前 10 根均量 → 量比
- 信号分类：放量上涨 / 放量下跌⚠️ / 放量滞涨⚠️ / 缩量异动

## 集成点

### 狙击手 sniperd (v8.3)

| 参数 | 默认值 | 说明 |
|:--|:--|:--|
| INTRO_DAY_INTERVAL | 60s | 分时扫描间隔 |
| INTRO_DAY_VOL_RATIO | 2.5 | 放量告警阈值 |
| ALERT_COOLDOWN_INTRO | 180s | 冷却时间 |

- `TriggerEngine.check_intraday_volume(pos)` - 每 60s 扫描持仓
- 量比 >2.5x → P2 级别告警 (🟣放量上涨 / 🟠放量下跌)

### 侦察兵 scout (v8.3)

- `INTRA_VOLUME_BONUS = 8` - 分时放量加分上限
- `score_intraday_candidate()` 内嵌 volume_bonus
- 放量上涨 → +2~10 附加分

## 缓存策略

- `get_intraday_minutes`: 60s TTL，第二次调用 0ms
- 适合盘中高频扫描场景
- 不在 sniperd 每个 tick(3s) 都调用——用 INTRO_DAY_INTERVAL 控制频率
