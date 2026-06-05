#!/usr/bin/env python3
"""
backtest_chart.py — 回测曲线可视化引擎 v1.0
===========================================
基于 portfolio_backtest.py 的回测数据，生成权益曲线和回撤曲线图。

用法:
  python3 backtest_chart.py                     # 读取最新回测数据生成图表
  python3 backtest_chart.py --data portfolio_backtest.json  # 指定数据文件
  python3 backtest_chart.py --days 90           # 回测近90天并生成图表

输出:
  reports/charts/equity_curve_YYYYMMDD.png      # 权益曲线
  reports/charts/drawdown_curve_YYYYMMDD.png    # 回撤曲线
"""

import sys, os, json, math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

CHARTS_DIR = SCRIPT_DIR.parent / 'reports' / 'charts'
DATA_PATH = SCRIPT_DIR / 'data' / 'portfolio_backtest.json'
FONT_FAMILY = 'sans-serif'

__version__ = "1.0.0"

# 颜色方案
COLORS = {
    'portfolio': '#2f9e44',    # 安幕诺绿
    'benchmark': '#e8590c',    # 橙色
    'drawdown': '#e03131',     # 红色
    'watermark': '#f8f9fa',    # 浅灰
    'grid': '#dee2e6',         # 网格
    'bg': '#ffffff',           # 白底
    'text': '#212529',         # 文字
}


def _setup_matplotlib():
    """配置 matplotlib 中文字体 + Agg 后端"""
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm

    # 尝试中文字体（按优先级）
    cjk_fonts = [
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',
        'WenQuanYi Micro Hei',
        'Noto Sans CJK SC',
    ]
    for font_path in cjk_fonts:
        try:
            prop = fm.FontProperties(fname=font_path) if '/' in font_path else fm.FontProperties(family=font_path)
            fm.fontManager.addfont(font_path) if '/' in font_path else None
            plt.rcParams['font.family'] = prop.get_name()
            break
        except Exception:
            continue

    plt.rcParams['axes.unicode_minus'] = False
    plt.rcParams['figure.dpi'] = 120
    return plt


def _load_data(data_file: str = None) -> Dict:
    """加载回测数据"""
    path = Path(data_file) if data_file else DATA_PATH
    if not path.exists():
        return None
    with open(path) as f:
        return json.load(f)


def _compute_equity_curve(daily_returns: List[Dict], initial: float = 100000) -> tuple:
    """从日收益计算权益曲线"""
    dates = []
    equity = []
    benchmark = []

    cum_port = initial
    cum_bench = initial

    for d in daily_returns:
        dates.append(d.get('date', '')[:10])
        port_ret = d.get('portfolio_return', 0) / 100
        bench_ret = d.get('benchmark_return', 0) / 100
        cum_port *= (1 + port_ret)
        cum_bench *= (1 + bench_ret)
        equity.append(cum_port)
        benchmark.append(cum_bench)

    return dates, equity, benchmark


def _compute_drawdown_series(equity: List[float]) -> List[float]:
    """计算滚动回撤序列"""
    dd = []
    peak = equity[0]
    for v in equity:
        if v > peak:
            peak = v
        dd.append((v / peak - 1) * 100)
    return dd


def generate_equity_chart(data_file: str = None, output_path: str = None) -> str:
    """
    生成权益曲线图 (组合 vs 基准)

    Returns: 输出文件路径
    """
    data = _load_data(data_file)
    if not data:
        print("❌ 无回测数据")
        return None

    daily = data.get('daily_returns', data.get('daily', []))
    report = data.get('report', {})
    if not daily:
        print("❌ 回测数据无日收益序列")
        return None

    dates, equity, benchmark = _compute_equity_curve(daily)

    plt = _setup_matplotlib()
    fig, ax = plt.subplots(figsize=(14, 6))

    # 填充区域
    ax.fill_between(range(len(dates)), equity, benchmark,
                    where=np.array(equity) >= np.array(benchmark),
                    color=COLORS['portfolio'], alpha=0.08, label='超额收益')
    ax.fill_between(range(len(dates)), equity, benchmark,
                    where=np.array(equity) < np.array(benchmark),
                    color=COLORS['benchmark'], alpha=0.08, label='跑输基准')

    # 曲线
    ax.plot(equity, color=COLORS['portfolio'], linewidth=2.0, label='推荐池组合')
    ax.plot(benchmark, color=COLORS['benchmark'], linewidth=1.5,
            linestyle='--', label='沪深300')

    # 标注
    excess = (equity[-1] / benchmark[-1] - 1) * 100 if benchmark[-1] > 0 else 0
    ax.annotate(f'超额 {excess:+.1f}%',
                xy=(len(equity)-1, equity[-1]),
                xytext=(len(equity)-10, equity[-1] * 0.98),
                color=COLORS['portfolio'] if excess > 0 else COLORS['drawdown'],
                fontsize=11, fontweight='bold')

    # X轴日期标注（间隔取点）
    n = len(dates)
    step = max(1, n // 10)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([dates[i] for i in ticks], rotation=45, ha='right', fontsize=8)

    # 标签
    total_ret = report.get('total_return', (equity[-1]/100000 - 1)*100)
    sharpe = report.get('sharpe_ratio', 0)
    maxdd = report.get('max_drawdown', 0)

    ax.set_title(f'推荐池回测权益曲线  |  总收益 {total_ret:+.1f}%  |  '
                 f'夏普 {sharpe:.2f}  |  最大回撤 -{maxdd:.1f}%',
                 fontsize=14, fontweight='bold', color=COLORS['text'])
    ax.set_ylabel('净值 (¥)', fontsize=11)
    ax.legend(loc='upper left', framealpha=0.9)
    ax.grid(True, alpha=0.3, color=COLORS['grid'])
    ax.set_facecolor(COLORS['bg'])

    # Y轴格式化为金额
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f'¥{x/10000:.0f}万'))

    plt.tight_layout()

    # 保存
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = output_path or str(CHARTS_DIR / f'equity_curve_{datetime.now().strftime("%Y%m%d")}.png')
    fig.savefig(out, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close(fig)
    return out


def generate_drawdown_chart(data_file: str = None, output_path: str = None) -> str:
    """
    生成回撤曲线图

    Returns: 输出文件路径
    """
    data = _load_data(data_file)
    if not data:
        return None

    daily = data.get('daily_returns', data.get('daily', []))
    if not daily:
        return None

    dates, equity, _ = _compute_equity_curve(daily)
    drawdowns = _compute_drawdown_series(equity)
    report = data.get('report', {})

    plt = _setup_matplotlib()
    fig, ax = plt.subplots(figsize=(14, 5))

    # 水下区域着色
    ax.fill_between(range(len(dates)), 0, drawdowns,
                    where=np.array(drawdowns) < 0,
                    color=COLORS['drawdown'], alpha=0.3, label='回撤区间')
    ax.fill_between(range(len(dates)), 0, drawdowns,
                    where=np.array(drawdowns) >= 0,
                    color=COLORS['portfolio'], alpha=0.1)

    # 回撤曲线
    ax.plot(drawdowns, color=COLORS['drawdown'], linewidth=1.8, label='滚动回撤')

    # 最大回撤标注
    min_idx = np.argmin(drawdowns)
    ax.annotate(f'最大回撤 {drawdowns[min_idx]:.1f}%',
                xy=(min_idx, drawdowns[min_idx]),
                xytext=(min_idx + 5, drawdowns[min_idx] - 2),
                arrowprops=dict(arrowstyle='->', color=COLORS['drawdown'], lw=1.5),
                fontsize=10, fontweight='bold', color=COLORS['drawdown'])

    # 均值线
    mean_dd = np.mean(drawdowns)
    ax.axhline(y=mean_dd, color='gray', linestyle=':', alpha=0.5,
               label=f'均值 {mean_dd:.1f}%')

    # X轴
    n = len(dates)
    step = max(1, n // 10)
    ticks = list(range(0, n, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([dates[i] for i in ticks], rotation=45, ha='right', fontsize=8)

    maxdd = report.get('max_drawdown', abs(drawdowns[min_idx]))
    maxdd_days = report.get('max_drawdown_days', 0)

    ax.set_title(f'推荐池回撤曲线  |  最大回撤 -{maxdd:.1f}%  |  回撤天数 {maxdd_days}',
                 fontsize=14, fontweight='bold', color=COLORS['text'])
    ax.set_ylabel('回撤 (%)', fontsize=11)
    ax.set_ylim(min(drawdowns) * 1.15, 5)
    ax.legend(loc='lower left', framealpha=0.9)
    ax.grid(True, alpha=0.3, color=COLORS['grid'])
    ax.set_facecolor(COLORS['bg'])

    plt.tight_layout()

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    out = output_path or str(CHARTS_DIR / f'drawdown_curve_{datetime.now().strftime("%Y%m%d")}.png')
    fig.savefig(out, bbox_inches='tight', facecolor=COLORS['bg'])
    plt.close(fig)
    return out


def generate_all_charts(data_file: str = None) -> Dict[str, str]:
    """生成全部图表，返回 {type: path}"""
    results = {}
    eq = generate_equity_chart(data_file)
    if eq:
        results['equity'] = eq
    dd = generate_drawdown_chart(data_file)
    if dd:
        results['drawdown'] = dd
    return results


def generate_markdown_embed(charts: Dict[str, str]) -> str:
    """生成 Markdown 嵌入文本（用于文工团复盘）"""
    lines = []
    lines.append("## 📈 回测图表")
    lines.append("")
    for chart_type, path in charts.items():
        label = {'equity': '权益曲线', 'drawdown': '回撤曲线'}.get(chart_type, chart_type)
        lines.append(f"### {label}")
        lines.append(f"MEDIA:{path}")
        lines.append("")
    return '\n'.join(lines)


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description='回测曲线可视化引擎 v1.0')
    ap.add_argument('--data', type=str, help='回测数据文件路径')
    ap.add_argument('--days', type=int, default=60, help='回测天数（需重新回测）')
    ap.add_argument('--output', type=str, help='输出目录')
    ap.add_argument('--equity-only', action='store_true', help='仅生成权益曲线')
    ap.add_argument('--drawdown-only', action='store_true', help='仅生成回撤曲线')
    args = ap.parse_args()

    if args.days and not args.data:
        # 触发回测
        print(f"🔄 运行 {args.days} 天回测...")
        from portfolio_backtest import run_backtest
        result = run_backtest(days=args.days)
        if result is None:
            print("❌ 回测失败")
            sys.exit(1)

    if not _load_data(args.data):
        print("❌ 无回测数据，请先运行 portfolio_backtest.py")
        print("   python3 portfolio_backtest.py --days 60 --report")
        sys.exit(1)

    if args.drawdown_only:
        path = generate_drawdown_chart(args.data, args.output)
        if path:
            print(f"✅ 回撤曲线: {path}")
    elif args.equity_only:
        path = generate_equity_chart(args.data, args.output)
        if path:
            print(f"✅ 权益曲线: {path}")
    else:
        charts = generate_all_charts(args.data)
        for ctype, path in charts.items():
            print(f"✅ {ctype}: {path}")

        # 输出 Markdown 嵌入
        print()
        print(generate_markdown_embed(charts))


if __name__ == '__main__':
    main()
