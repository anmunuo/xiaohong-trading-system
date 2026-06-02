# LLM 复盘 → 进化引擎 · 自动优化管线

## 时间线

```
17:00 文工团 no_agent → 每日复盘报告
17:05 文工团·LLM复盘 → 7模块全域诊断 → review_diagnosis.json → 触发 evolution_engine
17:30 进化引擎 cron（兜底）→ extract_changes → sandbox → apply
```

## 管线步骤

### 1. LLM 复盘输出 review_diagnosis.json

路径: `~/scripts/kb/review_diagnosis.json`

LLM 复盘 prompt 要求：
- 诊断 7 个模块（推荐引擎/侦察兵/狙击手/弹药库/知识库/竞价/文工团）
- rule 关键词必须精确匹配 19 个映射表中的 keyword
- change 字段最后一个数字 = 目标新值
- confidence=low 不写入 rule_changes_suggested
- 写完后立即执行 `evolution_engine.py --dry-run && evolution_engine.py`

### 2. 进化引擎 extract_changes()

- 读取 `review_diagnosis.json` → 遍历 `rule_changes_suggested`
- 用 `rule_map` 将 rule 关键词映射到 param_id
- 用正则 `(\d+\.?\d*)` 从 change 字段提取最后一个数字作为新值

### 3. 进化引擎 sandbox_test()

分层策略:
- `FILTER_PARAMS` (13个) → `_simulate_filter_change()` — 读 daily_pool.json excluded 统计
- `WEIGHT_PARAMS` (7个) → `_check_reflection_trend()` — 反射 reflection_log 3天趋势
- `RISK_PARAMS` (5个) → `boundary_only` — 仅安全校验
- `INFRA_PARAMS` (2个) → `boundary_only` — 仅安全校验

全部 < 15s 完成（旧沙箱跑 tushare 全市场需 120s+）

### 4. 安全边界

| 规则 | 值 |
|:--|:--|
| 单次最大调整 | ±20% |
| 范围边界 | [min, max] |
| 回测天数 | ≥ 3 天 reflection_log |
| reflection_log 趋势下降 >2% | 拒绝 |
| 超时兜底 | 15s |

### 5. 自动落地

```python
create_backup() → apply_param_to_file() → evolution_log.json
```

所有变更可追溯可回滚。
