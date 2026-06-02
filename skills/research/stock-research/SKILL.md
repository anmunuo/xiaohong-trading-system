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
  - "侦察兵|开盘确认|竞价分析|集合竞价|auction|自主学习.*优化|盘中.*更新|盘中.*扫描|推荐池.*更新"
  - "狙击手|日内监控|止损.*监控|入场信号"
  - "弹药库|仓位.*上限|行业集中度|回撤.*追踪|风控.*检查"
  - "文工团|每日复盘|选股复盘|涨幅.*6%|纪律.*清单|错误.*归类"
  - "交叉验证|多维选股"
  - "自查.*数据|假数据|虚构|数据真实"
  - "知识库|知识库检索|每小时采集|最新线索"
  - "Skills.*MCP|claude-trading-skills|Skills架构"
  - "交易系统.*架构|系统全景|整体架构"
  - "部署|Docker.*交易|硬件盒子|Pi.*交易"
  - "TradingSkill|交易系统升级|产品化|硬件盒子|小程序|MCP"
  - 进化引擎|自动进化|LLM复盘|全域进化|推荐池.*逻辑|推荐引擎|诊断.*执行|沙箱.*超时|沙箱.*验证
  - 对标.*系统|交易日志|结构化日志|Paper Trading
  - 美化|格式化|架构图|报告.*美化|SVG|boxes|ascii|excalidraw
  - 健康检查|自检|系统健康|system_health|health_check|7维扫描
  - 研究员|助理研究员|议会|多方|空方|数据研究员|基本面研究员|技术面研究员|协同研究
---

# 小红 · 股票投研工作流

## ⛔ 铁律

**禁止凭空捏造数据或标的。** 所有代码、估值、财务数据必须来自真实数据源。不得拍脑袋预设自选池、不得编造 PE/PB/ROE 数值、不得在没有数据的情况下断言涨跌逻辑。

当不确定数据是否可用时，先探测，再说话。宁可不给结论，不给假结论。

**大规模改动必须先展示方案**：涉及系统架构变更、多模块重构、新产品化功能时，必须先输出完整技术方案（架构全景 + 优化项 + 执行顺序 + 风险评估），待用户审阅确认后再动手编码。禁止跳过方案阶段直接写代码。

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
| `get_top_flow_stocks(n=10)` | 个股净流入 TOP N | n: 返回数量 |
| `get_market_money_flow()` | 全市场主力/散户资金 | 无 |
| `get_stock_realtime(codes: list)` | 个股实时日线 (OHLCV) | codes: 代码列表 |
| `get_watchlist()` | 自选股监控（基于持仓+资金流） | 无 |
| `get_intraday_minutes(code, scale=5, count=48)` | 分时K线 (Sina) 🆕 | code: 纯数字, scale: 1/5/15/30/60 |
| `get_intraday_volume_alert(code, scale=5)` | 分时量价异动检测 🆕 | code: 纯数字 |
| `get_financial_indicator(stock_code, period=None)` | 核心财务指标 (ROE/毛利率/负债率/现金流等13项) 🆕 | stock_code: '000001.SZ' |
| `get_financial_summary(stock_code)` | 财务综合评分(0-100) + 亮点/风险 🆕 | stock_code: 纯数字或不带后缀 |
| `get_historical_k_with_ma(codes, days=30)` | BaoStock 历史K线+MA5/10/20+peTTM/pbMRQ 🆕 | codes: 代码列表, days: 回溯天数 |

**resource_pool 核心 API**：

| 函数 | 用途 | 返回 |
|------|------|------|
| `build_resource_pool()` | 全量事件采集 | `{announcements, research_reports, policy_news, sector_analysis, summary}` |

> ⚠️ `resource_pool` 导出的是函数 `build_resource_pool()`，非 `ResourcePool` 类。

**v4.0 `get_stock_realtime(codes: list)`**：**Sina 批量 HTTP 快路径优先**（单次请求 ~800 只，<0.05s），失败时 fallback 到 `data fetch` CLI。内置 2 分钟模块级缓存。**禁止在循环中逐只调用**——一次性传所有 code 即可。返回 `{code: {close, change_pct, open, high, low, volume, amount, name, data_source, trade_date}}`。

**安全注意**：Tushare Token 已从硬编码移至 `~/.hermes/profiles/xiaohong/.env`（`TUSHARE_TOKEN=`），`_load_tushare_token()` 自动从 env 或 .env 文件加载。**禁止在代码中硬编码任何 API key。**

**holdings.json 实时估值字段**：运行 `python3 scripts/ammo_risk.py --update` 同步写入 `lastPrice / marketValue / unrealizedPnL / pnlPct / lastUpdate`，同时更新 `currentNetValue` 和触发移动止盈计算。

完整 API 见 → `references/data-source-cheatsheet.md`。

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

**关键陷阱**：`rs.next()` 迭代器阻塞 60s+ → **必须用 `rs.data`（list of lists）**。MA 指标需从 close 自算。详见 `references/baostock-integration.md`。

---

## 数据单位陷阱

- tushare `total_mv` / `circ_mv` 单位是**万元**，转亿需 **÷ 1e4**（不是 ÷ 1e8）
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
| ⭐ 东方财富 `po` 参数取反 | `po=0` 是**升序**（最小值在前），`po=1` 是**降序**。`get_top_gainers()` 曾用 `po=0` → 取跌幅最大50只 → 从中筛 ≥6% 涨幅永远为空。`get_top_flow_stocks()` / `get_sector_flow_rank()` 都正确用 `po=1`。凡「取TOP N」必须 `po=1` |
| `data fetch company` 只返回利润表 | `overview`/`balance`/`fina` 三个 category 返回相同数据（仅 income statement），**没有资产负债表和财务比率**。需要 ROE/负债率/毛利率等用 `akshare` 或 `tushare` 直调 |
| akshare `stock_zt_pool_em` 列名不同于文档 | 涨停板列名是 `封板资金`、`连板数`（非 `封单金额`），最新价列是 `最新价`；跌停用 `stock_zt_pool_dtgc_em` |
| 东方财富 API 周末/晚间限流 | 非交易时段 `_em_api_get` 返回 None 或 RemoteDisconnected，属正常现象。代码中 `try/except` 兜底即可，不可据此判断 API 故障 |
| `_em_api_get` 批量请求限流 | 单票请求间隔 ≥150ms，批量时用 `time.sleep(0.15)` 避免触发东方财富反爬 |
| 竞价采集器 09:15 数据为空 | 东方财富 API 竞价初期冷启动（数据延迟）→ 脚本加 `sleep 10` + API 预热 3 次重试，`while` 循环外层加 `try/except` 隔离单轮失败 |
| 竞价采集器推荐池空时无标的 | `load_target_stocks()` 降级到默认蓝筹(6只) + `get_top_flow_stocks(6)` 资金流 TOP，确保始终有采集目标 |
| auction.db 为空导致学习器空转 | `auction_learner.py --diagnose` 先诊断 DB 状态，空数据时输出可操作建议而非静默跳过 |
| 狙击手 v4.0 守护进程异常 | `systemctl --user status sniperd.service` 检查状态；存活检测 cron 每 5 分钟自动恢复；`python3 sniperd.py --once --dry-run` 手动测试；日志在 `data/sniper_logs/` |
| 弹药库双重净值不同步 | `accountInfo.currentNetValue` 和 `riskManagement.currentNetValue` 不一致。v4.1 统一到前者，运行 `ammo_risk.py --update` 自动修复 |
| 弹药库 R 值不更新 | v4.0 及以前 R 值永不自动计算。v4.1 每次 --update 重算。`grep currentRValue data/holdings.json` 验证 |
| 弹药库 cron 忘了 --update | 不加 --update 只出报告不写数据，移动止盈和回撤永不更新。v4.1 cron 已修正 |
| 弹药库流动性误判 | v4.0 用当日成交额（不完整），v4.1 改 5 日均量 |
| `get_stock_realtime` 在循环中逐只调 | **禁止**。应一次传入全部 code 列表，函数内置 Sina 批量 HTTP 快路径（~800只/请求，<0.05s）。在循环中逐只调会退化为 subprocess 模式，每个 30s timeout |
| 裸 `except:` 禁止 | 吞掉 KeyboardInterrupt/SystemExit 等系统异常。全部用 `except Exception:`。2026-06-01 已全局修复 |
| ⭐ 推荐引擎所有候选评分完全相同 | **五个因子全部退化，不是只查技术因子**。逐因子诊断：(1) event — KB公告/龙虎榜全空？insights 未接入？(2) fund — tushare PE/ROE未返回（盘后无今日数据）？net_flow 全 0？(3) sentiment — KB无hot_events？候选 change_pct 全 0？(4) technical — Sina 不含 MA20/均量导致偏离 0%？(5) research — broker_views 空？修复优先级：`_prefetch_indicators()` 拉历史日线→`_load_insights()` 读 kb_insights.json→tushare daily_basic 补PE/市值 |
| ⭐ 推荐引擎 enrichment 层全部相同（操作建议/风险评级/止损比例 9只都一样） | **三个子函数各自有致命 bug**：(1) `_gen_operation`：5分支状态机，全部命中 `tech>=50` 分支→同一句"缩量回踩10日线低吸"。需改为类方法访问 `_quote_cache`/`_indicators`/`_insights_index`，用 MA20偏离 × insight情绪 × 创业板前缀 多维决策矩阵。(2) `_assess_risk`：`market_cap` 字段恒为 0→全体命中 `mkt_cap<80`→全"高"。需优先从 `_quote_cache` 补市值，加入波动/板别/技术面/消息面多因子打分。(3) `_calc_stop_loss`：ratio 硬编码 -5.0%，不区分创业板(300/301→应 -7%)。详情见 `references/recommender-enrich-v2.2.md` |
| ⭐ 候选池盲区：涨停股大量不在候选池（文工团诊断 118/120） | **候选源单一 + 全部连板被排除**：(1) `get_top_flow_stocks()` 盘前返回空→资金流候选源失效，(2) hot_events/broker_views 采集为空，(3) `_apply_filters` 排除所有涨停（含首板）。修复：盘前缓存 TTL→24h + 过期缓存兜底；`_get_multi_lianban_codes()` 仅排除 ≥2连板；新增 `_get_first_board_codes()` 将首板纳入候选源。详见 `references/candidate-pool-p0-fix.md` |
| 竞价采集器东方财富 API 价格单位错误 | `fetch_one()` 中 `f43`/`f2`/`f46`/`f60` 字段单位是**分**，需 ÷100。修复前收盘价显示 ¥976（实际 ¥9.76）。`auction_collector.py` 已修复。 |
| 竞价采集器 09:15 cron error | 东方财富 `push2.eastmoney.com/api/qt/stock/get` 在非交易时段主动拒绝连接（RemoteDisconnected）。修复：(1) API 预热从 3 轮→6 轮指数退避（2s-12s），(2) 预热失败后尝试批量拉取兜底，(3) 全部失败时干净退出不返回 error，(4) cron 脚本去掉 `exec` 避免进程跟踪丢失。 |
| ⭐ 腾讯行情解析失败 | `qt.gtimg.cn` 返回格式 `v_sz000001="51~名称~代码~..."`，双引号内用 `~` 分隔，**不能用 `split('=')` 解析**（`=` 在引号外）。正确方法：`content = r.text.split('"')[1]` 再 `content.split('~')`。字段索引从 0 开始：0=市场码, 1=名称, 2=代码, 3=现价, 4=昨收, 5=开盘, 6=成交量(手), 32=涨跌幅, 36=成交额(万)。量单位手(×100=股), 额单位万(×10000=元)。详见 `references/multi-channel-data-pattern.md`。 |
| ⭐ 多通道降级模式 | 当单一数据源不可靠时，建立「主通道→备1→备2」降级链。竞价采集器已落地（东方财富→腾讯→Sina），宏观资金面已落地（AKShare→tushare汇总）。每条返回数据含 `channel` 字段，采集结束输出分布统计。详见 `references/multi-channel-data-pattern.md`。 |
| 进化引擎 extract_changes 返回空 | **三重 bug**：(1) 路径偏移 — `DATA_DIR.parent/"kb"`→应为 `DATA_DIR/"kb"`，(2) 格式断层 — 诊断文件是 `list[{root_causes}]` 但代码期望 `dict{rule_changes_suggested}`，(3) `return changes` 在补丁中被误删。修复：路径修正 + list/dict 双格式兼容 + return 补回。详见 `references/evolution-engine-debug.md`。 |
| 进化引擎沙箱 KeyError: 'old_metric' | `sandbox_test()` 返回 dict 不含 `old_metric`，打印语句硬编码了不存在的键。改为 `test_result.get('details', 'ok')`。 |
| ⭐ 宏观资金面数据全部缺失（三路同时） | **系统性根因，不是单点故障**。诊断流程：(1) `python3 -c "from data_pipeline import get_xxx; print(get_xxx())"` 逐路测试返回值，(2) 检查 `market_snapshot.json` 中各字段的 `data_source` 和 `date`，(3) 绕过缓存直接调原始 API（AKShare/tushare/东方财富），(4) 对比缓存时间戳确认是拉取失败还是缓存过期。常见根因组合：北向=tushare moneyflow_hsgt 返回 7 天前过期数据（函数不检查日期新鲜度）→ AKShare 优先；市场资金=ak.stock_market_fund_flow() 东方财富断连被静默吞掉→ tushare moneyflow 全市场汇总回退；板块流=_em_api_get 无重试+UA不完整→ 3次重试+退避+完整 Chrome UA + tushare ths_daily 回退。修复文件 data_pipeline.py，验证用 `python3 market_snapshot.py`。 |
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
| ⭐ LLM复盘 cron 找不到数据文件 | **路径映射断层**：skill 文档引用 `~/scripts/`、`~/reports/`、`~/data/` 但实际部署在 `~/.openclaw/workspace/anmunuo-family/xiaohong/`。该目录包含完整系统（scripts + data + reports + holdings.json）。每次 LLM 复盘 cron 启动时，先用 `find ~/.openclaw -name 'holdings.json' -type f 2>/dev/null` 定位真实工作区，再以该路径为基准读取所有文件。如果 openclaw workspace 也为空，检查 `~/.hermes/profiles/xiaohong/data/` 作为备选。 |
| ⭐ 脚本命名 v1.0 vs v2.0 不匹配 | skill 文档引用 `evolution_engine.py`、`stock_recommender.py`、`mega_collector.py`、`ammo_risk.py`，但实际系统使用 `self_evolution.py`、`scout_recommender.py`、`ammo_risk_check.py` 等 v1.0 命名。两套体系数据格式不兼容——`self_evolution.py` 使用 SelfEvolution 类+角色分离 decisions JSON，不消费 `review_diagnosis.json`。先确认实际脚本命名再调用，不可假设 v2.0 入口存在。 |
| ⭐ 数据目录嵌套（data/data/） | 实际数据路径为 `<workspace>/data/data/`（双层嵌套），内含 `evolution/`、`stock_pool.json`、`trading_log.json` 等。skill 中 `scripts/data/` 路径指向 `<workspace>/scripts/data/`（仅含 push_history.json + watchlist.json）。复盘时优先读 `data/data/` 下的实际运行数据。 |
| ⭐ 盘后持仓估值未同步 | `holdings.json` 中 `lastPrice=None` 且 `pnlPct=None`。盘后估值同步脚本（对标 `ammo_risk.py --update`）未运行或不存在于 v1.0 系统。弹药库报告显示现价 ¥0.00。在估值同步修复前，LLM 复盘应标记此状态而非假装存在实时价格。 |

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

## 单票深度分析流程

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

30 个 cron 任务（19 个 no_agent + 8 个 LLM + 3 个待首次运行）:

**执行层（15 个 no_agent）**：

| 时间 | 角色 | 投递 |
|------|------|:--:|
| **每小时** | 📚 知识库·采集 | local |
| 08:25 | 🎯 推荐引擎 v2.3 → daily_pool.json (含 parliament) | 飞书 |
| 08:28 | 📊 市场统一快照 → market_snapshot.json (NEW) | local |
| 09:15 | 🔬 竞价采集器 v1.1 (sleep 10s + API预热) | 飞书(DB) |
| 09:25 | 🔍 侦察兵 v4.0 开盘确认 + 竞价 | 飞书 |
| 09:30-15:00 | 🎯 狙击手 v4.0 实时守护进程 (systemd) | 飞书(实时告警) |
| **每5分钟** | 💓 狙击手·存活检测 | 飞书(异常时) |
| **10:00/11:00/13:00/14:00** | 🔍 侦察兵·盘中扫描 | 飞书 |
| 15:30 | 🛡️ 弹药库 v4.1 --update (7项操作同步+报告) | 飞书 |
| 15:35 | 📊 股票跟踪器 (NEW: 60日跟踪/止损检测/胜率统计) | 飞书 |
| 16:00 | 🧠 竞价学习器 v1.1 | 飞书 |
| 17:00 | 🏥 文工团 v3.0 | 飞书 |
| 17:30 | 🧬 进化引擎 v2.2 (LLM·自主评估→patch→验证) | 飞书 |
| 周六 09:00 | 📊 文工团·周度复盘 (LLM·叙事性复盘+行为偏差) | 飞书 |

**认知层（8 个 LLM 驱动）**：

| 时间 | 角色 | 议会集成 | 投递 |
|------|------|:--:|:--:|
| **每小时 :05** | 🧠 知识库消化 | — | local → kb_insights.json |
| 02:05 (每日) | 🧠 研究员·LLM深度分析 🆕 | — | local → llm_diagnosis.json |
| 08:30 | 🌅 瞭望塔晨报 v8.0 | ✅ 读取 parliament 字段融入判断 | 飞书 |
| 14:30 | 🌹 决策官 | ✅ 读取 parliament 新增议会结论 section | 飞书 |
| 16:05 | 🧠 竞价诊断 | — | local → auction_diagnosis.json |
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
  ├─ 4. 通过 → patch 工具修改 + python3 py_compile 语法验证
  ├─ 5. 不通过 → 标记 rejected + 原因
  └─ 6. 输出结构化报告 (report_formatter.Report)

**覆盖模块 (7)**:

| 模块 | 参数数 | 诊断维度 |
|:--|:--|:--|
| 瞭望塔/推荐引擎 | **8** | 连板排除 / 市值上下限 / 🆕五因子权重(event/fund/sentiment/technical/research) |
| 侦察兵 | 3 | 资金门槛 / 涨跌范围 |
| 狙击手 | **12** | P1逼近 / P2涨跌 / P2量比 / 入场量比 / 入场偏离 / L1间隔 / P1冷却 / P2冷却 / 入场冷却 / 大盘冷却 / 大盘异动 / 🆕P0确认tick |
| 弹药库 | **9** | 凯利系数 / 单股上限 / 总持仓 / 止盈启动 / 步长 / 🆕R值分母 / 🆕止盈缓冲 / 🆕行业集中度 / 🆕流动性阈值 |
| 知识库 | 2 | 采集间隔 / 去重窗口 |
| 竞价学习器 | 7 | 五维权重 + 先验α/β |
| 文工团 | 2 | 涨幅阈值 / 数量 |
| 基础设施 | **4** | 采集间隔 / 去重窗口 / 🆕行情缓存TTL / 🆕MA刷新间隔 |

> **铁律**: 单次参数调整 ≤±20%，至少 3 天回测数据才自动落地，所有变更可追溯可回滚。

参数映射 → `references/evolution-v2-params.md`（49参数：推荐引擎8 + 侦察兵3 + 狙击手12 + 弹药库9 + 知识库2 + 竞价7 + 文工团2 + 基础设施4）

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
- **进化后自检**：进化引擎 live 模式完成后自动触发 `system_health_check.py --fix`，7维扫描+自动修复。详见 `references/health-check-system.md`。

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

- `scripts/data_pipeline.py` — 统一数据管道（Tushare/AKShare/东方财富/Sina四源聚合）
- `scripts/mega_collector.py` — 🆕 v7.0 统一采集器（9模块14数据源，每小时增量写知识库）
- `scripts/stock_recommender.py` — ⭐ v2.3 选股推荐引擎（7步管线：4源候选(公告+资金流+涨停首板+研报)→4重排除(ST+≥2连板+停牌+市值50-3000亿)→5因子打分→v2.3多维enrich(MA20偏离×insight情绪操作策略+6维风险打分+创业板止损)。Step 6.5 议会集成。tushare 逐只查询 PE/PB/市值(万元→亿元)。排除统计：ST 9/连板1/停牌2/小盘89/大盘14。详见 `references/candidate-pool-p0-fix.md` + `references/recommender-enrich-v2.2.md` + `references/researcher-parliament.md`）
- `scripts/resource_pool.py` — 基本面事件智能池（公告/合同/合作/政策/研报采集，供 mega_collector 和 recommender 调用）
- `scripts/knowledge_base.py` — 基本面知识库（增量采集+去重+倒排索引+检索）
- `scripts/auction_collector.py` — 🆕 竞价采集器 v1.2（三通道降级：东方财富→腾讯→Sina，09:15-09:25每3秒轮询，API预热+异常隔离+降级标的+通道统计）
- `scripts/auction_features.py` — 🆕 竞价五维特征提取（价格斜率+量能+不平衡+溢价+板块偏离）
- `scripts/auction_learner.py` — 🆕 Bayesian学习器 v1.1（盘后验证→α/β更新→权重自适应，--diagnose诊断空数据）
- `scripts/scout.py` — 🔍 侦察兵 v4.0（开盘确认 + 盘中池更新。--intraday 模式：资金异动扫描→多因子综合评分(资金40%+技术30%+情绪20%+板块10%)→基本面快筛→动态写入 daily_pool。无板块/数量硬上限，评分竞争9席，高分替低分。权重为可进化参数(intra_*_weight)）
- `scripts/sniper.py` — 🎯 狙击手 v3.0（手动备用，P0-P3分级止损+入场信号）
- `scripts/sniperd.py` — 🎯 狙击手 v4.0 实时守护进程 🆕（systemd 服务，3s轮询+状态机去重+秒级止损响应，11 可进化参数。`--once` 单次扫描，`--dry-run` 不写日志）
- `scripts/sniper_healthcheck.sh` — 💓 狙击手存活检测 🆕（交易日每5分钟 cron，自动检测+恢复 sniperd.service）
- `scripts/system_health_check.py` — 🏥 系统健康自检 v1.0（进化后自动触发，7维扫描+6种自修复）
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
- `references/sniper-v4-design.md` — 🆕 狙击手 v4.0 实时守护进程设计（cron→事件驱动+状态机+systemd部署+11进化参数）
- `references/auction-system-design.md` — 🆕 竞价分析系统（采集+五维特征+Bayesian学习+侦察兵集成）
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
- `references/health-check-system.md` — 🆕 系统健康自检 v1.0（进化后自动触发，7维扫描+6种自修复）
- `references/researcher-parliament.md` — 🆕 研究员议会 v1.1（5角色协同研究，3轮辩论协议，全链路集成：推荐引擎→daily_pool.parliament→瞭望塔/决策官/LLM复盘/进化引擎 veto）
- `references/scout-v4-design.md` — 侦察兵 v4.0 升级设计（独立侦察+板块排名+基本面快筛+反哺推荐池）
- `references/knowledge-base-design.md` — 知识库架构
- `references/claude-trading-skills-analysis.md` — Claude Trading Skills 生态分析
- `references/tradingskill-benchmark.md` — TradingSkill vs 小红系统对标矩阵
- `references/skills-framework-overview.md` — Skills 框架总览
- `references/workspace-layout-discovery.md` — 🆕 工作区路径发现与 v1.0/v2.0 版本映射（LLM 复盘 cron 必读）

## 数据流向架构 (v8.1)

```
data_pipeline.py ────→ mega_collector.py ──→ mega_latest.json ──→ 推荐引擎(scoring)
       │                      │                    │
       │                      │              market_snapshot.py (08:28)
       │                      │                    │
       │                      │              market_snapshot.json ──→ 瞭望塔/决策官 LLM
       │                      │                    │
       │                      │              data_hub.distribute()
       │                      │               ├── market_context.json
       │                      │               ├── sector_signals.json
       │                      │               └── macro_pulse.json
       │                      │
       ├──→ 侦察兵/弹药库/狙击手/跟踪器 (实时直调)
       └──→ 竞价采集器/学习器
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
