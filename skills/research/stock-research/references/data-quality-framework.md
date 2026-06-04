# 数据真实性管理框架 v1.0

## 架构

```python
from data_quality import verify as qv
stamp = qv(data, "north_flow", "get_north_flow")
# → QualityStamp(trust=VERIFIED, stars="★★★☆☆", passed_gates=5, failed_gates=0)
```

## 五道质检门

| 关卡 | 类 | 检查内容 | 不通过 |
|:--|:--|:--|:--|
| P0 时效 | FreshnessGate | 采集时间在 SLA 窗口内？ | BLOCKED |
| P1 来源 | SourceGate | 字段是否完整？有无已知陷阱字段？ | DEGRADED |
| P2 值域 | SanityGate | 值在合理范围？(如北向 -200~300亿) | DEGRADED |
| P3 交叉 | CrossGate | 独立数据源交叉验证一致性 | DEGRADED |
| P4 趋势 | TrendGate | 与历史基线连贯？偏离均值异常？ | CAUTION |

## 消费者接入模式

```python
# 生产端 (data_pipeline)
from data_quality import verify as qv
qs = qv(result, "north_flow", "get_north_flow")
result["_quality_stamp"] = qs.to_dict()

# 消费端 (researchers / scout / recommender)  
stamp = data.get("_quality_stamp", {})
if stamp.get("trust") in ("BLOCKED", "DEGRADED"):
    log.warning(f"数据不可信: {stamp.get('failed_gates')}")
    return  # 拒绝使用
```

## 铁律

> 信任等级 < ★★☆☆☆ (CAUTION) 时，**系统拒绝使用该数据**。必须先修复数据源。

## 已知字段陷阱

| 数据 | 陷阱 | 正确字段 | 误差 |
|:--|:--|:--|:--|
| 北向 | `ggt_ss+ggt_sz` (南向) | `north_money` (北向) | 6.8x |
| 财务 | 去年年报 (过时) | 最新季报 `roe_yearly` | 3x+ |
| 毛利率 | `None`→误标0 | `None`=无数据 | 定性误导 |
