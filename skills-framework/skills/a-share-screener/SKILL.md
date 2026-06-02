---
name: a-share-screener
description: 全市场多因子筛选（PE/PB/ROE/市值/动量/北向资金），输出 Top N 候选池 + 综合评分 + 行业分布。对标 tradermonty 的 canslim-screener + vcp-screener，适配A股全市场数据。
mcp_servers: [strategy, market-data]
api_profile: pro
estimated_minutes: 15
---

# A股多因子选股

## Overview

基于 Tushare 全A数据（5522只 → 清洗去ST/退市 → 3913有效），应用多因子模型筛选候选池。

### 筛选因子

| 因子 | 权重 | 说明 |
|------|:--:|------|
| 估值（PE/PB） | 30% | PE合理区间 + PB不极端 |
| 成长（ROE/营收增速） | 25% | ROE>10% + 营收正增长 |
| 质量（净利率/负债率） | 20% | 净利率>5% + 负债率<70% |
| 动量（20日涨幅） | 15% | 短期趋势强度 |
| 资金（北向持股变化） | 10% | 聪明钱认可度 |

### PE分布参考（2026-05-22 真实数据）
- 1%: 6.6 | 25%: 25.5 | 50%: 49.8 | 75%: 108.9

## When to Use

- 每周选股池更新
- 用户问"帮我选几只股票"
- 准备建仓但没有具体标的

## Workflow

### Step 1: 运行筛选脚本

```bash
python3 skills/a-share-screener/scripts/screener.py --top 30 --min-roe 10 --max-pe 50
```

### Step 2: 获取行业分布

```
mcp: get_sector_flow --top_n 10
```

对比筛选结果与热点板块的重合度。

### Step 3: Top 5 深度分析

对评分最高的5只逐只调用 `get_stock_quote` + `get_daily_bars`，检查：
- 技术面是否存在买入信号
- 近期有无利好事件（公告/研报）

### Step 4: 输出候选池

```
Top 30 候选池:
  1. 600xxx XX股份  综合82分  PE=15.2 ROE=18% 板块:新能源
  2. ...
  行业分布: 新能源(8) 半导体(6) 消费(5) ...
```

## Resources

- `references/factor_model.md`: 多因子模型参数说明
- `scripts/screener.py`: 筛选脚本（调用 data_pipeline + tushare 直调）
