# 安幕诺·小红量化交易系统 — 商业化 PRD

> **文档类型**: 产品需求文档 (PRD)  
> **版本**: v1.0  
> **日期**: 2026-06-05  
> **作者**: 安幕诺家族 · 小红  
> **目标**: 将小红交易系统从内部 AI 工作台改造为可对外复制销售、真实券商对接、稳定可控的商业级量化交易产品

---

## 目录

1. [执行摘要](#1-执行摘要)
2. [现状评估](#2-现状评估)
3. [产品定义](#3-产品定义)
4. [差距分析](#4-差距分析)
5. [系统架构](#5-系统架构)
6. [模块详设](#6-模块详设)
7. [券商对接方案](#7-券商对接方案)
8. [前端产品矩阵](#8-前端产品矩阵)
9. [SaaS 多租户体系](#9-saas-多租户体系)
10. [运维监控体系](#10-运维监控体系)
11. [合规与法律](#11-合规与法律)
12. [开发路线图](#12-开发路线图)
13. [风险登记册](#13-风险登记册)
14. [附录](#14-附录)

---

## 1. 执行摘要

### 1.1 产品定位

**安幕诺·小红**（以下简称「小红」）是一款面向**个人量化投资者**和**小型投资工作室**的 AI 驱动全自动量化交易系统。覆盖 A 股市场，提供从数据采集 → 因子挖掘 → 选股推荐 → 盘中监控 → 自动下单 → 复盘优化的**全闭环量化交易能力**。

对标产品：VibetradingLabs（策略探索）、TradingSkill（手动辅助）、聚宽/米筐（在线回测）。

**小红的差异化**：不是回测平台，不是信号工具，而是「装好就能跑的 AI 交易员」——LLM 驱动认知层 + 传统量化执行层的双引擎架构。

### 1.2 目标用户

| 用户画像 | 痛点 | 付费意愿 |
|----------|------|:--:|
| 个人量化爱好者 | 想量化但不会写代码 / 写了策略但没时间盯盘 | ★★★ |
| 小型投资工作室 | 需要标准化交易流程，降低人工依赖 | ★★★★ |
| 券商投顾团队 | 需要工具赋能客户，提升服务差异化 | ★★★★★ |
| 财经自媒体/KOL | 需要实盘验证的策略内容 | ★★★ |

### 1.3 商业模式

| 版本 | 月费 | 核心权益 |
|------|:--:|------|
| **Free** | ¥0 | 1策略/5只自选/Paper Trading/基础数据 |
| **Pro** | ¥299 | 全部策略/50只自选/实盘下单/完整数据 |
| **Studio** | ¥999 | 无限策略/500只自选/5子账户/API 接入/优先支持 |
| **Enterprise** | 议价 | 白标/私有部署/SLA/定制开发 |

### 1.4 核心指标（12个月目标）

| 指标 | 目标 | 
|------|:--:|
| 月活用户 (MAU) | 5,000 |
| 付费转化率 | 8% |
| 月经常性收入 (MRR) | ¥200,000 |
| 系统可用性 | 99.5% |
| 实盘接入券商数 | 5+ |
| 年化超额收益（推荐池 vs 沪深300） | >15% |

---

## 2. 现状评估

### 2.1 当前系统概况

```
代码规模:  50个 .py 文件，约 25,000 行
Cron 任务: 37 个（23 no_agent + 8 LLM + 6 新增）
进化参数: 62 个（10 模块覆盖）
数据管线: Bronze → Silver → Gold 三层架构
覆盖率:   5524 只全A / 26维因子面板 / 6类数据源
```

### 2.2 现有能力矩阵

| 能力域 | 模块 | 成熟度 | 商业化瓶颈 |
|--------|------|:--:|------|
| 数据采集 | data_pipeline / mega_collector / bronze_ingest | ★★★★★ | 依赖外部 API，需关注合规 |
| 因子工程 | factor_evaluator / gold_pipeline | ★★★★ | 26维因子需持续验证 |
| 选股推荐 | stock_recommender + 研究员议会 | ★★★★ | LLM 依赖需可控 |
| 盘中监控 | scout(侦察兵) + sniperd(狙击手守护进程) | ★★★★ | systemd 绑定 Linux，跨平台需重构 |
| 风控管理 | ammo_risk + portfolio_risk | ★★★★ | R值/凯利公式需用户可配置 |
| 自动执行 | auto_executor + broker_gateway | ★★★ | 券商接入仅 Paper 验证通过 |
| 复盘优化 | review(文工团) + evolution_engine | ★★★★ | 进化引擎变更需人工审核 |
| REST API | api_server (FastAPI) | ★★★ | JWT/多租户为内存版，不可生产 |
| 前端界面 | 无 | ★ | 仅飞书 Bot + 命令行 |
| 部署运维 | Docker + systemd | ★★★ | 无 Helm Chart / K8s |
| 用户管理 | multi_tenant (PG schema) | ★★ | 未实现计费/注册/权限 |

### 2.3 致命短板（阻碍直接商业化）

| # | 短板 | 严重度 | 说明 |
|:--|------|:--:|------|
| 1 | **无用户界面** | P0 | 用户只能通过飞书/命令行交互，不可交付 |
| 2 | **无用户注册/登录/计费** | P0 | 多租户模块存在但无注册流和支付集成 |
| 3 | **券商实盘未验证** | P0 | broker_gateway 支持 xtquant 但从未实盘跑过 |
| 4 | **LLM 依赖不可控** | P1 | 认知层依赖 Claude/DeepSeek，成本和延迟不可预测 |
| 5 | **配置靠代码修改** | P1 | 62个参数散落在 .py 文件中，用户无法自行调整 |
| 6 | **无安装程序** | P1 | 用户需要手动 pip install + 配置 API Key + 初始化数据库 |
| 7 | **数据合规未确认** | P1 | 使用 AKShare/东方财富 API，商业分发有法律风险 |
| 8 | **无回测报告** | P2 | 有回测引擎但无前端图表和历史对比 |

---

## 3. 产品定义

### 3.1 产品架构（三层）

```
┌─────────────────────────────────────────────────┐
│              用户界面层 (Presentation)             │
│  Web SPA  │  桌面客户端  │  企业微信/钉钉 Bot      │
├─────────────────────────────────────────────────┤
│              平台服务层 (Platform)                 │
│  用户中心  │  策略市场  │  订阅管理  │  通知中心    │
├─────────────────────────────────────────────────┤
│              核心引擎层 (Core Engine)              │
│  数据管线  │  选股推荐  │  盘中监控  │  自动交易    │
│  风控管理  │  复盘优化  │  回测系统  │  券商网关    │
└─────────────────────────────────────────────────┘
```

### 3.2 用户旅程

```
第1天: 注册 → 选择套餐 → 一键安装客户端 → 配置券商(Paper默认)
第2天: 挑选策略模板 → 设置风险偏好 → 系统自动生成推荐池
第3天: 观察 Paper Trading 表现 → 调整参数 → 建立信心
第7天: 连接实盘券商 → 设置仓位上限 → 开启自动交易
第30天: 查看月度报表 → 对比基准 → 续费/升级
```

### 3.3 核心功能清单

#### P0 — 最小可售卖版本 (MVP)

| 功能 | 说明 | 来源 |
|------|------|------|
| 一键安装 | Docker 镜像 / Windows Installer | 新增 |
| Web 管理后台 | React SPA，策略配置 + 持仓查看 + 信号历史 | 新增 |
| 策略模板市场 | 5 套预置模板 (balanced/aggressive/defensive + 2 行业专项) | 改造 strategy_templates |
| Paper Trading | 零风险模拟，含滑点和手续费 | 已有 paper_trading.py |
| 实盘券商对接 | 招商 QMT / 华泰 easytrader / 国金 QMT | 已有 broker_gateway |
| 日报推送 | 晨报 + 复盘，支持微信/钉钉/邮件 | 已有，需多通道 |
| 基础风控 | 单票上限/总仓位/止损止盈 | 已有 ammo_risk |

#### P1 — 完整产品

| 功能 | 说明 |
|------|------|
| 策略自定义 | 可视化因子权重调节 + 回测验证 |
| 多账户管理 | 一个用户多券商/多策略并行 |
| 信号市场 | 用户间策略信号共享（匿名化） |
| 移动端小程序 | 微信小程序，查看持仓/信号/日报 |
| 社区 | 策略讨论 + 实盘排行 + 经验分享 |

#### P2 — 生态扩展

| 功能 | 说明 |
|------|------|
| 美股/港股 | 跨市场支持 |
| 策略 SDK | 用户用 Python 写策略上传 |
| 机构版 | 白标 + 私有部署 + 定制因子 |
| 数据订阅 | 另类数据（舆情/产业链/供应链） |

---

## 4. 差距分析

### 4.1 代码层面

| 当前 | 目标 | 迁移工作 |
|------|------|------|
| 50个零散 .py 文件 | 标准 Python 包 `xiaohong/` | 重构导入路径，setup.py/pyproject.toml |
| cron 调度 + systemd | Celery / APScheduler + Redis | 解耦调度与业务逻辑 |
| LLM 硬依赖 | LLM 可选 + 规则引擎回退 | 瞭望塔/决策官/复盘增加 `--no-llm` 模式 |
| 62个硬编码参数 | `config.yaml` + Web UI | 抽取参数到配置文件，Web 端读写 |
| 单机运行 | 分布式可扩展 | 数据层/执行层/Web层分离 |
| 飞书 Bot 专属报告 | 多通道 (邮件/微信/钉钉/Webhook) | notifier.py 通用化 |

### 4.2 架构层面

| 当前 | 目标 |
|------|------|
| Agent 驱动的 LLM cron | 服务化：API + Worker + Scheduler 三层 |
| 无用户认证 | JWT + OAuth2 + 2FA |
| 单进程 | 微服务（数据服务/策略引擎/执行引擎/API网关） |
| SQLite + JSON 文件 | PostgreSQL + Redis |
| 无监控 | Prometheus + Grafana + Sentry |

### 4.3 数据合规

| 风险点 | 缓解方案 |
|------|------|
| AKShare 抓取东方财富 | 购买东方财富 CHOICE 数据终端授权 / 改用聚宽数据 |
| tushare 免费额度不足 | 购买 tushare Pro 高级会员 / 多数据源冗余 |
| LLM 用户数据隐私 | 用户数据不出境，认知层支持本地模型 (Ollama) |
| 投顾牌照 | 不提供投资建议，系统定位为「决策辅助工具」 |

---

## 5. 系统架构

### 5.1 目标架构全景

```
                            ┌──────────────┐
                            │   CDN/Nginx   │
                            └──────┬───────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
              ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐
              │  Web SPA  │ │ 小程序 API │ │ 第三方 API │
              │  (React)  │ │  (REST)   │ │  (REST)   │
              └─────┬─────┘ └─────┬─────┘ └─────┬─────┘
                    │              │              │
                    └──────────────┼──────────────┘
                                   │
                         ┌─────────▼─────────┐
                         │    API Gateway    │
                         │  Kong / Nginx     │
                         │  限流·认证·路由    │
                         └─────────┬─────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
    ┌─────────▼─────────┐ ┌───────▼───────┐ ┌─────────▼──────────┐
    │   User Service    │ │ Strategy Svc  │ │  Execution Svc     │
    │   注册·登录·订阅   │ │ 选股·风控·回测│ │  下单·撤单·持仓同步 │
    └─────────┬─────────┘ └───────┬───────┘ └─────────┬──────────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                    ┌──────────────┼──────────────┐
                    │              │              │
              ┌─────▼─────┐ ┌─────▼─────┐ ┌─────▼─────┐
              │ PostgreSQL│ │   Redis   │ │ S3/MinIO  │
              │  主数据库  │ │ 缓存·队列 │ │ 文件存储   │
              └───────────┘ └───────────┘ └───────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
    ┌─────────▼─────────┐ ┌───────▼───────┐ ┌─────────▼──────────┐
    │  Data Pipeline    │ │  AI Engine    │ │  Notification      │
    │  采集·ETL·因子    │ │  LLM·ML·进化  │ │  消息·邮件·推送     │
    └───────────────────┘ └───────────────┘ └────────────────────┘
```

### 5.2 技术栈选型

| 层级 | 技术 | 理由 |
|------|------|------|
| 前端 | React 18 + TypeScript + Ant Design | 生态成熟，中文友好 |
| 移动端 | Taro / uni-app | 一套代码多端（微信/支付宝/字节小程序） |
| API 网关 | Nginx + Kong | 限流 + 认证 + 路由 |
| 后端框架 | FastAPI (已有) + Celery | 异步高性能 + 成熟任务队列 |
| 数据库 | PostgreSQL 15 + TimescaleDB | 时序数据优化 |
| 缓存 | Redis 7 | 实时行情 + 会话 + 限流 |
| 消息队列 | Redis Streams / RabbitMQ | 事件驱动 |
| 文件存储 | MinIO (S3 兼容) | 可私有部署 |
| 监控 | Prometheus + Grafana + Sentry | 标准运维三件套 |
| 容器 | Docker + Kubernetes (Helm) | 弹性伸缩 |
| CI/CD | GitHub Actions + ArgoCD | GitOps 自动化 |

### 5.3 部署方案

| 方案 | 适用场景 | 月成本 |
|------|------|------|
| **云服务器单机** | 个人用户 / Pro | ¥200-500 (4C8G) |
| **云服务器集群** | 小型工作室 | ¥1,500-3,000 (K8s 3 节点) |
| **私有部署** | 企业白标 | 议价 |
| **桌面客户端** | 不想用服务器的个人用户 | 一次性 ¥999 |

---

## 6. 模块详设

### 6.1 用户中心

```
功能:
  ├── 注册 (邮箱/手机 + 验证码)
  ├── 登录 (JWT + 2FA可选)
  ├── 套餐管理 (Free/Pro/Studio/Enterprise)
  ├── 支付集成 (微信支付/支付宝/Stripe)
  ├── API Key 管理 (生成/轮转/删除)
  └── 审计日志 (登录/IP/操作)

数据模型:
  users (id, email, phone, password_hash, tier, created_at)
  subscriptions (id, user_id, plan, status, start_date, end_date)
  api_keys (id, user_id, key_hash, key_prefix, permissions, created_at)
```

### 6.2 策略引擎

> 核心复用: `stock_recommender.py` + `strategy_templates.py` + `scout.py`

```
改造要点:
  1. 抽取 config.yaml: 因子权重 / 排除规则 / 风控参数
  2. 策略模板 → 可克隆/可编辑/可分享
  3. 增加 --no-llm 模式: 规则引擎回退，降低成本和延迟
  4. 回测集成: 参数变更 → 自动回测 → 对比报告
  5. 因子面板: 可视化因子 IC/ICIR 趋势图
```

### 6.3 交易执行引擎

> 核心复用: `auto_executor.py` + `broker_gateway.py` + `algo_executor.py`

```
改造要点:
  1. 券商驱动标准化: 统一 Order/Position/Account 接口
  2. 订单状态机: PENDING → SUBMITTED → PARTIAL → FILLED / REJECTED
  3. 异常处理: 断线重连 / 重复订单检测 / 成交确认超时
  4. 风控前置: 下单前验证仓位/资金/频率/涨跌停
  5. 交易审计: 每笔订单完整链路可追溯
```

#### 券商接口标准

```python
class BrokerDriver(ABC):
    """券商驱动基类 — 所有券商实现此接口"""
    
    @abstractmethod
    def connect(self, config: BrokerConfig) -> bool: ...
    
    @abstractmethod 
    def get_account(self) -> Account: ...
    
    @abstractmethod
    def get_positions(self) -> List[Position]: ...
    
    @abstractmethod
    def submit_order(self, order: OrderRequest) -> OrderResponse: ...
    
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...
    
    @abstractmethod
    def get_order(self, order_id: str) -> OrderStatus: ...
    
    @abstractmethod
    def get_orders(self, date: date) -> List[OrderStatus]: ...
    
    @abstractmethod
    def subscribe_quote(self, symbols: List[str]) -> None: ...
    
    @abstractmethod
    def get_quote(self, symbol: str) -> Quote: ...
```

### 6.4 数据管线

> 核心复用: `data_pipeline/` + `bronze_ingest.py` + `silver_pipeline.py` + `gold_pipeline.py`

```
改造要点:
  1. 数据源正规化: 东方财富 API → CHOICE / Wind 授权
  2. 实时行情: Sina → 券商 level2 / 交易所行情
  3. 数据质量: 增加数据断点检测 + 自动修复
  4. 数据服务化: REST API 供前端消费
  5. 多市场: A股 → + 港股 → + 美股
```

### 6.5 AI 认知引擎

> 核心复用: 瞭望塔/决策官/文工团 LLM cron + evolution_engine

```
改造要点:
  1. LLM 解耦: 支持 Claude / GPT / DeepSeek / 本地 Ollama
  2. 成本控制: 非关键任务用规则引擎，LLM 仅用于复杂研判
  3. Prompt 模板化: 所有 LLM prompt 外置为 YAML 模板
  4. 结果缓存: 相同上下文复用上次 LLM 结果
  5. 人类监督: P0 决策（大额下单/参数变更）需用户确认
```

### 6.6 通知中心

> 核心复用: `notifier.py`

```
支持通道:
  ├── 企业微信 Bot (已有)
  ├── 钉钉 Bot
  ├── 飞书 Bot (已有)
  ├── 邮件 (SMTP)
  ├── 短信 (阿里云/腾讯云)
  ├── Webhook (自定义)
  └── App Push (Firebase/APNs)

优先级:
  P0 🔴: 止损触发 → 短信 + App Push
  P1 🟡: 信号生成 → 企业微信 + 邮件
  P2 🔵: 日报 → 邮件 + App
  P3 ⚪: 系统通知 → App 内消息
```

---

## 7. 券商对接方案

### 7.1 对接路线

```
Phase 1: QMT (招商/国金)
  └── xtquant Python SDK → 标准化 BrokerDriver 接口
  └── 验证: Paper → 模拟盘 → 小资金实盘

Phase 2: Easytrader (华泰/银河/广发)
  └── easytrader Python 库 → 同上接口
  └── 限制: 部分券商需客户端常驻

Phase 3: 直连 (CTP/XTP)
  └── C API → Python wrapper
  └── 优势: 低延迟，适合高频
```

### 7.2 QMT 接入流程（用户侧）

```
1. 在合作券商开通 QMT 权限（资金门槛 ~10-50万）
2. 下载券商提供的 xtquant SDK
3. 在小红客户端中「券商管理」→「添加」→ 选择券商
4. 填入 QMT 安装路径 → 系统自动检测 xtquant
5. 连接测试 → 获取账户信息 → 开始交易
```

### 7.3 券商合作策略

| 阶段 | 策略 |
|------|------|
| MVP | 自运维，用户自行开通 QMT |
| 增长期 | 与 2-3 家券商合作，联合推广 |
| 规模化 | 券商分成模式，小红引流 → 券商开户 → 佣金返点 |

---

## 8. 前端产品矩阵

### 8.1 Web 管理后台 (MVP 核心)

```
技术栈: React 18 + TypeScript + Ant Design Pro + ECharts

页面结构:
  ├── 仪表盘
  │   ├── 今日收益 / 累计收益 / 最大回撤
  │   ├── 持仓饼图 / 行业分布
  │   └── 最近信号时间线
  ├── 策略中心
  │   ├── 策略模板市场
  │   ├── 我的策略 (自定义因子权重)
  │   └── 回测对比
  ├── 交易中心
  │   ├── 今日推荐池
  │   ├── 持仓管理
  │   ├── 订单历史
  │   └── 券商账号管理
  ├── 数据中心
  │   ├── 大盘概览
  │   ├── 板块热力图
  │   └── 个股深度分析
  ├── 报表中心
  │   ├── 日报 / 周报 / 月报
  │   ├── 收益归因分析
  │   └── 交易行为分析
  └── 系统设置
      ├── 风险偏好配置
      ├── 通知设置
      └── API Key 管理
```

### 8.2 微信小程序

```
功能: 持仓查看 / 信号推送 / 日报阅读 / 一键操作(止损/止盈修改)
技术: Taro 3 + React + 微信云开发
```

### 8.3 桌面客户端

```
技术: Electron / Tauri
优势: 
  - 常驻系统托盘，本地运行策略引擎
  - 降低服务器成本
  - 用户数据本地化，隐私友好
定位: Pro 版本可选部署方式
```

---

## 9. SaaS 多租户体系

### 9.1 数据隔离

| 层级 | 方案 | 适用 |
|------|------|------|
| Schema 隔离 | 每个租户独立 PostgreSQL schema | Pro / Studio |
| 数据库隔离 | 每个租户独立 database | Enterprise |
| 行级隔离 | tenant_id 字段 + RLS | Free (共享实例) |

### 9.2 资源限额

```yaml
tiers:
  free:
    max_strategies: 1
    max_watchlist: 5
    max_positions: 3
    live_trading: false
    data_refresh: "15min"
    rate_limit: 30/min
    
  pro:
    max_strategies: 10
    max_watchlist: 50
    max_positions: 15
    live_trading: true
    data_refresh: "5min"
    rate_limit: 100/min
    
  studio:
    max_strategies: 100
    max_watchlist: 500
    max_positions: 50
    live_trading: true
    data_refresh: "real-time"
    rate_limit: 500/min
    sub_accounts: 5
    api_access: true
```

### 9.3 计费集成

```
支付渠道: 微信支付 (主) / 支付宝 / Stripe (海外)
计费模式: 
  - 月付 (默认)
  - 年付 (8折)
  - 永久 (一次性，仅桌面版)
开票: 电子发票自动开具
```

---

## 10. 运维监控体系

### 10.1 监控矩阵

| 维度 | 工具 | 指标 |
|------|------|------|
| 基础设施 | Prometheus + Node Exporter | CPU/内存/磁盘/网络 |
| 应用健康 | Prometheus + FastAPI metrics | QPS / 延迟 / 错误率 |
| 数据管线 | 自定义 Exporter | 数据到达率 / 时延 / 完整性 |
| 交易执行 | 自定义指标 | 订单成功率 / 成交延迟 / 滑点 |
| 策略表现 | 自定义指标 | 日收益 / 最大回撤 / 夏普比率 |
| 业务指标 | Grafana | 注册数 / 活跃数 / 付费率 / MRR |
| 错误追踪 | Sentry | 异常堆栈 / 频率 / 影响面 |
| 告警 | AlertManager | P0: 电话 / P1: 短信 / P2: 企微 |

### 10.2 灾备方案

| 组件 | 备份频率 | 恢复时间目标 | 恢复点目标 |
|------|:--:|:--:|:--:|
| PostgreSQL | 每小时 + WAL 流复制 | <5分钟 | <1分钟 |
| Redis | RDB 每15分钟 | <5分钟 | <15分钟 |
| 文件存储 | MinIO 实时同步 | <1分钟 | <1秒 |
| 配置文件 | Git 版本管理 | <1分钟 | 即时 |

---

## 11. 合规与法律

### 11.1 关键合规事项

| 事项 | 现状 | 行动 |
|------|------|------|
| 投顾牌照 | ❌ 未持有 | 定位为「决策辅助工具」，不提供投资建议 |
| 软件著作权 | ⚠️ 未申请 | 核心代码申请软著（保护好 algorithm） |
| 用户数据隐私 | ⚠️ 需完善 | 隐私政策 + 数据加密 + 不出境声明 |
| 券商 API 使用 | ⚠️ 需确认 | 确认 QMT/easytrader 的第三方使用许可 |
| 数据来源合规 | ⚠️ 需整改 | AKShare → 购买 CHOICE/Wind 授权 |
| ICP 备案 | ⚠️ 需办理 | Web 端上线前完成 |
| 等保 | ⚠️ 待评估 | 根据用户规模决定是否需要 |

### 11.2 免责声明 (产品内必含)

```
「小红」是量化交易辅助工具，不构成投资建议。
所有交易决策由用户自行做出并承担风险。
历史回测收益不代表未来表现。
```

---

## 12. 开发路线图

### Phase 0: 基础重构 (4周)

```
Week 1-2: 代码包化
  ├── 重组为 xiaohong/ 标准包
  ├── setup.py / pyproject.toml
  ├── config.yaml 参数外部化
  └── 单元测试补齐（目标覆盖率 >60%）

Week 3-4: 服务化
  ├── FastAPI 完整化（用户/策略/交易/数据 CRUD）
  ├── Celery 集成（解耦 cron → 任务队列）
  ├── PostgreSQL 迁移（SQLite → PG）
  └── Docker Compose 一键部署
```

### Phase 1: MVP 上线 (8周)

```
Week 5-6: Web 管理后台
  ├── React 项目搭建 + Ant Design Pro
  ├── 仪表盘 + 策略配置页
  ├── 持仓管理 + 订单历史
  └── 用户注册/登录/套餐

Week 7-8: 券商实盘验证
  ├── 招商 QMT 实盘测试（小资金 ¥10,000）
  ├── 华泰 easytrader 实盘测试
  ├── 异常处理完善
  └── 交易审计日志

Week 9-10: 支付 + 部署
  ├── 微信支付集成
  ├── K8s Helm Chart
  ├── Grafana 监控面板
  └── 文档站 (VitePress)

Week 11-12: 内测 + 上线
  ├── 邀请 50 名种子用户
  ├── Bug 修复 + 体验优化
  └── 正式发布 v1.0
```

### Phase 2: 增长 (12周)

```
Week 13-16: 移动端
  ├── 微信小程序开发
  └── App Push 通知

Week 17-20: 策略生态
  ├── 策略市场（模板分享/评分/排行）
  ├── 策略 SDK（用户自定义策略）
  └── 因子自定义

Week 21-24: 扩展
  ├── 港股支持
  ├── 美股支持
  └── 多语言 (英文)
```

### Phase 3: 平台化 (持续)

```
├── 券商合作 (佣金分成)
├── 数据订阅 (另类数据)
├── 机构版 (白标/私有部署)
├── AI 模型市场 (用户训练的 ML 模型)
└── 开放平台 (第三方接入)
```

---

## 13. 风险登记册

| # | 风险 | 概率 | 影响 | 缓解措施 |
|:--|------|:--:|:--:|------|
| R1 | 券商限制第三方 API 使用 | 中 | 高 | 多券商备份 + 与券商建立合作关系 |
| R2 | LLM API 成本过高 | 高 | 中 | --no-llm 规则模式 + 本地模型 Ollama |
| R3 | 数据源合规问题 | 中 | 高 | 逐步迁移到授权数据源 |
| R4 | 策略实盘大幅亏损 | 中 | 高 | Paper 验证 + 免责声明 + 风控硬限制 |
| R5 | 竞争对手出现 | 高 | 中 | 快速迭代 + AI 认知层差异 + 社区生态 |
| R6 | 系统安全漏洞 | 中 | 高 | 渗透测试 + Bug Bounty + 安全审计 |
| R7 | 团队能力不足 | 中 | 高 | 外包非核心模块 + 招聘关键岗位 |
| R8 | 监管政策变化 | 低 | 高 | 合规顾问 + 灵活调整产品定位 |

---

## 14. 附录

### 14.1 现有模块清单（50 个）

| 模块 | 行数 | 商业化复用度 |
|------|:--:|:--:|
| researchers.py | 1,481 | ★★★★★ 研究员议会 |
| evolution_engine.py | 1,354 | ★★★ 重构为配置化 |
| stock_recommender.py | 1,319 | ★★★★★ 核心引擎 |
| sniperd.py | 933 | ★★★★ 守护进程→Celery |
| scout.py | 853 | ★★★★★ 盘中监控 |
| gold_pipeline.py | 787 | ★★★★★ 因子面板 |
| system_health_check.py | 763 | ★★ 内部运维 |
| ammo_risk.py | 732 | ★★★★★ 风控核心 |
| resource_pool.py | 714 | ★★★★ 事件池 |
| api_server.py | 653 | ★★★★★ 需完整化 |
| factor_evaluator.py | 576 | ★★★★★ 因子评估 |
| auto_executor.py | 588 | ★★★★★ 执行引擎 |
| review.py | 591 | ★★★★ 复盘 |
| ml_predictor.py | 488 | ★★★★ ML 预测 |
| backtest_engine.py | 444 | ★★★★ 回测 |
| broker_gateway.py | 331 | ★★★★★ 券商网关 |
| multi_tenant.py | 379 | ★★★★★ 多租户 |
| strategy_templates.py | 375 | ★★★★★ 策略模板 |
| backtest_chart.py | 334 | ★★★★ 图表 |
| paper_trading.py | 478 | ★★★★ 模拟交易 |

### 14.2 技术债务清单

1. 大量 `try/except` 吞掉异常，缺少结构化日志
2. 配置文件散布在各 .py 中，无统一管理
3. 全局变量 (`SCRIPT_DIR`, `DATA_DIR`) 不利于测试
4. 数据库 Schema 无版本管理 (需 Alembic)
5. 无 CI/CD Pipeline
6. 无集成测试，仅靠 cron 空跑验证
7. `$HOME` 环境变量依赖问题 (已遇多次)

### 14.3 关键决策记录

| 决策 | 结论 | 日期 |
|------|------|------|
| QMT vs Easytrader | QMT 优先（更稳定） | 2026-06 |
| PostgreSQL vs MySQL | PostgreSQL（TimescaleDB 时序优化） | 2026-06 |
| K8s vs Docker Compose | MVP 用 Compose，增长期迁 K8s | 2026-06 |
| React vs Vue | React（Ant Design Pro 生态） | 2026-06 |
| 微信小程序 vs 独立 App | 小程序优先（获客成本低） | 2026-06 |

---

> **文档状态**: 待评审  
> **下一步**: 用户审阅 → 确认范围 → Phase 0 启动  
> **同步位置**: `~/wiki/交易系统/PRD-小红量化交易系统商业化.md`
