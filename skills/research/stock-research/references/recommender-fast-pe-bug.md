# 推荐引擎 --fast PE/PB 缺失 Bug (v9.0)

> 发现日期: 2026-06-09 | 严重度: P0 | 状态: 已修复

## 症状

`--fast` 模式下 daily_pool.json 中所有推荐标的 `factor_scores.fund = 30`，没有差异化。

```python
import json
d = json.load(open('scripts/data/daily_pool.json'))
scores = [r['factor_scores']['fund'] for r in d['recommendations']]
print(f'unique={len(set(scores))}, values={scores}')
# → unique=1, values=[30, 30, 30, 30, 30, 30, 30, 30]
```

## 根因链

```
cron_recommender.sh --fast
  → _prefetch_indicators() [line 228-261]
    → get_historical_k_with_ma(codes)  # Baostock 返回 peTTM/pbMRQ
    → 只提取 close / volume / ma20    # 🐛 跳过了 peTTM/pbMRQ
    → _indicators[code]['pe'] = 0     # 未设置
  → _score_fund() [line 808-863]
    → pe = ind.get('pe', 0)           # = 0
    → if pe > 0: ...                  # False
    → else: net_flow <= 0 → return 30 # 全部命中
```

## 修复

在 `_prefetch_indicators` 的 bar 遍历循环中，新增 Baostock peTTM/pbMRQ 提取：

```python
# 在 closes/volumes/ma20 提取之后，self._indicators[code] = ind 之前：
if bars:
    last = bars[-1]
    pe_ttm = last.get('peTTM', 0) or 0
    pb_mrq = last.get('pbMRQ', 0) or 0
    if pe_ttm > 0:
        ind['pe'] = float(pe_ttm)
    if pb_mrq > 0:
        ind['pb'] = float(pb_mrq)
```

## 验证

```bash
cd ~/.hermes/profiles/xiaohong/scripts
timeout 300 venv/bin/python3 stock_recommender.py --top 8 --fast
python3 -c "
import json; d=json.load(open('data/daily_pool.json'))
scores=[r['factor_scores']['fund'] for r in d['recommendations']]
print(f'unique={len(set(scores))}, range={min(scores):.1f}-{max(scores):.1f}')
"
# 期望: unique >= 3, range 30-80
```

## 防御

system_health_check 可增加维度：检测 daily_pool.json 中 fund score 的 unique 数量，若 all(n==30 for n in scores) → 标记 degraded。
