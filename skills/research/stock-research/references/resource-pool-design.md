# 基本面事件智能池 · 架构设计

位于 `~/.hermes/profiles/xiaohong/scripts/resource_pool.py`。

## 设计目标

不再依赖单一涨停池数据选股，而是从多元数据源采集基本面事件（公告/合同/合作/政策/研报），通过四维交叉验证（事件⇄资金⇄涨停⇄研报）生成板块和个股的多维评分。

## 数据源矩阵

```
┌──────────────┬─────────────────────────┬─────────────┐
│ 维度          │ 数据源                   │ 权重         │
├──────────────┼─────────────────────────┼─────────────┤
│ 公司公告      │ stock_notice_report()    │ 25%         │
│ 券商研报      │ stock_research_report_em │ 15%         │
│ 政策/宏观     │ news_economic_baidu()    │ 10%         │
│ 新闻舆情      │ stock_news_em() + RSS    │ 10%         │
│ 资金流向      │ data_pipeline            │ 25%         │
│ 涨停动量      │ stock_zt_pool_em()       │ 15%         │
└──────────────┴─────────────────────────┴─────────────┘
```

## 核心函数

### 数据采集

| 函数 | 来源 | 返回 | 规模 |
|------|------|------|:---:|
| `fetch_corporate_announcements(date)` | `ak.stock_notice_report()` | 事件列表（含板块标签） | ~304条/日 |
| `fetch_research_reports(hot_stocks)` | `ak.stock_research_report_em()` | 研报列表（含评级+盈利预测） | ~44篇 |
| `fetch_policy_macro_news()` | `news_economic_baidu()` + RSS + `stock_news_em()` | 政策/宏观事件 | ~86条 |

### 交叉验证引擎

`cross_validate_sectors(events, zt_df, fund_flow_sectors, research_reports)`

```
输入: 事件池 + 涨停池 + 资金流向 + 研报
  ↓
按板块聚合 → 各板块计算四维得分
  ↓
输出: [{sector, cross_score, confidence, key_stocks, event_drivers}]
```

#### 四维评分公式

```
板块综合 = 事件密度(MIN(25, total_weight × 5 + fresh_bonus × 3))
          + 涨停动量(MIN(20, count × 4 + lianban_max × 3))
          + 资金验证(MIN(25, 10 + flow / 2 or max(0, 10 + flow / 4)))
          + 研报共识(MIN(15, total × 3 + buy_ratio × 10))
          + 多样性  (MIN(15, unique_types × 5))
```

#### 置信度

- **高**：≥3 个维度有信号
- **中**：≥2 个维度有信号
- **低**：<2 个维度有信号

## 事件分类系统

### 关键词映射 → 6 类事件

```python
EVENT_KEYWORDS = {
    'contract_sign':       ['中标', '合同', '签订', '签约', '订单', ...],  # 权重 1.5
    'cooperation':         ['战略合作', '合作协议', ...],                # 权重 1.3
    'project_investment':  ['投资建设', '项目投资', '扩产', ...],        # 权重 1.2
    'major_restructure':   ['重大资产重组', '并购', '收购', ...],        # 权重 1.4
    'shareholder_bullish': ['增持', '回购', '股权激励', ...],            # 权重 1.1
    'policy_related':      ['政策', '补贴', '发改委', ...],             # 权重 1.0
}
```

### 行业映射 → 11 个板块

```python
SECTOR_KEYWORD_MAP = {
    '人工智能': ['AI', '人工智能', '大模型', '深度学习', '算力', 'GPU', '神经网络'],
    '半导体':   ['芯片', '半导体', '晶圆', '光刻', '封装测试', 'NAND', 'DRAM', '存储芯片'],
    '新能源':   ['光伏', '锂电', '储能', '新能源', '太阳能', '风电', '氢能'],
    '电力':     ['电力', '电网', '绿电', '电价', '发电', '输配电'],
    '医药':     ['创新药', '生物医药', '医疗器械', '疫苗', '基因治疗', '细胞治疗'],
    '消费':     ['白酒', '食品饮料', '零售连锁', '家电', '旅游'],
    '房地产':   ['房地产', '地产开发', '楼盘', '物业'],
    '汽车':     ['新能源车', '电动车', '自动驾驶', '汽车零部件', '智能驾驶'],
    '数字经济': ['数字人民币', '数据要素', '区块链', 'Web3', '信创'],
    '机器人':   ['机器人', '人形机器人', '智能制造'],
    '军工':     ['军工', '国防', '航天', '卫星互联网', '导弹'],
}

# 负向排除：标题包含这些词时强制排除该板块
SECTOR_NEGATIVE_FILTERS = {
    '半导体':   ['募集资金', '资金存储', '专户存储', '存储三方', '存储四方'],
    '数字经济': ['数字证书', '数字化'],
    '人工智能': ['人工智能生成', 'AI生成内容'],
}
```

### ⚠️ 设计原则

1. **单字/二字通用词必须复合化**。如 `'存储'` 改成 `'存储芯片'`，`'数字'` 改成 `'数字人民币'`
2. **所有板块都应配置负向排除**，防止误伤
3. **无 tag 公告通过涨停池行业推断补充**（`cross_validate_sectors` 中实现）

## 命令行

```bash
# 采集当日资源池，输出板块分析
python3 scripts/resource_pool.py [YYYYMMDD]

# 编程调用
from resource_pool import build_resource_pool
pool = build_resource_pool(date_str='20260527', zt_df=zt_df)
```

## 输出文件

`data/resource_pool/pool_YYYYMMDD.json` — 每日资源池快照（含板块分析摘要）

## 已知局限

- 公司所属行业未从 tushare `stock_basic()` 获取（受限于 API 调用量），关键词匹配可能漏判非涨停股
- 资金流向在非交易时段返回 0，需盘中数据才能体现资金验证有效性
- 研报覆盖率有限，仅覆盖热门股票（top 30 资金流入 + 公告事件个股）
