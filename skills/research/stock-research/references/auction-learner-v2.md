# 竞价学习器 v2.0 · 做多导向

> 2026-06-04 · 从 v1.1.1 升级

## 核心问题

v1.x 目标函数：`caution + actual<0 → hit +α`。下跌市中永远猜跌得高分，但对只做多的交易系统毫无价值——竞价跌→收盘跌的确认不会帮你赚钱。

## v2.0 四象限

| 竞价信号 | 实际走势 | v1.x | v2.0 | 含义 |
|:--|:--|:--|:--|:--|
| strong/moderate (看涨) | actual > 0 (涨) | hit +α | **learn +α** | 确认型上涨 ✅ |
| strong/moderate (看涨) | actual ≤ 0 (跌) | miss +β | **penalize +β** | 假突破 ❌ |
| caution (看跌) | actual < 0 (跌) | hit +α | **skip** | 熊市噪音 ➖ |
| caution (看跌) | actual > 0 (涨) | miss +β | **penalize +β** | 漏掉反转 ⚠️ |
| weak/neutral | any | skip | **skip** | 信号太弱 ➖ |

## 代码位置

`scripts/auction_learner.py` · `__version__ = "2.0.0"`

## 关键教训

学习器的"准确率"如果不是以赚钱为导向，就是自欺欺人。做多系统的学习器应该只关注**上涨捕获率**——它找出了多少会涨的股票，而不是它多么擅长预测下跌。
