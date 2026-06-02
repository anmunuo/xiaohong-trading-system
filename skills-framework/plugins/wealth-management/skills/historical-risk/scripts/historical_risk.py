#!/usr/bin/env python3
"""
历史风险指标计算
=================
对标 JoelLewis/finance_skills → historical_risk.py

计算: 年化收益/波动率、夏普/Sortino/Calmar、最大回撤、Beta、VaR/CVaR

用法:
  python3 historical_risk.py --returns "0.01,-0.02,..." [--benchmark "..."] [--risk-free 0.03]
"""
import sys
import json
import math
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional, List


@dataclass
class RiskMetrics:
    """历史风险指标"""
    # 基础
    annual_return: float = 0.0
    annual_volatility: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    
    # 回撤
    max_drawdown: float = 0.0
    max_drawdown_duration_days: int = 0
    calmar_ratio: float = 0.0
    
    # 系统性风险
    beta: Optional[float] = None
    alpha: Optional[float] = None
    
    # 尾部风险
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    cvar_99: float = 0.0
    
    # 分布
    skewness: float = 0.0
    kurtosis: float = 0.0
    positive_days_pct: float = 0.0
    
    # 元数据
    data_points: int = 0
    frequency: str = "daily"
    risk_free_rate: float = 0.03


def calculate_historical_risk(
    returns: np.ndarray,
    benchmark: np.ndarray = None,
    risk_free_rate: float = 0.03,
    frequency: str = "daily",
) -> RiskMetrics:
    """计算全部历史风险指标"""
    n = len(returns)
    if n < 20:
        raise ValueError(f"至少需要 20 个数据点，当前 {n}")
    
    # 年化系数
    ann_factor = {"daily": 252, "weekly": 52, "monthly": 12}.get(frequency, 252)
    rf_daily = risk_free_rate / ann_factor
    
    metrics = RiskMetrics(data_points=n, frequency=frequency, risk_free_rate=risk_free_rate)
    
    # ── 收益与波动 ──
    excess = returns - rf_daily
    mean_ret = np.mean(returns)
    mean_excess = np.mean(excess)
    std_ret = np.std(returns, ddof=1)
    
    metrics.annual_return = float((1 + mean_ret) ** ann_factor - 1)
    metrics.annual_volatility = float(std_ret * math.sqrt(ann_factor))
    
    if metrics.annual_volatility > 0:
        metrics.sharpe_ratio = float((metrics.annual_return - risk_free_rate) / metrics.annual_volatility)
    
    # ── Sortino ──
    downside = returns[returns < 0]
    if len(downside) > 1:
        downside_std = np.std(downside, ddof=1) * math.sqrt(ann_factor)
        if downside_std > 0:
            metrics.sortino_ratio = float((metrics.annual_return - risk_free_rate) / downside_std)
    
    # ── 最大回撤 ──
    cumulative = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cumulative)
    drawdowns = (cumulative - peak) / peak
    metrics.max_drawdown = float(np.min(drawdowns))
    
    # 回撤持续期
    dd_start = None
    max_duration = 0
    for i in range(len(drawdowns)):
        if drawdowns[i] < 0 and dd_start is None:
            dd_start = i
        elif drawdowns[i] >= 0 and dd_start is not None:
            duration = i - dd_start
            max_duration = max(max_duration, duration)
            dd_start = None
    metrics.max_drawdown_duration_days = max_duration
    
    if abs(metrics.max_drawdown) > 0:
        metrics.calmar_ratio = float(metrics.annual_return / abs(metrics.max_drawdown))
    
    # ── Beta / Alpha ──
    if benchmark is not None and len(benchmark) == n:
        bench_excess = benchmark - rf_daily
        cov = np.cov(excess, bench_excess)[0, 1]
        var_bench = np.var(bench_excess, ddof=1)
        if var_bench > 0:
            metrics.beta = float(cov / var_bench)
            bench_annual = float((1 + np.mean(benchmark)) ** ann_factor - 1)
            metrics.alpha = float(metrics.annual_return - (risk_free_rate + metrics.beta * (bench_annual - risk_free_rate)))
    
    # ── VaR / CVaR ──
    sorted_ret = np.sort(returns)
    metrics.var_95 = float(np.percentile(returns, 5))
    metrics.var_99 = float(np.percentile(returns, 1))
    metrics.cvar_95 = float(np.mean(sorted_ret[:int(n * 0.05)]))
    metrics.cvar_99 = float(np.mean(sorted_ret[:int(n * 0.01)]))
    
    # ── 分布 ──
    metrics.skewness = float((np.mean((returns - mean_ret) ** 3) / (std_ret ** 3)) if std_ret > 0 else 0)
    metrics.kurtosis = float((np.mean((returns - mean_ret) ** 4) / (std_ret ** 4)) if std_ret > 0 else 0)
    metrics.positive_days_pct = float(np.mean(returns > 0) * 100)
    
    return metrics


def generate_report(metrics: RiskMetrics) -> str:
    """生成 Markdown 报告"""
    def rating(sharp: float) -> str:
        if sharp >= 1.0: return "✅ 优秀"
        if sharp >= 0.5: return "⚠️ 一般"
        return "❌ 较差"
    
    def color(val: float) -> str:
        return "🟢" if val > 0 else "🔴"
    
    lines = [
        f"## 📊 历史风险分析报告",
        f"",
        f"**数据**: {metrics.data_points} 个{metrics.frequency}数据点 | **无风险利率**: {metrics.risk_free_rate*100:.1f}%",
        f"",
        f"| 指标 | 数值 | 评价 |",
        f"|------|------|------|",
        f"| 年化收益率 | {metrics.annual_return*100:+.2f}% | {color(metrics.annual_return)} |",
        f"| 年化波动率 | {metrics.annual_volatility*100:.2f}% | — |",
        f"| 夏普比率 | {metrics.sharpe_ratio:.2f} | {rating(metrics.sharpe_ratio)} |",
        f"| Sortino比率 | {metrics.sortino_ratio:.2f} | {rating(metrics.sortino_ratio)} |",
        f"| 最大回撤 | {metrics.max_drawdown*100:.1f}% | 持续{metrics.max_drawdown_duration_days}天 |",
        f"| Calmar比率 | {metrics.calmar_ratio:.2f} | — |",
    ]
    
    if metrics.beta is not None:
        lines.append(f"| Beta | {metrics.beta:.2f} | {'防御型' if metrics.beta < 1 else '进攻型'} |")
    if metrics.alpha is not None:
        lines.append(f"| Alpha | {metrics.alpha*100:+.2f}% | {color(metrics.alpha)} |")
    
    lines += [
        f"| VaR(95%) | {metrics.var_95*100:.2f}% | — |",
        f"| CVaR(95%) | {metrics.cvar_95*100:.2f}% | — |",
        f"| 偏度 | {metrics.skewness:.2f} | {'正偏(右尾)' if metrics.skewness > 0 else '负偏(左尾)'} |",
        f"| 峰度 | {metrics.kurtosis:.2f} | {'肥尾' if metrics.kurtosis > 3 else '正常'} |",
        f"| 正收益天数 | {metrics.positive_days_pct:.1f}% | — |",
        f"",
        f"*数据: historical-risk skill · {datetime.now().isoformat()}*",
    ]
    
    return "\n".join(lines)


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="历史风险指标计算")
    p.add_argument("--returns", required=True, help="逗号分隔的收益率序列")
    p.add_argument("--benchmark", help="基准收益率序列")
    p.add_argument("--risk-free", type=float, default=0.03, help="无风险利率(默认3%)")
    p.add_argument("--frequency", default="daily", choices=["daily","weekly","monthly"])
    p.add_argument("--output", help="JSON输出路径")
    p.add_argument("--report", action="store_true", help="输出Markdown报告")
    args = p.parse_args()
    
    returns = np.array([float(x) for x in args.returns.split(",")])
    benchmark = np.array([float(x) for x in args.benchmark.split(",")]) if args.benchmark else None
    
    metrics = calculate_historical_risk(returns, benchmark, args.risk_free, args.frequency)
    
    if args.report:
        print(generate_report(metrics))
    else:
        result = asdict(metrics)
        result["annual_return"] = round(result["annual_return"], 6)
        result["annual_volatility"] = round(result["annual_volatility"], 6)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(asdict(metrics), indent=2, ensure_ascii=False))
        print(f"📤 已保存: {args.output}")


if __name__ == "__main__":
    main()
