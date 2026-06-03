# 分层数据架构 v1.0 — Bronze/Silver/Gold

## 核心理念

> **可复现 > 短期收益。** 
> 每一层只依赖上一层的冻结产物，不跨层调实时 API。

```
Bronze 原始层 → Silver 清洗层 → Gold 特征层
  "API说什么         "全A统一          "模型吃的
   就存什么"          一行"             最后一公里"

不可变 · 冻结        可追溯 · 质量标记   可版本化 · 归一化
从不修改             从Bronze重放       从Silver重放
```

## 三层定义

| 层 | 位置 | 格式 | 原则 |
|:--|:--|:--|:--|
| **Bronze** | `data/bronze/` | gzip JSON | 写入后永不修改，缺失不补，错误不删 |
| **Silver** | `data/silver/` | Parquet/JSON | 每日期×代码唯一一行，缺失标记来源 |
| **Gold** | `data/gold/` | Parquet+JSON | 每特征可追溯Silver层来源 |

## Bronze 层 (Phase 1 · 已完成)

```
data/bronze/
├── daily_kline/{YYYY}/{MM}/{DD}/{source}.json.gz
├── fundamentals/{YYYY}/{MM}/{DD}/{source}.json.gz
├── fund_flow/{YYYY}/{MM}/{DD}/{source}.json.gz
├── market_index/{YYYY}/{MM}/{DD}/{source}.json.gz
├── events/{YYYY}/{MM}/{DD}/{source}.json.gz
└── _meta/
    ├── daily_manifest.json      ← 每日采集清单
    └── schema_registry.json     ← 字段定义
```

### 写入引擎 (`bronze_ingest.py`)
- `BronzeWriter.write(data, source, category, date)` — 原子写入+幂等检查
- `BronzeCollector.collect_all(date)` — 收盘批量采集6类数据
- 验证: `bronze_verifier.py --date YYYY-MM-DD`

### data_pipeline 钩子
`_core.py` 中 `_bronze_write()` 函数，在以下入口植入:
- `get_index_data()` → akshare/market_index
- `get_north_flow()` → tushare/fund_flow
- `get_market_money_flow()` → tushare/fund_flow
- `get_top_flow_stocks()` → eastmoney/fund_flow
- `get_stock_realtime()` → sina/daily_kline

环境变量 `XIAOHONG_BRONZE=0` 可关闭 Bronze 写入。

## Silver 层 (Phase 2 · 待实施)

```
data/silver/
├── stock_daily/{YYYY}/{MM}/{DD}/all.parquet
├── fundamentals/{YYYY}/{MM}/{DD}/all.parquet
├── events/{YYYY}/{MM}/{DD}/corporate.parquet
└── _meta/
    ├── quality_report.json
    └── stock_master.parquet      ← 全A主表(永不过期)
```

规则:
- 停牌日: forward-fill close, volume=0
- 复权: 统一前复权 (BaoStock adjustflag='2')
- 异常: close 变化>20% 且非涨跌停 → quality_flag='suspicious'
- 去ST: stock_master 标记 → 过滤

## Gold 层 (Phase 3 · 待实施)

```
data/gold/
├── factor_panel/{YYYY}/{MM}/{DD}/v3.parquet
├── ml_datasets/train_{date}_v3.npz
├── daily_pool/{YYYY}/{MM}/{DD}.json     ← 推荐结果历史归档
└── _meta/
    ├── feature_lineage.json
    └── feature_set_v3.json
```

### 可复现性命令
```bash
# 从 Bronze 全量重建 Silver + Gold
python3 scripts/replay_day.py --date 2026-06-03
# → Bronze hash = a1b2... (与当日一致 ✅)
# → Silver hash = c3d4... (与当日一致 ✅)
# → Gold hash   = e5f6... (与当日一致 ✅)
```

## 历史数据仓库

```
data/warehouse/
├── stock_kline/{YYYY}/{MM}/{DD}.parquet     ← 全A日K线
├── stock_fundamentals/{YYYY}/{MM}/{DD}.parquet
├── stock_factors/{YYYY}/{MM}/{DD}_v3.parquet
├── events/announcements/{YYYY}/{MM}/{DD}.parquet
├── market_wide/indices/{YYYY}/{MM}/{DD}.parquet
└── _catalog/
    ├── date_index.json
    ├── stock_master.parquet
    └── schema_versions.json
```

## 存储估算

| 层级 | 日增量 | 年化 |
|:--|:--|:--|
| Bronze | ~20MB | ~5GB |
| Silver | ~20MB | ~5GB |
| Gold | ~30MB | ~7.5GB |
| **合计** | **~70MB** | **~17.5GB** |

## 关键约束

- **Gold 层不调 API，Silver 层不调 API。只有 Bronze 层可以调 API。**
- 删除整个 Gold → 从 Silver 重算 → 结果完全一致
- AI训练数据: 从 Bronze 重建 → 保证训练/预测数据一致性
