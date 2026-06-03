# ETF 实战分析模板

基于 2026-06-03 对 515120（创新药ETF广发）的完整分析。

## 数据拉取命令（最小可复现）

```bash
cd ~/.hermes/profiles/xiaohong/scripts

python3 -c "
import os, json, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()
import tushare as ts
pro = ts.pro_api(os.environ['TUSHARE_TOKEN'])

# 1. ETF 基本信息
df = pro.fund_basic(ts_code='515120.SH', market='E')
print('BASIC:', df.iloc[0].to_dict())

# 2. ETF 日线 (3个月)
df2 = pro.fund_daily(ts_code='515120.SH', start_date='20260301', end_date='20260602')
print(f'DAILY COUNT: {len(df2)}')
print(f'HIGH: {max(df2.high)} LOW: {min(df2.low)} AVG: {round(df2.close.mean(),3)}')
print('LATEST:', df2.iloc[0][['trade_date','open','high','low','close','vol']].to_dict())

# 3. 持仓
df3 = pro.fund_portfolio(ts_code='515120.SH')
print('TOP HOLDINGS:', df3.head(8)[['symbol','mkv','stk_mkv_ratio']].to_dict('records'))

# 4. NAV 序列
df4 = pro.fund_nav(ts_code='515120.SH', start_date='20260520', end_date='20260602')
print('NAV:', df4[['nav_date','unit_nav']].to_dict('records'))
"
```

## 输出模板

```
一、产品画像（表格）
  - 全称/代码/类型/管理人/成立日/跟踪指数/费率/规模/最新净值

二、持仓分析（表格）
  - 前8大持仓：代码/名称/占比/所属
  - 行业覆盖总结（1句话）

三、技术面（ASCII K线图 + 表格）
  - 价格轨迹（YTD/3个月）
  - 关键位：YTD高/低、MA5/10/20/60、跌幅%
  - 均线多头/空头判断

四、板块逻辑（why 涨/跌）
  - 宏观因素：利率环境/政策/地缘
  - 行业因素：周期位置/业绩趋势/资金流向
  - ETF 特有：规模变化（净申购/赎回）

五、综合评分 + 终审
  - 风险等级（高/中/低）
  - 操作类型（定投/分批/一次性）
  - 关键观察位
  - 一句话结论
```

## 515120 案例总结

| 维度 | 发现 |
|:--|:--|
| 识别 | 5位代码→ETF，非个股 |
| 真名 | 创新药ETF广发（非股票名） |
| 逻辑 | 创新药板块低估 → 适合定投 → 等 0.554 支撑确认 |
| 与个股区别 | 不算 PE/PB/ROE，看指数趋势 + 资金流向 + 费率 |

## 持仓名称补全

ETF 的 `fund_portfolio` 只返回 `symbol`（如 '688235.SH'），需要用 `pro.stock_basic(ts_code=...)` 补全名称：

```python
symbols = df_portfolio['symbol'].tolist()
df_names = pro.stock_basic(ts_code=','.join(symbols[:20]), fields='ts_code,name')
name_map = df_names.set_index('ts_code')['name'].to_dict()
```
