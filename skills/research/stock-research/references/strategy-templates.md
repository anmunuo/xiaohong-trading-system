# 策略模板参数化引擎 v1.0

> 借鉴 VibetradingLabs 策略模板思路，将推荐引擎+侦察兵+止损规则打包为可切换模板。

**脚本**: `scripts/strategy_templates.py`
**版本**: v1.0 (2026-06-05)

## 设计动机

当前 `stock_recommender.py` 的因子权重硬编码（event=0.30/fund=0.25/sentiment=0.18/technical=0.15/research=0.07），进化引擎只能逐参数微调，无法根据市场环境整体切换策略风格。借鉴 VibetradingLabs 的 `vibetrading.templates.momentum.generate()` 参数化思路，创建模板系统。

## 三模板

| 模板 | 适用市场 | 因子倾斜 | 止损 | 仓位上限 |
|:--|:--|:--|:--|:--|
| `balanced` | 震荡/方向不明 | 均衡 (30/25/18/15/7) | -5%/-7% | 33%/9只 |
| `aggressive` | 强势上涨/北向流入 | 重事件+技术 (35/15/20/20/5) | -3%/-5% | 40%/12只 |
| `defensive` | 弱势/高估值/去杠杆 | 重基本面+研究 (15/35/15/10/20) | -7%/-10% | 20%/6只 |

## CLI

```bash
python3 strategy_templates.py --list           # 列出所有模板
python3 strategy_templates.py --show aggressive # 查看模板详情（含权重可视化条形图）
python3 strategy_templates.py --apply defensive # 切换模板 → data/active_template.json
```

## 集成链路

```
➊ LLM(瞭望塔晨报) 宏观判断 → 选择模板
➋ strategy_templates.py --apply <name>
➌ stock_recommender._load_factor_weights() 读取 active_template.json
➍ 模板权重 × IC动态微调(0.8~1.2) → 最终权重
➎ scout.py / ammo_risk.py 读取模板的风控/仓位配置
```

## 模板数据结构

```json
{
  "recommender": {
    "factor_weights": {"event": 0.30, "fund": 0.25, "sentiment": 0.18, "technical": 0.15, "research": 0.07, "new_factors": 0.05},
    "exclude": {"min_market_cap": 30, "max_market_cap": 2000, "max_lianban": 2, "max_change_pct": 9}
  },
  "scout": {"flow_threshold_neutral": 5000, "max_picks_double": 6, ...},
  "risk": {"default_stop_loss": -5.0, "max_position_pct": 33.3, ...},
  "position": {"light": 0.30, "medium": 0.50, "heavy": 0.70, "full": 0.90}
}
```

## 注意事项

- 模板切换立即生效，不改变已持仓标的的止损
- 用户可扩展自定义模板：写入 `data/strategy_templates.json`
- IC 动态权重微调（0.8~1.2 乘法叠加）不会改变模板的相对权重排序
