# 数据源速查表

## 调用方式

### 方式一：data fetch CLI
```bash
data fetch stock --symbol CODE --category TYPE [--market us|hk]
data fetch company --symbol CODE --category TYPE
data fetch news --query KEYWORD --limit N
data fetch search --query KEYWORD --limit N
```
**限制**：仅支持指定 symbol 的单票查询，无法做全市场扫描。

### 方式二：Python akdirect
```bash
python3 -c "import akshare as ak; print(ak.FUNC(PARAMS))"
```

### 方式三：Python tsdirect
```bash
python3 -c "import tushare as ts; pro = ts.pro_api(); print(pro.FUNC(PARAMS))"
```

---

## 已验证可用的函数清单

### akshare
| 函数 | 用途 | 关键参数 | 验证日期 |
|------|------|----------|----------|
| `stock_zt_pool_em` | 涨停板 | `date='20260522'` | 2026-05-24 |
| `stock_lhb_detail_em` | 龙虎榜 | `start_date`, `end_date` | 2026-05-24 |
| `stock_hot_rank_em` | 热度排行 Top100 | 无 | 2026-05-24 |
| `stock_hsgt_hist_em` | 北向历史 | `symbol='沪股通'`/`'深股通'` | 2026-05-24 |
| `stock_sh_a_spot_em` | 沪A实时行情 | 无 | ⚠️ 触发限流 |

### tushare（ETF 专属函数）

ETF 查询与个股使用**不同的 API**，不可混用：

| 函数 | 用途 | 关键字段 |
|------|------|----------|
| `fund_basic(ts_code='515120.SH', market='E')` | ETF 基本信息 | name, management, benchmark, m_fee, c_fee, found_date |
| `fund_daily(ts_code='515120.SH', start_date, end_date)` | ETF 日线 OHLCV | pre_close, open, high, low, close, vol, amount |
| `fund_portfolio(ts_code='515120.SH')` | 持仓明细 | symbol, mkv, stk_mkv_ratio, stk_float_ratio |
| `fund_nav(ts_code='515120.SH', start_date, end_date)` | 单位净值 | unit_nav, accum_nav, adj_nav |

**常见坑**：`fund_portfolio` 列名是 `symbol` 和 `mkv`（非 `sec_code`/`name`/`ratio`），持仓名需另调 `stock_basic` 补全。

---

## 搜索 akshare 可用函数
```python
[f for f in dir(ak) if 'lhb' in f.lower()]     # 龙虎榜
[f for f in dir(ak) if 'hsgt' in f.lower()]    # 北向
[f for f in dir(ak) if f.startswith('stock_')] # 所有stock函数
[f for f in dir(ak) if 'rank' in f.lower()]    # 排行
[f for f in dir(ak) if 'spot_em' in f.lower()] # 实时行情
```

## 搜索 tushare 可用字段
```python
df = pro.FUNC(...)
print(df.columns.tolist())
```

---

## 方式四：strategy_bridge（LLM 调用策略引擎）

```bash
cd ~/.hermes/profiles/xiaohong/scripts
python3 strategy_bridge.py signal   # 交易信号（持仓+止损+建议）
python3 strategy_bridge.py risk      # 风控分析
python3 strategy_bridge.py list      # 策略列表
python3 strategy_bridge.py run CMP-001 300131  # 运行策略
```

所有输出为 JSON。详见 `strategy-trading` skill。

## 方式五：data_pipeline 统一管道（推荐）

位于 `~/.hermes/profiles/xiaohong/scripts/data_pipeline.py`，封装了 Tushare/AKShare/东方财富/Sina 四源聚合，内置缓存和 fallback。

```python
cd ~/.hermes/profiles/xiaohong/scripts
python3 -c "from data_pipeline import *; ..."
```

| 函数 | 用途 | 返回结构 | 数据源 |
|------|------|----------|--------|
| `get_index_data()` | 全球指数实时 | `{asia: {nikkei/hangseng/shanghai}, europe: {ftse/dax}, us: {dow/sp500/nasdaq}}` | AKShare+Sina+Tushare |
| `get_north_flow()` | 北向资金 | `{net_flow(亿), status, detail}` | Tushare→AKShare fallback |
| `get_market_money_flow()` | 大盘资金 | `{main_net(亿), sh_index, sh_change, sz_index}` | AKShare |
| `get_individual_money_flow(code, market)` | 个股资金 | `{main_net(万), main_pct(%), close, change_pct}` | Tushare→AKShare fallback |
| `get_sector_flow_rank(type)` | 板块排名 | `[{name, flow(万), change_pct}]` type='3'=行业 | 东方财富API |
| `get_top_flow_stocks(n)` | 资金TOP股票 | `[{code, name, net_flow(万), change_pct}]` | 东方财富API |
| `get_stock_candidates()` | 选股推荐 | `[{code, name, reason, target}]` | 东方财富→筛选 |
| get_watchlist() | 观察池 | 基于 holdings.json 持仓+实时资金流向 | 上述全部 |
| get_stock_realtime(codes) | 个股日线 (v3.1) | {code: {close, change_pct, open, high, low, volume, data_source, trade_date}} | data fetch CLI (Hermes) |

缓存策略

**硬编码注意事项**：
- Tushare token 内嵌在 data_pipeline.py 顶部（`TUSHARE_TOKEN = "..."`）
- holdings.json 路径：`data_pipeline.py` 同级 `../data/holdings.json`
- 非交易时段返回 data_source: no_data，不是错误
- get_stock_realtime() 通过 subprocess 调用 data fetch CLI，每次调用单只股票，需 30s 超时
