# KB 知识库消化工作流

> 每小时 :05 cron 的 LLM 操作手册。输入 mega_latest.json → 输出 kb_insights.json。

## 步骤

### 1. 定位数据

```bash
ls -t /home/pc/.hermes/profiles/xiaohong/data/kb/mega_*.json | head -5
```

`mega_latest.json` 是最新快照，但同名文件每小时覆盖。上一小时的版本在 `mega_YYYYMMDD_HHMM.json`。

### 2. 对比增量

**关键原则**：不要只看 mega_latest.json，必须对比上一小时。如果所有模块 count 完全相同，说明无新数据——输出空数组或 [SILENT]。

```python
prev = mega_YYYYMMDD_prevHH.json
curr = mega_latest.json

for module in curr.modules:
    delta = curr[module].count - prev[module].count
    if delta > 0: 标记为增量信号
```

常见模块 delta 含义：
- `announcements` 增量 > 20 → 公告潮，检查回购/重组/ST 分布变化
- `hot_events` 从 0 → N → 热搜数据刚到达（通常延迟 2-3 小时），关注涨停集中度
- `broker_views` 从 0 → N → 研报数据刚到达，关注行业聚类
- `dragon_tiger` 增量 → 新交易日龙虎榜，关注板块分布

### 3. 提炼洞察

每条洞察必须：
- **来源可追溯**：`sources` 字段注明模块名
- **含具体数字**：占比/数量/幅度
- **有对比基准**：vs 上一小时 / vs 正常水平
- **不重复已有洞察**：检查 kb_insights.json 最近 2 批，同一主题不重复报

优先级：broker_views（机构信号）> hot_events（情绪极值）> industry_news（板块共振）> announcements（事件密度）> north_flow（资金信号，盘后静态不重复报）

### 4. 洞察类型决策

| 信号 | 类型 | 示例 |
|:--|:--|:--|
| 研报行业集中 > 30% | `sector_anomaly` | 通信设备 6/15=40% |
| 热搜涨停比 > 5:1 或 < 1:3 | `sentiment_shift` | 涨停/跌停 18:1 |
| 公告回购占比急剧变化 | `sector_anomaly` | 回购 77% vs 昨日 43% |
| 北向连续多日同向 | `fund_signal` | 连续3日净流入 |
| 龙虎榜板块切换 | `sentiment_shift` | 科技→周期轮动 |
| ST 风险升级 | `risk_alert` | 证监会立案调查 |

### 5. 保存

```python
# 读取现有 → 追加新批次 → 保留最近 50 条 → 写回
all_insights.append(new_batch)
all_insights = all_insights[-50:]
json.dump(all_insights, f, ensure_ascii=False, indent=2)
```

### 6. 静默规则

以下情况输出 `[SILENT]`（不推送）：
- 所有模块 count 与上一小时完全相同
- 仅 announcements 有微小增量（< 10 条）且无类型分布变化
- 盘后非交易时段（16:00-08:00）且无 broker_views / hot_events 增量

## 数据位置速查

```
/home/pc/.hermes/profiles/xiaohong/data/kb/
├── mega_latest.json          ← 最新快照（每小时覆盖）
├── mega_YYYYMMDD_HHMM.json   ← 历史快照
└── kb_insights.json           ← LLM 洞察（数组，最多 50 批）
```

## 已知问题

- **热搜名称空**：akshare `stock_hot_rank_em()` 返回的 name 字段经常为空，用 code 反查名称或用板块归类替代
- **盘后数据静态**：16:00 后 announcements/hot_events/dragon_tiger 通常不再更新，broker_views 可能在 03:00-04:00 批量到达
- **mega_latest.json 非原子写入**：极少数情况下读取时文件只写了一半，json.load 会报错——重试一次即可
