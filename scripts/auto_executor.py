#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 自动交易执行器
=====================================
TradingSkill 风格增强版：信号→风控→执行→日志 全链路

参照 gwrxuk/TradingSkill → src/trading/executor.ts

模式:
  --paper    模拟交易（默认，零风险测试）
  --live     实盘模式（需券商 API）
  --cron     Cron 调度模式（每30分钟检查信号）

架构:
  信号源 (策略引擎) → 风控检查 → 仓位计算 → 执行 → 日志
       ↑                                  ↓
       └──── 持仓反馈 ─────────────────────┘
"""
import sys
import os
import json
import time
import signal as unix_signal
import subprocess
import logging
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from collections import defaultdict
from enum import Enum

# 添加项目路径
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from transaction_logger import TransactionLogger, TradeRecord
from report_formatter import Report

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
_log = logging.getLogger("executor")


# ═══════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════

class SignalStrength(Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


class ExecStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Signal:
    """交易信号"""
    symbol: str
    symbol_name: str = ""
    side: str = "BUY"               # BUY/SELL/HOLD
    strength: SignalStrength = SignalStrength.MODERATE
    confidence: float = 60.0        # 0-100
    price: float = 0.0
    strategy_id: str = ""
    indicators: Dict[str, Any] = field(default_factory=dict)
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reason: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class Position:
    """持仓"""
    symbol: str
    symbol_name: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0
    market_value: float = 0.0
    unrealized_pnl: float = 0.0
    pnl_pct: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    strategy_id: str = ""

    def __post_init__(self):
        if self.current_price > 0:
            self.market_value = round(self.current_price * self.quantity, 2)
            self.unrealized_pnl = round(
                (self.current_price - self.avg_cost) * self.quantity, 2)
            self.pnl_pct = round(
                (self.current_price - self.avg_cost) / self.avg_cost * 100, 4)


@dataclass
class Account:
    """账户"""
    initial_capital: float = 100000
    available_cash: float = 100000
    total_value: float = 100000
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    positions: Dict[str, Position] = field(default_factory=dict)
    max_position_pct: float = 33.3     # 单股最大仓位
    max_positions: int = 9              # 最大持仓数
    kelly_fraction: float = 0.125       # 凯利分数
    risk_per_trade_pct: float = 2.0     # 单笔最大亏损%


# ═══════════════════════════════════════
# 风控引擎
# ═══════════════════════════════════════

class RiskManager:
    """风控引擎 — 对标 TradingSkill Risk Management"""

    def __init__(self, account: Account):
        self.account = account

    def check_buy(self, signal: Signal) -> tuple[bool, str]:
        """检查买入信号是否可以执行"""
        # 1. 持仓数量上限
        if len(self.account.positions) >= self.account.max_positions:
            return False, f"持仓数已达上限 {self.account.max_positions}"

        # 2. 单股仓位上限
        target_value = signal.price * self._calc_shares(signal)
        position_pct = (target_value / self.account.total_value) * 100
        if position_pct > self.account.max_position_pct:
            return False, f"仓位 {position_pct:.1f}% 超过上限 {self.account.max_position_pct}%"

        # 3. 可用资金
        if target_value > self.account.available_cash * 0.95:
            return False, f"资金不足: 需要 {target_value:,.0f} 可用 {self.account.available_cash:,.0f}"

        # 4. 单笔最大亏损 (R 值检查)
        if signal.stop_loss > 0 and signal.price > 0:
            risk_per_share = abs(signal.price - signal.stop_loss)
            max_risk = self.account.total_value * (self.account.risk_per_trade_pct / 100)
            shares = self._calc_shares(signal)
            total_risk = risk_per_share * shares
            if total_risk > max_risk:
                return False, f"单笔风险 {total_risk:,.0f} > 上限 {max_risk:,.0f}"

        return True, "风控通过"

    def check_sell(self, position: Position, signal: Signal) -> tuple[bool, str]:
        """检查卖出信号"""
        if position.symbol not in self.account.positions:
            return False, "未持有该标的"
        if position.quantity <= 0:
            return False, "持仓数量为0"
        return True, "风控通过"

    def _calc_shares(self, signal: Signal) -> int:
        """R 值仓位计算：总净值 × 凯利分数 ÷ (价格 × 100) × 100"""
        r_value = self.account.total_value * self.account.kelly_fraction
        shares = int(r_value / (signal.price * 100)) * 100
        return max(100, shares)  # 最少1手


# ═══════════════════════════════════════
# 执行引擎
# ═══════════════════════════════════════

class AutoExecutor:
    """
    自动交易执行器 — TradingSkill 风格
    
    参照: gwrxuk/TradingSkill → src/trading/executor.ts
    """

    def __init__(self, mode: str = "paper",
                 csv_path: str = "workspace/transactions.csv",
                 holdings_path: str = "data/holdings.json"):
        self.mode = mode                    # paper / live
        self.is_paper = mode != "live"
        self.logger = TransactionLogger(csv_path=csv_path)
        self.holdings_path = Path(holdings_path)
        
        # 加载账户
        self.account = self._load_account()
        self.risk_mgr = RiskManager(self.account)
        
        # 运行状态
        self.running = False
        self.last_check: Optional[datetime] = None
        self.signals_processed = 0
        self.trades_executed = 0
        
        # 活跃订单
        self.pending_orders: Dict[str, Signal] = {}

        _log.info(f"🚀 交易执行器启动 | 模式: {mode} | "
                  f"净值: ¥{self.account.total_value:,.0f} | "
                  f"持仓: {len(self.account.positions)}只")

    def _load_account(self) -> Account:
        """从 holdings.json 加载账户"""
        if self.holdings_path.exists():
            try:
                data = json.loads(self.holdings_path.read_text())
                acct = data.get("accountInfo", {})
                rules = data.get("rules", {}).get("riskManagement", {})
                
                account = Account(
                    initial_capital=acct.get("initialCapital", 100000),
                    available_cash=acct.get("availableCash", 100000),
                    total_value=acct.get("currentNetValue", 100000),
                    max_position_pct=rules.get("maxPositionPerStockPct", 33.3) * 100
                    if isinstance(rules.get("maxPositionPerStockPct"), float) else 33.3,
                    max_positions=data.get("rules", {}).get("maxHoldingsCount", 9),
                )
                
                # 加载持仓
                for h in data.get("holdings", []):
                    pos = Position(
                        symbol=h.get("code", ""),
                        symbol_name=h.get("name", ""),
                        quantity=int(h.get("quantity", 0)),
                        avg_cost=float(h.get("avgCost", 0)),
                        current_price=float(h.get("lastPrice", 0) or h.get("avgCost", 0)),
                        stop_loss=float(h.get("stopLoss", 0)),
                        take_profit=float(h.get("takeProfit", 0)),
                    )
                    if pos.quantity > 0:
                        account.positions[pos.symbol] = pos
                
                return account
            except Exception as e:
                _log.warning(f"加载 holdings.json 失败: {e}")
        
        return Account()

    def _save_account(self):
        """保存账户状态到 holdings.json"""
        holdings = []
        for pos in self.account.positions.values():
            holdings.append({
                "code": pos.symbol,
                "name": pos.symbol_name,
                "quantity": pos.quantity,
                "avgCost": pos.avg_cost,
                "lastPrice": pos.current_price,
                "marketValue": pos.market_value,
                "unrealizedPnL": pos.unrealized_pnl,
                "pnlPct": pos.pnl_pct,
                "stopLoss": pos.stop_loss,
                "takeProfit": pos.take_profit,
                "lastUpdate": datetime.now().isoformat(),
            })
        
        data = {
            "updateTime": datetime.now().isoformat(),
            "accountInfo": {
                "initialCapital": self.account.initial_capital,
                "currentNetValue": self.account.total_value,
                "availableCash": self.account.available_cash,
            },
            "holdings": holdings,
            "trading": {
                "mode": self.mode,
                "lastCheck": self.last_check.isoformat() if self.last_check else None,
                "signalsProcessed": self.signals_processed,
                "tradesExecuted": self.trades_executed,
            }
        }
        
        self.holdings_path.parent.mkdir(parents=True, exist_ok=True)
        self.holdings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # ── 信号处理 ──

    def process_signal(self, signal: Signal) -> str:
        """处理单个交易信号 → 返回 trade_id 或错误信息"""
        self.signals_processed += 1

        if signal.side == "BUY":
            return self._execute_buy(signal)
        elif signal.side == "SELL":
            return self._execute_sell(signal)
        else:
            return f"HOLD: {signal.reason}"

    def _execute_buy(self, signal: Signal) -> str:
        """执行买入"""
        # 风控检查
        ok, reason = self.risk_mgr.check_buy(signal)
        if not ok:
            _log.warning(f"❌ 买入拒绝: {signal.symbol} — {reason}")
            return f"REJECTED: {reason}"

        # 计算仓位
        shares = self.risk_mgr._calc_shares(signal)
        total_cost = signal.price * shares
        fee = total_cost * 0.0003  # 万三佣金

        if self.is_paper:
            # Paper Trading: 直接「成交」
            self.account.available_cash -= (total_cost + fee)
            
            if signal.symbol in self.account.positions:
                # 加仓：更新均价
                pos = self.account.positions[signal.symbol]
                new_total = pos.quantity + shares
                pos.avg_cost = round(
                    (pos.avg_cost * pos.quantity + signal.price * shares) / new_total, 4
                )
                pos.quantity = new_total
                pos.current_price = signal.price
            else:
                self.account.positions[signal.symbol] = Position(
                    symbol=signal.symbol,
                    symbol_name=signal.symbol_name,
                    quantity=shares,
                    avg_cost=signal.price,
                    current_price=signal.price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    strategy_id=signal.strategy_id,
                )

            self.account.total_value = self.account.available_cash + sum(
                p.market_value for p in self.account.positions.values()
            )

            trade_id = self.logger.log_buy(
                symbol=signal.symbol, name=signal.symbol_name,
                price=signal.price, quantity=shares,
                fee=fee, strategy_id=signal.strategy_id,
                signal_type=signal.side, signal_strength=signal.strength.value,
                signal_confidence=signal.confidence,
                stop_loss=signal.stop_loss, take_profit=signal.take_profit,
                is_paper=True, reason=signal.reason,
                portfolio_value=self.account.total_value,
            )
            
            self.trades_executed += 1
            self._save_account()
            
            _log.info(f"📈 买入成交: {signal.symbol} {shares}股 @ {signal.price} "
                      f"费用 {fee:.2f} | 可用: ¥{self.account.available_cash:,.0f}")
            return trade_id

        else:
            # 实盘：调用券商 API（占位）
            self.pending_orders[signal.symbol] = signal
            _log.info(f"📊 实盘下单: {signal.symbol} {shares}股 @ {signal.price} [待确认]")
            return f"PENDING: {signal.symbol}"

    def _execute_sell(self, signal: Signal) -> str:
        """执行卖出"""
        if signal.symbol not in self.account.positions:
            return f"REJECTED: 未持有 {signal.symbol}"

        pos = self.account.positions[signal.symbol]
        ok, reason = self.risk_mgr.check_sell(pos, signal)
        if not ok:
            return f"REJECTED: {reason}"

        shares = pos.quantity  # 全卖
        proceeds = signal.price * shares
        fee = proceeds * 0.0003 + proceeds * 0.001  # 佣金+印花税

        if self.is_paper:
            self.account.available_cash += (proceeds - fee)
            pnl = (signal.price - pos.avg_cost) * shares
            
            trade_id = self.logger.log_sell(
                symbol=signal.symbol, name=signal.symbol_name,
                price=signal.price, quantity=shares,
                buy_price=pos.avg_cost, fee=fee,
                strategy_id=signal.strategy_id,
                signal_type=signal.side, signal_strength=signal.strength.value,
                is_paper=True, reason=signal.reason,
                portfolio_value=self.account.total_value,
            )

            del self.account.positions[signal.symbol]
            self.account.total_value = self.account.available_cash + sum(
                p.market_value for p in self.account.positions.values()
            )
            self.account.total_pnl += pnl
            
            self.trades_executed += 1
            self._save_account()
            
            _log.info(f"📉 卖出成交: {signal.symbol} {shares}股 @ {signal.price} "
                      f"PnL: {pnl:+,.0f} | 净值: ¥{self.account.total_value:,.0f}")
            return trade_id
        else:
            self.pending_orders[signal.symbol] = signal
            _log.info(f"📊 实盘卖出: {signal.symbol} {shares}股 @ {signal.price} [待确认]")
            return f"PENDING: {signal.symbol}"

    # ── 策略桥接 ──

    def fetch_signals(self) -> List[Signal]:
        """从策略引擎获取交易信号"""
        try:
            result = subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "strategy_bridge.py"), "signal"],
                capture_output=True, text=True, timeout=30,
                cwd=str(SCRIPT_DIR),
            )
            data = json.loads(result.stdout)
            signals = []
            
            for rec in data.get("recommendations", []):
                sig = Signal(
                    symbol=rec.get("code", ""),
                    symbol_name=rec.get("name", ""),
                    side=rec.get("action", "HOLD").upper(),
                    strength=SignalStrength(
                        "strong" if rec.get("severity") == "critical"
                        else "moderate" if rec.get("severity") == "warning"
                        else "weak"
                    ),
                    reason=rec.get("reason", ""),
                )
                if sig.side in ("BUY", "SELL"):
                    signals.append(sig)
            
            return signals
        except Exception as e:
            _log.error(f"获取信号失败: {e}")
            return []

    # ── 主循环 ──

    def run_once(self) -> Dict[str, Any]:
        """执行一次交易检查"""
        self.last_check = datetime.now()
        signals = self.fetch_signals()
        results = []

        for sig in signals:
            tid = self.process_signal(sig)
            results.append({"symbol": sig.symbol, "side": sig.side, "result": tid})

        return {
            "timestamp": self.last_check.isoformat(),
            "mode": self.mode,
            "signals_found": len(signals),
            "results": results,
            "account": {
                "total_value": self.account.total_value,
                "available_cash": self.account.available_cash,
                "positions": len(self.account.positions),
                "total_pnl": self.account.total_pnl,
            }
        }

    def run_loop(self, interval: int = 60):
        """主循环 — 定时检查信号"""
        self.running = True
        _log.info(f"🔄 启动主循环 | 间隔 {interval}秒 | 模式 {self.mode}")

        def _stop(sig, frame):
            _log.info("⏹ 收到停止信号，安全退出...")
            self.running = False

        unix_signal.signal(unix_signal.SIGINT, _stop)
        unix_signal.signal(unix_signal.SIGTERM, _stop)

        while self.running:
            try:
                result = self.run_once()
                active = result["signals_found"]
                trades = len([r for r in result["results"] if "REJECTED" not in str(r["result"])])

                if active > 0:
                    _log.info(f"📡 扫描: {active}信号 → {trades}笔交易 | "
                              f"净值 ¥{result['account']['total_value']:,.0f}")

            except Exception as e:
                _log.error(f"主循环错误: {e}")

            # 等待
            for _ in range(interval):
                if not self.running:
                    break
                time.sleep(1)

        self._save_account()
        _log.info(f"⏹ 执行器已停止 | 共处理 {self.signals_processed} 信号 "
                  f"{self.trades_executed} 笔交易")

    # ── 报告 ──

    def generate_status_report(self) -> str:
        """生成状态报告"""
        stats = self.logger.get_statistics()
        
        r = Report(title="自动交易执行器 · 状态报告", icon="🤖",
                   color="green" if stats["total_pnl"] >= 0 else "red")
        r.header_meta(
            模式=self.mode,
            净值=f"¥{self.account.total_value:,.0f}",
            持仓=f"{len(self.account.positions)}只",
            可用=f"¥{self.account.available_cash:,.0f}",
        )
        
        r.section("交易统计")
        r.table(
            ["指标", "数值"],
            [
                ["总交易数", str(stats["total_trades"])],
                ["胜率", f"{stats['win_rate']}%"],
                ["总盈亏", f"¥{stats['total_pnl']:+,.0f}"],
                ["平均盈利", f"¥{stats['avg_win']:+,.0f}"],
                ["平均亏损", f"¥{stats['avg_loss']:+,.0f}"],
                ["盈亏比", str(stats['profit_factor'])],
            ]
        )
        
        if self.account.positions:
            r.section("当前持仓")
            pos_data = []
            for p in self.account.positions.values():
                pos_data.append([
                    p.symbol, p.symbol_name,
                    str(p.quantity),
                    f"¥{p.avg_cost:.2f}",
                    f"¥{p.current_price:.2f}" if p.current_price else "—",
                    f"¥{p.unrealized_pnl:+,.0f}" if p.unrealized_pnl else "—",
                ])
            r.table(
                ["代码", "名称", "数量", "成本", "现价", "浮盈"],
                pos_data,
            )
        
        r.footer(f"数据: TransactionLogger + StrategyBridge · {datetime.now().isoformat()}")
        return r.markdown()


# ═══════════════════════════════════════
# CLI 入口
# ═══════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description="小红自动交易执行器")
    p.add_argument("--paper", action="store_true", default=True,
                   help="模拟交易模式（默认）")
    p.add_argument("--live", action="store_true",
                   help="实盘模式")
    p.add_argument("--cron", action="store_true",
                   help="Cron 模式：执行一次后退出")
    p.add_argument("--interval", type=int, default=300,
                   help="轮询间隔（秒，默认300）")
    p.add_argument("--status", action="store_true",
                   help="输出状态报告后退出")
    p.add_argument("--once", action="store_true",
                   help="执行一次信号扫描后退出")
    args = p.parse_args()

    mode = "live" if args.live else "paper"
    executor = AutoExecutor(mode=mode)

    if args.status:
        print(executor.generate_status_report())
        return

    if args.once or args.cron:
        result = executor.run_once()
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # 默认：主循环
    executor.run_loop(interval=args.interval)


if __name__ == "__main__":
    main()
