# 技术指标 Python 计算模板

> 在 execute_code 中直接引用，输入 bars_sorted（从 data fetch JSON 解析的日线列表）。

## 数据准备

```python
import json
from hermes_tools import terminal

result = terminal("data fetch stock --symbol 600XXX --type daily --days 120", timeout=30)
data = json.loads(result["output"])
bars = data["providers_attempted"][0]["data"]
bars_sorted = sorted(bars, key=lambda x: x["trade_date"])

closes = [b["close"] for b in bars_sorted]
highs  = [b["high"] for b in bars_sorted]
lows   = [b["low"] for b in bars_sorted]
opens  = [b["open"] for b in bars_sorted]
vols   = [b["vol"] for b in bars_sorted]
dates  = [b["trade_date"] for b in bars_sorted]
n = len(closes)
```

## MA (简单移动平均)

```python
def ma(data, period):
    result = [None]*(period-1)
    for i in range(period-1, len(data)):
        result.append(sum(data[i-period+1:i+1])/period)
    return result

ma5, ma10, ma20, ma30, ma60 = ma(closes,5), ma(closes,10), ma(closes,20), ma(closes,30), ma(closes,60)
```

## EMA (指数移动平均)

```python
def ema(data, period):
    result = [data[0]]
    k = 2/(period+1)
    for i in range(1, len(data)):
        result.append(data[i]*k + result[-1]*(1-k))
    return result
```

## MACD

```python
ema12 = ema(closes, 12)
ema26 = ema(closes, 26)
dif = [e12 - e26 for e12, e26 in zip(ema12, ema26)]
dea = ema(dif, 9)
macd_hist = [2*(d - de) for d, de in zip(dif, dea)]
# 金叉: dif[-2] < dea[-2] and dif[-1] > dea[-1]
# 死叉: dif[-2] > dea[-2] and dif[-1] < dea[-1]
```

## RSI(14) — Wilder 平滑

```python
def rsi(data, period=14):
    result = [None]*period
    gains, losses = [], []
    for i in range(1, len(data)):
        diff = data[i] - data[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[:period])/period
    avg_loss = sum(losses[:period])/period
    rs = avg_gain/avg_loss if avg_loss else 100
    result.append(100 - 100/(1+rs))
    for i in range(period, len(gains)):
        avg_gain = (avg_gain*13 + gains[i])/14
        avg_loss = (avg_loss*13 + losses[i])/14
        rs = avg_gain/avg_loss if avg_loss else 100
        result.append(100 - 100/(1+rs))
    return result
```

## 布林带 (20,2)

```python
std20 = [None]*19
for i in range(19, n):
    window = closes[i-19:i+1]
    avg = sum(window)/20
    variance = sum((x-avg)**2 for x in window)/20
    std20.append(variance**0.5)

boll_mid = ma20
boll_upper = [m + 2*s if m and s else None for m, s in zip(boll_mid, std20)]
boll_lower = [m - 2*s if m and s else None for m, s in zip(boll_mid, std20)]
```

## 形态识别辅助

```python
# 阶段划分：按日期过滤
phase1 = [b for b in bars_sorted if "YYYYMMDD" <= b["trade_date"] <= "YYYYMMDD"]
phase1_vol_avg = sum(b["vol"] for b in phase1)/len(phase1)

# 涨停日识别
for b in bars_sorted:
    if b["pct_chg"] >= 9.9:
        print(f"涨停日: {b['trade_date']} 量{b['vol']:.0f}手")

# 前高/前低
before_break = [b for b in bars_sorted if b["trade_date"] < "关键日期"]
pre_high = max(b["high"] for b in before_break[-20:])

# 量比
vol_5avg = sum(vols[-6:-1])/5
vol_20avg = sum(vols[-21:-1])/20
vol_ratio_5 = vols[-1]/vol_5avg  # vs 5日均量
vol_ratio_20 = vols[-1]/vol_20avg  # vs 20日均量

# 回踩确认：缩量 + 不破关键支撑
is_shrink = vols[-1] < vols[-2] * 0.9  # 缩量
is_hold = lows[-1] > key_support  # 不破支撑
```

## 关键价位命名规范

- **R1**：近期最高点（第一阻力）
- **R2**：整数关口或前期筹码密集区
- **S1**：最近回踩低点
- **S2**：MA5 对应价
- **S3**：MA10 对应价
- **S4**：MA20 / 涨停日收盘价
- **S5**：前期平台顶/底
