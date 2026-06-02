# KB LLM 洞察 → 推荐引擎数据流

> 2026-06-01 补充：发现 kb_insights.json（18条LLM结构化洞察）完全未被推荐引擎使用，已修复。

## 数据流

```
mega_collector (每小时)
  └→ data/kb/mega_latest.json (原始采集)      ← 推荐引擎 _load_kb() 读
       ├── modules/dragon_tiger/
       ├── modules/hot_events/
       ├── modules/announcements/
       └── modules/broker_views/

KB LLM 消化 cron (每小时 :05)
  └→ data/kb/kb_insights.json (结构化洞察)    ← 推荐引擎 _load_insights() 读 🆕
       └── [{timestamp, insights: [{type, title, body}]}]

推荐引擎 v2.1
  ├── _load_insights() → _insights_index {code: [insight]}
  ├── _score_event()    — risk 告警 -10, signal/anomaly +5
  └── _score_sentiment() — sentiment/signal +10
```

## 洞察类型

| type | 含义 | 评分影响 |
|:--|:--|:--|
| `fund_signal` | 宏观资金信号 | sentiment +10 |
| `sector_anomaly` | 板块异常 | event +5 |
| `risk_alert` | 风险告警（特定股票） | event -10 |
| `sentiment_shift` | 情绪转变 | sentiment +10 |

## 索引方式

`_load_insights()` 用 `re.findall(r'\b(\d{6})\b', text)` 从洞察文本中提取股票代码，建立 `{code: [insight]}` 索引。

示例：洞察中出现 "科隆股份（300405）" → `_insights_index["300405"]` 命中。

## 注意事项

- 洞察按 code 索引，只影响匹配的股票
- 无匹配 code 的洞察（纯宏观/板块分析）不参与个股评分
- 盘后非交易时段 kb_insights.json 可能包含当天最后一批洞察
- 推荐引擎不生成洞察，只消费
