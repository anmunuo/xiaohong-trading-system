# 数据管线调试手册

> 宏观资金面数据三路同时缺失的标准化诊断流程。

## 快速诊断 (30s)

```bash
cd ~/.hermes/profiles/xiaohong/scripts

# 1. 市场快照整体健康
python3 -c "
from data_pipeline import get_north_flow, get_market_money_flow, get_sector_flow_rank
nf = get_north_flow()
mm = get_market_money_flow()
sf = get_sector_flow_rank('3')
print(f'北向: {nf[\"data_source\"]} date={nf.get(\"date\",\"?\")} net={nf[\"net_flow\"]}亿')
print(f'市场: {mm[\"data_source\"]} main={mm[\"main_net\"]}亿 retail={mm[\"retail_net\"]}亿')
print(f'板块: {len(sf)}条')
"

# 2. 重建快照
python3 market_snapshot.py
```

## 三层诊断法

### Layer 1: 检查缓存

数据可能被过期的缓存覆盖。绕过缓存：
```python
# 强制清空 data_pipeline 缓存
import sys
for mod in list(sys.modules.keys()):
    if 'data_pipeline' in mod:
        del sys.modules[mod]
from data_pipeline import get_north_flow
```

### Layer 2: 直调原始 API

```python
# AKShare
import akshare as ak
df = ak.stock_hsgt_fund_flow_summary_em()  # 北向资金
df = ak.stock_market_fund_flow()            # 市场资金流

# tushare
import tushare as ts
pro = ts.pro_api()
df = pro.moneyflow_hsgt(trade_date='20260602')  # 北向
df = pro.moneyflow(trade_date='20260601')        # 全市场汇总
df = pro.ths_daily(trade_date='20260601')        # 板块涨跌

# 东方财富 (绕过 akshare)
import requests
r = requests.get('https://push2.eastmoney.com/api/qt/clist/get',
    params={'pn':1,'pz':10,'fs':'m:90+t:3','fields':'f12,f14,f3,f62'},
    headers={'User-Agent':'Mozilla/5.0 ... Chrome/120...'})
```

### Layer 3: 回退链路验证

确认每个数据源的 fallback 是否生效：
- 北向: AKShare → tushare (日期新鲜度决胜负)
- 市场: AKShare → tushare moneyflow 汇总
- 板块: 东方财富(3次重试) → tushare ths_daily

## 常见故障模式

| 症状 | 根因 | 修复 |
|:--|:--|:--|
| 北向日期=7天前 | tushare `moneyflow_hsgt` 数据滞后，函数无新鲜度检查 | AKShare 优先，仅当日期≥yesterday 用 tushare |
| 市场主力=0 | `ak.stock_market_fund_flow()` RemoteDisconnected 被静默吞掉 | 新增 tushare `moneyflow` 5192只汇总回退 |
| 板块TOP5=空 | `_em_api_get` 无重试+UA 被拒 | 3次重试+退避+完整 UA+ths_daily 回退 |
| 一切正常但值全0 | 盘前/周末调用，市场未开盘 | 检查交易时段，T-1数据兜底 |
| 缓存导致用旧数据 | 缓存 TTL 内恰好 API 失败 | 诊断时绕过缓存直调 |

## 验证清单

- [ ] `get_north_flow()` 返回 data_source 非 'no_data'
- [ ] `get_market_money_flow()` 返回 main_net ≠ 0（或明确标注 T-1）
- [ ] `get_sector_flow_rank()` 返回 ≥5 条
- [ ] `market_snapshot.py` 运行无异常
- [ ] `market_snapshot.json` 三字段均非空/非0
- [ ] `data_hub.py --health` 全部 ✅
