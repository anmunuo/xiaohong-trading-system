# 竞价分析系统 v1.0

> 09:15-09:25 竞价期间每 3 秒采集东方财富 API → SQLite 轨迹存储 → 五维特征提取 → 0-100 打分 → 侦察兵叠加 → Bayesian 闭环学习。

## 架构

```
09:15 🔬 auction_collector.py (cron)
        ├─ 读取 daily_pool.json → 目标股票列表
        ├─ 每 3s 轮询东方财富 push2 API (f43/f19/f20/f3)
        ├─ 写入 data/auction.db → auction_frames 表
        └─ 09:25 结束，~200 帧/只

09:25 🔍 scout.py --auction
        └─ 调用 auction_features.auction_signal(code)
              ├─ 五维特征提取 (price_slope/volume_accel/imbalance/premium/sector_dev)
              ├─ 0-100 综合评分
              └─ 叠加到侦察兵报告 → 🔥/📈/⚠️ 竞价信号

16:00 🧠 auction_learner.py (cron)
        ├─ 读取当日 auction_frames
        ├─ 提取特征 → 生成竞价信号
        ├─ 对比当日实际涨跌 (东方财富 API)
        ├─ Bayesian 更新: 命中→α+1, 未命中→β+1
        └─ 写入 data/auction_weights.json → 次日自动使用
```

## 五维特征

| 维度 | 权重 | 计算方式 | 信号 |
|------|:--:|------|------|
| 价格轨迹斜率 | 0.25 | (09:20后均价 - 09:15均价) / 前期均价 + W型检测 | 正=抢筹，负=抛压，W=分歧转一致 |
| 量能加速度 | 0.25 | 后半段量增速 / 前半段量增速 | >1.5 尾段爆量（强），<0.5 无人问津 |
| 委托不平衡 | 0.20 | 最后一帧量 / 帧均量 | >2.0 抢筹明显 |
| 开盘溢价率 | 0.15 | (开盘价 - 前收盘) / 前收盘 × 100 | 2-5% 最佳，>7% 高开低走风险 |
| 板块偏离度 | 0.15 | 个股涨跌 - 板块平均涨跌 | >2% 强势 |

## Bayesian 学习

```
初始: α=1, β=1 (每维度后验 = 50%)

每日盘后:
  竞价信号 bullish + 实际收涨 → α+1 (命中)
  竞价信号 bearish + 实际收跌 → α+1 (命中)
  否则 → β+1 (未命中)

后验权重 = α/(α+β) × 默认权重 × 2 (归一化)
```

## 侦察兵集成

```python
# scout.py --auction
from auction_features import auction_signal
result = add_auction_overlay(scout_result)
# → 每只侦察兵标的附加 auction_score + auction_signal
# → 报告增加竞价列: 🔥65 / 📈48 / ⚠️22
```

## 数据表

```sql
CREATE TABLE auction_frames (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    code TEXT NOT NULL,
    name TEXT,
    seq INTEGER NOT NULL,        -- 帧序号 (1-200)
    price REAL,                  -- 虚拟匹配价 (f43)
    volume REAL,                 -- 竞价量 (f19)
    amount REAL,                 -- 竞价额 (f20)
    change_pct REAL,             -- 涨跌幅 (f3)
    open_price REAL,             -- 开盘价 (f46)
    prev_close REAL,             -- 前收盘 (f60)
    recorded_at TEXT NOT NULL,   -- 采集时间戳
    UNIQUE(date, code, seq)
);
```

## 常见问题

| 问题 | 处理 |
|------|------|
| 周末/非交易时段无数据 | auction_collector 返回空，scout --auction 显示 — |
| 东方财富 API 限流 | 批量请求间隔 150ms，单票 8s 超时 |
| 空 DB 调用特征提取 | 返回 `{'error': 'no_data'}`，score=0, signal=neutral |
| 学习器无当日数据 | `diagnose_db()` 先诊断，显式输出根因+建议再跳过 |
| 推荐池为空 | `load_target_stocks()` 降级：默认蓝筹(6只) + TOP资金流(最多+6只) |

## v1.1 健壮性升级 (2026-06-01)

### 采集器加固 (`auction_collector.py`)

**痛点**：09:15 竞价初期东方财富 API 可能返回空数据或抛异常，原 `while is_auction_time()` 循环体无 try/except 保护，单次异常直接导致脚本崩溃退出（总帧=0，cron 标记 error）。

**修复**：

```
1. API 预热 — 进入 while 循环前先 ping 首只标的 3 次（间隔 2s）
2. 整轮 try/except — while 循环体用 try/except 包裹，单轮失败不中断
3. 连续失败计数 — consecutive_failures ≥ 10 → 退出（防无限空转）
4. 失败降噪 — 前 3 次失败逐条输出，之后每 5 次输出一次
5. conn.rollback() — 异常时回滚 SQLite 事务
6. cron_auction.sh — sleep 10 延迟到 09:15:10 启动，避开 API 冷启动
```

### 学习器加固 (`auction_learner.py`)

**痛点**：auction.db 为空时只打印 `⚠️ 无竞价数据` 后静默跳过，无从判断是采集器坏了还是真的无数据。

**修复**：

```
1. diagnose_db(date) — 查询 DB 状态（总行数/当日行数/标的数/帧数/历史日期）
2. learn_from_date() 先诊断后学习 — 空数据时输出明确诊断+建议
3. --diagnose CLI — 独立诊断入口，可指定日期
```

**诊断输出示例**：

```
⚠️ auction.db 完全为空（0行），竞价采集器可能从未成功运行
💡 检查: ① 09:15 cron是否触发 ② 东方财富API是否可达 ③ 默认标的是否有效
```
