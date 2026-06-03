#!/usr/bin/env python3
"""
portfolio_backtest.py — 推荐池组合回测引擎
===========================================
回测每日推荐池9只等权组合，验证推荐引擎整体有效性。

用法:
  python3 portfolio_backtest.py --days 60     # 回测近60个交易日
  python3 portfolio_backtest.py --report      # 输出回测报告
  python3 portfolio_backtest.py --compare     # 与沪深300对比

指标:
  夏普比率 / 最大回撤 / 胜率 / 换手率 / 超额收益 / 信息比率
"""

import sys, os, json, math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

POOL_DIR = SCRIPT_DIR / 'data'
REPORT_PATH = SCRIPT_DIR / 'data' / 'portfolio_backtest.json'
RISK_FREE_RATE = 0.015  # 1.5% 年化无风险利率


@dataclass
class DailyResult:
    date: str
    portfolio_return: float = 0.0
    benchmark_return: float = 0.0
    n_stocks: int = 0
    turnover: float = 0.0


@dataclass
class BacktestReport:
    start_date: str
    end_date: str
    n_days: int

    # 收益
    total_return: float = 0.0
    annual_return: float = 0.0
    excess_return: float = 0.0          # vs 沪深300

    # 风险
    volatility: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_days: int = 0

    # 风险调整
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    information_ratio: float = 0.0

    # 交易
    win_rate: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    avg_turnover: float = 0.0           # 平均日换手

    daily_results: List[Dict] = field(default_factory=list)


# ═══════════════════════════════════════
# 组合回测引擎
# ═══════════════════════════════════════

class PortfolioBacktest:
    """推荐池等权组合回测"""

    def __init__(self, pool_dir: Path = None):
        self.pool_dir = pool_dir or POOL_DIR

    def run(self, lookback_days: int = 60,
            benchmark_code: str = '000300') -> BacktestReport:
        """
        回测最近 N 个交易日的推荐池表现。

        策略: 每日按推荐池等权持有，次日收盘调仓
        """
        # 收集每日推荐池
        pool_files = sorted(self.pool_dir.glob('daily_pool*.json'))
        if not pool_files:
            # fallback: 直接用当前 pool
            pool_path = self.pool_dir / 'daily_pool.json'
            if pool_path.exists():
                pool_files = [pool_path]

        if not pool_files:
            raise FileNotFoundError("无推荐池数据。请先运行 stock_recommender.py")

        # 提取股票池
        pool_history = self._extract_pool_history(pool_files, lookback_days)
        if not pool_history:
            raise ValueError("无法从推荐池提取历史数据")

        # 获取历史行情
        all_codes = set()
        for stocks in pool_history.values():
            all_codes.update(stocks)
        codes = list(all_codes)

        price_data = self._get_price_data(codes, lookback_days + 30)
        if not price_data:
            raise ValueError("无法获取历史行情")

        # 获取基准行情
        benchmark_prices = self._get_benchmark_prices(benchmark_code, lookback_days + 30)

        # 逐日回测
        dates = sorted(pool_history.keys())
        if len(dates) < 10:
            raise ValueError(f"有效交易日不足: {len(dates)}")

        daily_results = []
        prev_stocks = set()

        for i, date in enumerate(dates[1:], 1):  # 从第二天开始（用前一天选股）
            prev_date = dates[i-1]
            stocks = pool_history.get(prev_date, [])
            if not stocks:
                continue

            n = min(len(stocks), 9)
            selected = stocks[:n]
            weight = 1.0 / n if n > 0 else 0

            # 计算当日组合收益
            port_ret = 0.0
            valid_count = 0
            for code in selected:
                px = price_data.get(code, {})
                if prev_date in px and date in px:
                    ret = (px[date] - px[prev_date]) / px[prev_date]
                    port_ret += ret * weight
                    valid_count += 1

            if valid_count == 0:
                continue

            # 基准收益
            bench_ret = 0.0
            if prev_date in benchmark_prices and date in benchmark_prices:
                bench_ret = (benchmark_prices[date] - benchmark_prices[prev_date]) / benchmark_prices[prev_date]

            # 换手率
            curr_stocks = set(selected)
            turnover = len(curr_stocks - prev_stocks) / max(len(curr_stocks), 1)
            prev_stocks = curr_stocks

            daily_results.append(DailyResult(
                date=date,
                portfolio_return=round(port_ret, 6),
                benchmark_return=round(bench_ret, 6),
                n_stocks=valid_count,
                turnover=round(turnover, 4),
            ))

        return self._compute_report(daily_results)

    def _extract_pool_history(self, pool_files: List[Path],
                               lookback: int) -> Dict[str, List[str]]:
        """从推荐池文件提取历史选股列表"""
        history = {}
        for f in pool_files[-lookback:]:
            try:
                data = json.loads(f.read_text())
                date = data.get('date', '')
                if not date:
                    # 从文件名尝试提取
                    stem = f.stem
                    date = stem.replace('daily_pool_', '').replace('daily_pool', '')

                candidates = data.get('candidates', data.get('recommendations', []))
                codes = [str(c['code']) for c in candidates[:9] if c.get('code')]
                if codes and 8 <= len(date) <= 10:
                    history[date] = codes
            except Exception:
                continue
        return history

    def _get_price_data(self, codes: List[str],
                         days: int) -> Dict[str, Dict[str, float]]:
        """获取多只股票的历史收盘价 {code: {date: close}}"""
        try:
            from data_pipeline import get_historical_k_with_ma
            bs_data = get_historical_k_with_ma(codes[:50], days=days)
        except Exception:
            return {}

        price_data = {}
        for code, bars in bs_data.items():
            px = {}
            for b in bars:
                date = b.get('date', '')
                close = b.get('close', 0)
                if date and close > 0:
                    px[date] = close
            if px:
                price_data[code] = px
        return price_data

    def _get_benchmark_prices(self, code: str,
                               days: int) -> Dict[str, float]:
        """获取基准指数历史收盘价"""
        try:
            from data_pipeline import get_historical_k_with_ma
            bs_data = get_historical_k_with_ma([code], days=days)
            bars = bs_data.get(code, [])
            return {b['date']: b['close'] for b in bars if b.get('date') and b['close'] > 0}
        except Exception:
            return {}

    def _compute_report(self, results: List[DailyResult]) -> BacktestReport:
        """计算回测指标"""
        if not results:
            return BacktestReport(start_date='', end_date='', n_days=0)

        returns = np.array([r.portfolio_return for r in results])
        bench_returns = np.array([r.benchmark_return for r in results])
        n = len(results)

        # 累计收益
        cum_ret = np.prod(1 + returns) - 1
        bench_cum = np.prod(1 + bench_returns) - 1
        excess = cum_ret - bench_cum

        # 年化
        ann_factor = 252 / n if n > 0 else 1
        ann_ret = (1 + cum_ret) ** ann_factor - 1

        # 波动率
        vol = float(np.std(returns) * np.sqrt(252))

        # 最大回撤
        cum = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        max_dd = float(dd.min())
        max_dd_days = int((dd < 0).sum())

        # 夏普
        excess_ret = returns - RISK_FREE_RATE / 252
        sharpe = float(excess_ret.mean() / excess_ret.std() * np.sqrt(252)) if excess_ret.std() > 0 else 0

        # Sortino
        downside = excess_ret[excess_ret < 0]
        sortino = float(excess_ret.mean() / downside.std() * np.sqrt(252)) if len(downside) > 0 and downside.std() > 0 else 0

        # Calmar
        calmar = ann_ret / abs(max_dd) if max_dd < 0 else 0

        # 信息比率
        tracking_error = np.std(returns - bench_returns) * np.sqrt(252)
        ir = float(excess / tracking_error) if tracking_error > 0 else 0

        # 胜率
        wins = returns[returns > 0]
        losses = returns[returns < 0]
        win_rate = len(wins) / n if n > 0 else 0
        avg_win = float(wins.mean()) if len(wins) > 0 else 0
        avg_loss = float(losses.mean()) if len(losses) > 0 else 0
        profit_factor = abs(wins.sum() / losses.sum()) if losses.sum() != 0 else float('inf')

        # 换手率
        turnovers = [r.turnover for r in results]
        avg_turnover = float(np.mean(turnovers)) if turnovers else 0

        return BacktestReport(
            start_date=results[0].date,
            end_date=results[-1].date,
            n_days=n,
            total_return=round(cum_ret * 100, 2),
            annual_return=round(ann_ret * 100, 2),
            excess_return=round(excess * 100, 2),
            volatility=round(vol * 100, 2),
            max_drawdown=round(max_dd * 100, 2),
            max_drawdown_days=max_dd_days,
            sharpe_ratio=round(sharpe, 2),
            sortino_ratio=round(sortino, 2),
            calmar_ratio=round(calmar, 2),
            information_ratio=round(ir, 2),
            win_rate=round(win_rate * 100, 2),
            avg_win=round(avg_win * 100, 4),
            avg_loss=round(avg_loss * 100, 4),
            profit_factor=round(profit_factor, 2) if profit_factor != float('inf') else 99.99,
            avg_turnover=round(avg_turnover * 100, 2),
            daily_results=[{
                'date': r.date,
                'ret': round(r.portfolio_return * 100, 4),
                'bench': round(r.benchmark_return * 100, 4),
                'n': r.n_stocks,
                'turnover': round(r.turnover * 100, 2),
            } for r in results],
        )


# ═══════════════════════════════════════
# 报告格式化
# ═══════════════════════════════════════

def format_report(report: BacktestReport) -> str:
    from report_formatter import Report

    color = 'green' if report.total_return > 0 else 'red'
    r = Report(title='推荐池组合回测', icon='📊', color=color)
    r.header_meta(
        区间=f'{report.start_date} ~ {report.end_date}',
        交易日=f'{report.n_days}天',
    )

    r.section('收益指标')
    r.kv('累计收益', f'{report.total_return:+.2f}%',
         f'年化 {report.annual_return:+.2f}%')
    r.kv('超额收益 (vs HS300)', f'{report.excess_return:+.2f}%')

    r.section('风险指标')
    r.kv('年化波动率', f'{report.volatility:.2f}%')
    r.kv('最大回撤', f'{report.max_drawdown:.2f}%',
         f'持续 {report.max_drawdown_days} 天')
    r.kv('夏普比率', f'{report.sharpe_ratio:.2f}')
    r.kv('Sortino比率', f'{report.sortino_ratio:.2f}')
    r.kv('Calmar比率', f'{report.calmar_ratio:.2f}')
    r.kv('信息比率', f'{report.information_ratio:.2f}')

    r.section('交易统计')
    r.kv('日胜率', f'{report.win_rate:.1f}%')
    r.kv('平均盈利日', f'{report.avg_win:.3f}%')
    r.kv('平均亏损日', f'{report.avg_loss:.3f}%')
    r.kv('盈亏比', f'{report.profit_factor:.2f}')
    r.kv('平均换手率', f'{report.avg_turnover:.1f}%')

    # 评级
    star = '⭐⭐⭐⭐⭐' if report.sharpe_ratio > 2.0 else (
        '⭐⭐⭐⭐' if report.sharpe_ratio > 1.0 else (
        '⭐⭐⭐' if report.sharpe_ratio > 0.5 else '⭐⭐'))

    r.divider()
    r.section('综合评级')
    r.text(f'{star}  夏普={report.sharpe_ratio:.2f}  |  '
           f'超额={report.excess_return:+.1f}%  |  '
           f'回撤={report.max_drawdown:.1f}%')

    r.footer(f'portfolio_backtest.py · {datetime.now().strftime("%Y-%m-%d")}')
    return r.markdown()


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=60, help='回测天数')
    ap.add_argument('--report', action='store_true', help='输出格式化报告')
    ap.add_argument('--json', action='store_true', help='JSON输出')
    args = ap.parse_args()

    bt = PortfolioBacktest()
    try:
        report = bt.run(lookback_days=args.days)
    except (FileNotFoundError, ValueError) as e:
        print(f'回测失败: {e}')
        print('提示: 需有 daily_pool.json 历史数据。')
        print('  当前仅有单日推荐池，累积多日后重新运行。')
        return

    # 保存
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps({
        **{k: v for k, v in report.__dict__.items() if k != 'daily_results'},
        'daily_results': report.daily_results,
    }, ensure_ascii=False, indent=2))

    if args.json:
        print(json.dumps(report.__dict__, ensure_ascii=False, indent=2, default=str))
    elif args.report:
        print(format_report(report))
    else:
        print(f'回测完成: {report.n_days}天')
        print(f'  累计: {report.total_return:+.2f}%  |  超额: {report.excess_return:+.2f}%')
        print(f'  夏普: {report.sharpe_ratio:.2f}   |  回撤: {report.max_drawdown:.2f}%')
        print(f'  胜率: {report.win_rate:.1f}%    |  盈亏比: {report.profit_factor:.2f}')


if __name__ == '__main__':
    main()
