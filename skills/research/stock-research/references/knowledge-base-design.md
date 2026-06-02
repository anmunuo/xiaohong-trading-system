# 基本面知识库 · 架构设计

位于 `~/.hermes/profiles/xiaohong/scripts/knowledge_base.py`。

## 定位

不与瞭望塔冲突——瞭望塔是 08:30 盘前快照，知识库是**每小时增量积累的持久化检索系统**。二者互补：

| 系统 | 频率 | 数据特点 | 用途 |
|------|:--:|------|------|
| 瞭望塔 v6.0 | 08:30 一次 | 实时快照 + 多维分析 | 盘前决策 |
| 知识库 | 每小时 | 持续累计 + 历史追溯 | 趋势分析 / 检索 |

## 目录结构

```
data/knowledge_base/
├── index.json              ← 总索引（最新时间戳 + 各分类条目数）
├── search_index.json       ← 倒排索引（关键词 → 事件ID 列表）
├── leads/
│   └── latest.json         ← 最新高价值线索 Top 20（按权重排序）
├── announcements/
│   └── YYYY-MM-DD.json     ← 每日公告事件（去重存储）
├── policy_news/
│   └── YYYY-MM-DD.json     ← 每日政策/宏观新闻
├── research/
│   └── YYYY-MM-DD.json     ← 每日券商研报摘要
└── stock_events/
    ├── 688525.json          ← 佰维存储事件链（最近30条）
    ├── 600519.json          ← 贵州茅台事件链
    └── ...（按需创建，目前已覆盖224只股票）
```

## 核心设计

### 增量采集

每次运行只拉取当天数据，与已有记录比哈希去重，仅新增不重复的条目。

```
collect_all(date_str)
  ├─ fetch_corporate_announcements() → 公告
  ├─ fetch_policy_macro_news()       → 政策/新闻
  └─ fetch_research_reports()        → 研报
        ↓
  _content_hash() 去重 → 仅新增条目
        ↓
  _save_records()          → 日期文件
  _update_search_index()   → 倒排索引
  _update_stock_events()   → 个股事件链（保留30条）
  _update_leads()          → Top 20 线索
```

### 去重算法

```python
DEDUP_FIELDS = ['code', 'title', 'date', 'source']
hash = md5('code|title[:100]|date|source')[:12]
```

### 数据保留

- 日文件：保留 7 天（`_cleanup_old_files()` 自动清理）
- 个股事件链：保留 30 条
- 线索：保留 Top 20（按权重 × 新鲜度排序）
- 倒排索引：持续累加

## 检索接口

| 命令 | 功能 |
|------|------|
| `python3 knowledge_base.py leads` | 最新高价值线索 Top 20 |
| `python3 knowledge_base.py search --sector 半导体` | 按板块搜索事件 |
| `python3 knowledge_base.py search --stock 688525` | 个股事件历史链 |
| `python3 knowledge_base.py search --keyword 合同签订` | 倒排索引关键词搜索 |
| `python3 knowledge_base.py stats` | 知识库统计数据 |
| `python3 knowledge_base.py collect` | 手动触发一次采集 |

## Cron 配置

- 时间：`0 * * * *`（每小时整点）
- 模式：`no_agent=true`（纯 Python 脚本，零 token 消耗）
- 投递：`local`（本地存储，不推送飞书）
- 脚本：`cron_kb_collector.sh` → `python3 knowledge_base.py collect`

## 与瞭望塔集成（未来）

瞭望塔 v6.0 当前直接从 API 拉取实时快照。未来可通过知识库获取：
- 「过去 7 天某板块的事件密度趋势」→ 判断动量加速/衰减
- 「某只股票 30 天内事件链」→ 识别持续催化 vs 一次性事件
- 「合同签订类事件近期高频板块」→ 提前发现订单驱动的板块轮动

## 已知局限

- 去重基于内容哈希，同一公告轻微修改标题会被视为新记录
- 板块分类依赖关键词匹配，非涨停股可能漏分类
- 倒排索引不清理过期条目（内存占用可控，暂缓优化）
- 研报只覆盖热门股票（top 30 资金流入股+事件关联股）
