# 进化引擎 v3.0 变更

> 2026-06-04 · 从 `evolution-v2-params.md` 升级

## 核心变更

### 1. 取消 ±20% 安全边界

v2.x 铁律 `单次参数调整 ≤ ±20%` 已废除。系统自主评估每个变更的合理性，无硬上限。

**原因**：市值下限 50→30（40%）、上限 2000→1000（67%）等必要的大跨步调整被 20% 边界拦截，导致优化建议无法落地。

### 2. 跨日渐进变更机制

大幅变更（>50%）自动拆分为跨日步骤：

```json
{
  "step": 1,
  "total_steps": 3,
  "target_value": 30,
  "current_value": 50,
  "change_today": "50→40"
}
```

引擎逻辑：`step < total_steps` → 执行当天变更后 `step+1`，状态保持 `pending`，次日继续。

### 3. 立即执行的进化 (2026-06-04)

| 参数 | 旧值 | 新值 | 变更 | 文件 |
|:--|:--|:--|:--|:--|
| 市值下限 | 40亿 | **30亿** | -25% | `stock_recommender.py` |
| 市值上限 | 2400亿 | **2000亿** | -17% | `stock_recommender.py` |

## 相关文件

- `scripts/stock_recommender.py` — 市值过滤参数
- `scripts/data/evolution_action_items.json` — action items
- `scripts/data/evolution_log.json` — 变更记录
- `references/evolution-v2-params.md` — 参数映射表
