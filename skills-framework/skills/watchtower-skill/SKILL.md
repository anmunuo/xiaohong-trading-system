---
name: watchtower-skill
description: 每日盘前瞭望塔晨报（08:45自动执行）。合并版：结构化七段数据（全球指数/北向/板块热点/五因子评分/事件驱动矩阵/操作建议）+ LLM AI深度研判。由原瞭望塔(no_agent)和每日晨报(LLM)合并而来，一份报告覆盖全部盘前需求。
mcp_servers: [market-data, strategy]
api_profile: pro
estimated_minutes: 5
cron: "45 8 * * 1-5"
mode: LLM-driven
---

# 瞭望塔晨报（合并版）

## Overview

小红系统最核心的盘前报告，由原 `🔭 瞭望塔 v6.0`（no_agent 脚本，08:30）和 `🌅 每日晨报`（LLM 驱动，08:45）合并而来。

**合并前**: 两份报告 → 内容重叠 4/6 段 → 飞书两条消息
**合并后**: 一份报告 → 结构化数据 + AI 研判 → 飞书一条消息

## When to Use

- 每个交易日 08:45 自动运行
- 手动触发: `cd scripts && TQDM_DISABLE=1 python3 watchtower.py`

## Workflow

### Step 1: 隔夜外围

```
mcp: get_index_data → 美股三大指数/DAX/A50期货
```

### Step 2: 前日A股复盘

北向资金 + 主力资金 + 涨跌停统计 + 上证MA20偏离

### Step 3: 五因子评分

| 因子 | 权重 | 数据源 |
|------|:--:|------|
| 隔夜美股 | 20% | get_index_data |
| 北向资金 | 25% | get_north_flow |
| 主力资金 | 20% | get_market_money_flow |
| 市场热度 | 15% | 涨停/跌停比 |
| 上证技术 | 20% | MA20偏离 |

### Step 4: 事件驱动矩阵

四维交叉验证选股（v6.0核心）:
- 事件催化(30%) + 资金流向(25%) + 涨停动量(20%) + 研报共识(15%) + 多样性(10%)

### Step 5: 输出操作建议

```
评分≥65 → 积极进攻·7-9成仓位
评分50-64 → 震荡操作·5-7成
评分35-49 → 防御为主·3-5成
评分<35 → 轻仓观望·≤3成
```

## Output

飞书推送 + `reports/daily/瞭望塔-YYYY-MM-DD.md`

## Resources

- `references/watchtower-v6-model.md`: v6.0多维交叉验证模型详解
