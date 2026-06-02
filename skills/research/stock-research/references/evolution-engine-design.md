# 进化引擎设计

> 每日 17:30：读取 LLM 诊断建议 → 翻译为参数变更 → 沙箱验证 → 自动落地或丢弃。

## 架构

```
17:05  文工团·LLM复盘 → review_diagnosis.json
16:05  竞价·LLM诊断   → auction_diagnosis.json
         ↓
17:30  进化引擎读取诊断 → 提取可执行参数变更
         ↓
      安全校验: 单次调整 ≤±20% | 参数在 [min, max] 内
         ↓
      沙箱验证: 运行推荐引擎 → 对比历史命中率
         ↓
   ┌─ 通过(≥2%提升) → 备份原文件 → 写入新参数 → 记录 evolution_log.json
   └─ 未通过       → 丢弃变更
```

## 可进化参数

| 参数 ID | 所属文件 | 默认值 | 范围 | 描述 |
|------|------|:--:|:--:|------|
| recommender_lianban_min | stock_recommender.py | 1 | 1-4 | 连板排除阈值 |
| recommender_market_cap_min | stock_recommender.py | 50 | 20-100 | 市值下限（亿） |
| recommender_market_cap_max | stock_recommender.py | 2000 | 500-5000 | 市值上限（亿） |
| scout_flow_base | scout.py | 5000 | 2000-15000 | 资金门槛基准（万） |
| scout_change_min | scout.py | -3 | -8-0 | 涨跌下限（%） |
| scout_change_max | scout.py | 9 | 5-15 | 涨跌上限（%） |
| auction_weight_* | auction_features.py | 0.15-0.25 | 0.05-0.50 | 五维权重（5个） |
| sniper_stop_approach_pct | sniper.py | 3.0 | 1.0-8.0 | 止损逼近阈值（%） |

## 安全边界

- 单次参数调整不超过 ±20%
- 至少 3 天回测数据才允许自动落地
- 命中率至少提升 2% 才通过沙箱
- 所有变更写入 `evolution_log.json`，自动备份源文件到 `evolution_backups/`
- 支持 `--rollback` 一键回滚

## 用法

```bash
python3 evolution_engine.py              # 执行进化
python3 evolution_engine.py --dry-run    # 只分析不落地
python3 evolution_engine.py --rollback   # 回滚到上一版本
python3 evolution_engine.py --log        # 查看进化历史
```

## Cron

```bash
30 17 * * 1-5  cd scripts && python3 evolution_engine.py
```

## evolution_log.json 格式

```json
[{
  "version": 1,
  "date": "2026-06-01",
  "changes_attempted": 3,
  "changes_applied": 2,
  "details": [{
    "param": "scout_flow_base",
    "description": "侦察兵资金门槛基准",
    "old_value": 5000,
    "new_value": 4000,
    "reason": "大盘强势，降低门槛捕捉跟风",
    "test_result": {"old_metric": 17.4, "new_metric": 22.1, "improvement": 4.7}
  }]
}]
```
