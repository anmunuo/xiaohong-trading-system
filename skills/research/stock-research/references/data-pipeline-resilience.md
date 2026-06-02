# 数据管线韧性修复模式 (v8.3)

## 触发条件

- 多个宏观/资金面数据源同时返回空/过期/零值
- `market_snapshot.json` 中某字段 `data_source: no_data` 或日期过期
- 下游消费者（推荐引擎/瞭望塔/决策官）报告数据缺失

## 诊断流程（按顺序）

### Step 1: 逐路隔离测试

```bash
cd ~/.hermes/profiles/xiaohong/scripts
python3 -c "
import sys
for mod in list(sys.modules.keys()):
    if 'data_pipeline' in mod: del sys.modules[mod]
from data_pipeline import get_north_flow, get_market_money_flow, get_sector_flow_rank
print('北向:', get_north_flow()['data_source'], get_north_flow()['date'])
print('资金:', get_market_money_flow()['data_source'])
print('板块:', len(get_sector_flow_rank('3')), '条')
"
```

### Step 2: 绕过缓存直调原始 API

```bash
# 北向 — AKShare
python3 -c "import akshare as ak; df=ak.stock_hsgt_fund_flow_summary_em(); print(df[['交易日','资金方向','成交净买额']])"

# 市场资金 — AKShare (易被限流)
python3 -c "import akshare as ak; df=ak.stock_market_fund_flow(); print(df.iloc[-1] if not df.empty else 'EMPTY')"

# 板块资金 — 东方财富 API
python3 -c "import requests; r=requests.get('https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=3&fs=m:90+t:3&fields=f12,f14,f3', headers={'User-Agent':'Mozilla/5.0'}); print(r.status_code, len(r.text))"

# tushare 回退
python3 -c "from data_pipeline import _get_ts_pro; pro=_get_ts_pro(); df=pro.moneyflow(trade_date='20260601',limit=3); print(len(df),'rows' if not df.empty else 'EMPTY')"
```

### Step 3: 对比缓存时间戳

检查 `market_snapshot.json` 中的 `generated_at` 和各字段 `date`，确认是拉取失败还是缓存过期。

## 常见根因组合

| 症状 | 根因 | 修复 |
|:--|:--|:--|
| 北向日期 7 天前 | tushare `moneyflow_hsgt` 最近可查日期滞后，函数不检查新鲜度 | AKShare 优先（始终返回当日），tushare 回退 |
| 市场资金全 0 | `ak.stock_market_fund_flow()` 东方财富 `RemoteDisconnected`，异常被静默吞掉 | tushare `moneyflow` 全市场 5192 只汇总 |
| 板块流空数组 | 东方财富 `push2` API 拒绝默认 UA 连接，`_em_api_get` 无重试 | 3次重试+退避+完整 UA + tushare `ths_daily` 回退 |
| 三路同时挂 | 东方财富全系 API 限流 + tushare 返回过期数据 | 三个修复组合覆盖 |

## 修复模式

### 模式 1: 数据源优先级反转

主源返回过期但"成功"的数据时（不抛异常、不返回空），回退逻辑永不触发。

```python
# ❌ 旧: tushare 优先，成功返回 7 天前数据后 AKShare 永不触发
df = pro.moneyflow_hsgt(trade_date=today)
if not df.empty: return result  # 过期但非空

# ✅ 新: 双源采集，按日期新鲜度择优
akshare_data = _try_akshare()  # 始终返回当日
tushare_data = _try_tushare()  # 可能过期
if akshare_date >= yesterday: use_akshare else: use_tushare
```

### 模式 2: 聚合回退

单次 API 失败时，用更重量级但一定可用的 API 做全量汇总。

```python
# ❌ 旧: akshare 失败 → 全 0
# ✅ 新: akshare 失败 → tushare 5192 只全量汇总
df = pro.moneyflow(trade_date=yesterday)
main_net = (sum(buy_elg) + sum(buy_lg) - sum(sell_elg) - sum(sell_lg)) / 1e4
```

### 模式 3: API 加固

单次请求升级为重试+退避+完整 UA。

```python
# ✅ 3次重试，1s/2s 退避，完整 Chrome UA
for attempt in range(3):
    try:
        r = requests.get(url, params=params, timeout=15, headers={...})
        if r.status_code == 200: return r.json()
    except: time.sleep(1 + attempt)
```

## 验证清单

- [ ] `python3 market_snapshot.py` 所有字段非空
- [ ] 北向 `data_source` ≠ `no_data`，`date` ≥ 昨天
- [ ] 市场资金 `main_net` ≠ 0
- [ ] 板块流 `len ≥ 5`
- [ ] `python3 data_hub.py --health` 全部 healthy
