# 侦察兵数据源健康检查 v4.1

## 问题

东方财富 `push2.eastmoney.com/api/qt/clist/get` 的 `f62`（主力净流入）字段在盘中**间歇性全部返回 0**，同时 `f66`/`f69`/`f184` 也归零。导致 `get_top_flow_stocks()` 返回的 `net_flow` 全为 0，侦察兵「双重确认」机制失效。

## 复现

```python
from data_pipeline import get_top_flow_stocks
stocks = get_top_flow_stocks(10, no_cache=True)
all_zero = all(s['net_flow'] == 0 for s in stocks)
# 盘中 True → f62 失效
```

## 修复架构

```
check_data_health()          # 探测层：样本检测各字段有效率
    ↓
get_top_flow_stocks()        # 数据层：内建 f62 健康检测 + 动量 fallback
    ↓
scout.py run_scout()         # 消费层：数据质量感知 + 自适应门槛
    ↓
format_report()              # 输出层：数据源降级告警
```

## check_data_health() 检测逻辑

```python
def check_data_health() -> Dict:
    # 1. 拉10只样本 → 统计 f62_valid / f184_valid / f66_valid
    # 2. 如果 f62_valid < 30%:
    #    a. f184_valid >= 30% → flow_field='f184'
    #    b. f66_valid >= 30% → flow_field='f66'  
    #    c. 全无效 → flow_field='momentum', status='degraded'
    # 3. 同时检测新浪 API 可用性
    return {'status': 'ok'|'degraded', 'flow_field': 'f62'|'f184'|'momentum', ...}
```

## 动量 fallback 评分

当 f62 失效时，用：
```python
_momentum_score = abs(涨跌幅%) × 0.7 + 换手率% × 0.2 + 量比 × 0.1
```
降序排列替代资金流排序。`net_flow` 置为 None，`_quality` 标记 `'fallback'`。

## scout.py 自适应

```python
flow_mode = health['flow_field']  # 'f62' | 'momentum'
if flow_mode == 'momentum':
    # 放宽门槛：涨跌幅 ±3%（替代资金流 5000万门槛）
    if abs(change) < 3: continue
```

## 报告输出

动量模式下在 report 顶部显示：
```
⚠️ 数据源降级: 资金流字段不可用，使用涨跌幅+量比替代
```

## 缓存注意事项

- 交易时段缓存 TTL = 300s（5分钟）
- 如果某次拉取 f62=0，缓存会保留 5 分钟的错误数据
- `no_cache=True` 参数强制跳过缓存（健康检查专用）
- 正常调用不设 `no_cache`，利用缓存减少 API 压力

## 关键函数签名

- `data_pipeline.check_data_health() → Dict` — 探测所有数据源（f62/f184/f66/sina）
- `data_pipeline.get_top_flow_stocks(n, no_cache=False) → List[Dict]` — 含健康检测 + 动量 fallback + `total_mv` 字段
- `scout.run_scout() → dict` — 含 flow_mode/data_status 字段

## 市值过滤修复（v4.1 追加）

**问题**：`is_market_cap_ok(code)` 依赖 `get_stock_realtime()`（Sina API），但 Sina API **不含 `market_cap` 字段** → 全部通过 → 万亿巨头（立讯精密5391亿、中际旭创13287亿）漏入池。

**修复**：
1. `get_top_flow_stocks()` 加入 `total_mv` 字段（push2 的 `f20`，**元→亿 ÷1e8**，不是万元÷1e4）
2. `is_market_cap_ok(code, pre_fetched_mv)` 优先用预取市值，无预取时 fallback
3. 侦察兵扫描循环 `is_market_cap_ok(code, s.get('total_mv'))` 传预取市值
4. `feed_intraday_pool()` 同样传预取市值
5. `new_entries` 构造保留 `net_flow`/`change_pct`/`_quality` 字段（之前遗漏导致 format_report KeyError）

**单位陷阱**：
| 来源 | 字段 | 原始单位 | 转亿 |
|------|------|:--:|:--:|
| tushare daily_basic | total_mv | 万元 | ÷ 1e4 |
| 东方财富 push2 | f20 | **元** | **÷ 1e8** ⚠️ 不一样！ |
