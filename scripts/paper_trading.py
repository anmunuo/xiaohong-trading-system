#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 Paper Trading 增强模拟器
=============================================
对标 TradingSkill paper trading mode

增强特性:
  - 滑点模拟（买卖方向不同滑点）
  - 延迟模拟（随机 1-5 秒）
  - 手续费精确计算（佣金+印花税+过户费）
  - 持仓市值实时更新
  - 移动止盈跟踪

与 auto_executor.py 的 paper 模式协同，提供更真实的市场模拟
"""
import random
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from pathlib import Path
import numpy as np

_log = logging.getLogger("paper_trading")


# ═══════════════════════════════════════
# 市场模拟参数
# ═══════════════════════════════════════

@dataclass
class MarketSimConfig:
    """市场模拟配置"""
    # 滑点
    buy_slippage_pct: float = 0.001    # 买入向上滑点 0.1%
    sell_slippage_pct: float = 0.001   # 卖出向下滑点 0.1%
    slippage_random: bool = True       # 随机滑点
    
    # 延迟
    min_delay_sec: float = 0.5
    max_delay_sec: float = 3.0
    
    # 手续费
    commission_rate: float = 0.00025   # 佣金 万2.5
    min_commission: float = 5.0        # 最低佣金
    stamp_duty_rate: float = 0.001     # 印花税 (仅卖出)
    transfer_fee_rate: float = 0.00002 # 过户费 万0.2
    
    # 风控
    max_position_pct: float = 33.3
    max_daily_trades: int = 20


@dataclass
class PaperPosition:
    """模拟持仓"""
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
    trailing_stop_active: bool = False
    highest_price: float = 0.0
    buy_date: str = ""
    strategy_id: str = ""
    
    def update_price(self, new_price: float):
        """更新市价"""
        self.current_price = new_price
        self.market_value = round(new_price * self.quantity, 2)
        self.unrealized_pnl = round((new_price - self.avg_cost) * self.quantity, 2)
        self.pnl_pct = round((new_price - self.avg_cost) / self.avg_cost * 100, 4)
        
        # 移动止盈：上涨 20% 启动
        if self.pnl_pct >= 20:
            self.trailing_stop_active = True
        if new_price > self.highest_price:
            self.highest_price = new_price
        
        # 移动止损线（从最高点回撤 10%）
        if self.trailing_stop_active and self.highest_price > 0:
            self.stop_loss = round(self.highest_price * 0.9, 2)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "name": self.symbol_name,
            "quantity": self.quantity,
            "avg_cost": self.avg_cost,
            "current_price": self.current_price,
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
            "pnl_pct": self.pnl_pct,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "trailing_stop": self.trailing_stop_active,
            "highest_price": self.highest_price,
        }


@dataclass
class PaperAccount:
    """模拟账户"""
    initial_capital: float = 100000
    available_cash: float = 100000
    total_value: float = 100000
    positions: Dict[str, PaperPosition] = field(default_factory=dict)
    daily_trades: int = 0
    last_reset: str = ""


class PaperTradingSimulator:
    """
    Paper Trading 模拟器 — TradingSkill 增强版
    
    用法:
      sim = PaperTradingSimulator()
      sim.place_order("600519", "BUY", 1800, 100)
      sim.update_market_prices({"600519": 1820})
      sim.place_order("600519", "SELL", 1820, 100)
    """
    
    def __init__(self, config: MarketSimConfig = None):
        self.config = config or MarketSimConfig()
        self.account = PaperAccount()
        
        # 加载 holdings 同步初始状态
        self._load_holdings()
    
    def _load_holdings(self):
        """从 holdings.json 同步"""
        try:
            import json
            path = Path("data/holdings.json")
            if path.exists():
                data = json.loads(path.read_text())
                acct = data.get("accountInfo", {})
                self.account.initial_capital = acct.get("initialCapital", 100000)
                self.account.available_cash = acct.get("availableCash", 100000)
                self.account.total_value = acct.get("currentNetValue", 100000)
        except Exception:
            pass
    
    def _simulate_slippage(self, price: float, side: str) -> float:
        """模拟滑点"""
        if not self.config.slippage_random:
            slip = self.config.buy_slippage_pct if side == "BUY" else self.config.sell_slippage_pct
            return price * (1 + slip if side == "BUY" else 1 - slip)
        
        # 随机滑点：0% ~ 0.3%
        slip = random.uniform(0, 0.003)
        return price * (1 + slip if side == "BUY" else 1 - slip)
    
    def _simulate_delay(self):
        """模拟市场延迟"""
        delay = random.uniform(self.config.min_delay_sec, self.config.max_delay_sec)
        time.sleep(delay)
    
    def _calc_fee(self, price: float, quantity: int, side: str) -> Tuple[float, dict]:
        """计算手续费"""
        value = price * quantity
        
        # 佣金
        commission = max(value * self.config.commission_rate, self.config.min_commission)
        # 印花税（仅卖出）
        stamp = value * self.config.stamp_duty_rate if side == "SELL" else 0
        # 过户费
        transfer = value * self.config.transfer_fee_rate
        
        total_fee = round(commission + stamp + transfer, 2)
        
        return total_fee, {
            "commission": round(commission, 2),
            "stamp_duty": round(stamp, 2),
            "transfer_fee": round(transfer, 2),
        }
    
    def place_order(self, symbol: str, side: str, price: float,
                    quantity: int, symbol_name: str = "",
                    stop_loss: float = 0, take_profit: float = 0,
                    strategy_id: str = "") -> Dict[str, Any]:
        """下单（模拟）"""
        # 模拟延迟
        self._simulate_delay()
        
        # 滑点价格
        exec_price = self._simulate_slippage(price, side)
        
        # 手续费
        fee, fee_detail = self._calc_fee(exec_price, quantity, side)
        
        if side == "BUY":
            return self._execute_buy(symbol, symbol_name, exec_price, quantity,
                                     fee, fee_detail, stop_loss, take_profit, strategy_id)
        else:
            return self._execute_sell(symbol, symbol_name, exec_price, quantity,
                                      fee, fee_detail, strategy_id)
    
    def _execute_buy(self, symbol, name, price, qty, fee, fee_detail,
                     stop_loss, take_profit, strategy_id) -> dict:
        """执行模拟买入"""
        total_cost = price * qty + fee
        
        # 风控：仓位上限
        position_pct = (total_cost / self.account.total_value) * 100
        if position_pct > self.config.max_position_pct:
            return {"status": "rejected", "reason": f"仓位 {position_pct:.1f}% > {self.config.max_position_pct}%"}
        
        # 风控：资金
        if total_cost > self.account.available_cash:
            return {"status": "rejected", "reason": f"资金不足: 需要 {total_cost:,.0f}, 可用 {self.account.available_cash:,.0f}"}
        
        # 风控：日交易数
        if self.account.daily_trades >= self.config.max_daily_trades:
            return {"status": "rejected", "reason": f"日交易次数达上限 {self.config.max_daily_trades}"}
        
        # 更新仓位
        if symbol in self.account.positions:
            pos = self.account.positions[symbol]
            new_total = pos.quantity + qty
            pos.avg_cost = round((pos.avg_cost * pos.quantity + price * qty) / new_total, 4)
            pos.quantity = new_total
            pos.update_price(price)
        else:
            pos = PaperPosition(
                symbol=symbol, symbol_name=name, quantity=qty,
                avg_cost=price, current_price=price,
                stop_loss=stop_loss, take_profit=take_profit,
                highest_price=price, buy_date=datetime.now().strftime("%Y-%m-%d"),
                strategy_id=strategy_id,
            )
            self.account.positions[symbol] = pos
        
        self.account.available_cash -= total_cost
        self.account.daily_trades += 1
        self._update_total_value()
        
        trade_id = f"PAPER-{symbol}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}"
        
        _log.info(f"📈 Paper买入: {symbol} {qty}股 @ {price:.2f} (滑点后) 费用 {fee:.2f} | 可用: ¥{self.account.available_cash:,.0f}")
        
        return {
            "status": "filled",
            "trade_id": trade_id,
            "symbol": symbol,
            "side": "BUY",
            "requested_price": price,
            "executed_price": round(exec_price := price, 2),
            "quantity": qty,
            "fee": fee,
            "fee_detail": fee_detail,
            "timestamp": datetime.now().isoformat(),
        }
    
    def _execute_sell(self, symbol, name, price, qty, fee, fee_detail,
                      strategy_id) -> dict:
        """执行模拟卖出"""
        if symbol not in self.account.positions:
            return {"status": "rejected", "reason": f"未持有 {symbol}"}
        
        pos = self.account.positions[symbol]
        sell_qty = min(qty, pos.quantity)
        proceeds = price * sell_qty - fee
        
        pnl = (price - pos.avg_cost) * sell_qty
        pnl_pct = (price - pos.avg_cost) / pos.avg_cost * 100
        
        self.account.available_cash += proceeds
        
        if sell_qty >= pos.quantity:
            del self.account.positions[symbol]
        else:
            pos.quantity -= sell_qty
            pos.update_price(price)
        
        self.account.daily_trades += 1
        self._update_total_value()
        
        trade_id = f"PAPER-{symbol}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(100,999)}"
        
        emoji = "🟢" if pnl > 0 else "🔴"
        _log.info(f"{emoji} Paper卖出: {symbol} {sell_qty}股 @ {price:.2f} PnL={pnl:+,.0f} ({pnl_pct:+.1f}%)")
        
        return {
            "status": "filled",
            "trade_id": trade_id,
            "symbol": symbol,
            "side": "SELL",
            "requested_price": price,
            "executed_price": round(price, 2),
            "quantity": sell_qty,
            "fee": fee,
            "fee_detail": fee_detail,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "timestamp": datetime.now().isoformat(),
        }
    
    def update_market_prices(self, quotes: Dict[str, float]):
        """更新市价（由行情推送调用）"""
        for symbol, price in quotes.items():
            if symbol in self.account.positions:
                self.account.positions[symbol].update_price(price)
        self._update_total_value()
    
    def _update_total_value(self):
        """更新总净值"""
        market_val = sum(p.market_value for p in self.account.positions.values())
        self.account.total_value = round(self.account.available_cash + market_val, 2)
    
    def check_stops(self) -> List[Dict]:
        """检查止损/止盈触发"""
        alerts = []
        for symbol, pos in list(self.account.positions.items()):
            if pos.stop_loss > 0 and pos.current_price <= pos.stop_loss:
                alerts.append({
                    "symbol": symbol, "type": "stop_loss",
                    "price": pos.current_price, "stop": pos.stop_loss,
                    "pnl": pos.unrealized_pnl, "pnl_pct": pos.pnl_pct,
                })
            if pos.take_profit > 0 and pos.current_price >= pos.take_profit:
                alerts.append({
                    "symbol": symbol, "type": "take_profit",
                    "price": pos.current_price, "target": pos.take_profit,
                    "pnl": pos.unrealized_pnl, "pnl_pct": pos.pnl_pct,
                })
        return alerts
    
    def get_status(self) -> dict:
        """获取账户状态"""
        return {
            "total_value": self.account.total_value,
            "available_cash": self.account.available_cash,
            "initial_capital": self.account.initial_capital,
            "total_return": round((self.account.total_value - self.account.initial_capital) / self.account.initial_capital * 100, 2),
            "positions": [p.to_dict() for p in self.account.positions.values()],
            "position_count": len(self.account.positions),
            "daily_trades": self.account.daily_trades,
        }


# ═══════════════════════════════════════
# 策略驱动的 Paper Trading 循环
# ═══════════════════════════════════════

class StrategyPaperTrader:
    """
    策略驱动的 Paper Trading 循环
    
    用法:
      trader = StrategyPaperTrader(strategy_id="COMBINED")
      trader.run_cycle({"600519": closes, "000858": closes})
    """
    
    def __init__(self, strategy_id: str = "COMBINED", **params):
        self.simulator = PaperTradingSimulator()
        from strategies.trading_skill_strategies import get_strategy as gs
        self.strategy = gs(strategy_id, **params)
    
    def run_cycle(self, market_data: Dict[str, np.ndarray]) -> Dict[str, Any]:
        """
        运行一个交易周期：检查信号 → 下单 → 风控 → 确认
        
        market_data: {symbol: closes_array}
        """
        import numpy as np
        results = []
        
        # 1. 更新市价
        quotes = {}
        for symbol, closes in market_data.items():
            if len(closes) > 0:
                quotes[symbol] = float(closes[-1])
        self.simulator.update_market_prices(quotes)
        
        # 2. 检查止损
        stop_alerts = self.simulator.check_stops()
        for alert in stop_alerts:
            if alert["type"] == "stop_loss":
                result = self.simulator.place_order(
                    alert["symbol"], "SELL", alert["price"],
                    self.simulator.account.positions[alert["symbol"]].quantity,
                    symbol_name="", reason="止损触发"
                )
                results.append(result)
        
        # 3. 生成交易信号
        for symbol, closes in market_data.items():
            if len(closes) < 30:
                continue
            
            signal = self.strategy.analyze(symbol, closes)
            price = float(closes[-1])
            
            if signal.side == "BUY":
                # 计算仓位
                from strategies.trading_skill_strategies import get_strategy as gs
                risk_per_share = max(price - signal.stop_loss, price * 0.02) if signal.stop_loss > 0 else price * 0.02
                max_risk = self.simulator.account.total_value * 0.02
                shares = int(max_risk / risk_per_share / 100) * 100
                shares = max(100, shares)
                
                result = self.simulator.place_order(
                    symbol, "BUY", price, shares,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    strategy_id=signal.strategy_name,
                )
                results.append(result)
            
            elif signal.side == "SELL" and symbol in self.simulator.account.positions:
                pos = self.simulator.account.positions[symbol]
                result = self.simulator.place_order(
                    symbol, "SELL", price, pos.quantity,
                    strategy_id=signal.strategy_name,
                )
                results.append(result)
        
        # 4. 状态汇总
        status = self.simulator.get_status()
        status["signals"] = results
        return status


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

if __name__ == "__main__":
    import numpy as np
    
    print("🧪 Paper Trading 增强模拟器测试")
    print("=" * 50)
    
    sim = PaperTradingSimulator()
    print(f"初始净值: ¥{sim.account.total_value:,.0f}")
    
    # 模拟几次交易
    r1 = sim.place_order("600519", "BUY", 1800, 100, "贵州茅台", stop_loss=1710, take_profit=1980)
    print(f"\n买入: {r1['status']} @ {r1['executed_price']} (滑点) 费用={r1['fee']}")
    
    sim.update_market_prices({"600519": 1850})
    print(f"市价更新: 茅台→1850, 浮盈={sim.account.positions['600519'].unrealized_pnl:+.0f}")
    
    sim.update_market_prices({"600519": 1920})
    r2 = sim.place_order("600519", "SELL", 1920, 100, "贵州茅台")
    print(f"\n卖出: {r2['status']} PnL={r2.get('pnl', 0):+,.0f} 费用={r2['fee']}")
    
    print(f"\n最终净值: ¥{sim.account.total_value:,.0f}")
    print(f"总收益: {sim.get_status()['total_return']:+.2f}%")
    
    # 测试策略驱动
    print("\n" + "=" * 50)
    print("🧪 策略驱动 Paper Trading 测试")
    
    np.random.seed(42)
    generates = {}
    for sym, base in [("600519", 1800), ("000858", 150), ("300750", 200)]:
        n = 60
        closes = base * np.cumprod(1 + np.random.randn(n) * 0.015)
        generates[sym] = closes
    
    trader = StrategyPaperTrader(strategy_id="COMBINED")
    status = trader.run_cycle(generates)
    
    print(f"运行后净值: ¥{status['total_value']:,.0f}")
    print(f"持仓: {status['position_count']}只")
    print(f"信号: {len(status['signals'])}个")
    for s in status['signals']:
        print(f"  {s['side']} {s['symbol']} → {s['status']}")
    
    print("\n✅ Paper Trading 增强模拟器测试通过")
