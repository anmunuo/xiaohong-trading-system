# 小红交易系统商业化路线图

> 来源: PRD v1.0 (2026-06-05)  
> 完整 PRD: `~/wiki/交易系统/PRD-小红量化交易系统商业化.md`  
> 架构图: `diagrams/小红商业化目标架构-v1.0.html`

## 一、商业化差距速查

| # | 短板 | 严重度 | 现有基础 | 缺失 |
|:--|------|:--:|------|------|
| 1 | 无用户界面 | P0 | 飞书 Bot + CLI | Web SPA + 小程序 |
| 2 | 无注册/计费 | P0 | multi_tenant.py (PG schema) | 注册流 + 微信支付 |
| 3 | 券商实盘未验证 | P0 | broker_gateway.py (331行) | 小资金QMT实盘跑通 |
| 4 | LLM 依赖不可控 | P1 | 瞭望塔/决策官/文工团 LLM cron | --no-llm 规则回退模式 |
| 5 | 配置靠代码 | P1 | 62参数散落 .py 文件 | config.yaml + Web UI |
| 6 | 无安装程序 | P1 | Docker Compose (基础) | 一键安装 + Helm Chart |
| 7 | 数据合规未确认 | P1 | AKShare/东方财富 API | CHOICE/Wind 授权 |
| 8 | 无回测报告 | P2 | backtest_engine.py (444行) | 前端图表 + 历史对比 |

## 二、券商接口标准 (BrokerDriver)

所有券商实现统一抽象接口，支持 Paper / QMT / Easytrader / CTP 可插拔：

```python
class BrokerDriver(ABC):
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
    def subscribe_quote(self, symbols: List[str]) -> None: ...
    @abstractmethod
    def get_quote(self, symbol: str) -> Quote: ...
```

**对接路线**: QMT(招商/国金) → Easytrader(华泰/银河) → CTP/XTP(直连)

## 三、SaaS 分层模型

| 版本 | 月费 | 策略数 | 自选数 | 实盘 | API | 数据刷新 |
|------|:--:|:--:|:--:|:--:|:--:|------|
| Free | ¥0 | 1 | 5 | ❌ | ❌ | 15min |
| Pro | ¥299 | 10 | 50 | ✅ | ❌ | 5min |
| Studio | ¥999 | 100 | 500 | ✅ | ✅ | 实时 |
| Enterprise | 议价 | ∞ | ∞ | ✅ | ✅ | 实时 |

数据隔离: Free(行级RLS) → Pro/Studio(Schema隔离) → Enterprise(独立DB)

## 四、开发阶段

| 阶段 | 周期 | 核心交付 |
|------|:--:|------|
| Phase 0: 重构 | 4周 | 代码包化 + config.yaml + PG迁移 + Docker |
| Phase 1: MVP | 8周 | Web后台 + QMT实盘 + 支付 + 上线 |
| Phase 2: 增长 | 12周 | 小程序 + 策略市场 + 港股 |
| Phase 3: 平台 | 持续 | 券商合作 + 白标 + 开放API |

## 五、合规检查清单

- [ ] 软件著作权申请
- [ ] 隐私政策 + 用户协议
- [ ] 数据来源授权 (AKShare → CHOICE/Wind)
- [ ] 券商 API 第三方使用许可确认
- [ ] ICP 备案 (Web 端)
- [ ] 产品内免责声明: "辅助工具，不构成投资建议"
- [ ] 等保评估 (根据用户规模)
