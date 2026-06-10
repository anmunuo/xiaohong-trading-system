# LLM复盘 v2.0 工作流模式 (2026-06-10)

## 数据采集：execute_code 批量模式

LLM复盘第一步需要从 ~15 个数据源采集数据。推荐使用**单一 `execute_code` 脚本**而非逐只 `terminal`/`read_file` 调用：

```python
from hermes_tools import terminal, read_file
import json, os, glob

BASE = "/home/pc/.hermes/profiles/xiaohong"  # ⚠️ 绝对路径
results = {}

# 收集所有数据源
for src, path in [
    ("pool", f"{BASE}/scripts/data/daily_pool.json"),
    ("parliament", f"{BASE}/scripts/data/research/parliament_log.json"),
    ("holdings", f"{BASE}/data/holdings.json"),
    ("reflection", f"{BASE}/scripts/data/reflection_log.json"),
    # ... 更多数据源
]:
    try:
        with open(path) as f:
            results[src] = json.load(f)
    except Exception as e:
        results[src] = {"error": str(e)}

print(json.dumps(results, indent=2, ensure_ascii=False, default=str))
```

**效率**：1次工具调用 vs 15+次，且所有数据在同一上下文中便于交叉比对。

## 观测期协议：不回建议已调整的参数

进化引擎昨日已落地的参数变更，需要 1 个交易日的观测期。LLM复盘时的正确做法：

1. **先读 evolution_log.json**：检查最近 1-2 条的 `changes_applied`
2. **标注观测中**：module_scores 中用 `"⏳观测中（昨日已调）"` 而非 `"warn"`
3. **不回建议**：rule_changes_suggested 中写 `change: "已执行，观测中"` + `confidence: "high"`
4. **不叠加变更**：等次日 reflection_log 验证效果后再评估

**反例**（今日6/10）：昨日进化引擎已将涨幅阈值6→5%、涨幅数量50→60，今日LLM若再建议同样的变更→引擎判定为 noop。

## 模块诊断速查表

| 模块 | 关键数据源 | 健康标志 | 需告警信号 |
|:--|:--|:--|:--|
| 推荐引擎 | daily_pool.json | 8+只，source多样化，tech≠None | source全同、pool_rate=0%×3天 |
| 侦察兵 | scout数据目录 | 目录存在+有今日产出 | 目录完全缺失 |
| 狙击手 | target_pool.json + transactions.db | 目标池≥1只 + 有交易记录 | target_pool不存在、0交易×3天 |
| 弹药库 | holdings.json + ammo_output | 持仓估值有效 | 持仓lastPrice=None |
| 知识库 | kb_insights.json | 今日有产出 | 文件不存在或>6h无更新 |
| 竞价学习器 | auction_diagnosis.json | 利用率>5% 或 样本>50 | 先验驱动（hits全0）+ 样本<20 |
| 文工团 | reflection_log.json | 有今日记录 + tips差异化 | 5天相同tips |
| 议会 | parliament_log.json | 有意义条目数≥1 + timestamp新鲜 | 全是空壳（rounds=0）|

## 议会日志健康检查污染

**问题**：`system_health_check.py` 在扫描议会新鲜度时会向 `parliament_log.json` 追加空壳条目（rounds=0, decision={}, bull_strength=0）。

**正确统计**：
```python
meaningful = [e for e in plog if e.get('bull_signals', 0) > 0 or e.get('bear_signals', 0) > 0]
# 有意义条目数 vs 总条目数 → 判断污染程度
```

## review_diagnosis.json 双路径写入

evolution_engine.py 从 `scripts/data/kb/review_diagnosis.json` 读取，但 skill 文档引用 `scripts/kb/`。**必须同时写入两个路径**：

```python
for p in [f"{BASE}/scripts/data/kb/review_diagnosis.json",
          f"{BASE}/scripts/kb/review_diagnosis.json"]:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w") as f:
        json.dump(diagnosis, f, ensure_ascii=False, indent=2)
```
