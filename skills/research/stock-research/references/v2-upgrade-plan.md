# 小红 v2.0 升级蓝图

> 从零散脚本到 TradingSkill 风格产品化交易平台的全链路实施记录

## 五阶段规划

| Phase | 主题 | 内容 | 交付物 | 工期 |
|:--:|------|------|------|:--:|
| 1 | 基础设施 | Docker + 执行器 + 日志 | 7 files, 48K | 完成 |
| 2 | 协议+接口 | MCP Gateway + REST API + 通知 | 10 files, 101K | 完成 |
| 3 | 策略+回测 | 5策略 + 回测引擎 + PaperTrading | 3 files, 60K | 完成 |
| 4 | 多租户+硬件 | 租户管理 + Pi盒子 + LED | 4 files, 42K | 完成 |
| 5 | 产品化 | 小程序 + Web后台 + SDK | 20 files, 156K | 完成 |

## 系统全景

```
📱 小程序 ──→ 🌐 REST API (17 endpoints) ──→ 🐍 Python 引擎
🖥️ Web后台 ──→ 🔧 MCP Gateway (17 tools) ──→ 🗄️ PostgreSQL/Redis/SQLite
                                         ──→ 🖥️ Pi 5 + WS2812 LED
```

## 核心设计原则

1. **先展示完整方案，再动手执行**：涉及架构改动时，先输出架构全景 + 风险评估 + 执行顺序，确认后再编码。
2. **每 Phase 4 步**：核心模块 + 辅助模块 + 集成测试 + 验证
3. **不做假数据**：所有分析基于 `data_pipeline` 真实数据源
4. **MCP + Skills 双轨**：MCP 提供数据获取和执行能力，Skills 提供领域知识和决策框架

## 对标 TradingSkill 完成度

| TradingSkill 特性 | 小红实现 |
|------|:--:|
| Docker 部署 | ✅ docker-compose 6 服务 |
| Auto Executor | ✅ paper/live 双模式 |
| CSV 日志 + PnL | ✅ CSV + SQLite + PostgreSQL |
| 多策略 | ✅ 5 策略（超越原生 4 策略） |
| 回测 | ✅ 夏普/最大回撤/网格搜索 |
| Paper Trading | ✅ 滑点/延迟/手续费模拟 |
| MCP 协议 | ✅ 17 tools / 5 servers |
| 多租户 | ✅ 4 Tier schema 隔离 |
| 硬件盒子 | ✅ Pi 5 + LED + 仪表盘 |
| 小程序 | ✅ 5 页面 Taro + React |
| 通知系统 | ✅ 四通道 + P0-2 分级 |
