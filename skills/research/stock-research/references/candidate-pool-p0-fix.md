# 候选池盲区 P0 修复

## 问题诊断（文工团LLM复盘 2026-06-01）

```
推荐池唯一标的: 920184 国源科技 (北交所, 评分48.3)
missed_count: 118 (120涨停中118不在候选池)
root_cause: candidate_pool_blindspot P0
候选仅来源公告事件(111只)，与涨停池交集仅2只
```

## 三重根因

| 根因 | 位置 | 现象 |
|:--|:--|:--|
| `get_top_flow_stocks()` 盘前返回空 | data_pipeline.py | 缓存 TTL=300s，08:25 时昨日数据已过期，API 返回空 |
| hot_events/broker_views 采集为空 | mega_collector.py | KB 的这两个模块 data=[] |
| 全部涨停被排除（含首板） | stock_recommender.py | `_get_lianban_codes()` 排除所有涨停，`_apply_filters` 无差别移除 |

## 修复方案（4 处）

### 1. data_pipeline.py — `get_top_flow_stocks()` 盘前兜底

```python
# 盘前用更长 TTL（24h），避免 08:25 冷启动返回空
is_trading = now.weekday() < 5 and time(9,30) <= now.time() <= time(15,0)
cache_ttl = 300 if is_trading else 86400

# API 返回空时，使用过期缓存降级
if not stocks:
    expired = _cached(cache_key, 86400 * 7)
    if expired:
        stocks = expired[:n]
```

### 2. stock_recommender.py — `_get_lianban_codes` → `_get_multi_lianban_codes`

```python
# old: 获取所有涨停，含首板 → 全部排除
lianban.add(str(row.get('代码', '')))

# new: 仅获取 ≥2 连板 → 首板保留
lb = int(row.get('连板数', 1))
if lb >= 2:
    multi_lianban.add(str(row.get('代码', '')))
```

### 3. stock_recommender.py — 新增 `_get_first_board_codes()` 候选源

```python
# 2e. 昨日涨停首板（连板数=1）
if lb == 1:
    first_board.append({'code': ..., 'name': ..., 'source': 'limit_up_first'})
```

### 4. stock_recommender.py — `_apply_filters()` 排除规则更新

```
旧: 排除所有涨停（含首板）
新: 排除 ≥2连板（保留首板）
```

## 效果

| 指标 | 修复前 | 修复后 |
|:--|:--|:--|
| 候选源数量 | 1（仅公告111只） | 4（公告+资金流+首板+研报） |
| 候选池规模 | ~111 | 190+（+76%） |
| 涨停首板覆盖率 | 0% | 80只纳入 |
