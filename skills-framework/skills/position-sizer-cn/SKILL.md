---
name: position-sizer-cn
description: 计算A股交易的R值仓位。支持固定分数/ATR/凯利三种方法，自动适配A股规则（T+1/涨跌停板/最低1手=100股/单股≤33.3%/印花税千一）。对标 tradermonty 的 position-sizer。
mcp_servers: [risk]
api_profile: basic
estimated_minutes: 3
---

# 仓位计算（中国版）

## Overview

对标 tradermonty 的 position-sizer，适配A股规则：

- **固定分数法**：风险账户净值固定百分比（默认1%）
- **ATR法**：用平均真实波幅设定止损距离
- **凯利法**：从历史胜率/盈亏比计算最优仓位（使用半凯利保守值0.2）

**A股特殊规则**:
- 最低交易单位: 100股（1手），必须整百取整
- T+1: 当日买入不可卖出
- 涨跌停: ±10%（主板）/ ±20%（科创创业）
- 印花税: 卖出千一，买入免
- 单股仓位上限: 33.3%（系统铁律）

## When to Use

- 收到买入信号后计算具体买多少股
- 用户问"这个价位买多少合适"
- 调整持仓比例

## Workflow

### Step 1: 收集参数

```bash
# 固定分数（最常用）
python3 skills/position-sizer-cn/scripts/sizer.py \
  --account-size 898698 \
  --entry 50.0 \
  --stop 47.5 \
  --risk-pct 1.0 \
  --market A

# ATR法
python3 skills/position-sizer-cn/scripts/sizer.py \
  --account-size 898698 \
  --entry 50.0 \
  --atr 1.80 \
  --atr-mult 2.0 \
  --market A
```

### Step 2: R值计算

```
R值 = 净值 × 凯利分数 ÷ 8
    = 898,698 × 0.125 ÷ 8
    = 6,927

股数 = R值 ÷ (买入价 × 100) × 100
     = 6,927 ÷ 5,000 × 100
     = 100 股（取整到百）
```

### Step 3: 约束检查

- 仓位占比 ≤ 33.3%
- 总持仓 ≤ 9只
- 可用资金足够

### Step 4: 输出建议

```json
{
  "method": "fixed_fractional",
  "recommended_shares": 100,
  "position_value": 5000.00,
  "dollar_risk": 250.00,
  "risk_pct": 0.028,
  "r_value": 6927,
  "binding_constraint": "R值（最紧约束）"
}
```

## Resources

- `references/sizing_methods_cn.md`: 三种方法详解 + A股规则适配
- `scripts/sizer.py`: 仓位计算脚本
