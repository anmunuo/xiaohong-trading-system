# BaoStock 集成文档

> 小红交易系统 v8.5 — BaoStock 作为 K 线快路径接入 `_prefetch_indicators`，ProcessPool 并行化

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

### 4. ⚠️ 登录态管理 + 并发限制

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
- **ThreadPoolExecutor 不可用**：baostock 底层共享全局 HTTP session，多线程并发导致 utf-8 解码乱码 + 数据交叉读取。现象：`'utf-8' codec can't decode byte 0x8a`、`Error -3 while decompressing data`

### 5. ⚠️ ProcessPoolExecutor 并行化（v8.5）

```python
# ✅ 正确：ProcessPoolExecutor + 模块级 worker
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing

def _baostock_batch_worker(args):
    """模块级函数（非闭包，可 pickle）"""
    batch_codes, start_d, end_d, day_limit = args
    import baostock as bs
    batch_results = {}
    lg = bs.login()
    if lg.error_code == '0':
        for code in batch_codes:
            # ... 查询 + 自算 MA ...
        bs.logout()
    return batch_results

# 分批：每进程 ~50 只，最多 8 进程
batch_size = max(50, len(codes) // multiprocessing.cpu_count())
batches = [codes[i:i+batch_size] for i in range(0, len(codes), batch_size)]
tasks = [(b, start_date, end_date, days) for b in batches]

with ProcessPoolExecutor(max_workers=min(8, len(batches))) as ex:
    futures = {ex.submit(_baostock_batch_worker, t): t for t in tasks}
    for fut in as_completed(futures):
        results.update(fut.result())
```

**为什么不用 ThreadPool？** baostock 非线程安全。ThreadPool 尝试过（40 workers → 乱码 → 15 workers → 仍乱码），根源是 `bs.login()` 设置的全局 HTTP session 被多线程交叉读取响应数据。

**为什么不用闭包？** `ProcessPoolExecutor` 需要 pickle worker 函数。`def _worker()...` 嵌套在函数内部时 `Can't pickle local object`。必须提到模块级。

**worker 数**：8 进程已验证安全，更高的并发可能导致服务端拒绝。batch 大小 ~50 只/进程，每进程独立 `login()` → 查询 → `logout()`。

| 并发方案 | 结果 | 原因 |
|:--|:--|:--|
| 串行 for 循环 | 528码 87.8s | 原始实现，稳定但慢 |
| ThreadPoolExecutor 40w | 乱码海 + 超时 | 共享全局 HTTP session |
| ThreadPoolExecutor 15w | 仍有乱码 | 同上 |
| ProcessPoolExecutor + 闭包 | pickle 失败 | 不能序列化局部函数 |
| **ProcessPoolExecutor 8w + 模块级函数** | **528码 10.8s ✅** | 进程隔离 + 可 pickle |

---

## 推荐引擎集成（v8.5）

### 数据流

```
_prefetch_indicators(codes)
  ├─ BaoStock get_historical_k_with_ma()  ← ProcessPool 8procs (v8.5)
  │   └─ _baostock_batch_worker(args)     ← 模块级，每进程独立 login/logout
  ├─ subprocess data fetch CLI            ← fallback（仅补漏 ~15% 代码）
  └─ tushare daily_basic PE/PB/市值       ← ThreadPool 10procs (v8.5)
      └─ _fetch_fundamental()             ← 独立 pro_api 实例/线程
```

### 性能对比

| 场景 | 旧方案 (串行) | v8.5 (ProcessPool) |
|:--|:--|:--|
| 528 只 | 87.8s | **10.8s** |
| 200 只 | ~34s | ~4s |
| 提速比 | — | **~8x** |

### tushare 并行化（v8.5）

`stock_recommender.py` `_prefetch_indicators()` 中 tushare `daily_basic` 查询也并行化：

```python
def _fetch_fundamental(code):
    """独立 pro_api 实例（ThreadPool 安全）"""
    _pro = ts.pro_api(token)  # 每线程独立
    df = _pro.daily_basic(ts_code=..., ...)
    return (code, {...})

with ThreadPoolExecutor(max_workers=10) as ex:
    futures = {ex.submit(_fetch_fundamental, c): c for c in codes}
    ...
```

- 10 workers（保守，避免触发 tushare 限流）
- 每线程独立 `ts.pro_api(token)` 实例 → 无 session 共享问题

---

## 其他可用 API（待接入）

| API | 用途 | 接入点 |
|:--|:--|:--|
| `query_growth_data` | YOY增速 | `get_financial_indicator` 互补 |
| `query_balance_data` | 负债率/流动比率 | `get_financial_summary` 评分因子 |
| `query_stock_industry` | 行业分类 | `_guess_sector` 替代关键词匹配 |
| `query_all_stock` | 全A股列表 | `_get_candidates` 兜底候选源 |
| `query_hs300_stocks` | 大盘股判定 | `_apply_filters` 市值过滤辅助 |
