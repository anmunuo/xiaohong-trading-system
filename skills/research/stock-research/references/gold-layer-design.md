# Gold 层设计 v1.0

## 架构

```
Silver stock_daily (历史60日)        scripts/data/daily_pool.json
         │                                       │
         ▼                                       │
┌─────────────────────────────────────┐          │
│         gold_pipeline.py            │          │
│                                     │◄─────────┘
│  factor_builder → 26维因子面板       │
│  ml_builder    → train.npz+eval.npz │
│  pool_archiver → 日期分区归档        │
└──────────────────────────────────────┘
               ▼
     data/gold/
     ├── factor_panel/YYYY/MM/DD/v3.parquet
     ├── ml_datasets/train_YYYYMMDD_v3.npz
     ├── daily_pool/YYYY/MM/DD.json
     └── _meta/gold_manifest.json
```

## 因子注册表 (v3, 26维)

| 类别 | 因子ID | 需要回溯 |
|:--|:--|:--|
| 动量 | mom_5d, mom_20d, mom_60d, alpha_idx | 6-61天 |
| 波动 | atr_14, vol_20d, downside_vol | 14-20天 |
| 资金 | net_flow, turnover, volume_ratio | 0 (直接取自Silver) |
| 筹码 | turnover_zscore, vol_ratio_trend, amplitude_5d | 5-20天 |
| 估值 | pe_ttm, pb, total_mv_log | 0 (直接取自Silver) |
| 质量 | is_suspended, is_st, n_quality_flags | 0 (直接取自Silver) |
| 滚动 | close_zscore, volume_zscore, pe_percentile, pb_percentile, ma5_deviation, ma20_deviation | 5-20天 |

## 启动期因子覆盖率时间线

```
Day 1:  ██░░░░░░░░ 24%  (资金+质量类，可直接从Silver读取)
Day 7:  ██████░░░░ 60%  (动量5d/20d/波动/筹码可用)
Day 30: █████████░ 90%  (全部短期因子可用)
Day 60: ██████████ 100% (mom_60d/滚动分位数全量)
```

## 启动期关键陷阱

### 陷阱1: 因子面板为0 → 所有代码被跳过

**现象**: `n_computed==0` → 因子面板未写入 → Pool也跳过归档
**修复**: 
1. 降低 `n < 5` → `n < 1` 门槛
2. 无历史日线时用当日 Silver 行构造最小 bars
3. Pool 归档提升到 `if/else` 外部始终执行

### 陷阱2: 因子覆盖率低是正常现象

不要在启动期告警因子覆盖率低。覆盖率随 Silver 历史积累自然提升。
不要为此绕过 Silver 直接调 BaoStock/tushare API——破坏可复现性。

### 陷阱3: PE/PB 全为 None

Silver 样本首批仅 100 只且 PE/PB 为 0（Bronze 样本缺基本面数据）。
需 tushare `fina_indicator` 或 `daily_basic` 注入 Silver 后才能激活估值因子。

## 可复现性

```bash
# 验证
python3 gold_pipeline.py --verify --date 2026-06-03
# → ✅ 可复现: 100只股票完全一致

# 从头重建
rm -rf data/gold/factor_panel/2026/06/03/
python3 gold_pipeline.py --date 2026-06-03
# 结果与首次写入完全一致（纯数学计算，无随机性）
```

## Cron 管线

```
15:40 Bronze 采集 → 15:45 Silver ETL → 15:50 Gold ETL
```
