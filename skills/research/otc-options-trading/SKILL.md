---
name: otc-options-trading
description: 场外个股期权交易模块 —— 香草看涨分成结构 / 保证金追踪 / 盈亏计算
triggers:
  - "期权.*交易"
  - "场外.*期权"
  - "个股.*期权"
  - "保证金.*追踪"
  - "看涨.*分成"
  - "OTC.*call"
  - "otc.*option"
  - "杠杆.*做多"
  - "收益.*分成.*期权"
  - "options_bridge"
---

# 场外个股期权交易模块

## 产品结构

```
类型一：场外看涨分成 (OTC Call + P&L Split)
─────────────────────────────────────────
  保证金    ¥100,000    风险资金，亏损先扣保证金
  期权费    ¥8,000      固定通道成本（开仓即扣，不可退）
  名义本金  ¥1,000,000  对应股票市值敞口
  
  上涨分成  个人 70% : 券商 30%
  下跌承担  个人 100%（亏损从保证金扣除）
  
  强平线    保证金剩余 ≤ 20%
  有效杠杆  ~10x（100万名义/10万保证金）
─────────────────────────────────────────
```

**关键认知**：这不是标准香草期权（标准香草最大亏损=权利金）。这是杠杆做多+收益分成结构。保证金（10万）是真正的风险资金，亏光即强制平仓。

## 模块架构

```
scripts/options/
├── __init__.py              # 模块入口
├── otc_call.py              # 结构定义 + 盈亏计算引擎
├── margin_tracker.py        # 保证金追踪 + 分级告警
├── options_bridge.py        # CLI 桥接器 (6命令)
├── signal_engine.py         # [Phase 2] 入场信号引擎
├── position_manager.py      # [Phase 2] 期权仓位管理
└── risk_guard.py            # [Phase 3] 期权专属风控
```

## CLI 桥接器

```bash
python3 scripts/options/options_bridge.py <command> [args]
```

| 命令 | 参数 | 说明 |
|:--|:--|:--|
| `list` | — | 列出所有活跃期权持仓 |
| `open` | `<code> <name> <entry_price> [margin] [notional]` | 开立期权仓位 |
| `close` | `<position_id> <close_price>` | 平仓 → 计算最终盈亏 |
| `check` | — | 保证金扫描 → 分级告警 → 格式化报告 |
| `signal` | — | 读 daily_pool.json → 期权适配建议 |
| `portfolio` | — | 全持仓汇总（需标的最新价） |

## 盈亏逻辑

### 上涨场景
```
gross_profit = change_pct × notional
total_profit = gross_profit - option_fee
personal_pnl = total_profit × 0.70    # 个人70%
broker_pnl   = total_profit × 0.30    # 券商30%
margin_health = 1.0                   # 保证金无损
```

### 下跌场景
```
loss = |change_pct| × notional
margin_consumed = min(loss, margin)
margin_remaining = margin - margin_consumed
margin_health = margin_remaining / margin
personal_pnl = -(margin_consumed + option_fee)

if margin_health ≤ 0.20 → 强制平仓
```

### 微涨不覆盖期权费
```
若 gross_profit < option_fee（如涨0.5%时 ¥5,000 < ¥8,000）
→ total_profit = negative
→ 个人承担差额，券商不分成
→ 保证金未动，但个人净亏
```

## 止损/风控规则

与现货不同，期权不按 MA20 或技术位止损，而是按**保证金健康度**：

| 保证金剩余 | 告警级别 | 操作 |
|:--|:--|:--|
| > 60% | 🟢 ok | 正常持有 |
| 40-60% | 🟡 warning | 密切监控 |
| 20-40% | 🟠 danger | 需补充保证金或减仓 |
| ≤ 20% | 🔴 liquidate | **强制平仓** |

## 与现货系统的关系

```
        共用                              独立
  ┌──────────────┐            ┌──────────────────────┐
  │ daily_pool   │            │ 入场条件（盈亏比≥3:1）   │
  │ target_pool  │            │ 止损规则（保证金健康度）  │
  │ 研究员/议会   │            │ 仓位管理（保证金分配制）  │
  │ 侦察兵资金流  │            │ 盈亏计算（70/30分成）    │
  └──────────────┘            │ 强平机制（自动化）       │
                              └──────────────────────┘
```

## 消息推送

期权消息通过**独立群聊窗口**推送（与现货消息分离）：
- 开仓/平仓 → 即时通知
- 保证金检查 → 盘中每5分钟 cron 扫描
- 强平告警 → 实时推送（不等待 cron）

## 进化参数

以下参数纳入进化引擎覆盖（62参数池新增）：

| 参数 | 当前值 | 说明 |
|:--|:--|:--|
| `split_personal` | 0.70 | 个人分成比例 |
| `liq_threshold` | 0.20 | 强平线（保证金剩余比例） |
| `warn_threshold` | 0.40 | 预警线 |
| `margin` | 100000 | 单笔保证金 |
| `notional` | 1000000 | 名义本金 |

## 常见陷阱

| 陷阱 | 正确做法 |
|:--|:--|
| 当成标准香草期权（最大亏损=权利金）| 保证金(10万)才是真正的风险资金，可亏光 |
| 算杠杆用 100万/8000=125x | 实际杠杆 = 100万/10万 = 10x（保证金撬动名义本金）|
| 用现货止损规则（MA20/技术位）| 期权按保证金健康度止损，40%预警线 |
| 建仓分批买入 | 场外期权一次性建仓，无法分批 |
| 期权费算进收益分成 | 期权费是固定成本，先扣费再分收益 |
| 推荐池直接照搬 | 需期权专属过滤：盈亏比 ≥ 3:1（上涨潜力/期权费）|

## 参考文档

- `references/otc-call-pnl-examples.md` — 盈亏场景详解（4场景）
