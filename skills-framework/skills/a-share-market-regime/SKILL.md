---
name: a-share-market-regime
description: 分析A股市场宽度、上升趋势参与度、板块轮动和北向资金流向，输出市场姿态（偏多/震荡/偏空）和净敞口建议。对标 tradermonty 的 market-breadth-analyzer + uptrend-analyzer + exposure-coach，适配中国A股市场特征。
mcp_servers: [market-data]
api_profile: basic
estimated_minutes: 10
---

# A股市场体制分析

## Overview

每日盘前/盘中量化A股市场整体健康度，输出一个简单的三态判断：**偏多（积极参与）/ 震荡（控制仓位）/ 偏空（防御为主）**。

核心指标（对标美股市场宽度分析，适配A股特征）：
- **指数MA20偏离**：上证/深证/创业板 vs MA20
- **涨跌家数比**：涨停/跌停比 + 上涨/下跌家数比
- **北向资金**：连续流入/流出趋势
- **板块轮动**：热点板块集中度 + 持续性
- **成交量**：两市成交额 vs 20日均量

## When to Use

- 每日盘前（08:30）评估是否可以积极交易
- 盘中市场出现剧烈波动时重新评估
- 持仓超过5只时需要确认市场环境
- 用户问"今天大盘怎么样"

## Prerequisites

- Tushare Token 已配置
- 数据管线正常运行

## Workflow

### Step 1: 获取指数数据

调用 MCP 工具获取全球指数和A股主要指数：

```
mcp: get_index_data → {asia: {shanghai, shenzhen, chinext, hang_seng}}
```

### Step 2: 获取北向资金

```
mcp: get_north_flow → {net_flow, status, consecutive_days}
```

### Step 3: 获取板块资金排名

```
mcp: get_sector_flow --top_n 10
```

分析板块轮动信号：
- 是否有3个以上板块同时净流入 → 市场有主线
- 板块轮动速度快（日换）→ 震荡市
- 防御板块（银行/公用事业）领涨 → 偏空

### Step 4: 涨跌停分析

运行脚本获取涨停/跌停数据：

```bash
python3 skills/a-share-market-regime/scripts/market_breadth.py
```

### Step 5: 综合评分

参考 `references/market_regime_scoring.md` 的评分模型：

```
指数技术(30%) + 涨跌比(25%) + 北向(20%) + 板块(15%) + 成交量(10%) = 总分
≥65 → 偏多 📈
50-64 → 震荡 ⚖️
35-49 → 偏空 📉
<35 → 防御 🧊
```

### Step 6: 输出决策

```
市场姿态: [偏多/震荡/偏空]
建议净敞口: [7-9成 / 5-7成 / 3-5成 / ≤3成]
关键信号:
  - 北向连续X日净流入/流出
  - 涨停Y只 vs 跌停Z只
  - 领涨板块: [...]
风险提示: [...]
```

## Output

报告保存到 `reports/daily/market-regime-YYYY-MM-DD.md`

## Resources

- `references/market_regime_scoring.md`: 五因子评分模型详解
- `scripts/market_breadth.py`: 市场宽度计算脚本
