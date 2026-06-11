# 小红交易系统 · 全流程架构审计
## 2026-06-11 Phase: 全流程架构优化提升系统稳定性

---

## 故障清单（9项）

| # | 级别 | 模块 | 症状 | 根因 | 修复方式 |
|---|------|------|------|------|----------|
| 1 | P0 | 股票跟踪器 | `TypeError: '>' NoneType vs int` L239 | stop_price 未判空 | 加 `if stop_price is not None` |
| 2 | P0 | 竞价采集器 | Script timeout 120s | --live 模式耗时 >120s | timeout→300s + 预热优化 |
| 3 | P0 | 涨幅榜学习 | Script timeout 120s | --winners 串行50只 >120s | 改LLM模式(300s) 或分批 |
| 4 | P0 | 健康检查 | exit=1 + push_text()崩溃 | degraded→exit(1) + feishu API参数错误 | 改exit逻辑 + 修复push |
| 5 | P0 | Silver管线 | 仅8行(应为5000+) | Bronze→Silver ETL数据注入不足 | 检查bronze_ingest→silver_pipeline链路 |
| 6 | P1 | 议会系统 | parliament_log不存在 | 从未被创建(无cron调度) | 添加cron调度 + 初始化 |
| 7 | P1 | DeepSeek | 流频繁断开(180s) | 模型服务端超时 | 降低context→减少token + 分段 |
| 8 | P2 | 推荐引擎LLM | daily_pool路径404 | $HOME覆盖导致路径错误 | 统一绝对路径 |
| 9 | P2 | 飞书推送 | push_text()参数错 | API升级未同步 | 修复push_text调用签名 |
