# 回测曲线可视化引擎 v1.0

> 基于 portfolio_backtest.py 回测数据，生成权益曲线和回撤曲线 PNG 图表，嵌入文工团复盘。

**脚本**: `scripts/backtest_chart.py`
**版本**: v1.0 (2026-06-05)
**依赖**: matplotlib (需 `pip install matplotlib`), Noto Sans CJK 字体

## 生成图表

| 图表 | 文件 | 内容 |
|:--|:--|:--|
| 权益曲线 | `reports/charts/equity_curve_YYYYMMDD.png` | 推荐池组合 vs 沪深300 净值对比，超额收益标注，夏普/回撤指标标签 |
| 回撤曲线 | `reports/charts/drawdown_curve_YYYYMMDD.png` | 滚动回撤序列，水下区间着色，最大回撤箭头+天数标注 |

## CLI

```bash
python3 backtest_chart.py                        # 读取 portfolio_backtest.json 生成两张图
python3 backtest_chart.py --data custom.json     # 指定数据源
python3 backtest_chart.py --equity-only          # 仅权益曲线
python3 backtest_chart.py --drawdown-only        # 仅回撤曲线
```

## 集成链路

```
➊ portfolio_backtest.py --days 60 → portfolio_backtest.json (cron 17:20)
➋ review.py v3.1 复盘末尾 → backtest_chart.generate_all_charts()
➌ PNG 写入 reports/charts/
➍ MEDIA: 路径嵌入复盘报告 → 飞书渲染为图片
```

## 中文字体

使用 Noto Sans CJK Regular (`/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`)。matplotlib 通过 `font_manager.FontProperties(fname=...)` 直接加载。首次运行后如中文显示方块，删除 `~/.cache/matplotlib/` 并重新运行。

## 颜色方案

- 组合净值: `#2f9e44` (安幕诺绿)
- 沪深300: `#e8590c` (橙色虚线)
- 回撤着色: `#e03131` (红色半透明)
- 超额填充: 绿/橙 8%透明度
