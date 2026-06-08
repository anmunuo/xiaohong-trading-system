---
name: stock-research
description: 小红股票投研工作流 —— 数据获取、筛选、分析的全链路规范
triggers:
  - "分析.*股票"
  - "自选池"
  - "筛选.*股票"
  - "选股"
  - "股票.*研究"
  - "基本面.*分析"
  - "技术面.*分析"
  - "买卖点"
  - "催化剂"
  - "交易系统|策略分析"
  - "资源池|事件驱动"
  - "瞭望塔|晨报|瞭望塔晨报|盘前报告"
  - "侦察兵|开盘确认|竞价分析|集合竞价|auction|自主学习.*优化|盘中.*更新|盘中.*扫描|推荐池.*更新|三级认证|盘中.*决策|目标池|target_pool|盘中入池|日内.*入场"
  - "狙击手|日内监控|止损.*监控|入场信号|开仓.*动作|量比.*入场|分时K线.*入场"
  - "弹药库|仓位.*上限|行业集中度|回撤.*追踪|风控.*检查"
  - "文工团|每日复盘|选股复盘|涨幅.*6%|纪律.*清单|错误.*归类"
  - "交叉验证|多维选股"
  - "自查.*数据|假数据|虚构|数据真实"
  - 知识库|知识库检索|每小时采集|最新线索|SQLite.*知识库|stock_kb|本地.*数据库
  - 个股.*事件|公告|新闻.*爬取|消息.*传言|催化.*事件|event.*type
  - "Skills.*MCP|claude-trading-skills|Skills架构"
  - "交易系统.*架构|系统全景|整体架构"
  - "部署|Docker.*交易|硬件盒子|Pi.*交易"
  - "TradingSkill|交易系统升级|产品化|硬件盒子|小程序|MCP|商业化|PRD|产品需求"
  - 进化引擎|自动进化|LLM复盘|全域进化|推荐池.*逻辑|推荐引擎|诊断.*执行|沙箱.*超时|沙箱.*验证
  - 因子.*分析|因子IC|因子.*有效性|ICIR|因子.*淘汰|新因子
  - 组合风控|VaR|CVaR|相关性.*矩阵|压力测试|portfolio.*risk
  - ML.*预测|机器学习|LightGBM|涨跌.*预测|ml_predictor
  - 券商.*对接|broker|xtquant|easytrader|实盘.*下单|paper.*trading
  - 对标.*系统|交易日志|结构化日志|Paper Trading
  - 美化|格式化|架构图|报告.*美化|SVG|boxes|ascii|excalidraw
  - 健康检查|自检|系统健康|system_health|health_check|7维扫描|11维扫描|12维扫描
  - "cron.*污染|cron.*行号|脚本.*行号"
  - 研究员|助理研究员|议会|多方|空方|数据研究员|基本面研究员|技术面研究员|协同研究|研究员.*个股|查.*个股.*分析|--query|query_stock|analyze_stock
  - 自主修复|auto_repair|auto_heal|健康检查.*修复|health_check.*fix|系统自愈
  - ETF.*分析|分析.*ETF|指数.*基金|创新药.*ETF|行业.*ETF
  - gold.*ETL|Gold.*层|因子面板.*构建|factor.*panel|分层数据.*Gold|数据血缘|gold.*pipeline
  - 目标池|target_pool|盘中决策|三级认证|intraday_gate|快速议会|quick_parliament|盘中.*目标池|当日可操作
  - 涨幅榜.*学习|winner.*study|6%.*个股.*研究|涨幅.*关联性|winners
---

# 小红 · 股票投研工作流

## ⛔ 铁律

**禁止凭空捏造数据或标的。** 所有代码、估值、财务数据必须来自真实数据源。不得拍脑袋预设自选池、不得编造 PE/PB/ROE 数值、不得在没有数据的情况下断言涨跌逻辑。

当不确定数据是否可用时，先探测，再说话。宁可不给结论，不给假结论。

**大规模改动必须先展示方案**：涉及系统架构变更、多模块重构、新产品化功能时，必须先输出完整技术方案（架构全景 + 优化项 + 执行顺序 + 风险评估），待用户审阅确认后再动手编码。禁止跳过方案阶段直接写代码。

**故障修复不用问，直接深入并修复 + 加检查机制**：遇到 cron 报错、数据异常、系统故障时，**不要先问用户「要不要修复」**。直接：(1) 深入排查根因（拉原始数据、对比字段、追溯调用链），(2) 一次性全量修复所有相关代码路径，(3) 添加自动健康检查/监控机制（如 `check_data_health()`、字段有效性检测、`_quality` 标记），确保同类问题能被自动发现而非依赖人工看到 cron error。修复完成后简洁汇报。这是用户明确的 workflow 偏好。

---

## 数据源能力矩阵

### data_pipeline 统一管道（⭐ 推荐首选）

位于 `~/.hermes/profiles/xiaohong/scripts/data_pipeline.py`。

```bash
cd ~/.hermes/profiles/xiaohong/scripts
python3 -c "from data_pipeline import get_index_data; print(get_index_data())"
```

封装了 Tushare/AKShare/东方财富/Sina/**BaoStock 五源聚合**，内置 2-5 分钟缓存和自动 fallback。覆盖：全球指数、北向资金、板块排名、个股资金流向、选股推荐、历史K线+MA。

**核心 API 速查**：

| 函数 | 用途 | 参数 |
|------|------|------|
| `get_index_data()` | 全球指数（美/欧/亚） | 无 |
| `get_north_flow()` | 北向资金流向 | 无 |
| `get_sector_flow_rank(sector_type='3')` | 板块资金排名 | sector_type: 行业分类 |
| `get_top_flow_stocks(n=10, no_cache=False)` | 个股净流入 TOP N 🆕 v4.1: f62 健康检测+动量 fallback | n: 返回数量 |
| `get_market_money_flow()` | 全市场主力/散户资金 | 无 |
| `get_stock_realtime(codes: list)` | 个股实时日线 (OHLCV) | codes: 代码列表 |
| `get_historical_k_with_ma(codes, days=30)` | BaoStock 历史K线+MA5/10/20+peTTM/pbMRQ (ProcessPool 8x加速) | codes: 代码列表, days: 回溯天数 |
| `check_data_health()` | 🆕 数据源健康检查 (f62/f184/sina) → status+flow_field | 无 |
| `get_intraday_minutes(code, scale=5, count=48)` | 分时K线 (Sina) | code: 纯数字, scale: 1/5/15/30/60 |
| `get_intraday_volume_alert(code, scale=5)` | 分时量价异动检测 🆕 | code: 纯数字 |
| `get_financial_indicator(stock_code, period=None)` | 核心财务指标 (ROE/毛利率/负债率/现金流等13项) 🆕 | stock_code: '000001.SZ' |
| `get_financial_summary(stock_code)` | 财务综合评分(0-100) + 亮点/风险 🆕 | stock_code: 纯数字或不带后缀 |
| `get_historical_k_with_ma(codes, days=30)` | BaoStock 历史K线+MA5/10/20+peTTM/pbMRQ (ProcessPool 8x加速) | codes: 代码列表, days: 回溯天数 |
| `check_data_health()` | 🆕 数据源健康检查 (f62/f184/sina) → status+flow_field | 无 |
| `get_intraday_minutes(code, scale=5, count=48)` | 分时K线 (Sina) | code: 纯数字, scale: 1/5/15/30/60 |
**resource_pool 核心 API**：

| 函数 | 用途 | 返回 |
|------|------|------|
| `build_resource_pool()` | 全量事件采集 | `{announcements, research_reports, policy_news, sector_analysis, summary}` |

> ⚠️ `resource_pool` 导出的是函数 `build_resource_pool()`，非 `ResourcePool` 类。

**v4.0 `get_stock_realtime(codes: list)`**：**Sina 批量 HTTP 快路径优先**（单次请求 ~800 只，<0.05s），失败时 fallback 到 `data fetch` CLI。内置 2 分钟模块级缓存。**禁止在循环中逐只调用**——一次性传所有 code 即可。返回 `{code: {close, change_pct, open, high, low, volume, amount, name, data_source, trade_date}}`。

**安全注意**：Tushare Token 已从硬编码移至 `~/.hermes/profiles/xiaohong/.env`（`TUSHARE_TOKEN=`），`_load_tushare_token()` 自动从 env 或 .env 文件加载。**禁止在代码中硬编码任何 API key。**

**holdings.json 实时估值字段**：运行 `python3 scripts/ammo_risk.py --update` 同步写入 `lastPrice / marketValue / unrealizedPnL / pnlPct / lastUpdate`，同时更新 `currentNetValue` 和触发移动止盈计算。

完整 API 见 → `references/data-source-cheatsheet.md`。

### SQLite 本地知识库 (stock_kb.py v1.1) 🆕

位于 `~/.hermes/profiles/xiaohong/scripts/stock_kb.py`，将所有 A 股历史数据爬取到本地 SQLite，毫秒级查询，不依赖远程 API。

```bash
# 查询单票（行情+财务+事件一键）
python3 scripts/stock_kb.py --query 600519

# 条件筛选
python3 scripts/stock_kb.py --query "ROE>15 PE<20" --query-type screen

# 事件/公告/新闻
python3 scripts/stock_kb.py --query 600519 --query-type events --limit 20
python3 scripts/stock_kb.py --query 600519 --query-type event_summary

# 数据库统计
python3 scripts/stock_kb.py --stats
```

**6 表设计**: `stocks`(主表) / `daily_kline`(日K+MA+PE/PB) / `financials`(ROE/毛利率等) / `fund_flow`(主力资金) / `index_daily`(5大指数) / `stock_events`(公告/新闻/传言)。

**3 数据源**: akshare(列表+财务+事件) / baostock(K线+指数) / tushare(备用)。全量初始化约 75 分钟，之后 `--update` 增量秒级。

**常见查询模式**:
```python
from stock_kb import StockKBQuery
q = StockKBQuery('data/stock_kb.db')
q.get_kline('600519', start='2025-06-01')        # K线
q.screen_stocks({'min_roe': 15, 'max_pe': 20})   # 筛选
q.get_events(code='600519', days=30)              # 事件
q.get_event_summary('600519')                     # 事件画像
```

> 完整 API 和陷阱见 → `references/stock-kb-design.md`

### data fetch CLI（便捷但受限）

| 能力 | 状态 | 用法 |
|------|:--:|------|
| 单票行情 | ✅ | `data fetch stock --symbol 600519 --category quote` |
| 单票日线 | ✅ | `data fetch stock --symbol 600519 --category daily --days 30` |
| 单票财报 | ✅ | `data fetch company --symbol 600519 --category overview` |
| 龙虎榜/北向/涨停 | ❌ | 返回 "please specify --symbol" |
| 全市场筛选 | ❌ | 无此接口 |

**结论：data fetch CLI 只能做单票查询，不能做市场级扫描。**

### 交易日志与执行（v2.0 新增）

| 模块 | 对标 TradingSkill | 入口 |
|------|:--:|------|
| 自动执行器 | `executor.ts` | `python3 scripts/auto_executor.py --once --paper` |
| 交易日志 | `logger.ts` | `python3 scripts/transaction_logger.py stats` |
| Docker 部署 | Dockerfile | `docker-compose up trading-engine -d` |

详见 → `strategy-trading` skill、`references/tradingskill-benchmark.md`

### akshare 直调（补充能力）

通过 `python3 -c "import akshare as ak; ..."` 直接调用。

| 功能 | 函数 | 验证状态 |
|------|------|:--:|
| 涨停板池 | `ak.stock_zt_pool_em(date='YYYYMMDD')` | ✅ |
| 龙虎榜 | `ak.stock_lhb_detail_em(start_date, end_date)` | ✅ |
| 热度排行 | `ak.stock_hot_rank_em()` | ✅ |
| 北向历史 | `ak.stock_hsgt_hist_em(symbol='沪股通')` | ✅ (近期NaN) |
| 沪A实时 | `ak.stock_sh_a_spot_em()` | ⚠️ 限流断连 |
| 深A实时 | `ak.stock_sz_a_spot_em()` | ⚠️ 同上 |
| 公司公告 | `ak.stock_notice_report(symbol='全部', date='YYYYMMDD')` | ✅ 1500+条/日 |
| 券商研报 | `ak.stock_research_report_em(symbol='000001')` | ✅ 评级+盈利预测 |
| 经济日历 | `ak.news_economic_baidu(date='YYYYMMDD')` | ✅ 宏观数据发布 |
| 东方财富新闻 | `ak.stock_news_em()` | ✅ 个股市场新闻 |

### ⚠️ 期权函数（场内 ETF 期权专用）

> 🚨 场外个股期权无公开 API，不走这些函数。仅场内 ETF 期权可用。

| 功能 | 函数 | 状态 |
|------|------|:--:|
| 期权链 | `ak.option_sse_list_sina()` / `option_sse_codes_sina()` | ✅ |
| 实时行情 | `ak.option_current_em()` | ✅ |
| Greeks | `ak.option_sse_greeks_sina()` | ✅ Delta/Gamma/Theta/Vega/Rho+IV |
| QVIX | `ak.index_option_50etf_qvix()` / `_300etf_qvix()` | ✅ |

### tushare 直调（全市场筛选主力）

通过 `python3 -c "import tushare as ts; pro = ts.pro_api(); ..."` 直接调用。

| 功能 | 函数 | 关键字段 |
|------|------|----------|
| 全A列表 | `pro.stock_basic()` | ts_code, name, industry, list_date |
| 全市场估值 | `pro.daily_basic(trade_date=...)` | pe_ttm, pb, ps_ttm, total_mv, circ_mv |
| 财务指标 | `pro.fina_indicator(ts_code=...)` | roe, roa, netprofit_margin, tr_yoy, debt_to_assets |
| 竞价汇总 🆕 | `pro.stk_auction(ts_code=..., trade_date=...)` | vol, price, amount, pre_close, turnover_rate, volume_ratio |
| 同花顺板块 | `pro.ths_daily(trade_date=...)` | ts_code, name, pct_chg (板块涨跌) |
| 全市场资金流 | `pro.moneyflow(trade_date=...)` | buy/sell_elg/lg/md/sm_amount, net_mf_amount |

### 腾讯行情 (qt.gtimg.cn) 🆕

```
GET https://qt.gtimg.cn/q=sz000001,sh600519
```

47+字段：五档买卖盘口、量比、涨跌停价、换手率、市盈率、总市值。批量查询逗号分隔。竞价期开盘价字段同步更新虚拟匹配价。字段映射见 `references/multi-channel-data-pattern.md`。

### BaoStock 直调（历史K线+MA，推荐引擎快路径）🆕

```python
import baostock as bs
bs.login()
rs = bs.query_history_k_data_plus('sh.600519',
    "date,open,high,low,close,volume,amount,turn,peTTM,pbMRQ",
    start_date='2026-05-01', end_date='2026-06-02',
    frequency='d', adjustflag='2')
bars = rs.data  # ⚠️ 必须用 rs.data，rs.next() 会阻塞 60s+
bs.logout()
```

| 功能 | 字段 | 说明 |
|------|------|------|
| 历史K线 | date,open,high,low,close,volume,amount | 前复权(adjustflag='2') |
| 估值 | peTTM, pbMRQ | 滚动市盈率+市净率 |
| 活跃度 | turn | 换手率 |
| **不支持** | ~~ma5,ma10,ma20~~ | ❌ 报错 10004012，需自算 |

**v8.5 并行化**：`get_historical_k_with_ma()` 使用 `ProcessPoolExecutor`（8 workers，~50 只/进程），每进程独立 `bs.login()` → 查询 → `bs.logout()`。528 码从 87.8s → 10.8s（8x 加速）。

**为什么用 ProcessPool 而非 ThreadPool？** baostock 底层共享全局 HTTP session，ThreadPool 并发导致 utf-8 解码乱码（服务端返回被不同线程交叉读取）。ProcessPool 每进程独立模块状态，天然隔离。

**关键陷阱**：

| 陷阱 | 现象 | 修复 |
|------|------|------|
| `rs.next()` 迭代器阻塞 | 单次调用卡 60s+ | **必须用 `rs.data`**（list of lists） |
| MA 指标字段不支持 | 报错 10004012 | 从 close 自算 MA5/MA10/MA20 |
| ThreadPoolExecutor 并发 | utf-8 decode error + 乱码 | 改用 ProcessPoolExecutor |
| ProcessPool + 闭包 | `Can't pickle local object` | worker 必须是**模块级函数** |
| 并发过高 | 服务端拒绝/乱码 | 限制 8 workers，batch 50 只/进程 |

详见 `references/baostock-integration.md`。

---

### 数据单位陷阱

- tushare `total_mv` / `circ_mv` 单位是**万元**，转亿需 **÷ 1e4**（不是 ÷ 1e8）
- **东方财富 push2 `f20`（总市值）单位是元**，转亿需 **÷ 1e8**（不是 ÷ 1e4）⚠️ 与 tushare 不同！
- tushare `daily_basic` 的 `trade_date` 格式是 `YYYYMMDD` 字符串
- tushare `daily_basic` **不支持批量多码查询**（逗号分隔返回 0 行），必须逐只查询
- tushare `daily_basic` **不含 `roe` 字段**，`roe` 需从 `fina_indicator` 获取
- akshare 日期格式视函数而定，有的用 `YYYYMMDD`，有的用 `YYYY-MM-DD`

---

## 筛选工作流

### 标准流程

```
1. pro.stock_basic() → 全A列表 (5522只)
2. pro.daily_basic(trade_date=TODAY) → 估值数据
3. merge → 清洗(去ST/去退市/dropna PE+MV) → 3913有效
4. 应用筛选条件
5. 计算综合评分 → Top N
6. 对Top N逐只拉财务深度数据 → 输出
```

### 筛选条件参考（基于 2026-05-22 真实分布）

PE_TTM 分布 (N=3961):
- 1%: 6.6 | 5%: 12.3 | 10%: 15.5 | 25%: 25.5
- 50%: 49.8 | 75%: 108.9 | 90%: 250.3

PB 分布 (N=3961):
- 1%: 0.55 | 25%: 1.85 | 50%: 2.92 | 75%: 5.00 | 95%: 13.04

### 常见问题

| 症状 | 根因 |
|------|------|
| 筛选结果全是银行 | PE/PB 权重过高 + 未加 ROE/增长因子 |
| 筛选结果 0 只 | 条件过严或单位换算错误 |
| akshare 断连 | 东方财富限流，换 tushare 或稍后重试 |
| tushare Python 直连报 token error | 直接用 `data fetch` CLI 替代，CLI 自带凭证管理 |
| akshare `stock_zh_a_spot_em()` RemoteDisconnected | 东方财富实时行情限流，换 `data fetch stock` 或等 10 分钟重试 |
| akshare 新闻标题为空 | `stock_news_em` 有时截断，改用浏览器直接搜东方财富搜索页 |
| akshare cron 输出污染 | tqdm 进度条输出到 stdout，在脚本开头加 `os.environ['TQDM_DISABLE'] = '1'` |
| akshare `stock_notice_report` 历史数据 | 无参调用返回 2022 数据，必须传 `date='YYYYMMDD'` |
| ⭐ BaoStock `rs.next()` 阻塞 60s+ | **必须用 `rs.data` 直接读 list**。`rs.next()` 是迭代器模式，在生产环境会无限阻塞。正确用法：`for row in rs.data: ...`。字段索引与 `fields` 参数顺序一致，需显式映射。详见 `references/baostock-integration.md` |
| ⭐ BaoStock ThreadPool 并发乱码 | **baostock 非线程安全**。底层共享全局 HTTP session，ThreadPool 并发导致 utf-8 decode error + 服务端数据交叉读取。**必须用 ProcessPoolExecutor**，每进程独立 `bs.login()` → 查询 → `bs.logout()`。`get_historical_k_with_ma()` v8.5 已改为 ProcessPool（8 workers, batch 50只/进程, 528码 87.8s→10.8s） |
| ⭐ ProcessPool pickle 闭包失败 | `Can't pickle local object '_worker'` → worker 函数必须是**模块级**（非闭包）。`data_pipeline.py` 采用 `_baostock_batch_worker(args)` tuple 传参绕过。tushare 基本面并行化可用 ThreadPool（独立 `pro_api` 实例，10 workers） |
| ⭐ 竞价学习器 v1.0 目标函数错误（做多系统不应为"猜对下跌"加分） | **根因**：v1.0 `caution + actual<0 → hit +α`，下跌市中永远猜跌得高分，但对做多系统毫无价值。v2.0 改为做多导向：`strong/moderate+涨→learn +α`、`strong/moderate+跌→penalize +β`（假突破）、`caution+跌→skip`（熊市噪音）、`caution+涨→penalize +β`（漏掉反转）。详见 `auction_learner.py` v2.0。 |
| ⭐ **反复回归** Cron 脚本行号污染 (v8.10→v8.12) | **根因**：`cron_*.sh` 文件内容被写入带 `     N|` 行号前缀（如 `     1|#!/bin/bash`），bash 无法解析 shebang 报 `未找到命令` → exit 2。**此问题会反复回归** — 健康检查上次运行没问题不代表这次没问题，每次 cron 扫描都要检查。**诊断**：`xxd cron_scout.sh | head -3` 看首字节是否为 `2020 2020 2031 7c`（空格+`1|`）而非 `2321`（`#!`）。**修复**：`python3 -c "import re; [open(f,'w').write(re.sub(r'^\s*\d+\|','',open(f).read(),flags=re.MULTILINE)) for f in ...]"` 或 `sed -i 's/^[[:space:]]*[0-9]\+\|//' cron_*.sh`。**自动防御**：`system_health_check.py` v1.2 维度12 + `auto_repair.py` `_clean_cron_line_numbers()` 自动清理。
| ⭐ **BaoStock 日期格式必须是 YYYY-MM-DD** | **致命 bug**：`bs.query_history_k_data_plus()` 的 `start_date`/`end_date` 只接受 `YYYY-MM-DD` 格式。传入 `YYYYMMDD` 不会报错但返回 `rs.error_msg='日期格式不正确，请修改'` 且 `rs.data` 为空，导致全部 K 线写入静默失败。`stock_kb.py` v1.0 因此 4915 只股票全返回 0 条。**修复**：所有调用点必须：1) 默认参数用 `'2020-01-01'`，2) 接收外部参数时加格式转换 `if len(start_date)==8: start_date=f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"`。baostock 没有此问题的文档说明。 |
| ⭐ **SQLite INSERT OR REPLACE 列/值数量不匹配静默失败** | **致命 bug**：`INSERT OR REPLACE INTO t(c1,c2,...,c13) VALUES (?,?,...,?)` 当 VALUES 的 `?` 数量与列名数量不一致时，SQLite 报 `X values for Y columns` 错误。此错误在 `try/except Exception: continue` 块中被静默吞掉，进度日志正常（`进度: 4915/4915, 累计 0 条`），极易误判为数据源问题。`stock_kb.py` v1.0 因 13 列只写 12 个 `?` 浪费数小时调试。**防御**：1) 用命名参数 `INSERT ... VALUES (:code, :date, ...)` 而非位置 `?`，2) 新表建立后立即 `INSERT` 一条测试数据验证列数，3) `except Exception` 至少打 `_log.warning`。 |
| akshare `stock_zt_pool_em` 列名不同于文档 | 涨停板列名是 `封板资金`、`连板数`（非 `封单金额`），最新价列是 `最新价`；跌停用 `stock_zt_pool_dtgc_em` |
| 东方财富 API 周末/晚间限流 | 非交易时段 `_em_api_get` 返回 None 或 RemoteDisconnected，属正常现象。代码中 `try/except` 兜底即可，不可据此判断 API 故障 |
| `_em_api_get` 批量请求限流 | 单票请求间隔 ≥150ms，批量时用 `time.sleep(0.15)` 避免触发东方财富反爬 |
| ⭐ 侦察兵 `is_market_cap_ok` 依赖不存在字段 | `get_stock_realtime()`（Sina API）**不含 `market_cap` 字段**，`is_market_cap_ok(code)` 永远读不到市值 → 全部通过（含万亿巨头）。**修复**：(1) `get_top_flow_stocks()` 加入 `total_mv`（push2 的 `f20` 字段，元→亿 ÷1e8），(2) `is_market_cap_ok(code, pre_fetched_mv)` 优先用预取市值，(3) `feed_intraday_pool()` 同样传预取市值，(4) `new_entries` 构造时保留 `net_flow`/`change_pct`/`_quality` 字段避免 format_report KeyError。修复后立讯精密5391亿、中际旭创13287亿等大市值股正确排除 |
| 竞价采集器 09:15 数据为空 | 东方财富 API 竞价初期冷启动（数据延迟）→ 脚本加 `sleep 10` + API 预热 3 次重试，`while` 循环外层加 `try/except` 隔离单轮失败 |
| 竞价采集器推荐池空时无标的 | `load_target_stocks()` 降级到默认蓝筹(6只) + `get_top_flow_stocks(6)` 资金流 TOP，确保始终有采集目标 |
| ⭐ `review.py` 盘后选股复盘无数据 | **双重根因**：(1) `po=1` 取跌幅最大50只→筛涨≥6%永远空（已修正为 `po=0`），(2) 东方财富 push2 API 盘后 HTTP 000 不可达，cron 17:00 运行时 API 已关闭。**修复**：(1) `get_top_gainers()` 主通道 push2(po=0) + 回退通道 tushare daily（`pro.daily(trade_date=today)` → 自算涨跌幅+批量 `stock_basic` 补名称），(2) cron 提前到 15:30，(3) `system_health_check.py` 增加 `push2_gainers` 专项检测 |\n| auction.db 为空导致学习器空转 | `auction_learner.py --diagnose` 先诊断 DB 状态，空数据时输出可操作建议而非静默跳过 |
| ⭐ 竞价学习器 v1.1.0 `main()` 盲取昨天导致空转（cron 16:00 永远找不到当日数据） | **根因**：`main()` 无 `--date` 时盲取 `yesterday=datetime.now()-timedelta(1)`。cron 16:00 在当天收盘后运行，应学习当天（如 6/3）竞价数据，但代码查的是前一天（6/2）→ auction.db 有 6/3 数据但被跳过。**修复 v1.1.1**：新增 `_get_latest_date_in_db()`，`SELECT MAX(date) FROM auction_frames` → 自动适配跨日/周末。DB 为空时才回退到昨天。`python3 auction_learner.py --reset && python3 auction_learner.py` 验证修复。 |
| 狙击手 v4.0 守护进程异常 | `systemctl --user status sniperd.service` 检查状态；存活检测 cron 每 5 分钟自动恢复；`python3 sniperd.py --once --dry-run` 手动测试；日志在 `data/sniper_logs/` |
| 弹药库双重净值不同步 | `accountInfo.currentNetValue` 和 `riskManagement.currentNetValue` 不一致。v4.1 统一到前者，运行 `ammo_risk.py --update` 自动修复 |
| 弹药库 R 值不更新 | v4.0 及以前 R 值永不自动计算。v4.1 每次 --update 重算。`grep currentRValue data/holdings.json` 验证 |
| 弹药库 cron 忘了 --update | 不加 --update 只出报告不写数据，移动止盈和回撤永不更新。v4.1 cron 已修正 |
| 弹药库流动性误判 | v4.0 用当日成交额（不完整），v4.1 改 5 日均量 |
| `get_stock_realtime` 在循环中逐只调 | **禁止**。应一次传入全部 code 列表，函数内置 Sina 批量 HTTP 快路径（~800只/请求，<0.05s）。在循环中逐只调会退化为 subprocess 模式，每个 30s timeout |
| 裸 `except:` 禁止 | 吞掉 KeyboardInterrupt/SystemExit 等系统异常。全部用 `except Exception:`。2026-06-01 已全局修复 |
| ⭐ 北向资金实时数据永久不可用 | 2024年5月政策变更后，交易所不再实时披露北向资金买卖额。AKShare `stock_hsgt_fund_flow_summary_em()` 日期新鲜但 `成交净买额` 恒为0。东方财富 push2 同样全0。**修复 v8.10**：`get_north_flow()` 策略改为 AKShare `net_flow!=0` 才可信，否则回退 tushare `moneyflow_hsgt`（T-1日终数据）。回退窗口从7天扩大到30天，逐日尝试。返回含 `_quality: 'T-N'` 标记滞后天数。 |
| ⭐ 推荐引擎 enrichment 层全部相同（操作建议/风险评级/止损比例 9只都一样） | **三个子函数各自有致命 bug**：(1) `_gen_operation`：5分支状态机，全部命中 `tech>=50` 分支→同一句"缩量回踩10日线低吸"。需改为类方法访问 `_quote_cache`/`_indicators`/`_insights_index`，用 MA20偏离 × insight情绪 × 创业板前缀 多维决策矩阵。(2) `_assess_risk`：`market_cap` 字段恒为 0→全体命中 `mkt_cap<80`→全"高"。需优先从 `_quote_cache` 补市值，加入波动/板别/技术面/消息面多因子打分。(3) `_calc_stop_loss`：ratio 硬编码 -5.0%，不区分创业板(300/301→应 -7%)。详情见 `references/recommender-enrich-v2.2.md` |
| ⭐ 候选池盲区：涨停股大量不在候选池（文工团诊断 118/120） | **候选源单一 + 全部连板被排除**：(1) `get_top_flow_stocks()` 盘前返回空→资金流候选源失效，(2) hot_events/broker_views 采集为空，(3) `_apply_filters` 排除所有涨停（含首板）。修复：盘前缓存 TTL→24h + 过期缓存兜底；`_get_multi_lianban_codes()` 仅排除 ≥2连板；新增 `_get_first_board_codes()` 将首板纳入候选源。详见 `references/candidate-pool-p0-fix.md` |
| 竞价采集器东方财富 API 价格单位错误 | `fetch_one()` 中 `f43`/`f2`/`f46`/`f60` 字段单位是**分**，需 ÷100。修复前收盘价显示 ¥976（实际 ¥9.76）。`auction_collector.py` 已修复。 |
| ⭐ 东方财富 push2 f62 字段盘中归零 | **间歇性缺陷**：东方财富 `push2.eastmoney.com/api/qt/clist/get` 的 `f62`（主力净流入）字段在盘中可能全部返回 0，导致侦察兵「双重确认」机制失效。同一 API 的 `f66`（超大单）/`f69`（大单）/`f184`（小单）同时归零。**修复**：(1) `get_top_flow_stocks()` 内置 f62 健康检测——如果 TopN 的 `net_flow` 全为 0，自动切换「动量 fallback」：用 `abs(涨跌幅)×0.7 + 换手率×0.2 + 量比×0.1` 合成动量分排序，`net_flow` 置 None、`_quality` 标记 `fallback`；(2) `check_data_health()` 函数探测 list API 10 只样本，统计 `f62_valid`/`f184_valid`/`f66_valid` 比率，<30% 则返回 `status: degraded + flow_field: momentum`；(3) `scout.py` 在 `run_scout()` 开头调用 `check_data_health()`，动量模式下自动放宽涨跌幅门槛（±3% 替代资金流门槛），并在报告中显示「⚠️ 数据源降级」。数据恢复后下次扫描自动切回。详见 `references/scout-v4-healthcheck.md`。 |
| 竞价采集器 09:15 cron error | 东方财富 `push2.eastmoney.com/api/qt/stock/get` 在非交易时段主动拒绝连接（RemoteDisconnected）。修复：(1) API 预热从 3 轮→6 轮指数退避（2s-12s），(2) 预热失败后尝试批量拉取兜底，(3) 全部失败时干净退出不返回 error，(4) cron 脚本去掉 `exec` 避免进程跟踪丢失。 |
| ⭐ 腾讯行情解析失败 | `qt.gtimg.cn` 返回格式 `v_sz000001="51~名称~代码~..."`，双引号内用 `~` 分隔，**不能用 `split('=')` 解析**（`=` 在引号外）。正确方法：`content = r.text.split('"')[1]` 再 `content.split('~')`。字段索引从 0 开始：0=市场码, 1=名称, 2=代码, 3=现价, 4=昨收, 5=开盘, 6=成交量(手), 32=涨跌幅, 36=成交额(万)。量单位手(×100=股), 额单位万(×10000=元)。详见 `references/multi-channel-data-pattern.md`。 |
| ⭐ 多通道降级模式 | 当单一数据源不可靠时，建立「主通道→备1→备2」降级链。竞价采集器已落地（东方财富→腾讯→Sina），宏观资金面已落地（AKShare→tushare汇总）。每条返回数据含 `channel` 字段，采集结束输出分布统计。详见 `references/multi-channel-data-pattern.md`。 |
| ⭐ Gold 层 Bronze kline 格式不匹配 | `bronze_ingest.py` v8.7+ 写 `{code: row_dict}`（dict），`gold_pipeline.py` `_load_bronze_kline` 读 `[{code: row}]`（list）。遍历 dict 时 `r` 是字符串 → `r.get()` → AttributeError。**修复**：`isinstance(data, dict)` 检测直接返回，`isinstance(data, list)` 走旧逻辑。 |
| ⭐ **反复回归** `_em_api_get` 导入路径断裂 (v8.10→v8.12) | **根因**：v8.5 `data_pipeline` 拆分子模块后，`_em_api_get` 在 `data_pipeline/_core.py` 定义但**未从 `__init__.py` 重导出**。`review.py` 中 `from data_pipeline import _em_api_get` → ImportError。**此问题会反复回归** — 系统升级、重新部署、批量找替换时可能再次引入旧的 import 语法。**修复**：改为 `from data_pipeline._core import _em_api_get`（单独一行，不要合并到 `from data_pipeline import ...` 行）。**防御**：Cron 健康检查发现 `script failed + exit=1 + review.py` 时第一位排查此 import。**永久防御**：`grep -rn "from data_pipeline import _em_api_get" scripts/*.py` 扫描所有引用。
| 进化引擎沙箱 KeyError: 'old_metric' | `sandbox_test()` 返回 dict 不含 `old_metric`，打印语句硬编码了不存在的键。改为 `test_result.get('details', 'ok')`。 |
| 宏观资金面数据全部缺失（三路同时） | **系统性根因，不是单点故障**。诊断流程：(1) `python3 -c "from data_pipeline import get_xxx; print(get_xxx())"` 逐路测试返回值，(2) 检查 `market_snapshot.json` 中各字段的 `data_source` 和 `date`，(3) 绕过缓存直接调原始 API（AKShare/tushare/东方财富），(4) 对比缓存时间戳确认是拉取失败还是缓存过期。常见根因组合：北向=tushare moneyflow_hsgt 返回 7 天前过期数据（函数不检查日期新鲜度）→ AKShare 优先；市场资金=ak.stock_market_fund_flow() 东方财富断连被静默吞掉→ tushare moneyflow 全市场汇总回退；板块流=_em_api_get 无重试+UA不完整→ 3次重试+退避+完整 Chrome UA + tushare ths_daily 回退。修复文件 data_pipeline.py，验证用 `python3 market_snapshot.py`。 |
| ⭐ 分时数据获取方案 | tushare Pro **不是分时引擎**。分时K线用 Sina `quotes.sina.cn` KLineData API (免费无限制)。详见 `references/intraday-data-integration.md` |
| ⭐ 停牌股漏入推荐池 | **根因**：停牌检测只在 enrichment 层标记（`_gen_operation_v2`），此时股票已入池。**修复**：在 `_apply_filters()` 加第四重「停牌」过滤——`_get_suspended_codes()` 双路检测：KB洞察含「停牌」+ 行情 change_pct==0 && close==0。嘉美包装/徐工机械等停牌股在过滤阶段即被踢出。 |
| ⭐ 市值过滤器形同虚设（大市值漏网） | **根因**：`get_stock_realtime`（Sina API）不含 `market_cap` 字段，`_get_market_cap()` 对全部股票返回 None，`if mkt_cap is not None` 条件永不触发。招商银行 9634亿 轻松入池。**修复**：tushare `daily_basic` 逐只查询 `total_mv`（万元→亿元），注入 `_indicators[code]['total_mv']`，`_get_market_cap` 优先读此字段。修复后 `excluded.large_cap=14`。 |
| ⭐ tushare `daily_basic` 多码批量查询返回空 | **根因**：`ts_code='600036.SH,601969.SH'` 逗号分隔查询返回 0 行（tushare 限制或 bug），但单码查询正常。**修复**：改为逐只查询（~50只 × 0.5s ≈ 25s），用 `try/except+continue` 包裹。 |
| ⭐ tushare `daily_basic` 不支持 `roe` 字段 | **根因**：`daily_basic` 支持 `pe_ttm/pb/total_mv/circ_mv`，但不含 `roe`。`roe` 需从 `fina_indicator` 获取。**影响**：`_score_fund` 中 `ind.get('roe',0)` 恒为 0，回退到 net_flow 分支。v8.3 已通过 `get_financial_summary()` 补全。 |
| ⭐ `report_formatter.Report` API 调用陷阱 | **API 签名**：`Report(title, icon, color)` — 三个位置参数，无 `subtitle`。`header_meta(**kwargs)` 用 kwargs 设置元信息。`section(title)` 只设章节标题，内容需调用 `text(content)` 追加。`table(headers, rows)` 接受 list of lists。常见错误：传 `subtitle=` → TypeError；`header_meta(date=...)` 写成 `header_meta('date', 'val')` → TypeError。 |
| ⭐ `_save_pool()` 议会字段全空（v2.3陷阱） | Round 3 裁决字段名：`bull_strength`/`bear_strength`/`critical_flags`（非 `bull_signals`/`bear_signals`/`red_flags`）。见 `references/researcher-parliament.md`。 |
| 议会结论未流入下游节点 | **四重断层**：(1) `_save_pool()` 未写入 parliament 字段→daily_pool.json 无议会痕迹，(2) 进化引擎 `_parliament_review()` 只打印不拦截→veto 形同虚设，(3) 瞭望塔/决策官/LLM复盘 LLM cron prompt 未提议会，(4) 侦察兵 no_agent 脚本不知议会。修复：P0-1 `_save_pool` 写入 parliament；P0-2 进化引擎增加三级 veto 拦截；P1 三个 LLM cron prompt 追加议会引用。详见 `references/researcher-parliament.md`。 |
| daily_pool.json version < v2.3 无 parliament 字段 | 旧版推荐引擎未写入。等待 08:25 cron 运行新版 stock_recommender.py 即可自动生成。手动运行 `python3 scripts/stock_recommender.py` 也可立即生成。 |
| 进化引擎 veto 未拦截参数变更 | 检查 `_parliament_review()` 是否返回有效 verdict。如果 parliament_log.json 内 Round 3 verdict.bias 为 veto 但进化引擎仍执行，说明旧版代码未升级。v1.1 已修复。 |
| ⭐ LLM复盘 cron 路径优先级 | **主路径（唯一真实数据源）**: `~/.hermes/profiles/xiaohong/`。**绝对禁止**用 `find ~/.openclaw` 找数据——openclaw workspace 是已废弃的 v1.0 系统，包含过期持仓和历史记录。**已发生事故**：2026-06-03 LLM复盘因读到旧workspace的holdings.json（英唐智控+双良节能），基于旧数据做了错误诊断。复盘时直接读 `~/.hermes/profiles/xiaohong/data/holdings.json` 和 `~/.hermes/profiles/xiaohong/scripts/data/daily_pool.json`。 |
| ⭐ 脚本命名 v1.0 vs v2.0 不匹配 | skill 文档引用 `evolution_engine.py`、`stock_recommender.py`、`mega_collector.py`、`ammo_risk.py`，但实际系统使用 `self_evolution.py`、`scout_recommender.py`、`ammo_risk_check.py` 等 v1.0 命名。两套体系数据格式不兼容——`self_evolution.py` 使用 SelfEvolution 类+角色分离 decisions JSON，不消费 `review_diagnosis.json`。先确认实际脚本命名再调用，不可假设 v2.0 入口存在。 |
| ⭐ 数据目录嵌套（data/data/） | 实际数据路径为 `<workspace>/data/data/`（双层嵌套），内含 `evolution/`、`stock_pool.json`、`trading_log.json` 等。skill 中 `scripts/data/` 路径指向 `<workspace>/scripts/data/`（仅含 push_history.json + watchlist.json）。复盘时优先读 `data/data/` 下的实际运行数据。 |
| ⭐ 盘后持仓估值未同步 | `holdings.json` 中 `lastPrice=None` 且 `pnlPct=None`。盘后估值同步脚本（对标 `ammo_risk.py --update`）未运行或不存在于 v1.0 系统。弹药库报告显示现价 ¥0.00。在估值同步修复前，LLM 复盘应标记此状态而非假装存在实时价格。 |
| ⭐ 研究员研学报告为空壳 | `researchers.py` v1.0 `run_study_session()` 保存报告时只写 `_自主学习完成_` 模板文本，未捕获 `r.analyze()` 结果。修复 v2.0：重新调用 `r.analyze()`，写 `key_findings`/`data_evidence`/`red_flags`，输出计数。system_health_check 第7维检测「研学报告是否有实质内容」。 |
| ⭐⭐ **P0** 涨幅榜学习全是空壳 (v3.0) | **三重根因**：(1) `build_stock_context` 不填充 `data_sources` → DataResearcher 报告「全部 0 个数据源正常」，(2) 逐只串行 `build_stock_context` → ProcessPool 每次重建 → 50 只 12 分钟,(3) `_extract_domain_lesson` 收到的是扁平 `quick_context` 但代码写 `ctx.get('pool_stocks',[{}])[0]` 读嵌套结构→读不到数据。**修复 v3.0**：(1) 每步拉取后 `_ds["step"]={"ok":True,...}`，(2) `run_winner_study` 批量预拉取 `get_stock_realtime(all_codes)` + `get_historical_k_with_ma(all_codes)` + `get_financial_summary` 一次性→复用，(3) `_extract_domain_lesson_v3` 直接从 `ctx.get('ma5')`/`ctx.get('roe')` 读。新增覆盖率分级(🔴<30% 🟡30-60% 🟢>60%)+北交所(920)识别。详见 `references/winners-study-v3.md`。 |
| ⭐ hermes cron 全部缺 --task 参数导致空转 | **根因**：crontab 中 hermes 管理的 xiaohong cron（08:45 watchtower_hermes / 16:00 close_risk）调用 `family_hermes_manager.py --role xiaohong --task watchtower_hermes` 但 `family_hermes_manager.py` **要求 `--task` 参数指定任务ID**。当前 cron 只传 `--role` 和 `--task`，但脚本仍然报「请指定任务ID (--task)」→ 说明参数名不匹配或传参格式错误。**影响**：两个 LLM cron 完全空转——瞭望塔 hermes 版未产出、收盘风控 hermes 版未产出。**修复**：检查 `family_hermes_manager.py` 实际接受的参数名（可能是 `--task-id` 或 `--task_name` 而非 `--task`），修正 crontab。验证：手动跑一次 `python3 family_hermes_manager.py --role xiaohong --task watchtower_hermes --api http://localhost:8234` 确认不再报错。 |
| ⭐ self_evolution.py v1.0 不消费 review_diagnosis.json | **致命断层**：LLM复盘→review_diagnosis.json→进化引擎自动patch 的闭环在 v1.0 系统中**断裂**。`self_evolution.py` 使用 `SelfEvolution` 类 + 角色分离 decisions JSON（`ammo_decisions.json`/`scout_decisions.json`/`watchtower_decisions.json`/`review_decisions.json`），**不读取** `review_diagnosis.json` 中的 `rule_changes_suggested`。所有 LLM 复盘建议的参数变更**永不自动落地**。**现状**：decisions 文件停在 2026-03-20（最后一条 `review_20260320174707_5`「每日复盘完成」），80 天无新决策。**临时方案**：LLM 复盘仍需写 review_diagnosis.json（作为审计记录），但 rule_changes 需要手动执行或等待 v2.0 进化引擎部署。**不要在诊断中假设 rule_changes 会被自动应用。** |
| ⭐ LLM复盘 review_diagnosis.json 写入路径 | skill 文档引用 `~/scripts/kb/review_diagnosis.json`，但实际 v1.0 系统的写入路径是 `<workspace>/data/data/kb/review_diagnosis.json`（双层 data 嵌套）。写入前先用 `find` 定位实际 kb 目录。同理，`holdings.json` 在 `<workspace>/` 根目录而非 `data/` 下。LLM 复盘 cron 启动时第一步永远是定位真实工作区路径。 |
| ⭐ 新因子不重复拉K线 (v8.6) | `_prefetch_new_factors()` 必须从 `_indicators[code]['close_history']` 计算，**不能**调用 `get_historical_k_with_ma()`。原因：(1) `_prefetch_indicators` 已拉过一遍，重复拉浪费80s，(2) BaoStock ProcessPool 第二次调用可能与第一次的 login/logout 状态冲突，(3) `get_factor_panel()` 中的 `get_historical_k_with_ma` 也依赖 ProcessPool，嵌套调用可能死锁。正确做法：从 `ind.get('close_history', [])` 直接算动量/波动。 |
| ⭐ factor_scores 存加权值非原始值 (v8.6) | `scores['new_factors']` 应存 `new_factor_bonus * 0.15`（加权后0-15分），而非原始0-100分。否则 `total_score - scores['new_factors']` 计算结果无意义（混合量纲）。patch后先删旧赋值再在加权处追加。 |
| ⭐ 多方法 patch 防止重复/丢失 (v8.6) | 同一文件连续多次 `patch` 时，先 `grep` 确认每个方法只出现一次。本次 `_score_new_factors_bonus` 因两个 patch 都追加导致重复（两处定义），`_load_factor_weights` 因一次 patch 的 old_string 范围过大而被误删。修复：先确认唯一性，再 patch。 |
| ⭐ IC权重需20天数据才激活 (v8.6) | `_load_factor_weights()` 在 `factor_ic.json` 积累<5天记录时静默返回，不会用噪声权重覆盖硬编码。15%新因子权重硬编码在此阶段使用。`factor_evaluator.py` 需每日运行以积累数据。 |
| ⭐ ML双引擎降级 (v8.6) | `ml_predictor.py` 优先 LightGBM，`pip install lightgbm` 编译超时时自动降级 sklearn RandomForest。`_apply_ml_boost()` 在模型未训练时静默跳过（不影响推荐引擎正常输出）。LR/SVM 对小样本更稳但精度不如 LightGBM。 |
| ⭐ 新因子不重复拉K线 (v8.6) | `_prefetch_new_factors()` 必须从 `_indicators[code]['close_history']` 计算，**不能**调用 `get_historical_k_with_ma()`。原因：(1) `_prefetch_indicators` 已拉过一遍，重复拉浪费80s，(2) BaoStock ProcessPool 第二次调用可能与第一次的 login/logout 状态冲突，(3) `get_factor_panel()` 中的 `get_historical_k_with_ma` 也依赖 ProcessPool，嵌套调用可能死锁。正确做法：从 `ind.get('close_history', [])` 直接算动量/波动。 |
| ⭐ factor_scores 存加权值非原始值 (v8.6) | `scores['new_factors']` 应存 `new_factor_bonus * 0.15`（加权后0-15分），而非原始0-100分。否则 `total_score - scores['new_factors']` 计算结果无意义（混合量纲）。patch后先删旧赋值再在加权处追加。 |
| ⭐ 多方法 patch 防止重复/丢失 (v8.6) | 同一文件连续多次 `patch` 时，先 `grep` 确认每个方法只出现一次。本次 `_score_new_factors_bonus` 因两个 patch 都追加导致重复（两处定义），`_load_factor_weights` 因一次 patch 的 old_string 范围过大而被误删。修复：先确认唯一性，再 patch。 |
| ⭐ IC权重需20天数据才激活 (v8.6) | `_load_factor_weights()` 在 `factor_ic.json` 积累<5天记录时静默返回，不会用噪声权重覆盖硬编码。15%新因子权重硬编码在此阶段使用。`factor_evaluator.py` 需每日运行以积累数据。 |
| ⭐ Gold 层因子覆盖率为 0 (启动期) | **三重根因**：(1) Silver 仅 1天 → `_get_historical_bars()` 返回空，(2) `n < 5` 早期 return 导致所有标的被跳，(3) `n_computed==0` 进一步跳过 Pool 归档。**修复**：改为 `n < 1` → 用当日 Silver 行构造最小 bars `[{close,open,high,low,volume}]` → Pool 归档提升到 `if/else` 外部始终执行。详见 `references/gold-layer-design.md` |
| ⭐ Gold 因子覆盖率低 (启动期 ~24%) | 正常现象。仅有 Silver 当日数据的因子可用（资金+质量）。动量/波动/筹码/滚动需要 6-61 天回溯 → 随 Silver 日积累自动提升。不要为此告警或试图绕过 Silver 调 API。详见 `references/gold-layer-design.md` |
| ⭐ Gold PE/PB 全为 None | Silver 仅 100 只样本且 PE/PB 为 0（Bronze 样本缺基本面数据）。需 tushare `fina_indicator` 或 `daily_basic` 数据注入 Silver 后才能激活估值因子。PE/PB 为 0 时因子填 None。 |
| 🆕 议会静默停摆无人感知 (v8.11) | **根因**：parliament_log.json 超过 24h 无新记录，daily_pool.parliament 引用陈旧数据，认知层链路断裂但无监控。**检测**：`python3 -c "import json; log=json.load(open('scripts/data/research/parliament_log.json')); print(max(e['timestamp'] for e in log))"` 应与今天日期相差≤24h。**修复**：system_health_check 计划增加第13维「议会数据新鲜度」。详见 `references/llm-review-pitfalls.md`。 |
| 🆕 **v8.12** 议会僵尸条目——40条记录零真实裁决 | **根因**：(1) Round 3 key 是 `decision` 非 `verdict`→旧查询永远 null；(2) decision.bias/confidence 字段存在但值全空；(3) 后38条 rounds=0（健康检查空壳污染）。**检测**：不只查时间戳——必须验证 `decision.bias` 非空且 ≠ `?`。**修复**：crontab 添加 `researchers.py --parliament` 调度 + 修复裁决写入逻辑。详见 `references/llm-review-pitfalls.md` 陷阱1升级版。 |
| 🆕 **v8.12** 市场快照三重静默降级 | **症状**：北向 T-28 + 资金流全空 + 板块流全空同时发生。**根因**：三路 API 独立断连均被静默吞掉，瞭望塔/决策官 LLM 只看有值不看 `_quality` 标记→基于 28 天前假数据做判断。**检测**：`_quality` 前缀检查 + `main_net`/`sector_flow` 非空验证。详见 `references/llm-review-pitfalls.md` 陷阱5。 |
| 🆕 **v8.12** 进化引擎基线追踪——用原始值非当前值算变更幅度 | **症状**：2400→2000(16.7%) 被报 33% 拒绝。**根因**：引擎用参数首次定义值(3000)计算而非当前值(2400)，导致分步递进中间步被误拒。**应对**：建议前先 grep 源码确认当前值，计算 (当前-目标)/当前≤20%。详见 `references/llm-review-pitfalls.md` 陷阱6。 |
| 🆕 进化引擎 ±20% 边界拒绝大跨步变更 (v8.11) | **根因**：`review_diagnosis.json` 中建议「50→30」(40%) 被 --dry-run 拒绝。单次调整≤20% 是硬约束。**正确做法**：分步递进——50→40→32→30 (3天完成)，每步在 change 字段写明分步目标。详见 `references/llm-review-pitfalls.md`。 |
| 🆕 Gold ETL cron 路径双写 (v8.11) | **症状**：`can't open file '/home/pc/.../xiaohong/home/.hermes/.../gold_pipeline.py'` — 路径中出现双重 `home/.hermes/profiles/xiaohong`。**根因**：非 cron_gold.sh 自身问题（脚本使用相对路径正常），疑为 hermes cron 调度层将工作目录前缀重复拼接。**影响**：Gold 因子面板+ML 数据集+Pool 归档未产出。详见 `references/llm-review-pitfalls.md`。 |
| 🆕 三链路断裂：推荐池→侦察兵→狙击手→下单 (v8.11) | LLM 复盘应检查此四环节是否全部在线。任一断裂→系统处于「有信号无行动」状态，需在 diagnosis 首句标注。6/4 现状：推荐池✅ 侦察兵⚠️ 狙击手🔴 下单🔴。详见 `references/llm-review-pitfalls.md`。 |
| ⭐ Cron 裸 python3 导致 26 脚本静默失败 (v8.7) | **根因**：cron 环境的 PATH 仅为 `/usr/bin:/bin`，不包含 venv。`cron_*.sh` 中写 `python3` 或 `exec python3` → cron 找不到解释器 → `exit 127`。影响 26 个脚本，4 个 job 标记 error（选股推荐 08:25、竞价采集 09:15、侦察兵盘中 11:00、健康检查 08:15）。**修复**：全量替换为 `/home/pc/.hermes/hermes-agent/venv/bin/python3`。新 cron 脚本**必须**使用绝对路径。验证：`grep -l 'venv/bin/python3' cron_*.sh | wc -l` → 应为 26。 |
| ⭐ Cron 脚本行号污染 (v8.10) | **根因**：`cron_*.sh` 文件内容被写入带 `     N|` 行号前缀的内容（如 `     1|#!/bin/bash`）。bash 无法解析 shebang 报 `未找到命令`。22/26 脚本受影响。stdout 仍有产出（pipeline 后半段 `exec python3` 仍能执行）→ 健康检查只看输出文件永远发现不了。**修复**：`sed -i 's/^[[:space:]]*[0-9]\\+|//'` 批量去行号；`system_health_check.py` v1.2.0 新增维度12（Cron脚本完整性 - shebang 检测）+ 维度6重构（Cron执行退出码 - 扫描所有 output 目录的 `script failed` / `exited with code` 标记）。**教训**：监控产出物≠监控管道。写 cron 脚本时务必验证文件以 `#!` 开头。 |
| ⭐ **🆕 Cron `script` 参数不支持命令行参数** | **根因**：cron 调度器的 `script` 字段把整串当文件名。`system_health_check.py --fix` → 找名为 `system_health_check.py --fix` 的文件 → 不存在 → 永远 `Script not found`。**修复**：创建 wrapper shell 脚本（`cron_health_fix.sh`）包装参数：`exec python3 system_health_check.py --fix --push`，cron 指向 wrapper。本次修复前健康检查+自主修复连续 3 天静默失败，4 个 cron job 问题积压形成恶性循环。 |
| ⭐ **🆕 Cron 脚本默认 timeout 仅 120s** | **根因**：`config.yaml` 中 `cron.script_timeout_seconds` 默认 120s。推荐引擎 run ~120s、竞价采集器 >120s → 每天 `Script timed out`。**修复**：`config.yaml` → `cron: script_timeout_seconds: 300`，所有 no_agent 脚本全局受益。检测：`grep script_timeout ~/.hermes/config.yaml`。 |
| ⭐ **🆕 Stock Tracker ZeroDivisionError** | **根因**：`stock_tracker.py:217` 无快照时 `entry_close`=0，直接除 → 崩溃连续 4 天。**修复**：加 `if s["entry_close"] <= 0: vs_entry = 0` 防护。 |
| ⭐ **🆕 sed 修改 f-string 导致语法错误** | **根因**：`sed` 将 f-string 内的 `e["code"]` 转义为 `e[\"code\"]` → Python 无法解析。**修复**：f-string 内用变量提取：`code = e.get('code',''); f"{code}"`。**教训**：不要用 sed 修改含 f-string 的 Python 代码，用 Python 脚本做替换。 |
| ⭐ **🆕 sed 修改 Python f-string 导致 SyntaxError** | **根因**：用 `sed` 替换 Python f-string 时，双引号 `\"` 被转义成文字反斜杠+引号。f-string 内部 `.get("key")` 与外层引号冲突。**修复**：用 Python 脚本替代 sed 做多行复杂替换——`python3 -c "content = open('f.py').read(); content.replace(...); open('f.py','w').write(content)"`。或在 f-string 中将字典访问提取为独立变量。 |
| ⭐ **🆕 f-string 嵌套 .get() 引号冲突** | **根因**：`f\"{e.get(\"vol_ratio\",1.0)}\"` 中 `.get()` 的双引号与外层 f-string 分界符冲突→SyntaxError。**修复**：先提取变量 `vol_ratio = e.get('vol_ratio', 1.0)` 再用 `f\"{vol_ratio:.1f}\"`。**防御**：所有含 dict 访问的 f-string 都先提取变量。
| ⭐ 北向资金实时通道永久关闭 (v8.10) | **根因**：2024年5月起交易所不再实时披露北向资金。AKShare `stock_hsgt_fund_flow_summary_em()` 的 `成交净买额` 永久返回 0。`get_north_flow()` 择优逻辑 `if date>=yesterday or net_flow!=0` → 日期新鲜命中 → 永远用 AKShare 的 0。tushare 回退只查 7 天但最新数据 8 天前。**修复**：(1) `if net_flow != 0` 才信 AKShare，否则回退 tushare，(2) tushare 回退窗口 7→30天，(3) 新增 `_quality: T-N` 标记滞后天数。**教训**：API 永久归零与间歇性归零需要不同策略——不是 fallback，是彻底改变择优逻辑。 |
| ⭐⭐ **P0** 盘前推荐引擎全停牌误判 + 超时三重根因 (v8.12) | **根因链**：(1) `$HOME` 被 profile 覆盖→`Path.home()` 返回假路径→venv 找不着→所有 subprocess rc=-1，(2) `data fetch` CLI 是完整 hermes agent（每只启动 10s+），176只 subprocess 补漏=洪水，(3) 盘前 Sina 全返回 close=0→`close==0 AND change_pct==0` 误判全市场停牌。**修复**：subprocess 补漏全砍、`get_stock_realtime` 慢路径全砍、盘前 Baostock 昨收复 Sina 0 值、移除 close==0 停牌判断、`--fast` 跳过 tushare PE/研究员/议会。详见 `references/recommender-engine-timeout-fix.md` + `references/data-pipeline-resilience.md`。|
| ⭐⭐ **P0** `$HOME` profile 覆盖导致路径解析错误 | **根因**：hermes profile 系统将 `$HOME` 设为 `/home/pc/.hermes/profiles/xiaohong/home`（非真实 `/home/pc`）。`Path.home()` 依赖 `$HOME`→返回假路径；shell `$HOME` 同样被覆盖→`cd "$HOME/..."` 失败。**影响链**：`auto_repair.py` VENV_PYTHON 指向假路径→所有 `_run_script` rc=-1；`cron_gold.sh` cd 失败→Gold ETL 不执行。**修复**：(1) 所有 py 脚本用 `/home/pc/.hermes/hermes-agent/venv/bin/python3` 绝对路径，(2) 所有 `.sh` 脚本用 `/home/pc/...` 绝对路径，(3) 禁止 `Path.home()` 和 `$HOME` 在 cron/auto_repair 上下文中使用。**验证**：`grep -rn '\$HOME' scripts/*.sh` 应为空。|
| ⭐ **P1** 侦察兵 v4.0 只做资金流筛选不分析个股 | **根因**：`run_scout()` 仅基于 `get_top_flow_stocks(40)` 做资金流交叉验证，选中的股票无任何技术面/基本面分析。用户反馈「不能只根据资金面情况，还要个股详细分析」。**修复 v4.1**：新增 `_enrich_with_kline_analysis()` — 选中股票后批量拉 Baostock K线（`get_historical_k_with_ma`，~2s for ≤15 codes），为每只附加 MA20偏离(%)、量比(vs 5日均量)、PE(TTM)。三张表格（双重确认/新增异动/待确认）全部新增 MA20/量比/PE 列。详见 `references/scout-v4-design.md`。|
| ⭐⭐ **P0** 北向字段张冠李戴 — ggt_ss/ggt_sz 是南向！(v8.12) | **致命 bug (2026-06-04发现)**：`get_north_flow()` tushare 回退逻辑用了 `ggt_ss + ggt_sz` 字段计算北向。但 `ggt_ss`=港股通(沪)、`ggt_sz`=港股通(深) → 南向！正确北向字段是 `north_money`（或 `hgt+sgt`）。真实北向 36.5亿 被算成 5.4亿 → 误差 6.8x，系统宏观判断失真数月。**修复**：`north_money = float(row.get('north_money', 0)); north_total = north_money / 1e4`。**防御**：1) `DataResearcher._validate_data_content()` 直接拉 tushare 交叉比对 north_money vs south_money，如果当前值更接近 south → 🚩字段混淆红旗。2) `CapitalFlowResearcher.analyze()` 前置验证：北向 <10亿 → 🚩严重偏低+暂停决策。3) 每次修改数据管线函数后，打印 tushare 原始行并逐字段标注含义，确认字段映射正确。 |
| ⭐⭐ **P1** 研究员数据内容盲区 (v2.2) | **根因**：`DataResearcher.analyze()` 只检查数据源连通性和文件时效，不验证数据**内容**的正确性。`CapitalFlowResearcher.analyze()` 盲信 `north_flow` 输入不做前置校验。导致北向字段混淆 bug 存活数月无人发现。**修复 (v2.2)**：`DataResearcher` 新增 `_validate_data_content()` → 直接拉 tushare 原始数据交叉比对字段一致性、检测值异常（<10亿偏低→红旗）。`CapitalFlowResearcher` 新增前置验证：北向 <10亿 → 标记红旗 + 暂停决策 + 不生成失真假设。**教训**：连通性检查 ≠ 内容检查。研究员必须像审计师一样对待数据——不只确认管道通不通，还要确认数据对不对。 |
| ⭐ `_em_api_get` 从 `_core` 导入非 `__init__` (v8.10) | **根因**：v8.5 `data_pipeline` 拆分子模块后，私有函数 `_em_api_get` 只在 `data_pipeline/_core.py` 定义，**未从 `data_pipeline/__init__.py` 重导出**。`review.py` 仍用 `from data_pipeline import _em_api_get` → ImportError。**修复**：改为 `from data_pipeline._core import _em_api_get`。**检测**：`grep -rn "_em_api_get" scripts/*.py | grep "from data_pipeline import"` 扫描所有引用。 |
| ⭐ 竞价学习器目标函数做空导向 (v2.0) | **根因**：`auction_learner.py` 将 "caution信号 + 实际下跌" 算作命中（hit→α+1）。下跌市中永远猜跌得高分，但对只做多的交易系统毫无价值——竞价跌→收盘跌的确认不会帮你赚钱。**修复 v2.0**：目标函数改为做多导向——(1) 看涨→涨: 学习 +α，(2) 看涨→跌: 惩罚 +β，(3) 看跌→跌: 跳过（熊市噪音），(4) 看跌→涨: 惩罚 +β（漏了反转机会）。**教训**：学习器的"准确率"如果不是以赚钱为导向，就是自欺欺人。详见 `references/auction-learner-v2.md`。 |
| ⭐ `review.py` `_em_api_get` 导入失败 (v8.10) | 同 `_em_api_get` 根因。`review.py` line 28 的 `from data_pipeline import _em_api_get` 在 v8.5 拆分后失败。修复为 `from data_pipeline._core import _em_api_get`。 |
| ⭐ `get_historical_k_with_ma` 返回 list-of-dicts 非 dict-of-dicts (v8.12) | **根因**：`get_historical_k_with_ma(['000001'])` 返回 `{code: [{date,close,ma5,ma10,peTTM,...}, ...]}`——每只 code 映射到 **list of daily bar dicts**，而非 `{close_history: [...], ma20: ..., ...}` 这种单层 dict。`kl.get("close_history")` 会因 `kl` 是 list 而报 `AttributeError: 'list' object has no attribute 'get'`。**修复**：`bars = kline.get(code, []); closes = [b.get('close') for b in bars]` 从 bar 列表提取 close；`last = bars[-1]` 获取最新 bar 的 ma5/ma10/peTTM 等；MA20 需自算（BaoStock 不支持 ma20 字段）。**注意**：返回的 dict key 是纯数字码（如 `000001`）不带后缀，需与传入 code 一致。 |
| ⭐ 推荐引擎 researcher_analysis 集成 (v2.3) | **新增**：`stock_recommender._run_researcher_analysis()` 在 `_save_pool()` 前逐只调用 `analyze_stock()`，6位研究员分析写入 `daily_pool.recommendations[i].researcher_analysis` 字段。`researchers.analyze_stock()` 拉取行情/财务/K线/资金/KB → 各研究员 analyze() → `cross_analysis`(bias+votes+flags+consensus)。侦察兵 `feed_intraday_pool()` 中新加入股同理。用户查询用 `researchers.py --query 600519`。 |
| ⭐ system_health_check 自主修复 v1.3 | **新增**：`--fix` 标志触发 `auto_repair.run_auto_repair()`，逐维修复已知问题（D2估值→ammo更新、D3议会→重新生成、D5管线→清缓存、D6 cron→重启sniperd+清行号、D7研究员→重新研学、D10-11管线→重新生成、D12脚本→clean）。修复日志写入 `data/fix_log.json`。Cron 已更新为 `system_health_check.py --fix`。 |
| ⭐ system_health_check degraded → exit 1 造成假 error (v8.7) | **根因**：健康检查在 08:15/15:15/22:15 运行，大部分时段 Silver/Gold 管线未产出、研学报告未生成、R 值未计算 → `overall=degraded`。旧逻辑 `if overall in ('degraded','down','critical'): sys.exit(1)` 把「黄灯」当「红灯」→ 每次运行都报 error。**修复**：改为 `if overall in ('down','critical'): sys.exit(1)` + `sys.exit(0)`。degraded 是"需要注意"不是"故障"。|
| ⭐ Cron 脚本行号污染 → 静默失败 (v8.9) | **根因**：cron_*.sh 文件内容被写入了带行号前缀的内容（每行开头为 `     N|`），导致 bash 无法解析 shebang，尝试将 `1|#!/bin/bash` 当命令执行 → 报「未找到命令」→ exit 2。2026-06-04 发现 **22/26** 脚本被污染，影响侦察兵(09:25+盘中4次)、弹药库(15:30)、竞价采集器(09:15)、文工团(15:30) 等关键任务。**诊断方法**：`xxd cron_scout.sh | head -3` 看前几个字节是否为 `2020 2020 2031 7c`（空格+`1|`）而非 `2321`（`#!`）。**修复**：`sed -i 's/^[[:space:]]*[0-9]\+|//' cron_*.sh` 批量清除行号前缀。**自动检测**：`system_health_check.py` v1.2 新增第12维「📜 Cron脚本」——遍历所有 `cron_*.sh` 检查首字节是否 `#!`，异常时标记 `status: down`。验证：`python3 -c "from system_health_check import check_cron_scripts; print(check_cron_scripts())"` |

---

### 数据获取优先级（单票深度分析）

```
Step 1: data fetch stock --symbol XXXX --type daily --days 120  ← 行情+日线
Step 2: data fetch company --symbol XXXX --type overview        ← 历史财报
Step 3: akshare stock_financial_analysis_indicator              ← 财务指标(Roe/负债等)
Step 4: 浏览器搜索 + akshare 龙虎榜/新闻                        ← 资金面+催化剂
Step 5: Python 计算技术指标 (MA/MACD/RSI/布林)                  ← 形态分析
```

估值数据兜底：如果 tushare daily_basic 不可用，用 EPS 和股价反推 PE。

---

## ETF分析流程（🚨 与个股分析完全不同）

> **触发条件**：代码以 51/58/56/15 开头的 5-6 位数字 → 大概率是 ETF/LOF，非个股。到达 Step 0 先判类型。

### 识别规则

| 代码特征 | 类型 | 示例 |
|:--|:--|:--|
| 51xxxx | 上交所 ETF | 515120（创新药ETF广发） |
| 58xxxx | 上交所 ETF | — |
| 56xxxx | 上交所 ETF | — |
| 159xxx | 深交所 ETF | — |
| 16xxxx | LOF | — |

### ETF 数据拉取

ETF 与个股使用**不同的 tushare 函数**：

| 函数 | 用途 | 关键字段 |
|------|------|----------|
| `pro.fund_basic(ts_code='515120.SH', market='E')` | ETF 基本信息 | name, management, benchmark, invest_type, found_date, list_date, m_fee, c_fee |
| `pro.fund_daily(ts_code='515120.SH', ...)` | ETF 日线 (OHLCV) | pre_close, open, high, low, close, vol, amount |
| `pro.fund_portfolio(ts_code='515120.SH')` | 持仓明细 | symbol, mkv, amount, stk_mkv_ratio, stk_float_ratio |
| `pro.fund_nav(ts_code='515120.SH', ...)` | 单位净值序列 | unit_nav, accum_nav, adj_nav |

### ETF 分析四段式

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 产品画像  │ → │ 底层资产   │ → │ 技术面    │ → │ 投资策略   │
│ 费率+规模  │    │ 持仓+行业   │    │ 趋势+均线  │    │ 定投/分批/时机│
│ (15%)     │    │ (35%)     │    │ (30%)     │    │ (20%)     │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

1. **产品画像**：管理人、成立日、跟踪指数、管理费+托管费（总费率 <0.5%=优）、规模（>10亿=流动性好）
2. **底层资产**：持仓股名称和占比、行业分布、指数估值水位（PE/PB 分位数）
3. **技术面**：与个股相同（MA/MACD/RSI/量价），但**关注指数趋势而非个股形态**
4. **投资策略**：
   - ETF 适合「定投/分批」而非「一次性抄底」
   - 关键位在指数支撑而非个股支撑
   - 资金面关注净申购/赎回（`fund_nav` 规模变化）

### ETF vs 个股对比

| 维度 | 个股 | ETF |
|:--|:--|:--|
| 分析核心 | 盈利质量/护城河/管理层 | 行业趋势/资金流向/费率 |
| 估值方法 | PE/PB/DCF | 指数 PE 分位数/历史水位 |
| 技术分析 | 个股形态+量价 | 指数趋势+均线系统 |
| 风险 | 个股黑天鹅（暴雷） | 系统性风险（板块波动） |
| 适合策略 | 择时+选股 | 定投+分批布局 |
| 下行保护 | 无 | 分散化天然保护 |

### 常见陷阱

| 陷阱 | 正确做法 |
|------|------|
| 给 ETF 算 PE/PB/ROE | ETF 是篮子，必须看底层指数的 PE 分位数 |
| 用个股止损逻辑 | ETF 用指数关键位（前低/MA60/整数关口） |
| 把 ETF 当股票追涨杀跌 | ETF 费率低、波动小，适合中长期持有 |
| 忽略管理费 | 总费率 0.6%+ 的考虑换同类更便宜产品 |
| `fund_portfolio` 列名不匹配 | tushare 返回 `symbol`(非 `sec_code`)、`mkv`(市值)、`stk_mkv_ratio`(占净值比)。**不要**假设列名是 `sec_code`/`name`/`ratio`。先 `print(df.columns)` 确认实际列名后再索引 |

> 完整模板和 515120 案例见 → `references/etf-analysis-pattern.md`

### 标准四段式

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 基本面    │ → │ 技术面    │ → │ 催化剂    │ → │ 交易系统  │
│ 估值+财务  │    │ 形态+指标  │    │ 新闻+公告  │    │ 买卖点+仓位│
│ (40%)     │    │ (35%)     │    │ (25%)     │    │ 整合输出  │
└──────────┘    └──────────┘    └──────────┘    └──────────┘
```

### 每段产出
1. **基本面**：营收/利润趋势表、ROE/净利率/负债率对比、PE 估值推算、TTM EPS 手工计算
2. **技术面**：多阶段形态划分、均线/MACD/RSI/布林/量价分析、关键支撑阻力位
3. **催化剂**：浏览器搜索公司名+关键词、提取具体进展（送样/定点/量产）、区分确认/传闻/误传
4. **交易系统**：三面共振打分、分批建仓计划、退出机制、情景推演

---

## 技术面分析

### 用 execute_code 批量计算指标

```python
# 从 data fetch 的 JSON 中提取 bars_sorted
closes = [b["close"] for b in bars_sorted]
highs  = [b["high"]  for b in bars_sorted]
lows   = [b["low"]   for b in bars_sorted]
vols   = [b["vol"]   for b in bars_sorted]

# 均线：MA5, MA10, MA20, MA30, MA60（标准 SMA）
# MACD：EMA12, EMA26, DIF, DEA(9), 柱状=2*(DIF-DEA)
# RSI(14)：标准 Wilder 平滑算法
# 布林带(20,2)：中轨=MA20，带宽=2×标准差
# 成交量：5日/20日均量，量比
```

### 形态识别要点
- 阶段划分：底部盘整 → 突破 → 主升 → 冲高回踩（四阶段命名）
- 关键位：前高（阻力 R1）、近期最低（支撑）、MA 支撑位序列
- 量价关系：突破放量(≥2倍地量)、回踩缩量(≤突破量85%) = 筹码锁定
- 回踩质量：回撤幅度（38.2%/50%/61.8% 黄金分割）、是否破前高

### 危险信号
- 放量滞涨（冲高回落+巨量）= 分歧加大
- 连续缩量阴跌（跌破 MA10）= 回踩失败
- RSI > 80 超买 + MACD 顶背离

---

## 催化剂研究

### 浏览器搜索模式

```
URL: https://so.eastmoney.com/news/s?keyword=公司名+关键词&page=1
```

| 搜索目标 | 关键词组合 |
|------|------|
| 客户订单 | 公司名 + 北美/客户/订单/定点 |
| 产品进展 | 公司名 + 送样/验证/量产 |
| 新业务布局 | 公司名 + 机器人/卫星/光模块/AI |
| 互动问答 | 使用"问董秘"标签页 |
| 研报观点 | 使用"研报"标签页 |

### 催化剂分级
- ✅ **已确认**：公司官方互动平台/公告/正规媒体报道中直接引用
- 🔄 **进行中**：有明确时间线但未完成（如送样未定点）
- ⚠️ **传闻/推测**：仅有市场猜测，无官方确认
- ❌ **未发现/误传**：搜索无结果或张冠李戴

---

## 小红交易决策系统

见 `references/trading-system.md`，核心框架：
- **三面共振打分**：基本面(40%)+技术面(35%)+催化剂(25%) → 综合分 /10
- **分批建仓**：底仓(回踩支撑)、加仓(确认反包)、追击(突破确认)、重仓(深度回调)
- **退出机制**：固定止损→移动止盈渐进，关键时间节点（财报）触发审查
- **仓位铁律**：单票≤8%、行业≤15%、分批间隔≥2日、止损无条件执行

## 自动化 Cron 报告系统

37 个 cron 任务（23 个 no_agent + 8 个 LLM + 6 个新增）:

**执行层（23 个 no_agent）**：

| 时间 | 角色 | 投递 |
|------|------|:--:|
| **每小时** | 📚 知识库·采集 | local |
| 08:00 | 🎯 推荐引擎 v2.3 --fast → daily_pool.json (⚠️ 必须在晨报08:30之前，含 context_from 依赖) | 飞书 |
| 08:28 | 📊 市场统一快照 → market_snapshot.json | local |
| 09:15 | 🔬 竞价采集器 v1.2 | 飞书(DB) |
| 09:25 | 🔍 侦察兵 v4.0 开盘确认 + 竞价 | 飞书 |
| 09:30-15:00 | 🎯 狙击手 v4.0 实时守护进程 (systemd) | 飞书(实时告警) |
| **每5分钟** | 💓 狙击手·存活检测 | 飞书(异常时) |
| 08:15/15:15/22:15 | 🩺 系统健康检查 v1.3 (🆕12维扫描 → 7维自主修复 → --fix 模式) | 飞书 |
| **10:00/11:00/13:00/14:00** | 🔍 侦察兵·盘中扫描 | 飞书 |
| 15:30 | 🛡️ 弹药库 v4.1 --update (+🆕组合风控section) | 飞书 |
| 15:35 | 📊 股票跟踪器 (60日跟踪/止损检测/胜率统计) | 飞书 |
| 15:40 | 🗄️ Bronze 全量采集 | local |
| 15:45 | 🥈 Silver ETL (Bronze→清洗) | local |
| 🆕 15:50 | 🏆 涨幅榜学习 (研究员逐只分析6%+个股) + 🏅 Gold ETL | local |
| 16:00 | 🧠 竞价学习器 v1.1 | 飞书 |
| 17:00 | 🏥 文工团 v3.0 + 🆕📊 因子IC评估 | 飞书 |
| 17:10 | 🆕 🤖 ML模型增量训练 | 飞书 |
| 17:20 | 🆕 📈 组合回测 | 飞书 |
| 17:30 | 🧬 进化引擎 v2.3 (62参数 LLM·自主评估→patch→验证) | 飞书 |
| 周六 09:00 | 📊 文工团·周度复盘 (LLM·叙事性复盘+行为偏差) | 飞书 |
| 周六 09:30 | 🆕 💥 周度压力测试 | 飞书 |

**认知层（8 个 LLM 驱动）**：

| 时间 | 角色 | 议会集成 | 投递 |
|------|------|:--:|:--:|
| **每小时 :05** | 🧠 知识库消化 | — | local → kb_insights.json |
| 02:05 (每日) | 🧠 研究员·LLM深度分析 🆕 | — | local → llm_diagnosis.json |
| 08:30 | 🌅 瞭望塔晨报 v8.0 | ✅ 读取 parliament 字段融入判断 | 飞书 |
| 14:30 | 🌹 决策官 | ✅ 读取 parliament 新增议会结论 section | 飞书 |
| 16:05 | 🧠 竞价诊断 | — | local → auction_diagnosis.json |

> 竞价诊断完整工作流 → `references/auction-diagnosis-workflow.md`
| 17:05 | 🧠 文工团·LLM复盘 v2.1 | ✅ 新增 ⑧ 议会模块诊断 | local → review_diagnosis.json → 触发进化引擎 |
| 17:30 | 🧬 进化引擎 v2.2 (LLM) 🆕 | ✅ 读action→评估合理性→patch+验证 | 飞书 → evolution_log |
| 周六 09:00 | 📊 文工团·周度复盘 (LLM) 🆕 | ✅ 叙事性复盘+行为偏差+6维评分 | 飞书 |

### 盘中推荐池更新 (scout v4.0)

交易时段(09:30-14:30)侦察兵每小时扫描资金异动，发现优质标的自动加入 daily_pool.json：

- **标记**: `source: "scout_intraday"`，推荐引擎次日清空（08:25 fecha重生成，跨日不保留）
- **评分**: 多因子综合评分 — 资金流(40%) + 技术面(30%) + 情绪面(20%) + 板块热度(10%)，对标推荐引擎五因子体系
- **竞争**: 无板块/数量硬上限，评分竞争 9 席。新高分标的可替换低分标的
- **基本面快筛**: PE > 0 且 < 200（失败不阻塞）
- **权重可进化**: `INTRA_FUND_WEIGHT` / `INTRA_TECH_WEIGHT` / `INTRA_SENT_WEIGHT` / `INTRA_SECTOR_WEIGHT` — evolution_engine v2.0 可自动调整
- **CLI**: `python3 scout.py --intraday`
- **Cron**: 4 个 (10:00 / 11:00 / 13:00 / 14:00)，脚本 `cron_scout_intraday.sh`

## 自我进化闭环 v2.2

7 模块 **49** 参数全覆盖（2026-06-01 升级，+12：推荐引擎五因子权重 + 弹药库 4 风控 + 基础设施 2 + 狙击手 P0 确认），LLM 复盘统一诊断入口。🆕 v2.2 进化引擎升级为 LLM 驱动（2026-06-02）：不再盲打 patch，改为 LLM 读取 action_items → 读目标源码确认上下文 → 评估合理性（市场环境+历史准确率）→ 安全范围内 patch + 语法验证 → 记录 evolution_log。

```
LLM认知层 (17:05)
  └─ 文工团·LLM复盘 — 全域诊断 8 个模块（含🆕议会） → review_diagnosis.json
         │
         ├─ 触发进化引擎 action_items 积累
         └─ 周六 研究员周报 → 追加 action_items
              │
进化引擎 v2.2 (17:30, LLM cron)
  ├─ 1. 读取 evolution_action_items.json (仅 status=pending)
  ├─ 2. 逐条读目标源码 → 确认参数位置和当前值
  ├─ 3. LLM 评估合理性 — 市场环境 / 历史准确率 / 参数类型风控
## 自我进化闭环 v2.3 (🆕 v8.6 升级)

10 模块 **62** 参数全覆盖（v8.6 +13：ML模型4 + 组合管理6 + 算法执行3），LLM 复盘统一诊断入口。v2.2 进化引擎升级为 LLM 驱动（2026-06-02）：不再盲打 patch，改为 LLM 读取 action_items → 读目标源码确认上下文 → 评估合理性（市场环境+历史准确率）→ 安全范围内 patch + 语法验证 → 记录 evolution_log。

**覆盖模块 (10)**:

| 模块 | 参数数 | 诊断维度 |
|:--|:--|:--|
| 瞭望塔/推荐引擎 | **8** | 连板排除 / 市值上下限 / 五因子权重 |
| 侦察兵 | 3 | 资金门槛 / 涨跌范围 |
| 狙击手 | **12** | P1-P2-P0 + 冷却 + 入场 + 大盘 |
| 弹药库 | **9** | 凯利系数 / R值 / 止盈缓冲 / 行业集中度 |
| 知识库 | 2 | 采集间隔 / 去重窗口 |
| 竞价学习器 | 7 | 五维权重 + 先验α/β |
| 文工团 | 2 | 涨幅阈值 / 数量 |
| 基础设施 | **4** | 采集间隔 / 去重窗口 / 缓存TTL / MA刷新 |
| 🆕 ML模型 | **4** | boost权重 / 置信阈值 / 重训间隔 / 特征数 |
| 🆕 组合管理 | **6** | VaR/CVaR阈值 / 相关性 / 行业集中度 / 压力测试频率 |
| 🆕 算法执行 | **3** | TWAP切片 / VWAP天数 / 最大冲击bps |

> **铁律 (v3.0)**: 系统自主评估参数变更幅度，无硬上限。大变更自动分步执行（跨日渐进）。所有变更可追溯可回滚。

参数映射 → `references/evolution-v2-params.md`（62参数） + `references/v8.6-factor-and-risk.md`（🆕 v8.6升级详情）

### 周末手动生成瞭望塔晨报

当交易日在周末/节假日需要手动生成时，使用 V8.0 自然三段格式：

```python
# Step 1: 采集
from data_pipeline import get_index_data, get_north_flow
idx = get_index_data(); nf = get_north_flow()

# Step 2: 运行推荐引擎
# python3 stock_recommender.py → daily_pool.json

# Step 3: LLM 编译报告
# → 一个判断（1段话）→ 今天看什么（板块分组+逻辑+操作）→ 今天怎么做（仓位+纠错+时间窗）
```

详见 `references/watchtower-v8-model.md`

---

## 输出规范

- 结论先行：代码 → 方向 → 逻辑 → 止损
- 每次分析必标风险等级（高/中/低）
- 用表格呈现关键指标，不用冗长叙述
- 自选池必须注明数据来源和筛选日期
- 口头禅：从基本面看…… 心里有数就好
- **自审查铁律**：每次生成含数据的报告后，必须逐项验证数据来源——对照实时 API 检查关键数值（指数、资金、涨跌停、MA20、公告数、个股事件数），不得凭「看上去合理」放过。详见 `references/system-pitfalls.md`（v5.0·26项）。
- **进化后自检**：进化引擎 live 模式完成后自动触发 `system_health_check.py --fix`，12维扫描+自动修复。详见 `references/health-check-system.md`。

### 晨报生成强制检查清单

每次生成瞭望塔晨报（无论 LLM cron 还是手动）必须逐项核对。详见 `references/watchtower-v8-model.md`。

| # | 检查项 | 通过标准 |
|:--|:--|:--|
| 1 | 一个判断字数 | ≥150 字深度分析，含宏观→A股→资金→板块逻辑链 |
| 2 | KB 洞察融入 | 不单独堆 ⚡ 标记，融在分析段落中自然引用 |
| 3 | 板块按逻辑聚类 | 不是 tushare 行业名，是有明确投资逻辑的主题（如"通信光缆—板块级资金共振"） |
| 4 | 操作策略差异化 | pool 中 operation 唯一值 > 2，因股而异 |
| 5 | 5 列表格 | 代码/名称/选股逻辑/操作策略/风险，不可省略 |
| 6 | 仓位分类表 | 空仓/中等/重仓各给建议 |
| 7 | 纠错纪律 | 单票止损、日回撤上限、连续止损停手 |
| 8 | 关键时间窗口 | 竞价/开盘/尾盘三个节点 + 观察重点 |
| 9 | 因子分隐藏 | 全文不出现 event/fund/sentiment 数字 |
| 10 | 数据完整性 | 手动生成时必须拉取指数/资金面/板块轮动（不可仅凭 daily_pool.json） |

### 飞书输出自动美化

根据内容类型自动选择美化方式，无需用户每次指定：

| 内容类型 | 美化方式 |
|:--|:--|
| 架构图/管线图/流程图 | `architecture-diagram` skill 生成**亮色白底** SVG → browser 截图 → MEDIA: |
| 表格/状态清单/对比数据 | `boxes -d stone` 或 `boxes -d headline` 自动加边框 |
| 章节标题/分隔线 | `asciified` API 生成 ASCII 横幅 |
| 手绘风格/创意草图 | `excalidraw` → 截图 |
| 简单一两句话 | 不美化，直接发 |

**原则**：可读性优先于装饰。纯文本够清楚就不加框。不要对简单通知过度美化。

### 飞书消息自动美化规则（按内容类型自动选择，不声明）

所有飞书输出由类型驱动自动美化，**禁止手动声明「画个图」「美化一下」**——直接执行：

| 内容类型 | 美化方式 | 工具链 |
|:--|:--|:--|
| 架构图 / 管线图 / 流程图 | 亮色白底 SVG → browser 截图 → `MEDIA:` | `architecture-diagram` skill (light theme) |
| 架构图 / 管线图 / 流程图 (备选) | excalidraw 手绘 → 截图 → `MEDIA:` | `excalidraw` skill |
| 架构图 / 管线图 / 流程图 (备选) | excalidraw 手绘 → 截图 → `MEDIA:` | `excalidraw` skill |
| 表格 / 状态清单 / 对比数据 | `boxes -d stone` 或 `boxes -d headline` | `boxes` CLI |
| 章节标题 / 分隔线 | asciified API 生成 ASCII 横幅 | `curl asciified.thelicato.io` |
| 手绘风格 / 创意草图 | excalidraw JSON → 截图 → `MEDIA:` | `excalidraw` skill |
| 简单一两句话 | **不美化**，直接发纯文本 | — |

**铁律**：可读性优先于装饰。纯文本已够清楚时绝不过度包装。表格用 boxes 包裹但保留内部对齐。

---

## 脚本资产

- `scripts/stock_kb.py` — 🆕 v1.0 SQLite 本地股票知识库（5表：stocks/daily_kline/financials/fund_flow/index_daily，akshare+baostock+tushare 三源爬取全A历史数据）。CLI: `--init`全量 `--init-fast`快速 `--update`增量 `--query`查询(单票/条件/涨幅榜/市场快照) `--stats`统计。毫秒级 WAL 查询。后台运行全量爬取约40分钟(4915只×日K线)。
- `scripts/bronze_ingest.py` — 🆕 v8.6 Bronze 层写入引擎 (不可变原始数据冻结，gzip JSON，幂等)
- `scripts/bronze_verifier.py` — 🆕 v8.6 Bronze 完整性验证 (4维检测)
- `scripts/silver_pipeline.py` — 🆕 v8.6 Silver 层 ETL (Bronze→清洗→统一格式，含 stock_master)
- `scripts/silver_verifier.py` — 🆕 v8.6 Silver 完整性验证
- `scripts/gold_pipeline.py` — 🆕 v8.7 Gold 特征层 ETL (Silver→26维因子面板+ML数据集+Pool归档)
- `scripts/gold_verifier.py` — 🆕 v8.7 Gold 完整性验证 (4维：面板/ML/Pool/Manifest)
- `scripts/factor_evaluator.py` — 🆕 v8.6 因子IC/ICIR + 滚动窗口特征 (22因子)
- `scripts/portfolio_risk.py` — 🆕 v8.6 组合风控 (相关性矩阵+VaR+5压力场景)
- `scripts/ml_predictor.py` — 🆕 v8.6 ML涨跌预测 (LightGBM→sklearn降级，32维特征)
- `scripts/portfolio_backtest.py` — 🆕 v8.6 组合回测 (夏普/回撤/胜率)
- `scripts/algo_executor.py` — 🆕 v8.6 TWAP/VWAP算法执行 (分时量分布+冲击)
- `scripts/broker_gateway.py` — 🆕 v8.6 券商统一网关 (paper/xtquant/easytrader)
- `scripts/data_pipeline/_core.py` — 数据管道主逻辑 (1406行)
- `scripts/data_pipeline.py` — 向后兼容壳 (15行，重导出 data_pipeline/ 子模块)
- 🔥 所有模块清单见 `references/v8.6-factor-and-risk.md`
- `scripts/mega_collector.py` — 🆕 v7.0 统一采集器（9模块14数据源，每小时增量写知识库）
- `scripts/stock_recommender.py` — ⭐ v2.3 选股推荐引擎（🆕 v8.6: 六类因子打分，新因子动量/波动/MA偏离15%权重，`_load_factor_weights()` IC动态权重。新因子从已预取indicators计算避免重复拉K线。7步管线：4源候选→4重排除→5因子+新因子打分→v2.3多维enrich→议会集成。详见 `references/candidate-pool-p0-fix.md` + `references/recommender-enrich-v2.2.md` + `references/researcher-parliament.md` + `references/v8.6-factor-and-risk.md`）
- `scripts/resource_pool.py` — 基本面事件智能池（公告/合同/合作/政策/研报采集，供 mega_collector 和 recommender 调用）
- `scripts/knowledge_base.py` — 基本面知识库（增量采集+去重+倒排索引+检索）
- `scripts/auction_collector.py` — 🆕 竞价采集器 v1.2（三通道降级：东方财富→腾讯→Sina，09:15-09:25每3秒轮询，API预热+异常隔离+降级标的+通道统计）
- `scripts/researchers.py` — 🔬 研究员系统 v3.0（`run_quick_parliament(code,name)` 盘中快速议会4核心研究员2轮~10s；`run_parliament()` 完整3轮；`run_study_session()` 自主研学；`analyze_stock()` 全维分析6研究员；🆕 v3.0 `run_winner_study()` 批量预拉取+全量涨幅股分析+真实数据+覆盖率计算，见 `references/winners-study-v3.md`）
- `scripts/target_pool.py` — 🆕 v1.0 目标池管理（`select_target_pool()` 09:30初始选池3只 + `update_target_pool()` 盘中动态替换 + `get_target_pool_summary()` 狙击手消费接口）
- `scripts/auction_features.py` — 🆕 竞价五维特征提取（价格斜率+量能+不平衡+溢价+板块偏离）
- `scripts/auction_learner.py` — 🆕 Bayesian学习器 v1.1.1（盘后验证→α/β更新→权重自适应，`_get_latest_date_in_db()` 自动找最近交易日，--diagnose诊断空数据）
- `scripts/scout.py` — 🔍 侦察兵 v4.2（开盘确认 + 🆕 三级认证门 `_intraday_gate()`：快速议会→多因子→基本面，全过才入池。综合评分 0.5×侦察兵+0.5×五因子。目标池同步推送 `update_target_pool()`。09:30 初始化 `select_target_pool(force=True)`。`TARGET_POOL_ENABLED` 开关控制）\n- `scripts/strategy_templates.py` — 🆕 v1.0 策略模板参数化引擎（三模板：balanced/aggressive/defensive，JSON配置+因子权重条形图+CLI。`stock_recommender._load_factor_weights()` 自动读取 `data/active_template.json`，模板权重 × IC动态微调 → 最终权重。借鉴 VibetradingLabs 模板思路）\n- `scripts/backtest_chart.py` — 🆕 v1.0 回测曲线可视化引擎（生成权益曲线+回撤曲线 PNG，matplotlib+Noto CJK。`review.py` v3.1 复盘末尾自动嵌入 MEDIA: 路径 → 飞书渲染为图片。颜色方案：安幕诺绿 `#2f9e44`）
- `scripts/sniper.py` — 🎯 狙击手 v3.1（🆕 v4.2: 目标池驱动入场，量比分析 `_get_volume_ratio()` + 分时K线形态 `_analyze_intraday_kline()`，V反/连续上攻/放量判断，综合 `_build_entry_signal()` 决定开仓时机）\n- `scripts/target_pool.py` — 🆕 v1.0 目标池管理模块（select/update/load/mark_entry，CLI: `--select` `--show`，狙击手从 target_pool.json 读取入场标的）
- `scripts/sniperd.py` — 🎯 狙击手 v4.0 实时守护进程 🆕（systemd 服务，3s轮询+状态机去重+秒级止损响应，11 可进化参数。`--once` 单次扫描，`--dry-run` 不写日志）
- `scripts/sniper_healthcheck.sh` — 💓 狙击手存活检测 🆕（交易日每5分钟 cron，自动检测+恢复 sniperd.service）
- `scripts/system_health_check.py` — 🩺 系统健康自检 v1.3（12维扫描 → 自动触发7维修复 → --fix 模式。`auto_repair.py` 独立修复引擎，幂等可追溯。cron 08:15/15:15/22:15 自动扫描+修复+飞书）
- `scripts/auto_repair.py` — 🆕 自主修复引擎 v1.0（配合 system_health_check --fix，逐维修复已知问题，日志写入 data/fix_log.json）
- `scripts/factor_evaluator.py` — 🆕 因子有效性评估引擎（22因子IC/ICIR日频计算+月度自动淘汰。--report输出因子报告，--purge淘汰低效因子，--json JSON输出。依赖scipy做Spearman IC）
- `scripts/portfolio_risk.py` — 🆕 组合层面风控引擎（三层：相关性矩阵+VaR/CVaR+5场景压力测试。--daily日频，--weekly周频压力测试，--report输出格式化报告）
- `scripts/review.py` — 🏥 文工团 v3.0（日终复盘，当日盈亏+持仓体检+交易记录+选股复盘6%+涨幅对比+纪律7条+自我优化→reflection_log.json）
- `scripts/evolution_engine.py` — 🧬 进化引擎 v2.1（1234行，49参数定义+安全边界+沙箱验证。v2.2 已升级主逻辑为 LLM cron，此脚本保留为手动备选和参数定义参考）
- `scripts/strategy_bridge.py` — 策略引擎桥接器（LLM 可调，4 命令）
- `scripts/auto_executor.py` — 自动交易执行器（信号→风控→执行→日志，paper/live 双模式）
- `scripts/transaction_logger.py` — 结构化交易日志（CSV+SQLite 双写，PnL 统计）
- `scripts/backtest_engine.py` — 回测引擎（夏普/最大回撤/网格搜索/CSV 导出）
- `scripts/paper_trading.py` — Paper Trading 模拟器（滑点/延迟/手续费/移动止盈）
- `scripts/api_server.py` — REST API（FastAPI，17 端点，JWT+限流+Swagger）
- `scripts/notifier.py` — 通知中心（飞书+微信+邮件+短信，P0/P1/P2 分级）
- `scripts/multi_tenant.py` — 多租户管理（4 Tier，API Key SHA-256，PG schema 隔离）
- `strategies/trading_skill_strategies.py` — TradingSkill 风格 5 大策略
- `mcp/` — MCP Gateway（TypeScript，17 tools，5 servers）
- `hardware_box/` — 硬件盒子（Pi 5 install.sh + dashboard.html + led_controller.py）

## 参考文档

- `references/cron-llm-upgrade-pattern.md` — 🆕 no_agent → LLM cron 升级模式（判断标准+步骤+已执行案例）
- `references/data-registry.md` — 🆕 数据资产注册表（21项：来源/消费者/状态/缺口，数据研究员中枢维护）
- `references/screening-pitfalls.md` — 筛选踩坑记录
- `references/data-pipeline-resilience.md` — 🆕 数据管线韧性（f62归零/市值过滤/po方向/盘后回退/健康检查）
- `references/trading-system.md` — 小红交易决策系统（三面共振打分+仓位+止盈止损）
- `references/tech-indicators.md` — 技术指标 Python 计算代码模板
- `references/cron-trading-system.md` — Cron 报告系统（各角色+决策官+策略桥接器+no_agent 模式）
- `references/system-pitfalls.md` — 系统审查陷阱清单（29项，按P0/P1/P2分级）
- `references/llm-review-evolution-pipeline.md` — 🆕 LLM复盘 → 进化引擎自动优化管线（review_diagnosis.json 格式规范 + 安全边界）
- `references/holdings-operations.md` — holdings.json 清仓/重置/编辑操作手册
- `references/report-formatter-api.md` — 统一报告美化 Report API（双输出：markdown+飞书卡片）
- `references/watchtower-v8-model.md` — ⭐ 瞭望塔 v8.0 架构（单一真相源+自然三段+选股逻辑优先）
- `references/watchtower-v7-model.md` — 瞭望塔 v7.0 架构（mega_collector+stock_recommender+合并晨报）
- `references/watchtower-v6-model.md` — 瞭望塔 v6.0 多维交叉验证模型
- `references/watchtower-v5-model.md` — （已废弃）瞭望塔 v5.0 涨停驱动模型
- `references/scout-v4-design.md` — 🆕 侦察兵 v4.0 升级设计（独立侦察+板块排名+基本面快筛+反哺推荐池）
- `references/intraday-decision-chain.md` — 🆕 v1.0 盘中实时决策链（三级认证门+目标池+狙击手入场，完整数据流和模块文档）
- `references/sniper-v4-design.md` — 🆕 狙击手 v4.0 实时守护进程设计（cron→事件驱动+状态机+systemd部署+11进化参数）
- `references/auction-system-design.md` — 🆕 竞价分析系统（采集+五维特征+Bayesian学习+侦察兵集成）
- `references/auction-diagnosis-workflow.md` — 🆕 竞价诊断工作流（16:05 LLM cron 标准流程+数据Schema+维度分析指南+采集器健康判定）
- `references/kb-insights-flow.md` — 🆕 KB LLM 洞察→推荐引擎数据流（_load_insights→评分）
- `references/recommender-enrich-v2.2.md` — 🆕 推荐引擎 Enrich 层 v2.2（多维决策矩阵 + 多因子风险 + 创业板止损）
- `references/candidate-pool-p0-fix.md` — 🆕 候选池盲区 P0 修复（多源候选 + 首板/连板分离 + 盘前缓存兜底）
- `references/evolution-engine-debug.md` — 🆕 进化引擎调试手册（4 种故障模式：路径偏移/格式断层/return误删/沙箱KeyError）
- `~/docs/全面审计报告-2026-06-01.md` — 🆕 系统全面审计（架构/数据/功能/逻辑/效率/进化）
- `references/baostock-integration.md` — 🆕 BaoStock 数据源集成（K线快路径/rs.next阻塞/MA字段不支持/字段索引映射）
- `references/financial-data-integration.md` — 🆕 财务数据集成模式 (tushare fina_indicator → 推荐引擎+研究员)
- `~/diagrams/架构图-小红交易系统-v8.3-light.html` — 🆕 系统完整架构图 v8.3（亮色白底，含分时+财务+三通道竞价）
- `~/diagrams/架构图-小红交易系统-v8.1.excalidraw` — 备选手绘版本
- `references/evolution-engine-design.md` — 进化引擎 v1.0 设计（LLM诊断→沙箱验证→自动落地闭环）
- `references/evolution-v2-params.md` — 🆕 进化引擎 v2.0 全域参数映射（7模块49参数 + review_diagnosis.json 规范）
- `references/maturity-assessment.md`
- `references/winners-study-v3.md` — 🆕 涨幅榜学习 v3.0 架构与陷阱 — 🆕 六维成熟度评估框架（月度审计用：市场数据/清洗/特征/模型/风控/执行）
- `references/health-check-system.md` — 🆕 系统健康自检 v1.0（进化后自动触发，7维扫描+6种自修复）
- `references/layered-data-architecture.md` — 🆕 v8.6 分层数据架构 v1.0 (Bronze/Silver/Gold三层，可复现性保证，70MB/天×17GB/年)
- `references/gold-layer-design.md` — 🆕 v8.7 Gold 层设计 (26维因子注册表+启动期陷阱+因子覆盖率时间线+可复现性验证)
- `references/cron-script-corruption.md` — 🆕 v8.10 Cron脚本行号污染诊断与修复手册（症状/根因/诊断/修复/防范全流程）
- `references/cron-audit-pattern.md` — 🆕 v8.7 Cron 全面审计与修复模式 (四步法+常见根因+批量修复)
- `references/llm-review-pitfalls.md` — 🆕 v8.11 LLM复盘工作流陷阱（议会静默/20%边界/路径双写/三链路断裂）
- `references/v8.6-factor-and-risk.md` — 🆕 v8.6 因子扩充+组合风控升级（22因子注册表+IC/ICIR管线+3层组合风控+关键设计决策）
- `references/researcher-parliament.md` — 🆕 研究员议会 v1.1（5角色协同研究，3轮辩论协议，全链路集成：推荐引擎→daily_pool.parliament→瞭望塔/决策官/LLM复盘/进化引擎 veto）
- `references/recommender-engine-timeout-fix.md` — 🆕 v8.12 推荐引擎超时修复（$HOME/profile覆盖 + data fetch CLI agent洪水 + 盘前Sina全0 + --fast模式 + cron时序）
- `references/strategy-templates.md` — 🆕 v1.0 策略模板参数化引擎（三模板+buildtin JSON+CLI+集成链路+VibetradingLabs对比）
- `references/backtest-chart.md` — 🆕 v1.0 回测曲线可视化引擎（权益曲线+回撤曲线+中文字体+MEDIA嵌入+颜色方案）
- `references/PRD-小红量化交易系统商业化.md` — 🆕 v1.0 商业化 PRD（现状评估→产品定义→差距分析→目标架构→模块详设→券商对接→SaaS→路线图→风险。提交于 2026-06-05，已推送 GitHub）
- `references/knowledge-base-design.md` — 知识库架构
- `references/claude-trading-skills-analysis.md` — Claude Trading Skills 生态分析
- `references/tradingskill-benchmark.md` — TradingSkill vs 小红系统对标矩阵
- `references/skills-framework-overview.md` — Skills 框架总览
- `references/workspace-layout-discovery.md` — 🆕 工作区路径发现与 v1.0/v2.0 版本映射（LLM 复盘 cron 必读）
- `references/auto-repair-system.md` — 🆕 v1.3 自主修复系统（12维扫描→诊断→7维修复闭环，幂等可追溯，cron --fix 模式）
- `references/researcher-v2.1-pervasive.md` — 🆕 研究员全链路渗透 v2.1（analyze_stock / query_stock / 推荐引擎+侦察兵集成 / daily_pool schema）
- `references/data-quality-framework.md` — 🆕 v1.0 数据真实性管理框架（五道质检门/QualityStamp/字段陷阱/消费者接入模式/北向bug案例）\n- `references/intraday-decision-chain.md` — 🆕 v1.0 盘中实时决策链（侦察兵→三级认证门→目标池→狙击手开仓，完整数据流+模块版本+参数表）
- `~/wiki/交易系统/数据平台与管道需求说明文档.md` — 🆕 v1.0 数据平台SRS（10章完整需求：设计原则→平台→管道→数据源→质量→资产→消费者→存储→运维→路线图）

## 数据流向架构 (v8.7)

```
外部API ──→ data_pipeline.py ──→ Bronze (不可变) ──→ Silver (清洗) ──→ Gold (特征)
  │                                    │                  │                │
  │              ┌─────────────────────┤                  │                │
  │              ▼                     ▼                  ▼                ▼
  │      bronze_ingest.py      silver_pipeline.py   gold_pipeline.py
  │         (15:40)                (15:45)            (15:50)
  │
  ├──→ 侦察兵/弹药库/狙击手/跟踪器 (实时直调)
  ├──→ 竞价采集器/学习器
  └──→ mega_collector.py → mega_latest.json → 推荐引擎(scoring)
                             │
                       market_snapshot.py (08:28)
                             │
                       market_snapshot.json ──→ 瞭望塔/决策官 LLM
```

**关键数据注入点：**
| 数据 | 注入目标 | 注入方式 |
|------|------|------|
| 全球指数 | 推荐引擎 sentiment 因子 | `external_futures.us/asia` → 外盘方向评分 |
| 北向资金 | 推荐引擎 fund 因子 | `north_flow.net_flow` → 宏观资金面评分 |
| 板块资金 | 推荐引擎 sentiment 因子 | `sector_flow` → 所属板块热度评分 |
| 市场快照 | 瞭望塔/决策官 LLM | `market_snapshot.json` → prompt 注入 |

**数据研究员数据资产注册表：** 见 `references/data-registry.md`（21项系统数据资产：来源/消费者/更新频率/缺口状态）

## 架构图偏好

架构图统一使用 `architecture-diagram` skill 的**亮色白底 SVG**（不是暗色主题）。`excalidraw` 作为备选。
暗色图在飞书中不清晰，用户已明确否决。

小红采用 **Skills + MCP 双轨架构**（对标 tradermonty/claude-trading-skills）：

```
skills-framework/                    # 声明式技能层
├── skills-index.yaml                # 权威技能注册表
├── skills/                          # 8 个技能
├── workflows/                       # 3 个 YAML 流程
├── skillsets/                       # 4 个场景套装
└── mcp-bridge/                      # Skill ↔ MCP 双向映射
```

**Skills** 提供"做什么、何时做、怎么做"（领域知识+决策框架），**MCP Tools** 提供"拿什么数据、执行什么操作"。四级渐进加载。

## 系统架构文档（Obsidian）

系统整体设计和部署文档在 Obsidian vault (`~/wiki/交易系统/`) 下：
- `~/wiki/交易系统/小红交易系统/运维部署手册.md` — Docker/Pi5/MCP/Cron 完整部署流程
- `~/wiki/交易系统/小红交易系统/用户手册.md` — 小程序/Web/API 用户指南
- `~/wiki/交易系统/系统建设需求文档.md` — 原始需求文档
- `~/wiki/交易系统/Claude-Trading-Skills分析.md` — Skills 生态深度分析
- `~/wiki/交易系统/PRD-小红量化交易系统商业化.md` — 🆕 v1.0 商业化 PRD（752行，14章）
