# DESIGN-FINAL.md 改进建议

> 小红 🌹 | 2026-06-08 | 基于 v1.0 现网系统实战经验

---

## 总评

设计方案骨架正确——六层架构、四池模型、动态凯利方向都对。但对比现网 60+ 脚本、40 个 cron、62 个进化参数的实战系统，存在 **7 类缺口**：遗漏模块、过度抽象、配置盲区、冷启动缺陷、调度不完整、数据源细节缺失、时间线过于乐观。

---

## 改进 1：遗漏的已验模块（P0 — 不补则功能倒退）

现网以下模块经过数月实战锤炼，设计方案完全未提及：

| 遗漏模块 | 现网实现 | 价值 | 建议 |
|:--|:--|:--|:--|
| **竞价系统** | `auction_collector.py` + `auction_learner.py` (Bayesian) | 开盘 10 分钟预测当日方向，五维特征提取 | 补入 §3.2 决策链，侦察兵竞价之后增加「竞价学习器诊断」 |
| **研究员议会** | `researchers.py` — 6 研究员协同研究，3 轮辩论协议 | 推荐池每只标的必经议会审核，veto 拦截劣质标的 | `ai/researchers/` 已在包结构中，但 §3/§4/§8 均未提及其调度和作用 |
| **场外期权模块** | `options/` — OTC Call + 保证金追踪 + 70/30 分成 | 独立产品线，不补则功能丢失 | 增加 `anmunuo/options/` 包，§8 调度表增加保证金追踪 cron |
| **进化引擎** | `evolution_engine.py` — 62 参数，LLM 复盘 → patch → 验证闭环 | 系统自我优化能力 | `ai/evolution` 已在包结构中，§8 有 17:30 调度，但 §3/§4 未提及参数覆盖范围 |
| **自主修复** | `auto_repair.py` + `system_health_check.py` — 12 维扫描 → 7 维修复 | 幂等可追溯，cron 故障自动恢复 | §5 health.py 太简略，应展开为 health_check + auto_repair 双模块 |

---

## 改进 2：EntryExitEngine 过度抽象（P1）

### 问题

§3.3 引入 `EntryExitEngine` 作为狙击手和策略之间的中间层：

```
当前:  狙击手 → _build_entry_signal() → 量比+分时K线+议会 → 🟢入场
定稿:  狙击手 → ENT-001 → EntryExitEngine → POS-001 → STP-001 → POS-002 → 弹药库
```

**风险**：
- 现网狙击手 `_build_entry_signal()` 只需 3 个数据点（量比/分时K线/议会信号），延迟 <0.1s
- 新增 EntryExitEngine 编排 4 个策略，每个策略可能拉取额外数据 → 3s 轮询窗口可能不够
- 狙击手 v4.0 的核心价值是 **秒级响应**，中间层的编排逻辑不应成为瓶颈

### 建议

**取消 EntryExitEngine 独立层**，改为狙击手内部策略链：

```python
# agents/sniper/engine.py (狙击手内部，非独立层)
class SniperEngine:
    def evaluate_entry(self, target_stock):
        # 1. ENT-001 技术信号 (量比+分时形态)
        entry_signal = self.entry_strategy.should_enter(stock)
        if not entry_signal.ready:
            return None
        
        # 2. POS-001 凯利仓位
        kelly_pos = self.kelly_strategy.calculate(stock, net_value)
        
        # 3. STP-001 止损
        stop = self.stop_strategy.calculate(stock, entry_signal.price)
        
        # 4. POS-002 定仓确认
        final = self.ammo.confirm_position(kelly_pos, stop)
        
        return EntryPlan(...)
```

区别：不引入新模块层级，策略链在狙击手内部完成。弹药库仍独立但只做盘后。

---

## 改进 3：动态凯利的冷启动陷阱（P0）

### 问题

§4.2 动态凯利公式依赖 `p = 近 20 笔胜率`，且 `f* ≤ 5% → 观望，不建仓`。

**致命场景**：新用户 / 新系统上线 → PoolTracker 无历史 → `p = 0` → `f* = -0.25`（负数）→ **永远无法建仓**。

### 建议

增加**引导期（Bootstrap）逻辑**：

```python
def calculate_kelly(pool_tracker, config):
    trades = pool_tracker.get_recent_trades(config.lookback_trades)
    
    if len(trades) < config.min_trades_for_kelly:  # 默认 10
        # 引导期：使用默认保守凯利 + 标注来源
        return KellyResult(
            f_star=config.bootstrap_kelly,     # 默认 0.15
            source="bootstrap",
            trades_used=len(trades),
            warning="历史交易不足，使用引导凯利值"
        )
    
    p = sum(1 for t in trades if t.pnl > 0) / len(trades)
    b = config.profit_target_ratio
    f_star = (p * (b + 1) - 1) / b
    
    return KellyResult(
        f_star=f_star,
        source="dynamic",
        trades_used=len(trades),
        win_rate=p,
        formula=f"({p:.2f} × {b+1} - 1) / {b} = {f_star:.4f}"
    )
```

新增配置参数：
```yaml
kelly:
  bootstrap_kelly: 0.15          # 🆕 引导期默认值（比当前 0.2 更保守）
  min_trades_for_kelly: 10       # 🆕 最少需要多少笔才启用动态凯利
  dynamic_enabled: true           # 🆕 开关，可强制关闭回退到 bootstrap
```

---

## 改进 4：配置体系缺口（P1）

§7 仅有 7 个配置块，遗漏核心模块配置：

| 遗漏配置 | 说明 |
|:--|:--|
| `data_sources` | 五源优先级链、超时、重试、降级策略 |
| `auction` | 竞价采集频率(3s)、通道优先级(东方财富→腾讯→Sina)、学习器权重 |
| `researchers` | 议会辩论轮数(2/3)、快速议会研究员数(4)、bias 门槛 |
| `options` | 场外期权保证金(¥100,000)、期权费(¥8,000)、强平线(20%)、分成(70/30) |
| `evolution` | 参数变更幅度(±20%)、沙箱超时、auto_apply 开关 |
| `scout` | 资金流门槛、三级认证开关、分时放量加分 |
| `watchtower` | 晨报格式(V8三段)、KB洞察融入模式、推荐池编码规则 |
| `report` | 飞书推送目标群、报告保存路径、美化规则 |

**建议**：补全为 15 个配置块，每个模块一个。

---

## 改进 5：数据源具体化（P1）

§5 的 `market_data.py` 写「五源取数 + 降级链」但未列出具体五源。现网已验证的数据源矩阵：

| 用途 | 主通道 | 降级链 | 现网验证 |
|:--|:--|:--|:--|
| 实时行情 | Sina HTTP 批量 (800只/<0.05s) | 东方财富 push2 → 腾讯 qt | ✅ 数月无故障 |
| 历史K线 | **Baostock** ProcessPool (528码/10.8s) | tushare daily | ✅ 8x 加速 |
| 财务数据 | tushare fina_indicator | akshare | ✅ |
| 北向资金 | tushare moneyflow_hsgt (T-1) | — | ⚠️ 实时已永久关闭 |
| 竞价数据 | 东方财富 push2 → 腾讯 → Sina | 三通道降级 | ✅ |
| 市场资金流 | 东方财富 push2 f62/f66/f69 | 动量 fallback | ⚠️ f62 盘中偶发归零 |
| 分时K线 | Sina KLineData | — | ✅ |

**关键遗漏**：Baostock 作为历史K线主通道未被提及。Baostock 的 ProcessPool 8x 加速和 `rs.data` vs `rs.next()` 陷阱是重要的实现细节。

**建议**：§5 增加「数据源矩阵」子节，明确每类数据的主通道和降级链。

---

## 改进 6：调度表不完整（P1）

§8 调度表对比现网 40 个 cron，缺失：

| 缺失任务 | 建议补充 |
|:--|:--|
| 竞价学习器 (16:00) | Bayesian 权重更新 |
| 竞价 LLM 诊断 (16:05) | LLM 读取权重 → 诊断建议 |
| 研究员自主研学 (02:00) | 夜间 deep research |
| LLM 深度分析 (02:05) | 基于研学结果诊断 |
| 期权保证金追踪 (每5分钟 9:00-14:55) | 独立 Feishu 群推送 |
| 期权收盘检查 (15:00) | 保证金终态 |
| 涨幅榜学习 (15:50) | 研究员分析 6%+ 个股 |
| KB 每小时采集 + LLM 消化 | 增量采集 → 洞察写入 |
| GitHub 每日备份 (04:00) | 配置+数据 |

---

## 改进 7：凯利公式 POS-001 vs POS-002 职责重叠（P1）

### 问题

§4.1 和 §3.2 中两个仓位策略概念重叠：

- **POS-001 凯利仓位**：`f* = (p×(b+1)−1)/b`，输出仓位比例
- **POS-002 R值定仓**：`R = 净值 × f* × 0.02`，输出金额

§3.2 决策链写「POS-001 → STP-001 → POS-002」，意味着先算比例再算金额，两步都用凯利。但 §4.2 的公式 `R = 净值 × f* × 0.02` 本身就是 POS-002 的职责——POS-001 的 `f*` 还没出来，POS-002 的 R 怎么算？

### 建议

**合并为单一 POS-001**，内部两步：

```python
class KellyPositionStrategy(PositionStrategy):
    def calculate(self, stock, net_value, pool_tracker):
        # Step 1: 计算凯利比例
        f_star = self._calc_kelly_fraction(pool_tracker)
        
        # Step 2: 转为金额
        r_value = net_value * f_star * self.config.r_factor
        position_value = r_value / stock.stop_distance
        shares = int(position_value / stock.price / 100) * 100
        
        return PositionPlan(
            f_star=f_star,
            r_value=r_value,
            position_value=position_value,
            shares=shares,
            kelly_source=kelly_source
        )
```

删除 POS-002 独立 ID，将 R 值计算作为 POS-001 的第二步。弹药库盘后的 `calc_r_value()` 调用同一策略而非重复实现。

---

## 改进 8：Supervisor vs systemd 决策依据不足（P2）

### 问题

§2 技术栈和 §8 调度表指定 Supervisor 管理狙击手 daemon，但现网 systemd 方案已验证可行：

| 维度 | systemd (现网) | Supervisor (定稿) |
|:--|:--|:--|
| 部署 | 系统自带，零依赖 | 需安装配置 |
| 自动重启 | `Restart=always` | `autorestart=true` |
| 定时启动 | `sniperd.timer` 09:29 | cron 触发 supervisorctl start |
| 日志 | journalctl 统一 | 独立日志文件 |
| 存活检测 | cron + systemctl is-active | supervisorctl status |

### 建议

保留 systemd 作为默认方案，Supervisor 作为容器化部署时的备选。在配置中抽象进程管理接口：

```python
# platform/daemon.py
class DaemonManager(ABC):
    @abstractmethod
    def start(self, service_name): ...
    @abstractmethod
    def stop(self, service_name): ...
    @abstractmethod
    def status(self, service_name): ...

class SystemdDaemon(DaemonManager): ...    # 裸机默认
class SupervisorDaemon(DaemonManager): ... # Docker 环境
```

---

## 改进 9：缺失「已知陷阱」知识库（P1）

### 问题

现网 `stock-research` skill 积累了大量生产陷阱（100+ 条），新设计从零开始，所有陷阱会重演。

### 建议

增加 `anmunuo/core/pitfalls.py` 或在配置中增加 `known_pitfalls` 块：

```
核心陷阱（必须在新实现中避免）：
1. Baostock 日期格式必须是 YYYY-MM-DD，YYYYMMDD 静默失败
2. Baostock 必须用 rs.data 而非 rs.next()（阻塞 60s+）
3. Baostock 非线程安全，必须 ProcessPool 而非 ThreadPool
4. 东方财富 push2 f62 盘中偶发归零 → 需健康检测 + 动量 fallback
5. 北向资金实时数据 2024年5月起永久关闭，只能用 T-1
6. tushare daily_basic 不支持批量多码查询
7. tushare total_mv 单位是万元，东方财富 f20 是元
8. $HOME 被 profile 覆盖导致 Path.home() 返回假路径
9. 停牌股 close=0 且 change_pct=0 不等于停牌（盘前Sina全0）
10. 盘后东方财富 push2 HTTP 000 不可达
```

---

## 改进 10：决策官排除后的信号汇总真空（P1）

### 问题

§1 明确排除决策官，但 §8 调度表中 14:30 没有任何任务。当前系统 14:30 决策官整合瞭望塔+侦察兵+狙击手+弹药库信号给出综合研判。去掉后，谁来回答「今天到底要不要动手」？

### 建议

二选一：
- **方案 A**：保留简化版决策官，改名「盘中简报（Midday Brief）」，不主动建议操作，只汇总 P0-P2 信号 + 目标池状态 + 大盘环境。
- **方案 B**：将汇总逻辑交给狙击手 daemon，14:30 定时输出综合态势快照。

无论哪种，14:30 需要有一个汇总输出，不能留空。

---

## 改进 11：三池归档凌晨执行的风险（P2）

### 问题

§3.1 和 §8：00:00 三池归档 + 清空推荐池/目标池。凌晨执行看似合理，但存在：

- 如果 cron 在 00:00 失败，08:00 瞭望塔面对的是**昨天的残留推荐池**，而非空池重建
- 归档失败无重试机制
- 鱼池归档依赖持仓数据（弹药库 15:30 已同步），时间上可行，但缺乏校验

### 建议

```
00:00 三池归档
  │
  ├─ 成功 → 清空 → 正常
  └─ 失败 → 标记 archived=false + 告警 → 07:00 盘前检查重试
                └─ 仍失败 → 瞭望塔 08:00 强制清空 + 重建
```

增加归档幂等性：同一天多次执行不重复写入。

---

## 改进 12：分阶段时间线修正

基于现网实际耗时修正：

| Phase | 定稿周期 | 修正建议 | 理由 |
|:--|:--|:--|:--|
| Phase 0 | 1 周 | **2 周** | pydantic-settings + loguru + 测试框架搭建 |
| Phase 1 | 3-4 周 | **6-8 周** | 五源取数的降级链/陷阱/单位换算/ProcessPool 调试极耗时 |
| Phase 2 | 4-6 周 | **8-10 周** | 四池+5Agent 是核心业务逻辑，现网打磨了 2 个月才稳定 |
| Phase 3 | 4 周 | **6 周** | 实盘 Broker 对接+组合风控+进化引擎闭环 |
| Phase 4 | 6 周 | 6 周 | Web+多租户相对独立，时间合理 |

**总计**：18-23 周 → **28-36 周**（约 7-9 个月）

---

## 改进汇总优先级

| # | 改进项 | 级别 | 影响 |
|:--|:--|:--|:--|
| 1 | 遗漏模块（竞价/议会/期权/进化/自修复）| **P0** | 功能倒退 |
| 3 | 动态凯利冷启动陷阱 | **P0** | 新系统无法建仓 |
| 7 | POS-001/002 职责重叠 | **P1** | 实现混乱 |
| 2 | EntryExitEngine 过度抽象 | **P1** | 延迟增加，复杂度无益 |
| 4 | 配置体系缺口（8→15块）| **P1** | 实现时反复补漏 |
| 5 | 数据源具体化（Baostock遗漏）| **P1** | 历史K线性能退化 |
| 9 | 缺失已知陷阱知识库 | **P1** | 所有陷阱重演 |
| 10 | 决策官排除后信号汇总真空 | **P1** | 14:30 无输出 |
| 6 | 调度表不完整（9项缺失）| **P1** | 竞价学习/期权/研学停摆 |
| 12 | 时间线修正 | **P2** | 计划和现实的差距 |
| 8 | Supervisor vs systemd | **P2** | 无实质差异 |
| 11 | 三池归档失败处理 | **P2** | 边缘 case |

---

*建议在启动 Phase 0 前将以上 12 项纳入 DESIGN-FINAL.md v1.1*
