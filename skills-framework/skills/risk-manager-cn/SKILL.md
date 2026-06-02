---
name: risk-manager-cn
description: 小红弹药库风控：止损检查/移动止盈/仓位合规/凯利公式/组合热度监控。对标 tradermonty 的 portfolio-manager + exposure-coach，适配A股风控规则。
mcp_servers: [risk, execution]
api_profile: basic
estimated_minutes: 5
---

# 风控管理（中国版）

## Overview

对标 tradermonty 风控体系，适配A股规则：

**核心参数**:
- R值: ¥6,927（净值×33.3%×1/8×凯利0.2）
- 单股上限: 33.3%
- 总持仓上限: 9只
- 止损: 技术面R系数止损
- 移动止盈: 涨20%启动，每涨10%上移10%

**A股特殊风控**:
- T+1无法当日止损 → 需设置次日开盘止损单
- 涨跌停板 → 极端行情可能无法成交
- 北向资金大额流出 → 预警信号

## When to Use

- 每日15:30收市后自动运行
- 盘中价格触及止损线附近
- 新建仓位前验证合规

## Workflow

### Step 1: 止损检查

```bash
python3 scripts/ammo_risk.py --update
```

调用 MCP: `check_stop_loss` → 返回触发/接近的止损

### Step 2: 移动止盈更新

对浮盈 ≥20% 的持仓自动上移止损位

### Step 3: 仓位合规

```
mcp: get_positions
mcp: check_position_limit --symbol <code> --price <price>
```

### Step 4: 凯利更新

当平仓交易增加时重新计算凯利值：
```
凯利 = (胜率×平均盈利 - 败率×平均亏损) / (平均盈利×平均亏损)
```

### Step 5: 输出风控报告

```
🛡️ 弹药库风控报告
净值: ¥898,698
R值: ¥6,927
止损状态: [触发0/接近1/正常X]
仓位合规: [超标0/正常X]
组合热度: [总风险占净值X%]
```

## Resources

- `references/risk_rules_cn.md`: A股风控规则完整说明
