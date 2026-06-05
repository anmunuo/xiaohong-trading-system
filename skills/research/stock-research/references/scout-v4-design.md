# 侦察兵 v4.0 · 盘中推荐池更新设计

## 架构

```
                  ┌─ 资金流扫描 ──────────────────┐
                  │ get_top_flow_stocks(40)         │
                  │ 排除 ST/连板/异常涨跌            │
                  │ 资金>自适应门槛 → new_alert      │
                  └──────────┬──────────────────────┘
                             │
                             ▼
                  ┌─ 多因子综合评分 ────────────────┐
                  │ fund(40%) + tech(30%)            │
                  │ + sent(20%) + sector(10%)        │
                  │ 对标推荐引擎五因子体系            │
                  └──────────┬──────────────────────┘
                             │
                             ▼
                  ┌─ 基本面快筛 ────────────────────┐
                  │ get_stock_realtime → PE 检查     │
                  │ 0 < PE < 200 → 通过             │
                  │ PE=0 → 通过（不阻塞）            │
                  └──────────┬──────────────────────┘
                             │
                             ▼
                  ┌─ 智能合并 ──────────────────────┐
                  │ 推荐引擎标的(不可替换)             │
                  │ + 盘中标的(按评分竞争)             │
                  │ 总数 ≤ 9，高分替低分              │
                  │ 写入 daily_pool.json              │
                  └──────────────────────────────────┘
```

## 盘中评分公式

```python
INTRA_FUND_WEIGHT   = 0.40  # 可进化
INTRA_TECH_WEIGHT   = 0.30  # 可进化
INTRA_SENT_WEIGHT   = 0.20  # 可进化
INTRA_SECTOR_WEIGHT = 0.10  # 可进化

score = (fund_score * 0.40 + tech_score * 0.30 +
         sent_score * 0.20 + sector_score * 0.10)
```

各因子计算逻辑：
- **fund**: net_flow 归一化到 0-100（50000万=100, 0=20）
- **tech**: MA20偏离 + 量比（回踩MA20附近+20, 温和放量+15, 过度放量-5）
- **sent**: 涨跌幅区间（1-5%最佳=75, -3-0%回调机会=60, 大跌=30）
- **sector**: 是否属于今日资金流入 TOP3 板块

## daily_pool.json 记录格式

```json
{
  "code": "300750",
  "name": "宁德时代",
  "sector": "新能源",
  "operation": "盘中侦察兵发现 · 综合评分80.0",
  "risk_level": "中",
  "stop_loss": {"ratio": -5},
  "total_score": 80.0,
  "source": "scout_intraday",
  "added_at": "10:00"
}
```

## 生命周期

| 时间 | 事件 |
|:--|:--|
| 08:25 | 推荐引擎生成当日基础池（清空昨日 scout_intraday） |
| 09:25 | 侦察兵开盘确认（不写池） |
| 10:00 | 第一次盘中扫描 + 池更新 |
| 11:00 | 第二次盘中扫描 + 池更新 |
| 13:00 | 第三次盘中扫描 + 池更新 |
| 14:00 | 最后一次盘中扫描 + 池更新 |
| 14:30 | 决策官使用最终池做盘中决策 |
| 次日 08:25 | 清空重来 |

## 关键设计决策

1. **无硬上限**: 不设板块上限和数量上限，让评分自然竞争。系统通过 evolution engine 学习最优权重。
2. **可替换**: 盘中标的可被更高分候选替代，推荐引擎标的不可替换。
3. **跨日清除**: 推荐引擎 `_save_pool` 检查 `date` 字段，旧日 intraday 自然清除。

## v4.1 更新：个股K线技术分析 (2026-06-05)

**问题**：v4.0 只做资金流筛选，没有对被选中的股票做个股维度分析。用户明确要求「不能只根据资金面情况，还要把选中的股票进行个股的详细分析」。

**新增 `_enrich_with_kline_analysis()`**：

```python
def _enrich_with_kline_analysis(entries: list):
    """批量拉取K线，为每只股票附加 MA20偏离/量比/PE/昨收"""
    codes = [e['code'] for e in entries]
    kdata = get_historical_k_with_ma(codes, days=30)   # ~2s for ≤15 codes
    
    for e in entries:
        bars = kdata[e['code']]
        closes = [b['close'] for b in bars if b['close'] > 0]
        volumes = [b['volume'] for b in bars if b['volume'] > 0]
        
        e['ma20_dev']  = round((closes[-1] / (sum(closes[-20:])/20) - 1) * 100, 1)
        e['vol_ratio'] = round(volumes[-1] / (sum(volumes[-5:])/5), 1)
        e['pe']        = bars[-1].get('peTTM')  # from BaoStock
```

**表格新增列**：

| 表 | 新增列 |
|:--|:--|
| 双重确认 | MA20偏离 / 量比 / PE |
| 新增异动 | MA20偏离 / 量比 |
| 待确认 | MA20偏离 / 量比 / PE |

**调用位置**：`run_scout()` 中，三个列表 (double_confirm/new_alert/pending) 完成分类和截断后、返回前调用。K线数据拉取后由于是原地修改（list of dicts），需按长度重新切片回三个列表。

**性能**：`get_historical_k_with_ma` 使用 ProcessPoolExecutor，≤15 只代码约 2s 完成。
