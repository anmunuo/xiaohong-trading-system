# 系统审查陷阱清单 v5.0 · 26项

## P0 (阻塞)

| # | 陷阱 | 检测 |
|:--|:--|:--|
| 1 | 伪造数据 — 凭空捏造股票代码、PE、涨跌 | 每次报告后自审 |
| 2 | 假 daily_pool — 脚本未运行但声称有推荐 | 检查 generated_at 时间戳 |
| 3 | 覆盖 scout_intraday — 推荐引擎覆盖盘中新增 | _save_pool 必须合并 |
| 4 | 进化引擎落错参数 — apply_param_to_file 替换了错误行 | dry-run 先验证 |
| 18 | 候选池盲区 — 候选仅来源公告(111只)，涨停/资金流未接入 | 检查 daily_pool.json 中 source 多样性，仅 announcement → 盲区 |
| 19 | 盘前资金流冷启动 — `get_top_flow_stocks()` 08:25返回空（非交易时段，缓存过期） | 加 `is_trading_hour()` 判断，非交易时段 TTL→24h，API空时过期缓存降级 |

## P1 (功能)

| # | 陷阱 | 检测 |
|:--|:--|:--|
| 5 | auction.db 空 → 学习器空转 | --diagnose 先检查 |
| 6 | 竞价采集器 09:15 API 冷启动 → 采集失败 | sleep 10 + API 预热 |
| 7 | 进化引擎沙箱超时 → 重跑 tushare 全市场 | 分层策略秒级完成 |
| 8 | review_diagnosis.json 格式错误 → extract_changes 提取失败 | rule 关键词 + change 末位数字 |
| 9 | 凯利系数小数解析错 → 0.25 被提取为 25 | 正则 `\\d+\\.?\\d*` |
| 10 | excluded 字段类型不一致 → len(int) 崩溃 | isinstance 兼容 |
| 20 | 进化引擎格式断层 — LLM产出 list 格式 `[{root_causes}]` 但 `extract_changes()` 期望 dict `{rule_changes_suggested}` | 兼容两种格式：list→遍历entries，dict→直接读 |
| 21 | 进化引擎路径偏移 — `DATA_DIR.parent/kb/` 找不到文件（实际在 `DATA_DIR/kb/`） | 统一用 `DATA_DIR / "kb"`，不再加 `.parent` |
| 22 | 进化引擎 return changes 被替换时误删 — extract_changes() 无返回值 | 每次修改函数末尾确认 return 语句存在 |
| 23 | 进化引擎 KeyError — `test_result['old_metric']` 不存在（sandbox_test 返回 dict 不含此键） | 用 `.get('old_metric', 'N/A')` 安全访问 |

## P1 (功能) — 推荐引擎输出单调

| # | 陷阱 | 检测 |
|:--|:--|:--|
| 14 | 操作建议全部相同 | `_gen_operation()` 5 分支中 tech≥50 分支吞没全部（tech 55-65 集中）。检查 daily_pool.json 中 operation 字段唯一值 ≤2 |
| 15 | 风险评级全部相同 | `_assess_risk()` 依赖 `rec.market_cap`（常为 0），全体 ≤80 → 全"高"。检查 risk_level 字段分布 |
| 16 | 止损不区分创业板 | `_calc_stop_loss()` 硬编码 -5%，301/300 代码应放宽至 -7% |

## P2 (体验)

| # | 陷阱 | 检测 |
|:--|:--|:--|
| 11 | 侦察兵盘中报告重复 | feed_intraday_pool 去重 |
| 12 | LLM 复盘 confidence=low 被落地 | prompt 明确要求过滤 |
| 13 | 飞书输出无美化 | 按类型自动选择 SVG/boxes/asciified |
| 17 | 晨报手动生成偏离模版 | 手动拼凑时缺少完整数据上下文 → 退化模板填空。必须拉取同等数据（指数/资金面/板块轮动/公告）。详见 `watchtower-v8-model.md` 禁止事项 |
| 24 | 竞价采集器价格单位 — 东方财富 `f43`/`f2`/`f46`/`f60` 返回**分**，需 ÷ 100 | 检查 price 字段是否 > 100（正常A股 < 500元），异常偏高 → 单位bug |
| 25 | cron 脚本 `exec` 导致进程跟踪丢失 — `exec python3 ...` 替换 shell 进程，cron 框架可能报告 error | cron 脚本中去掉 `exec`，用 `python3 ...` |
| 26 | 弹药库报告路径误判 — 报告在 `reports/daily/弹药库风控-*.md` 而非 `data/ammo_report_*.json` | 检查 `BASE_DIR/reports/daily/` |
