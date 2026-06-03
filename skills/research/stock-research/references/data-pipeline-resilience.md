# 数据管线韧性模式 v1.0

> 2026-06-03 会话总结：三次数据故障 + 自动健康检查体系

---

## 故障 1: 东方财富 push2 f62 字段盘中归零

**症状**：侦察兵「双重确认」永远为 0，所有 `net_flow` 字段为 `0.0` 万元。

**根因**：东方财富 `push2.eastmoney.com/api/qt/clist/get` 的 `f62`（主力净流入）、`f66`（超大单）、`f69`（大单）、`f184`（小单）字段在盘中间歇性全部返回 0。涨跌幅 `f3` 正常。

**修复链**：
1. `get_top_flow_stocks()` — f62 健康检测：TopN 的 `net_flow` 全为 0 时，自动切换动量 fallback（`abs(涨跌幅)×0.7 + 换手率×0.2 + 量比×0.1`），`net_flow` 置 None、`_quality` 标记 `fallback`
2. `check_data_health()` — 新函数，探测 10 只样本统计 `f62_valid`/`f184_valid`/`f66_valid` 比率，<30% 返回 `status: degraded, flow_field: momentum`
3. `scout.py` `run_scout()` — 开头调用 `check_data_health()`，动量模式放宽涨跌幅门槛（±3%），报告显示「⚠️ 数据源降级」

**关键教训**：API 字段间歇性归零是常见模式，必须在每次调用后做健康检测，不能假设字段永远有效。

---

## 故障 2: 市值过滤器形同虚设

**症状**：立讯精密（5391亿）、中际旭创（13287亿）等万亿巨头通过侦察兵筛选。

**根因**：
1. Sina 实时 API 不含 `market_cap` 字段 → `is_market_cap_ok(code)` 永远读不到市值 → 全部通过
2. 东方财富 push2 虽有 `f20`（总市值），但未传递到过滤逻辑
3. `f20` 单位是**元** → 转亿需 `÷1e8`（错误用了 `÷1e4`）

**修复链**：
1. `get_top_flow_stocks()` — 输出中加入 `total_mv`（`f20 / 1e8`，元→亿）
2. `is_market_cap_ok(code, pre_fetched_mv)` — 新增参数，优先用预取市值
3. 侦察兵循环 + `feed_intraday_pool()` — 传 `s.get('total_mv')`
4. `feed_intraday_pool()` 的 `new_entries` — 保留 `net_flow`/`change_pct`/`_quality`

**关键教训**：跨 API 字段传递时必须验证单位转换（东方财富元→亿 ÷1e8，tushare 万元→亿 ÷1e4），并在中间结构体保留源字段。

---

## 故障 3: review.py 盘后选股复盘永远为空

**症状**：每日文工团复盘显示「今日无涨幅 ≥6% 数据（非交易日或数据未就绪）」，即使当天是交易日。

**根因**（三重）：
1. `po` 参数方向错误：`po=1`（升序）+ `fid=f3` → 取跌幅最大 50 只 → 筛涨≥6% 永远空。正确应为 `po=0`（降序）。此前 v3.0 将 `po=0→po=1` 的"修复"方向是反的
2. 东方财富 push2 盘后/晚间 HTTP 000 不可达（已知行为），cron 17:00 运行时 API 已关闭
3. 无回退数据源

**修复链**：
1. `po=1` → `po=0`（`fid=f3` 取涨幅降序）
2. 新增 tushare daily 回退：`pro.daily(trade_date=today)` → 自算涨跌幅 → 批量 `stock_basic` 补名称
3. cron 从 17:00 提前到 15:30（盘后即跑）
4. `system_health_check.py` 增加 `push2_gainers` 专项检测（po=0 取 top5 → 验证 top_chg≥5%）

**关键教训**：东方财富 push2 的 `po` 参数 `0=降序`、`1=升序`。每次盘后操作必须有一个非 push2 的回退通道。

---

## 自动健康检查体系

`system_health_check.py` — 7 维扫描，每次发现问题以非零 exit code 退出，cron 自动推送告警。

### 7 个维度

| 维度 | 检查项 | 关键判据 |
|------|------|------|
| 1. 数据新鲜度 | mega_latest / daily_pool / kb_insights / holdings / market_snapshot | 文件 mtime 年龄 vs 阈值 |
| 2. 持仓估值 | holdings.json | lastPrice 不为 None/0 |
| 3. 议会链路 | daily_pool.json | parliament.bias 字段存在 |
| 4. 弹药库风控 | holdings.json | R值/回撤/净值已更新 |
| 5. 数据管线 | push2_list(f62) + push2_gainers(po=0) + sina + tushare + baostock | 4+路连通性 |
| 6. 侦察兵 | 最近输出文件 | 运行时次 + 数据源降级标记 |
| 7. 研究员质量 | 研学报告 | 内容非空壳（非仅"自主学习完成"） |

### Cron 时间

| 时间 | 意义 |
|------|------|
| 08:15 | 开盘前 — 数据就绪、侦察兵准备 |
| 15:15 | 收盘后 — 估值同步、风控状态 |
| 22:15 | 夜间 — 数据管线、研究员质量 |

### 路径

所有路径以 `WORKSPACE = SCRIPT_DIR.parent`（`~/.hermes/profiles/xiaohong/`）为基准，不是 `SCRIPT_DIR`。
