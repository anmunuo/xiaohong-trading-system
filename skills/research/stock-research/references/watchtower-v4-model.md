# 瞭望塔 v4.0 · 多因子评分模型

位于 `~/.hermes/profiles/xiaohong/scripts/watchtower.py`。

## 五因子加权评分

```
总分 = Σ(因子得分 × 权重)
范围：0-100
```

| 因子 | 权重 | 数据源 | 核心逻辑 |
|------|:--:|------|------|
| 隔夜美股 | 20% | Sina API | 纳指涨跌幅 ± 标普确认 |
| 北向资金 | 25% | Tushare Pro | 净流入金额分级 |
| 主力资金 | 20% | AKShare | 全市场主力净额 + 占比 |
| 市场热度 | 15% | AKShare 涨停池 | 涨停跌停比 + 高度板 |
| 上证技术 | 20% | data fetch CLI | 现价 vs MA20 偏离度 |

## 评分分级

| 评分 | 情绪 | 策略 |
|:----:|------|------|
| ≥80 | 强势进攻 🔥🔥 | 高仓位 7-9 成，积极选股 |
| ≥65 | 偏多 📈 | 维持仓位 5-7 成，回调加仓 |
| ≥50 | 中性震荡 ⚖️ | 控制仓位，高抛低吸 |
| ≥35 | 偏空 📉 | 降至 3-5 成，回避高位 |
| <35 | 防御 🧊 | 轻仓/空仓，现金为王 |

## 热点板块分析

基于 `ak.stock_zt_pool_em()` 涨停池数据：

1. 按 `所属行业` 聚合涨停数
2. 识别连板龙头（`连板数` 字段）
3. 交叉验证 `get_sector_flow_rank()` 资金流向
4. 推断驱动逻辑（`infer_sector_logic()` 映射表覆盖 16 个行业）

## 关键函数

- `factor_us_overnight(us_data)` → (score, signal, detail)
- `factor_northbound(north)` → (score, signal, detail)
- `factor_main_flow(market_flow)` → (score, signal, detail)
- `factor_market_breadth()` → (score, signal, detail, zt_df, dt_df)
- `factor_shanghai_ma()` → (score, signal, detail)
- `assess_market(total_score)` → (label, color, strategy)
- `analyze_hot_sectors(zt_df, dt_df)` → [{industry, zt_count, leader, logic, ...}]
- `infer_sector_logic(industry, zt_count, lianban_max)` → str

## 注意事项

- 盘后非交易时段，主力资金/北向数据为上一交易日
- 涨停池日期格式 `YYYYMMDD`
- `stock_zh_a_spot_em()` 限流频繁，改用涨停池数据替代全A涨跌比
- MA20 通过 `data fetch stock --symbol 000001` 获取上证日线计算
