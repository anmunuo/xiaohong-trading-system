---
name: decision-officer
description: 14:30盘中综合决策。读取今日瞭望塔/侦察兵/狙击手报告，运行风控+信号分析，生成买入/卖出/持有建议 + P0/P1/P2行动项。小红的LLM驱动决策核心。
mcp_servers: [strategy, risk, execution, logging]
api_profile: pro
estimated_minutes: 10
cron: "30 14 * * 1-5"
dependencies: [risk-manager-cn, position-sizer-cn, watchtower-skill]
---

# 决策官·盘中决策

## Overview

小红系统唯一的LLM驱动Cron任务。对标 tradermonty 的 swing-opportunity-daily + core-portfolio-weekly 的组合决策能力。

**决策逻辑链**:
```
当日报告(瞭望塔/侦察兵/狙击手) → 风控分析 → 策略信号 → 综合研判 → 行动建议
```

## When to Use

- 每个交易日14:30自动运行
- 需要综合交易决策时手动调用

## Workflow

### Step 1: 收集当日数据

读取 `reports/daily/` 中今日的：
- 瞭望塔报告（市场环境）
- 侦察兵报告（资金选股）
- 狙击手报告（持仓监控）

### Step 2: 运行风控分析

```bash
python3 scripts/strategy_bridge.py risk
python3 scripts/strategy_bridge.py signal
```

### Step 3: 综合研判

结合大盘评分 + 持仓状态 + 策略信号：

```
大盘评分 ≥65 + 持仓正常 → 可加仓
大盘评分 <35 + 止损触发 → 立即减仓
策略发出卖出信号 + 浮盈>20% → 移动止盈
```

### Step 4: 生成决策报告

使用 `report_formatter.Report` 生成美化版报告：

```
🌹 决策官·盘中决策

净值: ¥898,698 | 浮亏: ¥0 | 告警: 0条

行动建议:
  🔴 600481 双良节能 → 立即卖出 (4批次已触发止损) [P0]
  🟡 300131 英唐智控 → 减仓 (仓位42.9%超33.3%) [P1]
  🔵 无新买入信号 [P2]
```

### Step 5: 推送飞书

自动投递到飞书群。

## Output

飞书推送 + `reports/daily/决策官-YYYY-MM-DD.md`

## Resources

- `references/decision-framework.md`: 决策框架完整说明
