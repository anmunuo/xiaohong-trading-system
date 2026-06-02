# 多通道数据降级采集模式

## 模式概要

当单一数据源不可靠时，建立 3 级降级链：**主通道 → 备1 → 备2 → 失败标记**。每通道返回数据需含 `channel` 字段，采集结束时输出通道分布统计。

## 已落地实例

### 1. 竞价采集器 (auction_collector.py v1.2)

```
fetch_one(code)
  ├─ ① 东方财富 push2  — 竞价专属 (f43/f19/f20)  ⚠️ 曾被限流
  ├─ ② 腾讯 qt.gtimg.cn — 47+字段 + 五档盘口     ✅
  └─ ③ Sina hq.sinajs.cn — 竞价期虚拟匹配价实时更新 ✅
```

关键代码模式：
```python
_channel_stats = {'em': 0, 'tencent': 0, 'sina': 0, 'fail': 0}

def fetch_one(code):
    for fn in [fetch_one_em, fetch_one_tencent, fetch_one_sina]:
        result = fn(code)
        if result and result.get('price', 0) > 0:
            _channel_stats[result['channel']] += 1
            return result
    _channel_stats['fail'] += 1
    return None
```

### 2. 宏观资金面 (data_pipeline.py)

| 数据 | 主通道 | 备1 | 备2 |
|:--|:--|:--|:--|
| 北向资金 | AKShare hsgt | tushare moneyflow_hsgt | — |
| 市场资金流 | AKShare market_fund_flow | tushare moneyflow 全市场汇总 | — |
| 板块资金流 | 东方财富 push2 (3次重试) | tushare ths_daily | — |

### 3. 分时K线 (data_pipeline.py)

Sina `quotes.sina.cn` KLineData API — 目前单通道。如需备选可接腾讯分钟线或东方财富 hist_min_em。

## 腾讯行情 API (qt.gtimg.cn)

```
GET https://qt.gtimg.cn/q=sz000001,sh600519

响应格式: v_sz000001="51~名称~代码~现价~昨收~开盘~成交量~外盘~内盘~买一价~买一量~...~卖五量~~时间~涨跌额~涨跌幅~最高~最低~...~成交额~换手率~市盈率~..."

字段映射 (从0):
  0=市场码(51/1), 1=名称, 2=代码, 3=现价, 4=昨收, 5=开盘
  6=成交量(手), 7=外盘, 8=内盘
  9-18=买一~五 (价量交替), 19-28=卖一~五
  30=时间, 31=涨跌额, 32=涨跌幅, 33=最高, 34=最低
  36=成交额(万), 37=换手率, 38=市盈率
  43=涨停价, 44=跌停价, 46=量比, 48=总市值, 49=流通市值

注意:
- 开盘前显示的是竞价虚拟匹配价(非最终开盘价)
- 量单位是手(×100=股), 额单位是万(×10000=元)
- 双引号内内容用 ~ 分隔, 不能用 split('=') 解析
- 市场前缀: 6/9开头→sh, 其他→sz
```

## tushare stk_auction API

```python
pro = ts.pro_api()
df = pro.stk_auction(ts_code='000001.SZ', trade_date='20260601')
# 返回列: ts_code, trade_date, vol(竞价量), price(竞价价), amount(竞价额),
#         pre_close, turnover_rate, volume_ratio, float_share
```

限制: 每天每只股票只返回 1 行（日终汇总），不能做盘中轮询。适合盘后验证。

## Sina 分时K线 API

```
GET https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData
  ?symbol=sz000001&scale=5&ma=no&datalen=48

参数:
  symbol: sz000001 / sh600519 (市场前缀+纯数字代码)
  scale: 1/5/15/30/60 (分钟)
  datalen: 返回K线数 (最大约240)

响应: JSONP格式 → 正则提取 JSON
字段: day(时间), open, high, low, close, volume(股), amount(元)
```

## 设计原则

1. **渐进降级**: 先试最快/最准的，失败再试备选
2. **通道统计**: 每次采集记录 `channel` 字段，结束输出分布
3. **独立请求**: 每个通道独立 try/except，不互相污染
4. **价格 > 0 校验**: 空数据或价格为 0 视为通道失败
5. **单票间隔**: 批量采集时 ≥150ms 间隔防限流
