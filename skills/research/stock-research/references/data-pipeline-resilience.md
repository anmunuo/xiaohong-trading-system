# 数据管线韧性模式 v1.1

> 2026-06-04 更新：新增故障 4（cron 脚本行号污染）和故障 5（北向资金实时通道关闭）

---

## 故障 4: Cron 脚本行号污染（22/26 脚本静默失败）

**症状**：侦察兵(09:25)、盘中扫描(11:00)、KB采集(每小时)、竞价采集器(09:15)、市场快照(08:28)、研究员研学(02:00)等多个 cron job 连续多日报 `last_status: error`，但健康检查从未告警。

**根因**（双重）：
1. **脚本层**：22/26 个 `cron_*.sh` 文件内容被写入了带行号前缀的内容，如 `     1|#!/bin/bash` 而非 `#!/bin/bash`。bash 无法解析 shebang，报 `行 1: 1: 未找到命令`。但管道 `N|cmd` 中后半段 `exec python3 scout.py` 仍能执行，所以 stdout 有产出。
2. **监控层**：`check_scout_sniper()` 只检查输出文件是否存在和内容，**从不检查 cron 退出码**。脚本 exit code=2 但 stdout 有报告文本 → 标记 `ok`。

**修复链**：
1. `sed -i 's/^[[:space:]]*[0-9]\+|//'` 批量清除 22 个脚本的行号前缀
2. `bash -n` 逐个语法验证
3. `system_health_check.py` v1.2.0：
   - 维度6 重构：`check_scout_sniper()` → `check_cron_execution_health()` — 扫描所有 cron output 目录，检测 `script failed` / `exited with code` → 标记 `status: down`
   - 维度12 新增：`check_cron_scripts()` — 检测 26 个 `cron_*.sh` 是否以 `#!` 开头

**关键教训**：监控产出物 ≠ 监控管道。产出物可能从破裂管道漏出来（bash pipeline 后半段仍执行），只有查 exit code 才知道管道破了。健康检查必须同时看「产物存在性」和「执行退出码」。

---

## 故障 5: 北向资金实时通道永久关闭

**症状**：`get_north_flow()` 连续多日返回 `net_flow: 0.0`，日期新鲜（当日），数据源 `akshare_hsgt`。用户怀疑数据有误。

**根因**（三重）：
1. **政策层**：2024年5月起交易所不再实时披露北向资金买卖额。东方财富实时通道已关闭，AKShare `stock_hsgt_fund_flow_summary_em()` 的 `成交净买额` 字段永久返回 0。
2. **管线策略Bug**：`get_north_flow()` 择优逻辑为 `if akshare_date >= yesterday or net_flow != 0` — 日期新鲜永远命中 → 永远用 AKShare 的 0。
3. **tushare回退Bug**：tushare `moneyflow_hsgt` 只有7天回退窗口，但最新数据在8天前（5月27日）→ 查不到 → 回退失效。

**修复链**：
1. 策略变更：`if net_flow != 0` 才信 AKShare，否则回退 tushare
2. tushare 回退窗口 7天 → 30天，逐日尝试最近10个交易日
3. 新增 `_quality: T-N`（滞后天数）和 `data_type` 追加 `(滞后N天)` 标记

**验证**：修复后返回 `net_flow: 5.4亿, data_source: tushare_pro, date: 20260603, _quality: T-1`

**关键教训**：API 字段永久归零（vs 间歇性归零）需要不同的处理策略 — 不是 health check + fallback，而是彻底改变择优逻辑。当数据源因政策/业务原因永久失效时，必须将其降级为备用而非主力。

---

## 健康检查维度演变

| 版本 | 维度数 | 关键变更 |
|:--|:--:|:--|
| v1.0 | 7维 | 数据新鲜度 / 持仓估值 / 议会链路 / 弹药库 / 数据管线 / 侦察兵 / 研究员 |
| v8.7 | 9维 | +因子有效性 / +组合风险 |
| v8.9 | 11维 | +Silver质量 / +Gold质量 |
| **v8.10** | **12维** | +Cron脚本完整性(12) / 维度6重构为Cron执行退出码检测 |
