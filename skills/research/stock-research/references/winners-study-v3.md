# 涨幅榜学习 v3.0 — 架构与陷阱

> 2026-06-08 | 基于 `researchers.py` v3.0 修复

---

## 架构

```
run_winner_study(gainers)
  │
  ├─ 1. 批量预拉取 (关键！)
  │     get_stock_realtime(all_codes)     ← Sina HTTP 批量, <0.05s
  │     get_historical_k_with_ma(all_codes) ← Baostock ProcessPool, ~10s for 50
  │     get_financial_summary(code)         ← tushare, 逐只
  │     get_north_flow / get_market_money_flow / get_index_data ← 共用
  │
  ├─ 2. 构建 quick_contexts (扁平dict, 直接可读)
  │     {code, name, change_pct, close, ma5, ma10, pe_ttm, roe, debt_ratio, ...}
  │
  ├─ 3. 报告生成:
  │     宏观环境 → 涨幅榜概览(表格,PE/池标记) → 系统覆盖率
  │     → TOP 5 深度分析(6研究员逐只) → 其余快速扫描(MA20偏离表)
  │     → 跨标的共性(MA20上方比例/PE中位数/覆盖率分级)
  │
  └─ 4. 研究员上下文: 复用预拉取数据, 不重复调 API
       ctx = {"pool_stocks": [{close, ma5, ma10, pe_ttm, roe, ...}], 
              "data_sources": {realtime: {ok, source}, kline: {ok, bars}, ...}}
```

## 关键修复

### 1. build_stock_context 必须填充 data_sources

**旧问题**: `data_sources` 始终为 `{}` → DataResearcher 报告「全部 0 个数据源正常」

**修复**: 每步数据拉取成功后标记 `_ds["step_name"] = {"ok": True, ...}`

```python
_ds = ctx["data_sources"]  # 引用，直接修改
# 每步成功后:
_ds["realtime"] = {"ok": True, "source": rt[code].get("data_source", "sina")}
_ds["kline"] = {"ok": True, "bars": len(bars), "source": "baostock"}
_ds["financial"] = {"ok": True, "score": fin.get("score")}
_ds["macro"] = {"ok": True, "source": "tushare+akshare"}
```

### 2. _extract_domain_lesson 接收的是 quick_context，不是 researcher context

**旧问题**: 函数内写 `stock = ctx.get('pool_stocks', [{}])[0]` 试图从嵌套结构读取。但 `run_winner_study` 传入的是扁平 `quick_context` 字典（`{code, name, ma5, ...}`），字段直接挂在 ctx 上。

**修复**: 直接从 `ctx` 读字段：
```python
ma5 = ctx.get('ma5')       # 不是 ctx['pool_stocks'][0]['ma5']
roe = ctx.get('roe')       # 不是 ctx['pool_stocks'][0]['roe']
in_pool = ctx.get('in_pool')
```

### 3. 批量预拉取优于逐只串行

**旧问题**: 每只股票独立调用 `build_stock_context(code)` → ProcessPool 每次重建 → 50只 × 15s = 12min

**修复**: 
```python
# 一次拉全部, ProcessPool 复用
all_quotes = get_stock_realtime(all_codes)    # 1 request, <0.05s
all_kline = get_historical_k_with_ma(all_codes)  # 1 ProcessPool, ~10s
```

### 4. 函数内必须显式 import data_pipeline

`run_winner_study` 在模块顶层 import 之外，需要在函数体内显式导入：
```python
from data_pipeline import (
    get_stock_realtime, get_historical_k_with_ma,
    get_north_flow, get_market_money_flow, get_index_data
)
```

## 覆盖率分级

| 覆盖率 | 级别 | 含义 |
|:--|:--|:--|
| <30% | 🔴 严重不足 | 需检查候选源和筛选条件 |
| 30-60% | 🟡 偏低 | 关注遗漏标的的共同特征 |
| ≥60% | 🟢 良好 | 正常范围 |

## 北交所(920xxx)处理

北交所代码(920开头)不在沪深推荐池覆盖范围，自动识别并单独标注：
```python
bj_count = sum(1 for c in not_covered if c['code'].startswith('920'))
if bj_count:
    lines.append(f"- 其中北交所(920): {bj_count}只 — 北交所标的不在沪深推荐池覆盖范围")
```
