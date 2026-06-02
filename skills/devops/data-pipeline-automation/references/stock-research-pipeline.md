# Stock Research Pipeline — Reference Implementation

Built for 小红 (安幕诺家族二姐, stock trader). A complete automated data → knowledge → analysis pipeline.

## Watchlist (12 stocks, 5 tiers)

```
🔴 Core: 600519 茅台, 000858 五粮液, 300750 宁德时代, 002594 比亚迪, 300274 阳光电源
🟡 Turnaround: 600481 双良节能 (CSRC investigation risk)
🟢 Cyclical: 601899 紫金矿业, 600900 长江电力
🔵 Growth: 002475 立讯精密, 688981 中芯国际, 300124 汇川技术
⚪ Defense: 600036 招商银行
```

## Wiki Layout

```
~/wiki/
├── 下载收藏/          ← 30+ JSON files per cycle
├── 股票研究/
│   ├── 自选池/README.md
│   ├── 财报分析/
│   ├── 行业研究/
│   └── 交易日志/
├── 资金面/            ← 北向资金, 龙虎榜, 融资融券
├── 新闻事件/          ← 政策解读, 行业动态
└── 策略研究/          ← 回测记录, 因子监控
```

## 6 Cron Jobs

| Time | Job | Type | Script/Prompt |
|------|-----|------|---------------|
| 8:30 AM Mon-Fri | 盘前采集 | no_agent | `cron_pre.sh` → pulls A50 futures, US close, northbound, news |
| 8:45 AM Mon-Fri | AI 晨报 | agent | Reads wiki → formats morning briefing with signals |
| 10:30 AM Mon-Fri | 盘中扫描 | no_agent | `cron_intra.sh` → realtime quotes, sector moves |
| 3:30 PM Mon-Fri | 盘后复盘 | no_agent | `cron_post.sh` → LHB, northbound, toplist, limit-up stocks |
| 10:00 AM Sat | 周度采集 | no_agent | `cron_weekly.sh` → financials, indicators, macro |
| 10:30 AM Sat | AI 周报 | agent | Reads weekly data → strategy report with stock-by-stock assessment |

## 6-Role Trading Report System (companion)

A separate 6-role cron system generates trading reports per role — 零 LLM token, stdout delivered to Feishu:

| Time | Role | Script |
|------|------|--------|
| 08:30 M-F | 瞭望塔 | cron_watchtower.sh |
| 09:25 M-F | 侦察兵 | cron_scout.sh |
| 09:35~14:30 M-F | 狙击手 | cron_sniper.sh |
| 15:30 M-F | 弹药库 | cron_ammo.sh |
| 17:00 M-F | 文工团 | cron_review.sh |
| Sat 09:00 | 周复盘 | cron_weekly.sh |

Full details → stock-research skill, `references/cron-trading-system.md`.

## Data Sources Used

Per cycle, the collector hits:
- `data fetch stock` (12 symbols × quote + daily)
- `data fetch stock` (lhb, northbound, toplist, limitup)
- `data fetch company` (12 symbols × overview + financial)
- `data fetch futures` (XINA50, HSI for market context)
- `data fetch news` (headlines, industry)
- `data fetch macro` (weekly overview)

## Key Script Files

All in `~/.hermes/scripts/`:
- `market_data_collector.sh` — main collector, 4 modes: pre/intra/post/weekly
- `cron_pre.sh`, `cron_intra.sh`, `cron_post.sh`, `cron_weekly.sh` — silent wrappers

## Profile Context

- Profile: `xiaohong`
- Real home: `/home/pc`
- Profile home: `/home/pc/.hermes/profiles/xiaohong/home`
- Scripts dir: `/home/pc/.hermes/profiles/xiaohong/home/.hermes/scripts/`

## Lessons Learned

1. Path bug: `$HOME/.hermes/...` in script → resolved to `/home/pc/.hermes/profiles/xiaohong/home/.hermes/...` which created double-nesting. Fixed by hard-coding `/home/pc/.hermes/profiles/xiaohong/home/wiki`.
2. Script path requirement: `cronjob` only accepts filenames relative to `~/.hermes/scripts/`. Absolute paths rejected with clear error.
3. `mkdir -p` in fetch function prevents "file not found" on first run.
