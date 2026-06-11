# 系统知识库获取逻辑 · 提示词模板

> 用于快速向新成员/LLM解释知识库整体架构。469字。

---

**系统知识库获取逻辑**

```
三层架构：Bronze(不可变原始冻结) → Silver(清洗统一) → Gold(26维因子+ML+归档)

数据采集四通道：
1. stock_kb(SQLite) — akshare+baostock+tushare 三源全A历史(4915只K线/财务/资金)
2. knowledge_base — 每小时增量采集公告/政策/研报 → 哈希去重 → 倒排索引 → 个股事件链+Top20高价值线索
3. resource_pool — 事件采集支撑层(公司公告/券商研报/政策新闻)
4. mega_collector — 9模块14数据源统一采集

消费路径：
- KB线索 → LLM每小时消化(05分cron) → kb_insights.json → 推荐引擎情感因子
- stock_kb → 毫秒级SQL查询(单票/条件筛选/事件画像)
- Gold层 → 因子IC评估 + ML训练 + 组合回测

核心原则：一次采集多处复用，统一写入分散消费，当天数据24h内冻结入Bronze不可变层。
```
