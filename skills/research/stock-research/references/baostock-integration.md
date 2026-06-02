# BaoStock 集成文档

> 小红交易系统 v8.4 — BaoStock 作为 K 线快路径接入 `_prefetch_indicators`

---

## 能力矩阵

| 函数 | 用途 | 速度 | 替代对象 |
|:--|:--|:--|:--|
| `query_history_k_data_plus` | 历史日K + peTTM/pbMRQ/turn | ~0.1s/只 | data fetch CLI subprocess (~5s/只) |
| `query_stock_basic` | 全A股列表+行业 | ~0.5s | tushare `stock_basic` |
| `query_growth_data` | 营收/利润/EPS YOY增速 | ~0.2s | tushare `fina_indicator`（互补） |
| `query_balance_data` | 流动比率/速动比率/负债率 | ~0.2s | 无现成对应 |
| `query_profit_data` | 利润表（净利润/营收） | ~0.2s | tushare |
| `query_hs300/zz500_stocks` | 指数成分股 | ~0.1s | 无现成对应 |

---

## 关键陷阱

### 1. `rs.next()` 阻塞 → 必须用 `rs.data`

```python
# 错误 — rs.next() 在生产环境阻塞 60s+
while rs.next():
    row = rs.get_row_data()

# 正确 — rs.data 是 list of lists，直接读取
for row in rs.data:
    # row[0] = date, row[1] = open, ... 按 fields 参数顺序
    pass
```

### 2. MA 指标字段不支持

BaoStock `query_history_k_data_plus` **不支持** `ma5/ma10/ma20` 作为 fields 参数，传入报错：
```
error_code: 10004012
error_msg: 日线指标参数传入错误:ma5
```

**解法**：拉 close 列表后自算 SMA。

### 3. 字段索引映射

`fields` 参数顺序决定 `rs.data` 行内索引。推荐字段组合：

| 索引 | 字段 | 类型 |
|:--:|:--|:--|
| 0 | date | str `YYYY-MM-DD` |
| 1 | open | float |
| 2 | high | float |
| 3 | low | float |
| 4 | close | float |
| 5 | volume | float (股) |
| 6 | amount | float (元) |
| 7 | turn | float (换手率%) |
| 8 | peTTM | float |
| 9 | pbMRQ | float |

### 4. 登录态管理

```python
import baostock as bs

lg = bs.login()
if lg.error_code != '0':
    return

# ... 逐只查询 ...

bs.logout()  # 必须调用，否则连接泄漏
```

- 免 API Key，免注册
- `login()` / `logout()` 成对调用
- **不要在 ThreadPool 内并行调用**（登录态不共享）

---

## 推荐引擎集成（v8.4）

### 数据流

```
_prefetch_indicators(codes)
  ├─ BaoStock get_historical_k_with_ma()  ← 快路径
  ├─ subprocess data fetch CLI            ← fallback
  └─ tushare daily_basic PE/PB/市值        ← 不变
```

### 性能对比

| 场景 | 旧方案 (subprocess) | 新方案 (BaoStock) |
|:--|:--|:--|
| 8 只 | ~40s | 3.3s |
| 50 只 | ~94s | ~12s |
| 提速比 | — | **~12x** |

---

## 其他可用 API（待接入）

| API | 用途 | 接入点 |
|:--|:--|:--|
| `query_growth_data` | YOY增速 | `get_financial_indicator` 互补 |
| `query_balance_data` | 负债率/流动比率 | `get_financial_summary` 评分因子 |
| `query_stock_industry` | 行业分类 | `_guess_sector` 替代关键词匹配 |
| `query_all_stock` | 全A股列表 | `_get_candidates` 兜底候选源 |
| `query_hs300_stocks` | 大盘股判定 | `_apply_filters` 市值过滤辅助 |
