# SQLite 本地股票知识库 (stock_kb.py) 设计文档

## 定位

位于 `~/.hermes/profiles/xiaohong/scripts/stock_kb.py`，本地 SQLite 数据库，将全 A 股历史数据（行情/财务/资金/事件）爬取到本地，支持毫秒级查询，替代每次分析时临时调用远程 API。

## 数据源

| 数据类型 | 主数据源 | 备用 |
|----------|----------|------|
| 股票列表 | akshare `stock_info_sh/sz/bj_name_code` | tushare `stock_basic` |
| 日K线 | baostock `query_history_k_data_plus` | — |
| 财务指标 | akshare `stock_financial_analysis_indicator` | tushare `fina_indicator` |
| 资金流向 | akshare `stock_individual_fund_flow` | — |
| 指数日线 | baostock | — |
| 公司公告 | akshare `stock_notice_report(symbol='全部')` | — |
| 个股新闻 | akshare `stock_news_em` | — |

## 数据库规格

- **引擎**：SQLite 3 (WAL 模式, synchronous=NORMAL)
- **缓存**：cache_size=-65536 (64MB)
- **数据库文件**：`scripts/data/stock_kb.db`
- **读取模式**：`file:path?mode=ro` URI (StockKBQuery 只读)

## 表结构 (6 表)

### stocks (全A主表)
| 字段 | 类型 | 说明 |
|------|------|------|
| code | TEXT PK | 纯数字 000001 |
| ts_code | TEXT UNIQUE | tushare格式 000001.SZ |
| name | TEXT | 名称 |
| market | TEXT | SH/SZ/BJ |
| industry | TEXT | 申万行业 |
| list_date | TEXT | 上市日期 YYYYMMDD |
| total_mv | REAL | 总市值(亿) |
| circ_mv | REAL | 流通市值(亿) |
| is_active | INTEGER | 是否正常交易 |

### daily_kline (日K线)
| 字段 | 类型 | 说明 |
|------|------|------|
| code | TEXT PK | 股票代码 |
| trade_date | TEXT PK | YYYY-MM-DD |
| open/high/low/close/pre_close | REAL | OHLCV |
| change_pct | REAL | 涨跌幅 |
| volume | REAL | 成交量(手) |
| amount | REAL | 成交额(万元) |
| turnover | REAL | 换手率 |
| pe_ttm | REAL | 滚动市盈率 |
| pb_mrq | REAL | 市净率 |
| ma5/ma10/ma20 | REAL | 均线(爬取后计算) |

### financials (财务指标, 季频)
| 字段 | 类型 |
|------|------|
| code + end_date | PK |
| roe/roa/gross_margin/net_margin | REAL |
| eps/bps/debt_ratio/current_ratio | REAL |
| revenue_yoy/profit_yoy/ocf_per_share | REAL |

### fund_flow (资金流向, 日频)
| 字段 | 说明 |
|------|------|
| main_net | 主力净流入(万元) |
| super_large_net/large_net/mid_net/small_net | 分类净流入 |

### index_daily (指数日线)
5 大指数：sh000001(上证) / sz399001(深证) / sz399006(创业板) / sh000300(沪深300) / sh000688(科创50)

### stock_events (个股事件, v1.1)
| 字段 | 说明 |
|------|------|
| code + event_date + title | UNIQUE 约束 |
| content | 内容摘要(截断500字) |
| source | 来源 |
| event_type | announcement/news/research/rumor/policy/insider |
| url | 原文链接 |
| keywords | 关键词(逗号分隔) |
| impact | 影响评级: +2大利好/+1利好/0中性/-1利空/-2大利空 |

## 查询 API

### StockKBQuery (只读查询)

```python
from stock_kb import StockKBQuery
q = StockKBQuery('data/stock_kb.db')

# 基本信息
q.get_stock_info(code)          # 股票基本信息
q.get_kline(code, start, end)   # 日K线
q.get_latest_price(code)         # 最新行情
q.get_financials(code, limit)   # 财务数据
q.get_fund_flow(code, limit)    # 资金流向
q.get_index(index_code, limit)  # 指数日线

# 事件查询 (v1.1)
q.get_events(code=None, event_type=None, days=30, limit=50, min_impact=None)
q.get_event_summary(code, days=90)

# 筛选和统计
q.screen_stocks(conditions)     # 条件筛选 (ROE/PE/市值/行业等)
q.get_top_gainers(date, limit)  # 涨幅榜
q.get_market_snapshot(date)     # 全市场快照
q.get_stats()                   # 数据库统计
```

## CLI 用法

```bash
# 初始化
python3 stock_kb.py --init                    # 全量 (定价+日K+财务+事件+指数) ~40min
python3 stock_kb.py --init-fast               # 快速 (列表+1年K线+指数) ~3min

# 更新
python3 stock_kb.py --update                  # 增量最近7天

# 查询
python3 stock_kb.py --query 600519                                  # 单票详情
python3 stock_kb.py --query "ROE>15 PE<20" --query-type screen      # 条件筛选
python3 stock_kb.py --query-type top --limit 20                     # 涨幅榜
python3 stock_kb.py --query 600519 --query-type events --limit 20   # 个股事件
python3 stock_kb.py --query 600519 --query-type event_summary       # 事件画像
python3 stock_kb.py --query-type snapshot                           # 市场快照
python3 stock_kb.py --stats                                         # 数据库统计
```

## 爬取耗时

| 数据类型 | 数量 | 耗时 |
|----------|------|:--:|
| 股票列表 | 4,915只 | ~10s |
| 日K线(2020至今) | ~1,000条/只 | ~40min (逐只) |
| 财务指标(5年) | ~20期/只 | ~30min (逐只) |
| 事件(30天公告+200只新闻) | ~8,000条 | ~5min |
| 5大指数 | ~8年/指数 | ~3s |
| **全量总计** | — | **~75min** |

## 关键陷阱

### Baostock 日期格式必须是 YYYY-MM-DD
`bs.query_history_k_data_plus()` 的 `start_date`/`end_date` **只接受** `YYYY-MM-DD`。传入 `YYYYMMDD` 不报错但返回 `error_msg='日期格式不正确'` 且 data 为空。所有调用点必须转换格式。

### INSERT OR REPLACE 列值数必须一致
SQLite 的 `INSERT OR REPLACE INTO t(c1,...,cN) VALUES (?,...,?)` 要求 `?` 数量与列名数量完全一致，否则报 `X values for Y columns`。在 `try/except: continue` 中被静默吞掉。建议用命名参数 `VALUES (:c1, :c2, ...)` 而非位置 `?`。

### baostock 非线程安全
底层全局 HTTP session → ThreadPool 并发导致 utf-8 乱码。多进程需每进程独立 login/logout（ProcessPoolExecutor）。

### akshare `stock_notice_report` 默认参数陷阱
无参调用返回 2022 年历史数据。必须传 `date='YYYYMMDD'`。

### akshare `stock_news_em` 内容截断
`新闻内容` 字段可能很长。`stock_kb.py` 截断到 500 字。全量内容需点击 `新闻链接`。
