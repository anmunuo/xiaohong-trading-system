# 数据管线韧性陷阱 (v8.12 更新)

## 🆕 `data fetch` CLI 是完整 agent — 禁止用 subprocess 逐只调用！

```bash
which data → /home/pc/.local/bin/data  # hermes CLI
```

每次 `subprocess.run(['data', 'fetch', 'stock', '--symbol', code, ...])` 启动完整 hermes agent。

| 调用方式 | 1只耗时 | 176只耗时 | 可行？ |
|----------|---------|-----------|--------|
| Sina 批量 HTTP | <0.05s (全量) | — | ✅ |
| Baostock ProcessPool | ~10s (全量) | — | ✅ |
| `data fetch` subprocess | ~10s/只 (agent 启动) | ~1760s | ❌ |

**修复**: `get_stock_realtime` 和 `_prefetch_indicators` 的 subprocess fallback 已移除。
Sina/Baostock 覆盖不足的码由上层容错处理——宁可缺数据，不可让 agent 洪水淹死管线。

## 🆕 Sina 批量 API URL 长度限制

>200 只股票时 Sina URL 被拒。**修复**: 100 只/批。

## 🆕 盘前 Sina 返回全 0 (v8.12)

09:30 开盘前 Sina 返回 `close=0, change_pct=0` 对所有股票。

**不要**用 `close==0 AND change_pct==0` 判断停牌——盘前全市场都是这个信号。
**修复**: 用 Baostock 昨收(`ind['close_history'][-1]`) 补 Sina 的 0 值。

## 🆕 `$HOME` 被 profile 覆盖

Profile 模式下 `$HOME` 指向 `<profile>/home`，非真实 `/home/pc`。
`Path.home()` 和 `$HOME` shell 变量都必须替换为绝对路径。

## 已有陷阱（保留）

### push2 f62 归零 (v4.1)
东方财富 push2 `f62`(主力净流入)盘中偶发全0 → 需 `check_data_health()` 健康检测 + 动量 fallback。

### push2 盘后不可达 (v4.2)
盘后 HTTP 000，`review.py` 的 push2 涨幅榜需回退 tushare。

### 市值过滤 → Sina 无 market_cap
Sina 实时行情 API 不含 `market_cap` 字段 → 过滤时必须用 push2 `f20`(元÷1e8) 或 tushare `total_mv`(万元÷1e4) 预取市值。

### po=0 是降序(高到低)
`review.py get_top_gainers()` po=0=降序取涨幅最大。po=1 方向反了。
