#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 回测引擎
===============================
TradingSkill 风格回测框架

功能:
  1. 基于历史日线回测任意策略
  2. 多指标统计：夏普比率/最大回撤/胜率/盈亏比/卡尔玛
  3. 参数网格搜索优化
  4. 可视化权益曲线（ASCII / JSON）
  5. 交易明细 CSV 导出

对标 gwrxuk/TradingSkill 的策略验证流程
"""
import sys
import json
import csv
import math
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple, Callable
import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from strategies.trading_skill_strategies import (
    get_strategy, list_strategies, StrategySignal,
    MACrossoverStrategy, RSIStrategy, MACDStrategy, 
    BollingerStrategy, CombinedStrategy,
)


# ═══════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════

@dataclass
class BacktestTrade:
    """回测中的单笔交易"""
    date: str
    symbol: str
    side: str
    price: float
    shares: int
    value: float
    fee: float
    signal_confidence: float
    strategy: str
    reason: str = ""
    pnl: float = 0.0
    pnl_pct: float = 0.0

@dataclass 
class BacktestResult:
    """回测结果"""
    strategy_name: str
    symbol: str
    start_date: str
    end_date: str
    initial_capital: float
    final_capital: float
    total_return: float
    annual_return: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    calmar_ratio: float
    win_rate: float
    total_trades: int
    wins: int
    losses: int
    avg_win: float
    avg_loss: float
    profit_factor: float
    equity_curve: List[Dict] = field(default_factory=list)
    trades: List[BacktestTrade] = field(default_factory=list)
    params: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════
# 回测引擎
# ═══════════════════════════════════════

class BacktestEngine:
    """
    回测引擎 — TradingSkill 风格
    
    用法:
      engine = BacktestEngine(initial_capital=100000, fee_rate=0.0003)
      result = engine.run(strategy, closes, dates, highs, lows)
    """
    
    def __init__(self, initial_capital: float = 100000, 
                 fee_rate: float = 0.0003, stamp_duty: float = 0.001,
                 slippage: float = 0.001):
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate          # 佣金
        self.stamp_duty = stamp_duty      # 印花税（仅卖出）
        self.slippage = slippage          # 滑点
    
    def run(self, strategy, symbol: str, closes: np.ndarray,
            dates: List[str] = None, highs: np.ndarray = None,
            lows: np.ndarray = None, volumes: np.ndarray = None
            ) -> BacktestResult:
        """运行回测"""
        n = len(closes)
        if n < 30:
            raise ValueError("至少需要 30 根 K 线")
        
        if dates is None:
            dates = [f"Day{i}" for i in range(n)]
        
        cash = self.initial_capital
        shares = 0
        equity = []
        trades = []
        
        buy_price = 0.0
        buy_date = ""
        
        # 预热期：前 30 根不交易，纯计算指标
        warmup = 30
        
        for i in range(warmup, n - 1):
            # 获取信号（用当前已知数据）
            window_closes = closes[:i + 1]
            window_highs = highs[:i + 1] if highs is not None else None
            window_lows = lows[:i + 1] if lows is not None else None
            window_volumes = volumes[:i + 1] if volumes is not None else None
            
            signal = strategy.analyze(
                symbol, window_closes, window_highs, window_lows, window_volumes
            )
            
            # 下一根开盘价（+滑点）
            next_open = closes[i + 1] * (1 + self.slippage)
            
            if signal.side == "BUY" and cash > 0:
                # 用 80% 可用资金买入
                trade_cash = cash * 0.8
                s = int(trade_cash / (next_open * 100)) * 100
                if s >= 100:
                    cost = next_open * s
                    fee = cost * self.fee_rate
                    if cost + fee <= cash:
                        shares += s
                        cash -= (cost + fee)
                        buy_price = next_open
                        buy_date = dates[i + 1]
                        
                        trades.append(BacktestTrade(
                            date=dates[i + 1], symbol=symbol, side="BUY",
                            price=next_open, shares=s, value=cost, fee=fee,
                            signal_confidence=signal.confidence,
                            strategy=signal.strategy_name,
                            reason=signal.reason,
                        ))
            
            elif signal.side == "SELL" and shares > 0:
                proceeds = next_open * shares
                fee = proceeds * self.fee_rate + proceeds * self.stamp_duty
                cash += (proceeds - fee)
                
                pnl = (next_open - buy_price) * shares
                pnl_pct = (next_open - buy_price) / buy_price * 100
                
                trades.append(BacktestTrade(
                    date=dates[i + 1], symbol=symbol, side="SELL",
                    price=next_open, shares=shares, value=proceeds, fee=fee,
                    signal_confidence=signal.confidence,
                    strategy=signal.strategy_name,
                    reason=signal.reason,
                    pnl=pnl, pnl_pct=pnl_pct,
                ))
                shares = 0
                buy_price = 0
            
            # 记录权益
            curr_price = closes[i + 1]
            total = cash + shares * curr_price
            equity.append({
                "date": dates[i + 1],
                "cash": round(cash, 2),
                "shares": shares,
                "price": round(curr_price, 2),
                "equity": round(total, 2),
            })
        
        # 最终清算（如果还有持仓）
        if shares > 0:
            final_price = closes[-1]
            proceeds = final_price * shares
            fee = proceeds * self.fee_rate + proceeds * self.stamp_duty
            cash += (proceeds - fee)
            
            pnl = (final_price - buy_price) * shares
            pnl_pct = (final_price - buy_price) / buy_price * 100
            
            trades.append(BacktestTrade(
                date=dates[-1], symbol=symbol, side="SELL",
                price=final_price, shares=shares, value=proceeds, fee=fee,
                signal_confidence=50.0, strategy=strategy.name,
                reason="回测结束清算",
                pnl=pnl, pnl_pct=pnl_pct,
            ))
            shares = 0
        
        final_capital = cash
        total_return = (final_capital - self.initial_capital) / self.initial_capital * 100
        
        # 年化收益率
        trading_days = n - warmup
        years = trading_days / 252
        annual_return = (pow(final_capital / self.initial_capital, 1 / max(years, 0.1)) - 1) * 100
        
        # 日收益率序列
        equity_values = [e["equity"] for e in equity]
        daily_returns = []
        for i in range(1, len(equity_values)):
            if equity_values[i - 1] > 0:
                daily_returns.append(
                    (equity_values[i] - equity_values[i - 1]) / equity_values[i - 1]
                )
        
        # 夏普比率
        if len(daily_returns) > 1:
            mean_ret = np.mean(daily_returns)
            std_ret = np.std(daily_returns, ddof=1)
            sharpe = (mean_ret / std_ret * math.sqrt(252)) if std_ret > 0 else 0
        else:
            sharpe = 0
        
        # 最大回撤
        peak = equity_values[0]
        max_dd = 0.0
        for v in equity_values:
            if v > peak:
                peak = v
            dd = (peak - v) / peak if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        
        # 卡尔玛比率
        calmar = annual_return / (max_dd * 100) if max_dd > 0 else 0
        
        # 胜率
        sell_trades = [t for t in trades if t.side == "SELL"]
        wins = sum(1 for t in sell_trades if t.pnl > 0)
        losses = sum(1 for t in sell_trades if t.pnl < 0)
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        
        avg_win = np.mean([t.pnl for t in sell_trades if t.pnl > 0]) if wins > 0 else 0
        avg_loss = np.mean([t.pnl for t in sell_trades if t.pnl < 0]) if losses > 0 else 0
        pf = abs(avg_win * wins / max(avg_loss * losses, 0.01)) if losses > 0 else 999
        
        return BacktestResult(
            strategy_name=strategy.name,
            symbol=symbol,
            start_date=dates[0] if dates else "",
            end_date=dates[-1] if dates else "",
            initial_capital=self.initial_capital,
            final_capital=round(final_capital, 2),
            total_return=round(total_return, 2),
            annual_return=round(annual_return, 2),
            sharpe_ratio=round(sharpe, 2),
            max_drawdown=round(max_dd * 100, 2),
            max_drawdown_pct=round(max_dd * 100, 2),
            calmar_ratio=round(calmar, 2),
            win_rate=round(win_rate, 1),
            total_trades=total_trades,
            wins=wins,
            losses=losses,
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            profit_factor=round(pf, 2),
            equity_curve=equity,
            trades=trades,
        )
    
    def grid_search(self, strategy_class, symbol: str, closes: np.ndarray,
                    param_grid: Dict[str, List], dates=None, highs=None, lows=None
                    ) -> List[BacktestResult]:
        """参数网格搜索"""
        results = []
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        
        from itertools import product
        for combo in product(*values):
            params = dict(zip(keys, combo))
            strategy = strategy_class(**params)
            result = self.run(strategy, symbol, closes, dates, highs, lows)
            result.params = params
            results.append(result)
        
        # 按夏普比率排序
        results.sort(key=lambda r: r.sharpe_ratio, reverse=True)
        return results
    
    def export_trades_csv(self, result: BacktestResult, path: str):
        """导出交易明细为 CSV"""
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Date", "Symbol", "Side", "Price", "Shares", "Value", "Fee",
                "Confidence", "Strategy", "Reason", "PnL", "PnLPct"
            ])
            for t in result.trades:
                writer.writerow([
                    t.date, t.symbol, t.side, t.price, t.shares, round(t.value, 2),
                    round(t.fee, 2), t.signal_confidence, t.strategy,
                    t.reason, round(t.pnl, 2), round(t.pnl_pct, 2),
                ])
        
        return len(result.trades)


# ═══════════════════════════════════════
# 回测报告生成器
# ═══════════════════════════════════════

def generate_backtest_report(result: BacktestResult) -> str:
    """生成回测报告"""
    pnl_color = "green" if result.total_return >= 0 else "red"
    sharpe_color = "green" if result.sharpe_ratio >= 1.0 else "yellow" if result.sharpe_ratio >= 0.5 else "red"
    win_color = "green" if result.win_rate >= 50 else "red"
    
    lines = []
    lines.append(f"## 📊 回测报告: {result.strategy_name} — {result.symbol}")
    lines.append(f"")
    lines.append(f"**期间**: {result.start_date} → {result.end_date} | **初始**: ¥{result.initial_capital:,.0f}")
    lines.append(f"")
    
    # 核心指标
    lines.append(f"| 指标 | 数值 | 评价 |")
    lines.append(f"|------|------|------|")
    lines.append(f"| 最终净值 | ¥{result.final_capital:,.0f} | {'📈' if result.total_return > 0 else '📉'} |")
    lines.append(f"| 总收益率 | {result.total_return:+.1f}% | — |")
    lines.append(f"| 年化收益 | {result.annual_return:+.1f}% | — |")
    lines.append(f"| 夏普比率 | {result.sharpe_ratio:.2f} | {'✅ 优秀' if result.sharpe_ratio >= 1 else '⚠️ 一般' if result.sharpe_ratio >= 0.5 else '❌ 较差'} |")
    lines.append(f"| 最大回撤 | -{result.max_drawdown:.1f}% | — |")
    lines.append(f"| 卡尔玛 | {result.calmar_ratio:.2f} | — |")
    lines.append(f"| 胜率 | {result.win_rate:.1f}% | {'✅' if result.win_rate >= 50 else '⚠️'} |")
    lines.append(f"| 盈亏比 | {result.profit_factor:.2f} | {'✅' if result.profit_factor >= 1.5 else '⚠️'} |")
    lines.append(f"| 总交易 | {result.total_trades} 笔 (赢{result.wins}/输{result.losses}) | — |")
    lines.append(f"| 平均盈利 | ¥{result.avg_win:+,.0f} | — |")
    lines.append(f"| 平均亏损 | ¥{result.avg_loss:+,.0f} | — |")
    
    # 参数
    if result.params:
        lines.append(f"")
        lines.append(f"**策略参数**: {json.dumps(result.params, ensure_ascii=False)}")
    
    return "\n".join(lines)


# ═══════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    p = argparse.ArgumentParser(description="小红回测引擎")
    p.add_argument("--strategy", default="MA-CROSS", help="策略ID")
    p.add_argument("--symbol", default="000001", help="股票代码")
    p.add_argument("--days", type=int, default=252, help="回测天数")
    p.add_argument("--capital", type=float, default=100000, help="初始资金")
    p.add_argument("--grid", action="store_true", help="网格搜索")
    p.add_argument("--export", type=str, help="导出CSV路径")
    args = p.parse_args()
    
    # 获取历史数据
    import subprocess
    print(f"🔄 获取 {args.symbol} 历史数据...")
    try:
        result = subprocess.run(
            [sys.executable, "-c", f"""
import sys, json
sys.path.insert(0, '.')
from data_pipeline import get_stock_realtime
# 通过 akshare 获取日线
import akshare as ak
df = ak.stock_zh_a_hist(symbol='{args.symbol}', period='daily', 
                         start_date='20240101', end_date='20260530', adjust='qfq')
closes = df['收盘'].values[-{args.days}:]
print(json.dumps({{'closes': closes.tolist(), 'dates': df['日期'].values[-{args.days}:].tolist()}}))
            """],
            capture_output=True, text=True, timeout=30,
            cwd=str(SCRIPT_DIR),
        )
        data = json.loads(result.stdout)
        closes = np.array(data["closes"])
        dates = data["dates"]
        print(f"  ✅ 获取 {len(closes)} 根 K线: {dates[0]} → {dates[-1]}")
    except Exception as e:
        print(f"⚠️ 真实数据获取失败 ({e})，使用随机模拟数据")
        np.random.seed(42)
        n = args.days
        closes = 100 * np.cumprod(1 + np.random.randn(n) * 0.02)
        dates = [f"2025-{i//30+1:02d}-{i%30+1:02d}" for i in range(n)]
    
    print(f"🧪 运行策略: {args.strategy}")
    strategy = get_strategy(args.strategy)
    engine = BacktestEngine(initial_capital=args.capital)
    
    if args.grid:
        # 网格搜索
        print("🔍 网格搜索中...")
        param_grid = {
            "MA-CROSS": {"fast_period": [5, 9, 13], "slow_period": [20, 26, 34]},
            "RSI": {"period": [7, 14, 21], "oversold": [25, 30, 35]},
            "MACD": {"fast": [8, 12, 16], "slow": [21, 26, 34]},
            "BOLLINGER": {"period": [14, 20, 26], "std_dev": [1.5, 2.0, 2.5]},
        }
        
        grid = param_grid.get(args.strategy, {"fast_period": [9], "slow_period": [21]})
        cls = type(strategy)
        results = engine.grid_search(cls, args.symbol, closes, grid, dates)
        
        print(f"\n🏆 网格搜索结果 (Top 5 by Sharpe):")
        for i, r in enumerate(results[:5]):
            print(f"  {i+1}. {r.strategy_name} {r.params} → "
                  f"Return={r.total_return:+.1f}% Sharpe={r.sharpe_ratio:.2f} "
                  f"WinRate={r.win_rate:.1f}% MaxDD={r.max_drawdown:.1f}%")
        
        best = results[0]
    else:
        result = engine.run(strategy, args.symbol, closes, dates)
        best = result
    
    print()
    print(generate_backtest_report(best))
    
    if args.export:
        n = engine.export_trades_csv(best, args.export)
        print(f"📤 导出 {n} 笔交易 → {args.export}")
