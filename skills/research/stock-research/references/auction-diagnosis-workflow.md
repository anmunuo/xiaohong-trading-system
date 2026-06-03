# 竞价诊断工作流 (16:05 LLM Cron)

## 目标

每日 16:05（竞价学习器 16:00 完成后），读取权重数据 + 大盘环境 + 选股复盘，输出权重诊断和调整建议。

## 数据输入

| 文件 | 路径 |
|------|------|
| 竞价权重 | `scripts/data/auction_weights.json` |
| 竞价数据库 | `scripts/data/auction.db` (auction_frames 表) |
| 选股复盘日志 | `scripts/data/reflection_log.json`（可能不存在） |
| 大盘资金面 | `data_pipeline.get_market_money_flow()` |
| 全球指数 | `data_pipeline.get_index_data()` |
| 上一轮诊断 | `scripts/data/kb/auction_diagnosis.json` |

## auction.db 关键 Schema

| 列 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 自增主键 |
| `date` | TEXT | 交易日 YYYYMMDD |
| `code` | TEXT | 股票代码（纯数字） |
| `name` | TEXT | 股票名称（竞价初期为空，后期有值） |
| `seq` | INTEGER | 帧序号（从 1 开始，~3s/帧） |
| `price` | REAL | 虚拟匹配价 |
| `volume` | REAL | 虚拟匹配量（股） |
| `amount` | REAL | 虚拟匹配额 |
| `change_pct` | REAL | 涨跌幅（%） |
| `open_price` | REAL | 开盘价 |
| `prev_close` | REAL | 昨收价 |
| `recorded_at` | TEXT | ISO 时间戳 |

**注意**：同一 code 会出现两次——一次 name 为空（竞价初期~10 帧，volume=0），一次有名称（真实数据）。按 `name != ''` 过滤真实数据。

## 分析维度

### 1. 大盘环境判定

| 条件 | 判定 |
|------|------|
| 上证涨跌幅 > ±1.5% | trending |
| 上证涨跌幅 0.5-1.5%，振幅 > 1% | volatile |
| 上证涨跌幅 < 0.5%，振幅 < 0.8% | ranging (低波震荡) |
| 主力/散户方向一致 | 趋势确认 |
| 主力/散户方向相反（主力流出+散户接盘） | 震荡结构市 |

### 2. 五维权重分析

| 维度 | 震荡市有效性 | 趋势市有效性 | 注意 |
|------|:--:|:--:|------|
| price_slope | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 最稳定维度 |
| volume_accel | ⭐⭐ | ⭐⭐⭐⭐ | 依赖竞价放量股 |
| imbalance | ⭐ | ⭐⭐⭐ | 震荡市买卖盘无显著失衡 |
| premium | ⭐⭐⭐ | ⭐⭐⭐ | 高开/低开偏离区间的信号 |
| sector_dev | ⭐ | ⭐⭐⭐ | **需同板块≥2只标的**才有意义 |

### 3. 维度信号质量评估

学习器对各维度使用 60% 阈值：`dim_score >= dim_max * 0.6` 才触发信号。
触发后与日内实际涨跌比对，命中则 α+1，未命中则 β+1。
中性信号（weak/neutral）不参与学习。

**当前默认权重（冷启动）**：
```
price_slope:  0.25
volume_accel: 0.25
imbalance:    0.20
premium:      0.15
sector_dev:   0.15
```

### 4. sector_dev 局限性

竞价采集器默认标的池跨多个行业（如 TCL家电、东阿中药、海利得化纤……），**板块偏离维度在此配置下无意义**。改进方向：
- (a) 按行业分组采集（每组 ≥2 只）
- (b) 改用「个股相对大盘偏离」替代「同板块偏离」

## 输出格式

写入 `scripts/data/kb/auction_diagnosis.json`：

```json
{
  "timestamp": "ISO8601",
  "version": "1.1.1",
  "market_condition": "ranging",
  "market_context": {
    "shanghai": "4083.97 (+0.22%)",
    "hang_seng": "...",
    "north_flow": "...",
    "main_vs_retail": "...",
    "volatility": "low",
    "note": "1-2句大盘环境解读"
  },
  "data_status": {
    "total_samples": 5,
    "auction_frames_collected": 1527,
    "unique_codes": 8,
    "stage": "day1_with_data",
    "note": "采集器状态描述"
  },
  "weights_current": {
    "price_slope": {"weight": 0.29, "alpha": 2, "beta": 1, "accuracy": 0.67}
  },
  "accuracy_trend": {
    "price_slope": "improving — 1-2句趋势说明",
    "volume_accel": "no_signal — ..."
  },
  "individual_analysis": {
    "000100_TCL科技": {"auction_chg": "+5.19%", "day_chg": "+7.00%", "signal": "strong", "hit": true}
  },
  "diagnosis": "2-3句核心诊断",
  "recommendation": {
    "price_slope": 0.29,
    "volume_accel": 0.22,
    "imbalance": 0.18,
    "premium": 0.18,
    "sector_dev": 0.13
  },
  "reasoning": "为什么给出这个建议，关联大盘和近期表现",
  "watch_items": ["监控项列表"]
}
```

## 铁律

- **权重调整幅度单次不超过 ±0.10**
- **样本 < 10 时不要手动调整权重**——让贝叶斯自动迭代
- **sector_dev 在跨行业标的池中为无意义维度**，诊断时应标注
- **学习器日期 bug (v1.1.0)** 已修复为 v1.1.1——如果 cron 又空转，检查 `_get_latest_date_in_db()` 是否被覆盖

## 学习器日期 Bug 速查 (v1.1.0 → v1.1.1)

```
Bug: main() 无 --date 时取 yesterday=datetime.now()-timedelta(1)
     cron 16:00 → 当天(6/3)收盘后应学习当天竞价数据
     但代码查6/2 → auction.db有6/3数据被跳过

Fix: _get_latest_date_in_db() → SELECT MAX(date) FROM auction_frames
     自动适配跨日/周末，DB为空时回退到昨天

验证: python3 auction_learner.py --reset && python3 auction_learner.py
```

## 竞价采集器健康状态判定

| 状态 | 条件 | 行动 |
|------|------|------|
| up | auction_frames > 0 且 frames ≥ 100 | 正常 |
| degraded | frames > 0 但 < 100 | 关注 |
| down | frames = 0 | P0：排查 cron + API + 标的有效性 |
| cold_start | auction.db 空或首次有数据 | 接受默认权重，不调整 |
