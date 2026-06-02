---
name: historical-risk
plugin: wealth-management
subdomain: risk-measurement
description: 计算和分析历史风险指标：标准差、Beta、夏普比率、Sortino比率、最大回撤、Calmar比率、VaR、CVaR。对标 JoelLewis/finance_skills → wealth-management/risk-measurement/historical-risk，适配A股市场数据。
depends_on: [core.return-calculations, core.statistics-fundamentals]
has_python: true
---

# 历史风险指标计算

## Purpose

从历史收益率序列计算完整的风险指标体系。涵盖：
- **波动率**: 年化标准差
- **系统性风险**: Beta（相对基准）
- **风险调整收益**: 夏普比率 / Sortino 比率 / Calmar 比率
- **尾部风险**: 历史 VaR / CVaR（95%/99%置信度）
- **回撤**: 最大回撤 / 回撤持续期

## When to Use

- 评估持仓或策略的历史风险特征
- 对比不同策略的风险调整后收益
- 计算持仓的 Beta 以便对冲
- 回测后生成风险评估报告
- 用户问"这个策略风险多大"

## Core Concepts

### 年化公式

```
年化收益率 = (1 + 总收益率)^(252/n) - 1
年化波动率 = 日波动率 × √252
夏普比率 = (年化收益 - 无风险利率) / 年化波动率
Sortino = (年化收益 - 无风险利率) / 下行波动率
```

### 最大回撤

```
回撤(t) = (峰值(t) - 净值(t)) / 峰值(t)
最大回撤 = max(回撤(t))
Calmar = 年化收益 / 最大回撤
```

### VaR / CVaR

```
历史VaR(95%) = 收益率分布的第5百分位数
CVaR(95%) = 低于VaR的所有收益率的均值
```

## Workflow

### Step 1: 准备数据

需要日收益率序列（百分比或小数形式）。从 `return-calculations` 技能获取。

### Step 2: 运行脚本

```bash
python3 plugins/wealth-management/skills/historical-risk/scripts/historical_risk.py \
  --returns "0.01,-0.02,0.015,..." \
  --benchmark "0.005,-0.01,0.01,..." \
  --risk-free 0.03 \
  --output reports/historical_risk.json
```

### Step 3: 解读输出

```
核心风险指标:
  年化收益: 15.2%
  年化波动: 22.5%
  夏普比率: 0.54
  Sortino:  0.82
  最大回撤: -18.3%
  Calmar:   0.83
  Beta:     1.15
  VaR(95%): -2.8%
  CVaR(95%): -4.1%
```

## Common Pitfalls

1. **收益率序列必须等频**（日频→年化用√252，周频→用√52）
2. **Beta 需要基准序列**（A股建议用沪深300）
3. **少于 60 个数据点的统计不可靠**（至少需要1个季度日数据）
4. **VaR 假设历史重演**，极端行情下可能低估

## Cross-References

- `core.return-calculations`: 收益率计算
- `wealth-management.performance-metrics`: Alpha/信息比率/Treynor
- `wealth-management.forward-risk`: 前瞻性VaR/蒙特卡洛
- `wealth-management.volatility-modeling`: GARCH波动率建模
