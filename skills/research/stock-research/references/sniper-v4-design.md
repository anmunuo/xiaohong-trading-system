# 狙击手 v4.0 升级设计

> 从 Cron 定时触发 → 实时事件驱动守护进程

---

## 一、升级动机

| v3.0 缺陷 | 影响 | v4.0 解决 |
|:--|:--|:--|
| 每 30 分钟 cron 触发 | 止损触发最坏延迟 30 分钟 | 每 3 秒轮询，秒级响应 |
| 一次性脚本无状态 | 同一条告警每 30 分钟重复 | 状态机去重，仅跃迁告警 |
| 数据冷启动 | 每次拉取独立 subprocess | Sina 批量 HTTP，一次请求覆盖全部标的 |
| 无大盘联动 | 不知市场整体环境 | 大盘实时监控 + 板块轮动感知 |

---

## 二、架构

```
                        sniperd (systemd 服务，09:30-15:00)
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ┌──────────────┐    ┌──────────────────┐    ┌───────────────┐  │
│  │ L1 持仓行情    │───▶│ TriggerEngine     │───▶│ stdout 输出    │  │
│  │ 每 3s Sina    │    │ (状态机去重)      │    │ (飞书投递)     │  │
│  │ 批量查询       │    │                  │    │               │  │
│  ├──────────────┤    │ P0: 止损穿透       │    │ cron 存活检测   │  │
│  │ L2 推荐池行情  │    │ P1: 逼近止损       │    │ 每 5 分钟      │  │
│  │ L1 回合批量    │    │ P2: 大幅异动       │    │ systemd 自恢复  │  │
│  ├──────────────┤    │ ENTRY: 入场信号     │    │               │  │
│  │ L3 大盘指数    │    │ MARKET: 大盘异动    │    └───────────────┘  │
│  │ 每 30s Sina   │    └──────────────────┘                       │
│  ├──────────────┤                                                │
│  │ L4 历史缓存    │                                                │
│  │ 每 30min 刷新  │                                                │
│  └──────────────┘                                                │
│                                                                  │
│  状态机规则:                                                     │
│  · 同优先级+同数值 → 静默                                       │
│  · 优先级跃迁(P3→P1, P1→P0) → 立即告警                          │
│  · P0 无冷却，穿透即告警                                         │
│  · P0 需连续 2 tick 确认（防数据尖刺）                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## 三、事件触发条件

| 事件 | 触发条件 | 冷却 | 确认次数 |
|:--|:--|:--|:--|
| P0🔴 止损穿透 | close ≤ stop_loss | 无冷却 | 2 tick (6s) |
| P1🟡 逼近止损 | 0 < distance ≤ 3% | 120s/股 | 1 tick |
| P1→P0 升级 | P1 进一步跌穿止损 | 无冷却 | 2 tick |
| P2🔵 大幅异动 | abs(change)>5% 或 vol>3x | 300s/股 | 1 tick |
| 🎯 入场信号 | 推荐池+放量+MA20附近 | 600s/股 | 1 tick |
| 📊 大盘异动 | 指数 ±3% | 600s | 1 tick |
| 💀 跌停锁定 | change ≤ -9.9% | 不重复 | 1 tick |

---

## 四、轮询分层

| 层级 | 标的范围 | 频率 | 数据源 |
|:--|:--|:--|:--|
| L1 | 持仓股 (≤9只) | 3秒 | Sina 批量 HTTP |
| L2 | 推荐池未持仓 (≤9只) | L1 回合批量 | Sina 批量 HTTP |
| L3 | 上证/深证/创业板 | 30秒 | Sina 指数 API |
| MA | 历史日线 | 30分钟 | data fetch CLI |
| 大盘 | 东方财富资金流 | 未实现(保留扩展) | data_pipeline |

> L1+L2 最多 18 只，Sina API 单次 HTTP 请求全部返回，无需逐只查询。

---

## 五、文件变更清单

| 文件 | 操作 | 说明 |
|:--|:--|:--|
| `scripts/sniperd.py` | **新建** | 守护进程主程序 (~530行) |
| `scripts/sniper_healthcheck.sh` | **新建** | 存活检测脚本 |
| `~/.config/systemd/user/sniperd.service` | **新建** | systemd 用户服务 |
| `~/.config/systemd/user/sniperd.timer` | **新建** | 交易日 09:29 启动定时器 |
| `scripts/sniper.py` | 保留 | v3.0 作为手动备用 `python3 sniper.py` |
| `scripts/cron_sniper.sh` | 废弃 | 被守护进程替代 |
| Cron `26aababd5d55` | **已停用** | 狙击手 30 分钟 cron |
| Cron `6bf08cd7d6dd` | **新建** | 存活检测 (每 5 分钟) |
| `scripts/evolution_engine.py` | **更新** | 狙击手参数从 5→11，适配 sniperd.py Config 类 |

---

## 六、进化参数（v4.0 新增 6 个）

| 参数 ID | Config 常量 | 默认 | 范围 | 说明 |
|:--|:--|:--|:--|:--|
| `sniper_l1_interval` | L1_INTERVAL | 3s | 1-10s | 持仓轮询间隔 |
| `sniper_alert_cooldown_p1` | ALERT_COOLDOWN_P1 | 120s | 60-300s | P1 告警冷却 |
| `sniper_alert_cooldown_p2` | ALERT_COOLDOWN_P2 | 300s | 120-600s | P2 告警冷却 |
| `sniper_alert_cooldown_entry` | ALERT_COOLDOWN_ENTRY | 600s | 300-1200s | 入场冷却 |
| `sniper_alert_cooldown_market` | ALERT_COOLDOWN_MARKET | 600s | 300-1800s | 大盘冷却 |
| `sniper_market_swing_threshold` | MARKET_SWING_THRESHOLD | 3.0% | 2-5% | 大盘异动阈值 |

> 加上 v3.0 原有 5 参数，狙击手模块共 11 个可进化参数。

---

## 七、部署与运维

```bash
# 启用服务（开机自动启动 + 交易日 09:29 自动唤醒）
systemctl --user enable sniperd.timer
systemctl --user start sniperd.timer

# 手动启动/停止
systemctl --user start sniperd.service
systemctl --user stop sniperd.service

# 查看日志
journalctl --user -u sniperd.service -f

# 单次扫描测试
python3 sniperd.py --once --dry-run

# 查看服务状态
systemctl --user status sniperd.service
```

---

## 八、风险矩阵

| 风险 | 等级 | 缓解措施 |
|:--|:--|:--|
| Sina API 限流 | 低 | 18只/3s 远低于限制 |
| 进程崩溃 | 中 | systemd Restart=always + 存活检测 cron |
| 误告警（数据尖刺） | 中 | P0 需 2 tick 确认 (6s) |
| 网络断连 | 中 | 连续错误计数，≤10 次静默恢复 |
| 内存泄漏 | 低 | 状态字典定期清理 |
| API 开销增加 | 低 | 批量查询(1 request/3s)，无 subprocess |
