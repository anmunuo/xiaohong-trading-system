---
name: trade-journal-cn
description: 结构化交易日志系统。CSV+SQLite双写，支持买入/卖出记录、PnL自动计算、胜率统计、各标的业绩分析、CSV导出。对标 tradermonty 的 trader-memory-core + signal-postmortem。
mcp_servers: [logging]
api_profile: basic
estimated_minutes: 3
---

# 交易日志（中国版）

## Overview

对标 tradermonty 的 trader-memory-core 交易记忆系统。每笔交易自动记录到 CSV + SQLite，支持完整的统计分析。

**CSV 格式（对标 TradingSkill CSV logger）**:
```
Timestamp,Symbol,Side,Price,Quantity,Value,Fee,Strategy,SignalStrength,Confidence,StopLoss,TakeProfit,PnL,PnLPct,PortfolioValue,Reason
```

## When to Use

- 每笔交易执行后自动调用
- 盘后复盘查看统计
- 导出交易记录做深度分析

## Workflow

### Step 1: 记录交易

```bash
# 买入
python3 scripts/transaction_logger.py log \
  --symbol 600519 --side BUY --price 1800 --quantity 100 \
  --strategy MA-CROSS --confidence 85 --reason "金叉突破"

# 卖出（自动计算PnL）
python3 scripts/transaction_logger.py log \
  --symbol 600519 --side SELL --price 1900 --quantity 100 \
  --buy-price 1800 --reason "死叉离场"
```

### Step 2: 查看统计

```
mcp: get_trade_stats
→ {total_trades: 29, win_rate: 37.9%, total_pnl: 48698, profit_factor: 1.20}
```

### Step 3: 信号复盘

```
mcp: get_recent_trades --limit 20
```

分析最近交易：
- 哪些策略胜率最高？
- 哪些时段/标的亏损最多？
- 是否有重复的错误模式？

### Step 4: 导出分析

```bash
python3 scripts/transaction_logger.py export --symbol 300843 --output workspace/300843_trades.csv
```

## Output

交易统计表（与小程序统计页一致）:
```
总交易: 29笔  胜率: 37.9%  总盈亏: ¥48,698
平均盈利: ¥4,457  平均亏损: ¥3,721  盈亏比: 1.20
```

## Resources

- `references/trade_journal_best_practices.md`: 交易日志最佳实践
