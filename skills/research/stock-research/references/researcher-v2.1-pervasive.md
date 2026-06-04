# 研究员全链路渗透 v2.2

## 核心函数

### `analyze_stock(code, name)` — 个股全维度分析
```
build_stock_context(code) → 6 researchers.analyze() → cross_analysis
```

拉取: 行情 / 财务 / K线+MA / 资金流向 / KB洞察

返回: `{reports: {fundamental, technical, flow, bull, bear, data}, cross_analysis: {bias, votes, flags, consensus}}`

### `query_stock(code, name)` — 用户查询格式化
CLI: `python3 researchers.py --query 600519`

### 关键陷阱
- `get_historical_k_with_ma` 返回 `{code: [{date,close,ma5,...}]}` — list-of-dicts，不是 dict-of-dicts
- MA20 不包含在返回数据中，需自行从 close 计算
- 返回的 code key 是纯数字（无后缀），与传入一致

## 集成点

| 节点 | 文件 | 调用点 |
|:--|:--|:--|
| 推荐引擎 | stock_recommender.py | `_run_researcher_analysis()` → `_save_pool()` 前 |
| 侦察兵 | scout.py | `feed_intraday_pool()` 后 newly added 股 |
| 用户查询 | researchers.py | `--query CODE` |

## daily_pool.json schema
```json
{
  "recommendations": [{
    "code": "300xxx",
    "researcher_analysis": {
      "timestamp": "...",
      "reports": { "fundamental": {...}, "technical": {...}, ... },
      "cross_analysis": { "bias": "偏多", "bull_votes": 3, "bear_votes": 1, ... }
    }
  }]
}
```

## 研究员 v2.2 新增

### DataResearcher._validate_data_content()
- 直接拉 tushare north_money 交叉验证北向值
- 检测字段混淆（当前值更接近 south_money → 🚩）
- 标记异常低值（<10亿）

### CapitalFlowResearcher 前置验证
- 北向 <10亿 → 🚩 红旗 + 暂停决策
- 不生成基于失真数据的假设
