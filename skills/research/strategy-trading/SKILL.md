---
name: strategy-trading
description: 小红策略交易引擎 —— 策略执行、风控分析、交易信号生成
triggers:
  - "策略.*分析"
  - "期权.*交易|场外.*期权|期权.*模块|保证金.*追踪|option.*trade"
  - "交易.*信号"
  - "止损.*检查"
  - "风控.*评估"
  - "仓位.*建议"
  - "决策官"
  - "多指标.*策略|组合策略|MA.*交叉|RSI.*策略|布林.*策略"
  - "交易日志|CSV.*日志|PnL.*统计|回测"
  - "Paper Trading|模拟交易|纸交易"
  - "交易.*执行|自动.*下单|执行器"
  - "Docker.*部署|docker-compose|容器化"
  - "硬件.*盒子|树莓派|Raspberry"
  - 狙击手|弹药库|文工团|交易规则|规则体系|R值|凯利
  - 进化引擎|自我进化|自动调参|参数优化|broker|券商|xtquant|实盘下单
  - 账户.*重置|清空.*持仓|重置.*净值
  - 商业化|产品化|对外.*销售|PRD|可复制|量化.*产品|SaaS.*交易
  - 券商.*接口.*标准|BrokerDriver|券商.*抽象|券商.*统一
category: research
---

# 策略交易引擎

## 场外个股期权交易 🆕

独立模块，与现货共用推荐池/目标池，但仓位/止损/盈亏计算全部独立。

| 要素 | 值 | 说明 |
|:--|:--|:--|
| 保证金 | ¥100,000 / 手 | 风险资金，亏损先扣 |
| 期权费 | ¥8,000 / 手 | 固定通道成本（开仓即扣） |
| 名义本金 | ¥1,000,000 / 手 | 对应股票市值敞口 |
| 收益分成 | 个人 70% : 券商 30% | 仅上涨时 |
| 强平线 | 保证金 ≤ 20% | 亏损 ≥ ¥80,000 强制平仓 |

```bash
# CLI 桥接器（6 命令）
python3 scripts/options/options_bridge.py list|open|close|check|signal|portfolio
# Cron: 盘中每 5 分钟 + 收盘 15:00 保证金扫描 → 独立 Feishu 群
```

| 模块文件 | 职责 |
|:--|:--|
| `options/otc_call.py` | 盈亏计算引擎（含 70/30 分成） |
| `options/margin_tracker.py` | 保证金追踪 + 分红告警 |
| `options/options_bridge.py` | CLI 桥接器 |

> 完整产品结构和盈亏逻辑 → `references/otc-call-options.md`

## 桥接器入口（现货）

**现货桥接器**：
```
python3 ~/.hermes/profiles/xiaohong/scripts/strategy_bridge.py <command> [args]
```

**期权桥接器** 🆕：
```
python3 ~/.hermes/profiles/xiaohong/scripts/options/options_bridge.py <command> [args]
```

> 场外个股期权交易模块完整文档 → `otc-options-trading` skill
> 6 命令：`list | open | close | check | signal | portfolio`
> 推荐池/目标池与现货共用，止损/仓位/盈亏计算独立设计

所有输出为 JSON。

## 自动交易执行器 🆕

对标 TradingSkill `src/trading/executor.ts`。

```bash
python3 scripts/auto_executor.py [--paper|--live] [--once|--cron] [--interval SECONDS]
```

### 模式

| 参数 | 说明 |
|------|------|
| `--paper` | 模拟交易（默认），零风险 |
| `--live` | 实盘模式（需券商 API 接入） |
| `--once` | 执行一次信号扫描后退出 |
| `--cron` | Cron 调度模式，同 `--once` |
| `--status` | 输出状态报告后退出 |
| `--interval 300` | 主循环轮询间隔（秒） |

### 架构

```
信号源 (strategy_bridge) → 风控检查 (RiskManager) → 仓位计算 (R值) → 执行 → 日志 (TransactionLogger)
```

### 风控检查清单

执行前必过 4 关：
1. 持仓数 ≤ 9 只
2. 单股仓位 ≤ 33.3%
3. 可用资金足够（留 5% 缓冲）
4. 单笔风险 ≤ 总净值 × 2%（R 值约束）

### 编程调用

```python
from auto_executor import AutoExecutor, Signal, SignalStrength

executor = AutoExecutor(mode="paper")
sig = Signal(symbol="600519", symbol_name="贵州茅台", side="BUY",
             strength=SignalStrength.STRONG, confidence=85.0,
             price=1800.0, stop_loss=1710.0,
             strategy_id="MA-CROSS", reason="金叉突破")

trade_id = executor.process_signal(sig)
# → 买入/卖出执行，返回 trade_id
```

## 交易日志系统 🆕

对标 TradingSkill `src/trading/logger.ts`：CSV + SQLite 双写 + PnL 统计分析。

```bash
python3 scripts/transaction_logger.py [stats|recent|export]
```

### 数据模型

```python
from transaction_logger import TransactionLogger, TradeRecord

logger = TransactionLogger(
    csv_path="workspace/transactions.csv",
    db_path="data/transactions.db"
)

# 便捷方法
logger.log_buy("600519", "茅台", 1800.0, 100, strategy_id="MA-CROSS")
logger.log_sell("600519", "茅台", 1900.0, 100, buy_price=1800.0)

# 统计分析（对标 TradingSkill getStatistics）
stats = logger.get_statistics()
# → {total_trades, wins, losses, win_rate, total_pnl, avg_win, avg_loss, profit_factor, portfolio_value}

# 导出过滤 CSV（对标 TradingSkill exportFiltered）
logger.export_filtered("workspace/btc-only.csv", symbol="600519")
```

### CSV 格式（24 字段）

`Timestamp, TradeID, Symbol, SymbolName, Market, Side, OrderType, Price, Quantity, Value, Fee, StrategyID, SignalType, SignalStrength, SignalConfidence, StopLoss, TakeProfit, PositionPct, IsPaper, ExecStatus, PnL, PnLPct, PortfolioValue, Reason`

### 注意事项

- `log_sell()` 的 PnL 依赖 `buy_price` 参数正确传入，否则为 0
- SQLite 写入失败时 CSV 仍会成功（双写独立）
- `created_at` 由 SQLite `datetime('now')` 自动填充，不需要在代码中传

## 券商对接详情

### xtquant (QMT) — 首选

| 券商 | 门槛 | 备注 |
|:--|:--|:--|
| 招商证券 | ~50万 | 生态成熟，系统已完整对接 |
| 国金证券 | ~50万 | 量化生态最成熟 |
| 华鑫证券 | ~10万 | 低门槛明星 |
| 国信证券 | ~50万 | MiniQMT 支持 |
| 中泰证券 | ~30万 | XTP 接口可选 |
| 光大证券 | ~50万 | QMT 或 PTrade（后者需额外开发） |

**配置步骤**：
1. 开通券商 QMT 权限 → 下载 QMT 客户端
2. 从 QMT 安装目录复制 `xtquant/` 到 venv: `cp -r xtquant/ venv/lib/python3.11/site-packages/`
3. 验证: `python3 -c "from xtquant import xtdata; print('OK')"`
4. 测试: `python3 broker_gateway.py --live --status`

### easytrader — 备用

| 券商 | 配置 |
|:--|:--|
| 华泰证券 | `easytrader.use('ht')` |
| 银河证券 | `easytrader.use('yh')` |
| 广发证券 | `easytrader.use('gf')` |
| 国金证券 | `easytrader.use('gjzq')` |

招商证券和光大证券**不在 easytrader 默认支持列表**，只能走 QMT。

| 命令 | 参数 | 说明 |
|------|------|------|
| `list` | 无 | 列出所有可用策略 |
| `signal` | 无 | 生成当前持仓的综合交易信号 |
| `risk` | `[code1 code2 ...]` | 持仓风控分析（止损状态、仓位、盈亏） |
| `run` | `<STRATEGY_ID> [stock_code]` | 运行指定策略 |

## signal 输出示例

```json
{
  "overall_assessment": "🔴 发现 4 个止损警报，建议立即处理",
  "recommendations": [
    {
      "code": "300131",
      "action": "减仓",
      "reason": "仓位 42.9% 超过 33.3% 上限",
      "severity": "warning"
    },
    {
      "code": "600481", 
      "action": "立即卖出",
      "reason": "4 个批次已触发止损",
      "severity": "critical"
    }
  ]
}
```

## 每日数据管线时间线 (v8.7+)

```
15:00 收盘
15:05 ⏱️  分时K线冻结 → Bronze intraday/
15:30 🛡️  弹药库风控
15:30 🏥  文工团复盘
15:35 📊  股票跟踪器
15:40 🗄️  Bronze全量采集 → daily_kline + fund_flow + events
15:45 🥈  Silver ETL      → Bronze→清洗→统一格式 (5524只)
15:50 🏆  Gold ETL        → Silver→26维因子面板+ML+Pool归档
17:00 📊  因子IC评估      → 读 Gold factor_panel
17:10 🤖  ML增量训练      → 读 Gold ml_datasets
17:20 📈  组合回测        → 读 Gold daily_pool 历史
17:30 🧬  进化引擎
```

## 分层数据架构 (v8.7+)

```
Bronze (不可变)          Silver (清洗)            Gold (特征)
═══════════════          ════════════            ═══════════════
bronze_ingest.py    →    silver_pipeline.py  →    gold_pipeline.py
  (15:40)                   (15:45)                 (15:50)

数据源:                   数据源:                  数据源:
  · 外部API               · Bronze only            · Silver (主)
  · 6类数据                · 5524只全A主表           · Bronze (启动期补充)
                            · 质量标记               · 26维因子计算
                            · 不可变清洗              · ML数据集构建
                                                     · daily_pool归档
```

> Gold 层产出 `factor_panel/v3.parquet` + `ml_datasets/*.npz`，供因子IC、ML训练、组合回测消费。因子覆盖从~24%起步随Silver积累60天后达100%。详见 `stock-research` → `references/gold-layer-design.md`。

决策官 (14:30 cron) 的标准化流程：

1. **收集当日数据**：读取 `reports/daily/` 中今日的瞭望塔晨报（V8.0 自然三段）、侦察兵（v3.0 三档信号+竞价）、狙击手 v4.0 实时告警（10:00/11:00/13:00/14:00 时段摘要，见 sniper_daily_*.jsonl 日志）
2. **读取竞价数据**：`auction.db` 中的竞价轨迹 + `auction_weights.json` 的学习权重
3. **读取 V8.0 推荐池**：`scripts/data/daily_pool.json`，确认哪些推荐股已被资金确认
4. **运行风控分析**：`python3 scripts/strategy_bridge.py risk`
5. **运行交易信号**：`python3 scripts/strategy_bridge.py signal`
6. **综合研判**：结合大盘环境 + 持仓状态 + 策略信号 + 竞价信号 + V8.0 推荐池，给出决策
7. **输出决策报告**：使用 `report_formatter.Report` 构建美化报告

> 侦察兵 v3.0 提供 ⭐双重确认/🆕新增异动/⏳待确认三档信号 + 竞价 🔥评分；狙击手 v4.0 为实时事件驱动守护进程（systemd 服务），提供秒级 P0-P3 分级告警、状态机去重、入场信号和大盘异动监控；弹药库 v4.0 提供回撤追踪、行业集中度和 V8.0 池交叉验证。决策官应综合这些信号做最终判断。

### 决策报告模板

```python
from report_formatter import Report
import json, subprocess

# 获取风控数据
risk = json.loads(subprocess.run(['python3','scripts/strategy_bridge.py','risk'], capture_output=True, text=True).stdout)
signal = json.loads(subprocess.run(['python3','scripts/strategy_bridge.py','signal'], capture_output=True, text=True).stdout)

r = Report(title="决策官 · 盘中决策", icon="🌹", color="red" if risk['alerts_triggered'] > 0 else "green")
r.header_meta(净值=f"¥{risk['net_value']:,.0f}", 浮亏=f"¥{risk['total_pnl']:+,.0f}", 告警=f"{risk['alerts_triggered']}条")

r.section("行动建议")
for rec in signal['recommendations']:
    icon = {"critical":"🔴","warning":"🟡","info":"🔵","ok":"🟢"}.get(rec['severity'],'⚪')
    r.kv(f"{icon} {rec['code']} {rec['name']}", rec['action'], rec['reason'])

r.section("市场研判")
r.text(填入1句话市场情绪判断)

r.footer("数据 hermes:tushare · 报告时间 14:30")

print(r.markdown())  # cron 自动投递
```

## TradingSkill 风格策略集（v2.0 新增）

对标 gwrxuk/TradingSkill → `src/trading/strategies.ts`，新增 5 大策略：

| 策略ID | 信号机制 | 参数 | 文件 |
|--------|----------|------|------|
| MA-CROSS | EMA 快/慢线金叉死叉 | fast=9, slow=21 | `strategies/trading_skill_strategies.py` |
| RSI | 超买超卖反转 | period=14, 30/70 | 同上 |
| MACD | DIF/DEA 金叉死叉 | fast=12, slow=26, sig=9 | 同上 |
| BOLLINGER | 价格触轨反弹 | period=20, std=2.0 | 同上 |
| COMBINED | 加权投票共识 (买≥60分) | MA30%+RSI25%+MACD25%+BB20% | 同上 |

用法：
```python
from strategies.trading_skill_strategies import get_strategy
strat = get_strategy("COMBINED")
signal = strat.analyze("600519", closes_array)
# → StrategySignal(side="BUY", confidence=75.0, stop_loss=1710, ...)
```

## 回测引擎（v2.0 新增）

`scripts/backtest_engine.py` — 历史日线回测 + 参数网格搜索：

```python
from backtest_engine import BacktestEngine
engine = BacktestEngine(initial_capital=100000)
result = engine.run(strategy, "600519", closes, dates)
# → 夏普比率/最大回撤/卡尔玛/胜率/盈亏比/权益曲线

# 网格搜索
results = engine.grid_search(MACrossoverStrategy, "600519", closes,
    {"fast_period": [5,9,13], "slow_period": [20,26,34]})
```

## Paper Trading 增强（v2.0 新增）

`scripts/paper_trading.py` — 滑点/延迟/手续费模拟：

```python
from paper_trading import PaperTradingSimulator
sim = PaperTradingSimulator()
sim.place_order("600519", "BUY", 1800, 100, stop_loss=1710)
sim.update_market_prices({"600519": 1850})
# → 自动跟踪移动止盈
```

### TradingSkill 对标策略

| 策略ID | 名称 | 类型 | 信号机制 | 文件 |
|--------|------|------|---------|------|
| MA-CROSS | 双均线交叉 | 趋势 | EMA快/慢线金叉死叉 | `strategies/trading_skill_strategies.py` |
| RSI | 超买超卖 | 反转 | RSI超卖反弹/超买回落 | 同上 |
| MACD | MACD信号线 | 趋势 | DIF/DEA交叉 | 同上 |
| BOLLINGER | 布林带 | 波动 | 价格触轨反弹 | 同上 |
| COMBINED | 多指标共识 | 综合 | 4策略加权投票(买≥60分) | 同上 |

> 加上小红原生 4 策略（CMP-001/SEL-001/POS-002/STP-001），共 9 策略可用。
> Skills 框架设计详见 `stock-research` → `references/external-skills-ecosystem.md`

## 弹药库风控 v8.6

```bash
# cron 自动 (15:30): 同步 + 报告一步完成（含🆕组合风控）
python3 scripts/ammo_risk.py --update
```

一次 `--update` 完成八项操作：

1. **市值同步** / 2. **净值修正** / 3. **移动止盈** / 4. **回撤追踪**
5. **R 值自动计算** / 6. **V8.0 池交叉标记** / 7. **净值历史追加**
8. 🆕 **组合层面风控**：VaR + 相关性告警（集成 `portfolio_risk.py`）

### 新增组合风控模块 (v8.6)

| 工具 | 命令 | 说明 |
|------|------|------|
| 因子IC评估 | `python3 factor_evaluator.py` | 22因子日频IC/ICIR + 月度淘汰 |
| 组合风控 | `python3 portfolio_risk.py --daily` | 日频: 相关性+VaR |
| 压力测试 | `python3 portfolio_risk.py --weekly` | 周频: 5场景压力测试 |
| 组合回测 | `python3 portfolio_backtest.py --days 60` | 推荐池等权→夏普/回撤 |
| ML预测 | `python3 ml_predictor.py --train` | 增量训练涨跌模型 |
| 券商网关 | `python3 broker_gateway.py --status` | paper/live账户状态 |
| TWAP拆单 | `python3 algo_executor.py --twap CODE QTY` | 等时间片拆单 |
| VWAP拆单 | `python3 algo_executor.py --vwap CODE QTY` | 按量分布拆单 |
### 弹药库 v4.1 关键修复（2026-06-01）

| 问题 | 严重度 | 修复 |
|:--|:--|:--|
| cron_ammo.sh 缺少 --update | P0 | cron 改为 `ammo_risk.py --update` |
| 双重净值字段不同步 | P0 | 统一到 `accountInfo.currentNetValue` |
| R 值从未自动计算 | P1 | `calc_r_value()` 每次 --update 写入 |
| 流动性用当日成交额 | P1 | `_get_avg_amount_5d()` 5日均量 |
| 行业分类靠名称关键词 | P1 | tushare 官方 industry 优先 |
| 移动止盈无缓冲 | P1 | 止损距现价至少 3% |
| update/report 重复拉行情 | P2 | `get_cached_quotes()` 120s 缓存 |

## 风控参数（当前）

| 参数 | 值 | 说明 |
|------|:--:|------|
| R 值 | 净值 × 33.3% × 1/8 × 凯利 0.2 | 单笔最大风险 |
| 单股上限 | 33.3% | 持有池上限 |
| 总持仓上限 | 9 只 | |
| 止损 | 技术面 R 系数止损 | |
| 移动止损 | 涨 20% 启动，每涨 10% 上移 10% | |
| 建仓节奏 | 11.1% × 3 批 | 首仓→加仓→T仓 |

## signal 输出的 severity 含义

| severity | 含义 | 响应 |
|----------|------|------|
| `critical` | 止损已触发 | 立即清仓 |
| `warning` | 仓位超标或靠近止损 | 减仓或准备 |
| `info` | 浮亏但未触发 | 密切观察 |
| `ok` | 正常 | 持有 |

决策官报告应使用 P0/P1/P2 优先级标注行动项。

## 常见陷阱

- **弹药库双重净值**：`accountInfo.currentNetValue` 和 `riskManagement.currentNetValue` 必须一致。v4.1 统一到前者，`set_net_value()` 同步两处。如果发现不一致，运行 `python3 ammo_risk.py --update` 自动修复。
- **弹药库 R 值停滞**：v4.0 及以前 R 值永不自动计算。v4.1 每次 --update 重新计算并写入。检查：`grep currentRValue data/holdings.json`
- **弹药库 cron 必须加 --update**：不加 --update 时只出报告不写数据，移动止盈和回撤永远不更新。v4.1 cron 已修正为 `ammo_risk.py --update`。
- **流动性检查用日均量**：v4.0 用当日实时成交额（盘后不完整），v4.1 改用 5 日均量（`_get_avg_amount_5d()`）。
- 止损过期：`trailingStopUpdated` 字段可能停滞（弹药库 `--update` 会自动修复）
- 净值偏差：`currentNetValue` 不含浮动盈亏时，R 值和仓位百分比不准确
- 策略引擎验证：`validate_all_strategies()` 应覆盖全部 4 类策略（v1.6 已修复）
- **SQLite INSERT 列数不匹配**：手工数 `?` 容易出错。调试方法：`PRAGMA table_info(transactions)` 查看实际列数，再对照 INSERT 语句计数。
- **竞价数据空窗**：`auction_collector.py` 在 09:15-09:25 运行，侦察兵（09:25）和狙击手 v4.0 守护进程（09:30 起实时运行）可以读到竞价数据，但更早的任务（08:25推荐引擎、08:30瞭望塔）无法访问竞价数据——这是正常的，不要在盘前任务中尝试读取 auction.db。
- **狙击手 v4.0 守护进程**：已从 cron 定时触发升级为 systemd 实时守护进程（`sniperd.py`）。用 `systemctl --user status sniperd.service` 检查状态，用 `python3 sniperd.py --once` 手动测试。存活检测 cron（`sniper_healthcheck.sh`）每 5 分钟自动检查并恢复。旧 v3.0 `sniper.py` 保留作为手动备用。
- **裸 `except:` 禁止使用**：吞掉 `KeyboardInterrupt`/`SystemExit` 等系统异常，进程无法正常终止。全部改为 `except Exception:`。2026-06-01 已全局修复 knowledge_base(11处)/resource_pool(6处)/data_pipeline(2处)。
- **`get_stock_realtime()` now has Sina bulk fast-path**: Priority Sina batch HTTP (single request, ~800 stocks, <0.05s), falls back to subprocess. Built-in 2 min cache. Never call in a loop.
- **BaoStock `rs.next()` blocks 60s+**: Must use `rs.data` (list of lists). `rs.next()` is iterator mode that hangs in production.
- **BaoStock not thread-safe**: Shared global HTTP session → ThreadPool causes utf-8 decode errors. Must use ProcessPoolExecutor with per-process `bs.login()`/`bs.logout()`.
- **`data_pipeline.py` now a compatibility shell (15 lines)**: Real logic in `data_pipeline/_core.py`. New code: `from data_pipeline.market import get_stock_realtime`.
- **Bronze layer auto-records**: `_core.py` has `_bronze_write()` hooks on 5 key functions (index/north/flow/stocks/realtime). Set `XIAOHONG_BRONZE=0` to disable.
- **ML predictor sklearn fallback**: `ml_predictor.py` auto-degrades to sklearn RandomForest when lightgbm unavailable. Install: `pip install lightgbm --no-build-isolation`.
- **New factor computation**: Must use already-prefetched `_indicators[code]['close_history']` — do NOT re-call `get_historical_k_with_ma()` (ProcessPool deadlock + 80s waste).
- **efinance 与东方财富 push2 同源**：efinance 底层走 `push2.eastmoney.com`，和现有 `_em_api_get` 是同一管道。非交易时段同样断连。不引入新数据源价值。
- **场外期权 ≠ 场内 ETF 期权**：场外是 OTC 柜台交易、无连续行情、无公开期权链 API。数据靠手工录入和券商报价，不能调用 AKShare `option_sse_*`（那是场内 ETF 期权）。Greeks 需自算（BS 模型），IV 需从历史波动率估算。——2026-06-07 用户明确纠正
- **Docker TA-Lib 编译**：Raspberry Pi ARM 架构编译慢，建议用预编译 wheel 或 `--build-arg` 跳过；x86 机器正常
- **auto_executor 只在策略桥接返回信号时才执行**，空仓无信号时静默。若需强制测试，用 `process_signal()` 直接注入 Signal 对象
- **`get_stock_realtime()` now has Sina bulk fast-path**

> 🆕 v8.6 执行层升级: ML预测器 (`ml_predictor.py`)、算法执行 (`algo_executor.py`)、券商网关 (`broker_gateway.py`) 详见 `references/v8.6-execution-layer.md``paper_trading.py` 中 `StrategyPaperTrader.run_cycle` 的类型注解用了 `np.ndarray` 但模块顶部未 `import numpy as np`。务必在 dataclass 模块级 import numpy。
- **进化引擎 0 变更（静默失败）**：`extract_changes()` 返回空通常由三重 bug 导致：(1) 路径偏移 — cron workdir 是 `scripts/`，`DATA_DIR.parent/"kb"` 实际指向 `scripts/kb/` 而非 `scripts/data/kb/`，(2) 格式断层 — 诊断文件是 `list[{root_causes}]` 但代码期望 `dict{rule_changes_suggested}`，(3) `return changes` 在补丁操作中被误删。调试：手动验证 `load_diagnosis()` 返回类型和文件存在性。详见 `stock-research` → `references/evolution-engine-debug.md`。
- **进化引擎沙箱 KeyError: 'old_metric'**：`sandbox_test()` 返回 dict 不含 `old_metric`/`new_metric`/`improvement`。v2.0 沙箱有 4 种策略，仅 `reflection_log` 策略返回这些键。打印语句已改为 `test_result.get('details', 'ok')`。
- **竞价采集器 09:15 cron error**：(1) 东方财富 `push2.eastmoney.com/api/qt/stock/get` 在非交易时段拒绝连接，(2) `f43`/`f2`/`f46`/`f60` 字段单位是**分**需 ÷100，(3) `exec` 在 cron 脚本中可能使进程跟踪丢失。修复：6轮指数退避预热 + 批量拉取兜底 + 干净退出 + 去 exec。详见 `stock-research` → `references/candidate-pool-p0-fix.md`。
- **竞价采集器多通道降级**：v1.2 新增三通道（东方财富→腾讯→Sina），单通道故障时自动降级，采集结束输出通道分布统计。腾讯行情 (qt.gtimg.cn) 解析：`split('"')[1]` → `split('~')`，量单位手(×100)、额单位万(×10000)。详见 `stock-research` → `references/multi-channel-data-pattern.md`。

## 狙击手 v4.0 实时守护进程 🆕

从 cron 每 30 分钟触发升级为 systemd 实时事件驱动守护进程。

```bash
# 服务管理
systemctl --user status sniperd.service   # 查看状态
systemctl --user start sniperd.service    # 手动启动
journalctl --user -u sniperd.service -f   # 实时日志

# 单次扫描测试
python3 scripts/sniperd.py --once --dry-run

# 存活检测
python3 scripts/sniper_healthcheck.sh
```

### 核心指标

| 维度 | v3.0 Cron | v4.0 守护进程 |
|:--|:--|:--|
| 止损响应 | ≤30 分钟 | **≤3 秒** |
| 触发方式 | 定时轮询 | 事件驱动（状态机跃迁） |
| 告警去重 | 无（每次重复） | 优先级跃迁 + 冷却去重 |
| 数据源 | 逐只 subprocess | Sina 批量 HTTP（单请求） |
| 进程模型 | 一次性脚本 | systemd 自动恢复 |
| 可进化参数 | 5 个 | 17 个（+6 守护进程专属 +3 分时量价 +3 基础设施 🆕） |

### 事件优先级

| 级别 | 触发条件 | 冷却 | 确认 |
|:--|:--|:--|:--|
| P0🔴 | 价格穿透止损线 | 无冷却 | 2 tick (6s) |
| P1🟡 | 距止损 ≤ 3% | 120s | 1 tick |
| P2🔵 | 涨跌 >5% 或 量比 >3x | 300s | 1 tick |
| 🟣🟠 **分时放量** 🆕 | 5min量比 >2.5x | 180s | 1 tick |
| 🎯 ENTRY | 推荐池标满足建仓条件 | 600s | 1 tick |
| 📊 MARKET | 大盘指数 ±3% | 600s | 1 tick |

> 详细架构见 `stock-research` → `references/sniper-v4-design.md`
> 分时数据集成见 `stock-research` → `references/intraday-data-integration.md`

## 侦察兵 v4.1 盘中扫描增强 🆕

## 侦察兵 v4.1 盘中扫描增强 🆕

v8.3 新增 `INTRA_VOLUME_BONUS = 8`：候选标的通过 `get_intraday_volume_alert()` 检测 5min 分时放量，放量上涨额外 +2~10 附加分。不求换权重体系，直接叠加加分。

## 推荐引擎基本面增强 🆕

v8.3 `_score_fund()` 新增财务数据融合：PE/PB 基础评分(60%) + `get_financial_summary()` 财务综合评分(40%)。ROE/毛利率/负债率/利润增速/经营现金流五维打分。详见 `stock-research` → `references/financial-data-integration.md`。

## 瞭望塔集成

决策官应结合瞭望塔 v8.0 的自然三段报告和 V8.0 推荐池做综合研判。推荐池中的 ⭐ 标记股票为今日重点关注标的。狙击手和侦察兵会在此基础上做开盘资金验证和日内监控。

## 报告美化

统一使用 `report_formatter.Report` 构建所有报告输出。API 详见 `stock-research` skill → `references/report-formatter-api.md`。

```python
from report_formatter import Report
r = Report(title="标题", icon="🌹", color="green")
r.header_meta(日期="2026-05-27", 净值="¥898,698")
r.section("章节名")
r.kv("键", "值", "副文本")
r.table(["表头1","表头2"], [["行1","行2"]])
r.alert("告警信息", "critical")  # critical/warning/info
r.divider()
r.footer("页脚")
print(r.markdown())  # cron stdout 自动投递
```

## Docker 部署 🆕

项目根目录 `~/hermes/profiles/xiaohong/` 下：

```bash
# 一键启动（Paper Trading 模式）
docker-compose up trading-engine -d

# 启动全部服务（含 Grafana 监控）
docker-compose --profile monitoring up -d

# 仅执行一次交易扫描
docker-compose run trading-engine python3 scripts/auto_executor.py --once

# 查看实时日志
docker-compose logs -f trading-engine
```

### 服务矩阵

| 服务 | 容器名 | 端口 | 说明 |
|------|--------|:--:|------|
| trading-engine | xiaohong-engine | — | 核心交易引擎 |
| cron-scheduler | xiaohong-cron | — | 7 角色报告系统 |
| api-server | xiaohong-api | 8000 | FastAPI REST |
| redis | xiaohong-redis | — | 缓存+消息队列 |
| postgres | xiaohong-postgres | — | 多租户数据库 |
| grafana | xiaohong-grafana | 3000 | 监控仪表盘（可选） |

## 商业化相关参考 🆕

- **PRD 完整文档**: `~/wiki/交易系统/PRD-小红量化交易系统商业化.md` (752行 / 14章节)
- **架构图**: `diagrams/小红商业化目标架构-v1.0.html` (三层: 界面→平台→引擎)
- **商业化差距速查**: 本skill `references/commercialization-roadmap.md` (券商接口标准+ SaaS分层+合规清单)
- **券商接口标准**: 所有券商统一实现 `BrokerDriver` 抽象基类 — `connect/get_account/get_positions/submit_order/cancel_order/get_order/subscribe_quote/get_quote`
- **SaaS 四层**: Free(¥0/1策略/Paper) → Pro(¥299/实盘) → Studio(¥999/API) → Enterprise(白标)
- **实盘验证路线**: QMT(招商/国金) → Easytrader(华泰/银河) → CTP/XTP(直连低延迟)