# 财务数据集成模式 v8.3

## 概览

通过 tushare `fina_indicator` (108字段) + `income/balancesheet/cashflow` 三大报表，为推荐引擎和研究员系统注入深度基本面分析能力。此前系统仅依赖 PE/PB（daily_basic），缺少 ROE/毛利率/负债率/现金流等核心指标。

## 数据源

| API | 字段数 | 关键字段 | 权限要求 |
|:--|:--:|:--|:--|
| `pro.fina_indicator(ts_code, period)` | 108 | eps, bps, roe, roa_yearly, grossprofit_margin, netprofit_margin, debt_to_assets, ocfps, fcff, netprofit_yoy | 基础权限 ✅ |
| `pro.income(ts_code, period)` | 60+ | total_revenue, operate_profit, n_income, total_cogs | 基础权限 ✅ |
| `pro.balancesheet(ts_code, period)` | 80+ | total_assets, total_liab, total_hldr_eqy_exc_min_int | 基础权限 ✅ |
| `pro.cashflow(ts_code, period)` | 50+ | n_cashflow_act (经营现金流) | 基础权限 ✅ |

## 函数清单

### data_pipeline.py

| 函数 | 说明 | 缓存 |
|:--|:--|:--:|
| `get_financial_indicator(code, period=None)` | 核心财务指标（roe/roa/毛利率/负债率/eps/ocf/利润增速等13项） | 24h |
| `get_financial_summary(code)` | 综合财务评分(0-100) + highlights + risks | 24h |
| `_safe_float(row, col)` | 安全数值提取 | — |

### get_financial_summary 评分逻辑

```
基础分=50
+ ROE≥20: +15, ≥10: +8, ≥5: +2, 负值: -8
+ 毛利率≥40: +12, ≥20: +5, <10: -5
+ 负债率<40: +8, >80: -8
+ 利润增速≥30: +8, >0: +3, <-20: -10
+ 经营现金流>EPS: +6, OCF<0: -5
```

### 集成点

| 模块 | 方式 | 权重 |
|:--|:--|:--|
| 推荐引擎 `_score_fund()` | PE/PB(60%) + fin_summary(40%) 融合 | 40% |
| 研究员 `FundamentalResearcher.analyze()` | 扫描池内标的财报 → 池均分 + 个股亮点/风险 | — |

## 实测效果

```
茅台   600519: 85分  ROE 34.5%  毛利率 91.2%  低负债率         🟢
宁德   300750: 84分  ROE 24.7%  毛利率 26.3%  利润+42%         🟢
振华   603067: 79分  ROE 19.1%  毛利率 26.9%                   🟢
先达   603086: 60分  ROE  6.7%              经营现金流为负      🟡
镇洋   603213: 41分  ROE  3.9%  毛利率  9.3% 利润-60%          🔴
```

## 陷阱

1. **字段名是 `grossprofit_margin` 不是 `gross_margin`**：tushare fina_indicator 中毛利率字段名为 `grossprofit_margin`（108字段中的第20+列），ROE 是 `roe`，净利润率是 `netprofit_margin`。
2. **很多字段为空 (None)**：fina_indicator 的 108 个字段中，部分仅对特定行业或报告期有效（如 `gross_margin` 对银行股为空）。代码中全部用 `or 0` 兜底。
3. **period 格式**：`YYYYMMDD`，如 `20251231`。只支持季度末和年末日期。
4. **ts_code 格式**：必须带后缀如 `000001.SZ`。函数内部做了自动补全（`stock_code.startswith(('0','3')) → .SZ`），但传带后缀的最安全。
5. **盘后/盘前调用注意**：每只标的 ~0.3s（tushare API 响应），8 只标的 ~2.5s。推荐引擎已在 `_score_fund` 中用 try/except 包裹，单只失败不影响其他。
6. **不要逐季度拉取**：fina_indicator 一次只返回一个 period 的数据。如果要看趋势，多次调用。目前系统只拉最近年度，足够区分优质/劣质标的。
