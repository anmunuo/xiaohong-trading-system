---
name: post-market-review
description: 盘后17:00自动复盘。盈亏统计/持仓概览/交易纪律回顾/明日计划。对标 tradermonty 的 monthly-performance-review 的日频版本。
mcp_servers: [logging, execution]
api_profile: basic
estimated_minutes: 5
cron: "0 17 * * 1-5"
---

# 盘后复盘

## Overview

每个交易日17:00的文工团复盘报告。对标 tradermonty 的交易表现回顾体系。

**复盘四维度**:
- 盈亏统计: 今日/本周/累计
- 持仓概览: 现有持仓状态
- 纪律回顾: 是否遵守止损/仓位规则
- 明日计划: 关注标的/待执行操作

## When to Use

- 每个交易日17:00自动运行

## Workflow

### Step 1: 盈亏统计

```
mcp: get_trade_stats → 今日交易统计
mcp: get_recent_trades --limit 50 → 今日成交明细
```

### Step 2: 持仓概览

```
mcp: get_positions → 持仓+市值+浮盈
```

### Step 3: 纪律检查

对照规则检查：
- 是否有未执行的止损？
- 是否有超仓（>33.3%）？
- 是否有T+0违规？

### Step 4: 明日计划

- 关注瞭望塔评分决定明日仓位
- 标记接近止损/止盈的持仓
- 记录待研究标的

## Output

飞书推送 + `reports/daily/文工团复盘-YYYY-MM-DD.md`
