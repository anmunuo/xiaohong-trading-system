# 推荐引擎超时修复 (v8.12 会话记录)

## 症状

- 推荐引擎 cron (08:35) 每次都超时 120s，`daily_pool.json` 永远停留在前一天
- 晨报 (08:30) 先于推荐引擎运行，永远吃昨天推荐池
- 自主修复引擎 `auto_repair.py` 所有管线脚本返回 rc=-1

## 根因链

### 1. `$HOME` 被 profile 系统覆盖

```
echo $HOME → /home/pc/.hermes/profiles/xiaohong/home  (不是 /home/pc！)
```

**影响**：
- `auto_repair.py` 中 `Path.home()` 返回错误路径 → `VENV_PYTHON` 指向不存在的 venv
- `cron_gold.sh` 中 `cd "$HOME/..."` 展开到错误路径 → Gold ETL 静默失败
- **修复**: 全部改为绝对路径 `/home/pc/.hermes/hermes-agent/venv/bin/python3`，`cd /home/pc/...`

### 2. `data fetch` CLI 是完整 hermes agent

```bash
which data → /home/pc/.local/bin/data  # hermes CLI
```

每调用一次 `data fetch stock --symbol XXX` = 启动一个完整的 hermes agent 进程。176 只股票 = 176 个 agent。

**影响位置**：
- `stock_recommender._prefetch_indicators` 的 subprocess 补漏
- `data_pipeline._core.get_stock_realtime` 的慢路径补漏

**修复**: 砍掉所有 subprocess 补漏逻辑，仅用 Baostock/Sina 直接 API。

### 3. Sina 批量 API URL 长度限制

407 只股票的 Sina URL 过长 → 服务器拒绝连接 → 所有 407 只落到 `data fetch` 慢路径。

**修复**: 
- `get_stock_realtime` 分批 100 只/批
- 同时砍掉 `get_stock_realtime` 的慢路径（避免每只 agent 调用）

### 4. 盘前 Sina 返回全 0

09:30 开盘前，Sina API 对所有股票返回 `close=0, change_pct=0`。

**影响**：
- `_get_suspended_codes()` 把全部股票标记为停牌（`close==0 AND change_pct==0`）
- `_gen_operation()` 同逻辑导致操作建议全是"停牌中"
- market_cap=0 导致评分基准失效

**修复**：
- 盘前用 Baostock 昨收补 Sina 的 0 值（`ind['close_history'][-1]`）
- `_get_suspended_codes` 不再用 `close==0` 判断（盘前全0不可靠）
- `_gen_operation` 同样移除 `close==0` 停牌判断

### 5. 推荐引擎三大瓶颈

| 瓶颈 | 耗时 | 修复 |
|------|------|------|
| subprocess 补漏 176 只 (`data fetch` CLI) | ~∞ (每个启动 agent) | **砍掉** |
| tushare PE 逐只查询 407 只 | ~82s | `--fast` 跳过 |
| 研究员 `analyze_stock()` 逐只 9 只 | ~60s | `--fast` 跳过 |
| 议会 `Parliament.execute()` | ~15s | `--fast` 跳过 |

**修复后耗时**: ~30s (Baostock 12s + Sina 2s + 打分 5s + 过滤 1s)

### 6. Cron 时序倒挂

```
❌ 旧: 08:30 晨报(用昨天池) → 08:35 推荐引擎 → 超时失败
✅ 新: 08:00 推荐引擎 --fast → 08:30 晨报(用今天池，context_from 依赖)
```

## 修改文件清单

| 文件 | 改动 |
|------|------|
| `stock_recommender.py` | `--fast` 模式(跳过研究员/议会/tushare PE)；砍掉 subprocess 补漏；盘前 Baostock 昨收复；Sina 分批 100；移除 `close==0` 停牌判断 |
| `cron_recommender.sh` | 加 `--fast` 参数 |
| `data_pipeline/_core.py` | 砍掉 `get_stock_realtime` 慢路径(data fetch per stock) |
| `auto_repair.py` | `Path.home()` → 绝对路径 |
| `cron_gold.sh` | `$HOME` → 绝对路径 |
| cron 调度 | 推荐引擎 08:35 → 08:00；晨报加 `context_from` |

## 验证方法

```bash
# 手动测试推荐引擎
time python3 stock_recommender.py --top 8 --fast

# 确认 daily_pool.json 日期是今天
python3 -c "import json; d=json.load(open('scripts/data/daily_pool.json')); print(d['date'], d['generated_at'])"
```
