# TradingSkill vs 小红 系统对标

> 基于 gwrxuk/TradingSkill (GitHub, MIT) 的深度架构对比

## TradingSkill 核心架构

```
src/
├── client.ts              # MCP 客户端核心
├── run-trading.ts         # 交易系统入口
├── trading/
│   ├── indicators.ts      # 技术指标 (SMA/EMA/RSI/MACD/Boll/ATR/Stoch/VWAP)
│   ├── signals.ts         # 信号生成器
│   ├── strategies.ts      # 交易策略 + 仓位管理
│   ├── executor.ts        # 自动执行器
│   └── logger.ts          # CSV 交易日志
servers/                    # MCP wrappers
  ├── crypto-exchange/
  ├── google-drive/
  └── slack/
skills/                     # 高层自动化
```

## 对标矩阵

| 维度 | TradingSkill | 小红 v2.0 | 超越 |
|------|:-----------|:----------|:--:|
| 语言 | TypeScript | Python + TypeScript (MCP) | 双语言 |
| 策略数量 | 5 (MA/RSI/MACD/Boll/Combined) | 5 + 4 原有 = 9 | ✅ |
| 回测 | ❌ | ✅ 夏普/最大回撤/网格搜索 | ✅ |
| 多因子选股 | ❌ | ✅ 瞭望塔 v6.0 四维交叉 | ✅ |
| 多租户 | ❌ | ✅ 4 Tier SaaS | ✅ |
| 硬件盒子 | ❌ | ✅ Pi 5 + LED 灯带 | ✅ |
| 小程序 | ❌ | ✅ Taro + React 5 页面 | ✅ |
| 通知 | Slack 单通道 | 飞书+微信+邮件+短信 四通道 | ✅ |
| 日志 | CSV | CSV + SQLite + PostgreSQL | ✅ |
| 知识库 | ❌ | ✅ 每小时增量采集+去重+索引 | ✅ |

## 可借鉴的 TradingSkill 设计

1. **indicator→signal→strategy→executor→logger** 五层流水线
2. **Paper Trading 先行，实盘渐进** 的安全部署模式
3. **MCP 协议标准化** 工具交互接口
4. **Docker 一键部署** 降低运维门槛
