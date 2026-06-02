# 瞭望塔 v5.0 · 盘前综合战略模型

位于 `~/.hermes/profiles/xiaohong/scripts/watchtower.py`。

## v4.0 → v5.0 升级要点

| 维度 | v4.0 | v5.0 |
|------|------|------|
| 报告定位 | 盘中/盘后市场分析 | **盘前 08:30 发送** = 前日复盘 + 隔夜外围 + 当日预判 |
| 外围市场 | 仅全球指数 | + A50 期货 |
| 新闻事件 | ❌ | ✅ 隔夜要闻（RSS+东方财富），按标签分类 |
| 选股推荐 | 仅板块分析 | **≥3 个热点板块 × 每板块 ≤3 只个股**，含选股逻辑 |
| 操作建议 | 固定策略 | 情景化：四档仓位 + 逐板块建议 |

## 五因子加权评分（同 v4）

```
总分 = Σ(因子得分 × 权重)  /  0-100
```

| 因子 | 权重 | 数据源 | 核心逻辑 |
|------|:--:|------|------|
| 隔夜美股 | 20% | Sina API | 纳指涨跌幅 ± 标普确认 |
| 北向资金 | 25% | Tushare Pro | 净流入金额分级 |
| 主力资金 | 20% | AKShare | 全市场主力净额 + 占比 |
| 市场热度 | 15% | AKShare 涨停池 | 涨停跌停比 + 高度板 |
| 上证技术 | 20% | **akshare** | 现价 vs MA20 偏离度 |

### ⚠️ MA20 数据源陷阱

**错误做法**：
```python
data fetch stock --symbol 000001 --category quote  # ← 返回平安银行(000001.SZ)！
```

**正确做法**：
```python
import akshare as ak
df = ak.stock_zh_index_daily(symbol='sh000001')  # ← 上证指数日线
closes = df['close'].tail(20).astype(float)
ma20 = closes.mean()
```

`data fetch CLI` 只支持个股代码，不支持指数。指数日线必须通过 akshare 获取。

## 评分分级

| 评分 | 情绪 | 仓位 | 策略 |
|:----:|------|:----:|------|
| ≥80 | 强势进攻 🔥🔥 | 7-9成 | 积极选股，顺势加仓 |
| ≥65 | 偏多 📈 | 5-7成 | 维持仓位，回调加仓 |
| ≥50 | 震荡 ⚖️ | 5-7成 | 精选龙头，高抛低吸 |
| ≥35 | 偏空 📉 | 3-5成 | 防御为主，回避高位 |
| <35 | 防御 🧊 | ≤3成 | 现金为王 |

## 板块选股引擎（v5.0 核心新增）

### 数据流

```
ak.stock_zt_pool_em() → zt_df (前日涨停池)
    ↓
按「所属行业」分组聚合
    ↓
综合评分 = 涨停数×3 + 连板高度×5 + 3板以上×3 + 资金验证 + 新闻催化×2
    ↓
Top 5 板块 → 每板块精选 3 只个股
```

### 个股精选三维度

| 类型 | 筛选规则 | 标签 |
|------|------|:--:|
| 龙头 | 连板最高 + 封板资金最大 | 👑 |
| 跟风 | 封板资金第二（资金确认） | 🥈 |
| 补涨 | 早盘首封 + 尚未充分炒作 | 🎯 |

### 新闻事件采集

```python
# 1. data fetch news (RSS — 宏观/科技)
data fetch news --category headlines

# 2. AKShare (东方财富 — A股个股)
ak.stock_news_em()
```

新闻自动按标签分类：AI/科技、新能源、电力、消费、医药、宏观、A股。

## 关键函数

- `fetch_news()` → {items: [{title, source, tag}], count}
- `fetch_limit_data()` → (zt_df, dt_df)
- `get_overnight_markets()` → {asia, us, europe, a50_futures, nasdaq_chg, sp500_chg}
- `calc_factor_scores(overnight, north, market_flow, zt_df, dt_df)` → (factors, total_score)
- `analyze_sectors_with_stocks(zt_df, dt_df, news_items, fund_flow_top, total_score)` → (top_sectors, key_news)
- `pick_sector_stocks(group_df, flow_info, fund_flow_top, zt_count)` → [{code, name, reason, type}]
- `get_trading_advice(total_score, top_sectors)` → {strategy, risk, sectors: [{action, note}]}
- `infer_sector_logic(industry, zt_count, lianban_max)` → str

## 报告结构（7 段式）

```
一、隔夜外围市场 — 美股三大指数 + DAX + A50期货
二、前日 A 股复盘 — 上证/恒生收盘 + 北向 + 主力 + 涨跌停
三、多因子评分   — 五因子表格 + 综合评分
四、隔夜要闻     — 分类新闻 6 条
五、热点板块推荐 — 3 板块 × 3 个股表格
六、操作建议     — 仓位 + 逐板块建议
七、页脚         — 数据来源 + 版本
```

## 输出格式

所有报告使用 `report_formatter.Report` 构建：
- cron no_agent → `report.markdown()` → stdout → 飞书投递
- 手动调试 → `report.card()` → Feishu 交互卡片 JSON
