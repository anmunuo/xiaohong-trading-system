#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 TradingSkill 风格策略集
=============================================
对标 gwrxuk/TradingSkill → src/trading/strategies.ts

5 大策略:
  MA-CROSS   → 双均线交叉 (EMA fast/slow)
  RSI        → 超买超卖反转
  MACD       → MACD 信号线交叉
  BOLLINGER  → 布林带突破
  COMBINED   → 多指标共识投票（加权）

所有策略返回统一信号格式:
  {symbol, side, strength, confidence, indicators, stop_loss, take_profit}
"""
import numpy as np
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum


# ═══════════════════════════════════════
# 技术指标计算（对标 indicators.ts）
# ═══════════════════════════════════════

def sma(data: np.ndarray, period: int) -> np.ndarray:
    """简单移动平均"""
    result = np.full_like(data, np.nan, dtype=float)
    if len(data) >= period:
        result[period - 1:] = np.convolve(data, np.ones(period) / period, mode='valid')
    return result


def ema(data: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均"""
    result = np.full_like(data, np.nan, dtype=float)
    if len(data) < period:
        return result
    alpha = 2 / (period + 1)
    result[period - 1] = np.mean(data[:period])
    for i in range(period, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's RSI"""
    result = np.full_like(closes, np.nan, dtype=float)
    if len(closes) < period + 1:
        return result
    
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))
    
    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))
    
    return result


def macd(closes: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9
         ) -> Dict[str, np.ndarray]:
    """MACD 指标"""
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    dif = ema_fast - ema_slow
    
    # 只对非 NaN 的 dif 计算 DEA
    valid_dif = dif[~np.isnan(dif)]
    dea_raw = ema(valid_dif, signal)
    dea_on_valid = dea_raw[~np.isnan(dea_raw)]
    
    # 对齐到原始长度
    dea_full = np.full_like(closes, np.nan)
    # dif 的第一个有效位置 = max(fast, slow) - 1
    first_valid = max(fast, slow) - 1
    # dea 从 first_valid + signal - 1 开始有值
    dea_start = first_valid + signal - 1
    dea_len = len(dea_on_valid)
    end_idx = min(dea_start + dea_len, len(dea_full))
    dea_full[dea_start:end_idx] = dea_on_valid[:end_idx - dea_start]
    
    histogram = 2 * (dif - dea_full)
    
    return {"dif": dif, "dea": dea_full, "histogram": histogram}


def bollinger_bands(closes: np.ndarray, period: int = 20, std_dev: float = 2.0
                    ) -> Dict[str, np.ndarray]:
    """布林带"""
    middle = sma(closes, period)
    rolling_std = np.full_like(closes, np.nan)
    for i in range(period - 1, len(closes)):
        rolling_std[i] = np.std(closes[i - period + 1:i + 1], ddof=1)
    
    upper = middle + std_dev * rolling_std
    lower = middle - std_dev * rolling_std
    width = (upper - lower) / middle * 100  # 带宽百分比
    
    return {"upper": upper, "middle": middle, "lower": lower, "width": width}


def atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14
        ) -> np.ndarray:
    """平均真实波幅"""
    result = np.full_like(closes, np.nan, dtype=float)
    if len(closes) < period + 1:
        return result
    
    tr = np.maximum(
        highs[1:] - lows[1:],
        np.maximum(
            np.abs(highs[1:] - closes[:-1]),
            np.abs(lows[1:] - closes[:-1])
        )
    )
    result[period] = np.mean(tr[:period])
    for i in range(period + 1, len(closes)):
        result[i] = (result[i - 1] * (period - 1) + tr[i - 1]) / period
    
    return result


# ═══════════════════════════════════════
# 信号模型
# ═══════════════════════════════════════

class SignalStrength(Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"


@dataclass
class StrategySignal:
    """统一策略信号"""
    symbol: str
    side: str = "HOLD"            # BUY / SELL / HOLD
    strength: SignalStrength = SignalStrength.WEAK
    confidence: float = 50.0      # 0-100
    price: float = 0.0
    strategy_name: str = ""
    indicators: Dict[str, Any] = field(default_factory=dict)
    stop_loss: float = 0.0
    take_profit: float = 0.0
    reason: str = ""


# ═══════════════════════════════════════
# 策略 1: MA CROSS — 对标 TradingSkill
# ═══════════════════════════════════════

class MACrossoverStrategy:
    """
    双均线交叉策略
    
    买入: 快线上穿慢线（金叉）
    卖出: 快线下穿慢线（死叉）
    
    参数:
      fast_period: 快线周期 (default 9)
      slow_period: 慢线周期 (default 21)
    """
    
    def __init__(self, fast_period: int = 9, slow_period: int = 21):
        self.name = "MA-CROSS"
        self.fast_period = fast_period
        self.slow_period = slow_period
    
    def analyze(self, symbol: str, closes: np.ndarray, highs=None, lows=None,
                volumes=None, dates=None) -> StrategySignal:
        if len(closes) < self.slow_period + 1:
            return StrategySignal(symbol=symbol, strategy_name=self.name,
                                  reason="数据不足")
        
        fast_ema = ema(closes, self.fast_period)
        slow_ema = ema(closes, self.slow_period)
        
        # 最新值
        curr_fast = fast_ema[-1]
        curr_slow = slow_ema[-1]
        prev_fast = fast_ema[-2]
        prev_slow = slow_ema[-2]
        
        price = closes[-1]
        
        # 金叉：快线上穿慢线
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            # 计算置信度：基于交叉角度
            angle = (curr_fast - curr_slow) / curr_slow * 100
            confidence = min(90, 50 + angle * 20)
            strength = SignalStrength.STRONG if angle > 1.0 else SignalStrength.MODERATE
            
            # 止损：慢线下方 2%
            stop_loss = round(curr_slow * 0.98, 2)
            take_profit = round(price * 1.06, 2)
            
            return StrategySignal(
                symbol=symbol, side="BUY",
                strength=strength, confidence=round(confidence, 1),
                price=price, strategy_name=self.name,
                indicators={"fast_ema": round(curr_fast, 2), "slow_ema": round(curr_slow, 2)},
                stop_loss=stop_loss, take_profit=take_profit,
                reason=f"EMA{self.fast_period}({curr_fast:.2f}) 上穿 EMA{self.slow_period}({curr_slow:.2f})"
            )
        
        # 死叉：快线下穿慢线
        elif prev_fast >= prev_slow and curr_fast < curr_slow:
            angle = (curr_slow - curr_fast) / curr_slow * 100
            confidence = min(90, 50 + angle * 20)
            strength = SignalStrength.STRONG if angle > 1.0 else SignalStrength.MODERATE
            
            return StrategySignal(
                symbol=symbol, side="SELL",
                strength=strength, confidence=round(confidence, 1),
                price=price, strategy_name=self.name,
                indicators={"fast_ema": round(curr_fast, 2), "slow_ema": round(curr_slow, 2)},
                reason=f"EMA{self.fast_period}({curr_fast:.2f}) 下穿 EMA{self.slow_period}({curr_slow:.2f})"
            )
        
        else:
            # 趋势判断
            if curr_fast > curr_slow:
                return StrategySignal(symbol=symbol, side="HOLD",
                    strategy_name=self.name, price=price,
                    indicators={"fast_ema": round(curr_fast, 2), "slow_ema": round(curr_slow, 2)},
                    reason=f"多头排列，EMA{self.fast_period}>{self.slow_period}")
            else:
                return StrategySignal(symbol=symbol, side="HOLD",
                    strategy_name=self.name, price=price,
                    indicators={"fast_ema": round(curr_fast, 2), "slow_ema": round(curr_slow, 2)},
                    reason=f"空头排列，EMA{self.fast_period}<{self.slow_period}")


# ═══════════════════════════════════════
# 策略 2: RSI — 对标 TradingSkill
# ═══════════════════════════════════════

class RSIStrategy:
    """
    RSI 超买超卖策略
    
    买入: RSI 从超卖区反弹 (>30)
    卖出: RSI 从超买区回落 (<70)
    
    参数:
      period: RSI 周期 (default 14)
      oversold: 超卖阈值 (default 30)
      overbought: 超买阈值 (default 70)
    """
    
    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70):
        self.name = "RSI"
        self.period = period
        self.oversold = oversold
        self.overbought = overbought
    
    def analyze(self, symbol: str, closes: np.ndarray, highs=None, lows=None,
                volumes=None, dates=None) -> StrategySignal:
        if len(closes) < self.period + 2:
            return StrategySignal(symbol=symbol, strategy_name=self.name, reason="数据不足")
        
        rsi_vals = rsi(closes, self.period)
        curr_rsi = rsi_vals[-1]
        prev_rsi = rsi_vals[-2]
        price = closes[-1]
        
        # 超卖反弹 → 买入
        if prev_rsi <= self.oversold and curr_rsi > self.oversold:
            confidence = min(90, 50 + (curr_rsi - self.oversold) * 2)
            strength = SignalStrength.STRONG if prev_rsi < 25 else SignalStrength.MODERATE
            
            stop_loss = round(price * 0.95, 2)
            take_profit = round(price * 1.08, 2)
            
            return StrategySignal(
                symbol=symbol, side="BUY",
                strength=strength, confidence=round(confidence, 1),
                price=price, strategy_name=self.name,
                indicators={"rsi": round(curr_rsi, 1)},
                stop_loss=stop_loss, take_profit=take_profit,
                reason=f"RSI 超卖反弹 {prev_rsi:.0f}→{curr_rsi:.0f}"
            )
        
        # 超买回落 → 卖出
        elif prev_rsi >= self.overbought and curr_rsi < self.overbought:
            confidence = min(90, 50 + (self.overbought - curr_rsi) * 2)
            strength = SignalStrength.STRONG if prev_rsi > 80 else SignalStrength.MODERATE
            
            return StrategySignal(
                symbol=symbol, side="SELL",
                strength=strength, confidence=round(confidence, 1),
                price=price, strategy_name=self.name,
                indicators={"rsi": round(curr_rsi, 1)},
                reason=f"RSI 超买回落 {prev_rsi:.0f}→{curr_rsi:.0f}"
            )
        
        else:
            zone = "超卖区" if curr_rsi <= self.oversold else "超买区" if curr_rsi >= self.overbought else "中性区"
            return StrategySignal(symbol=symbol, side="HOLD",
                strategy_name=self.name, price=price,
                indicators={"rsi": round(curr_rsi, 1)},
                reason=f"RSI={curr_rsi:.0f} {zone}")


# ═══════════════════════════════════════
# 策略 3: MACD — 对标 TradingSkill
# ═══════════════════════════════════════

class MACDStrategy:
    """
    MACD 信号线交叉策略
    
    买入: DIF 上穿 DEA（金叉）且 DIF < 0（低位金叉更可靠）
    卖出: DIF 下穿 DEA（死叉）
    
    参数:
      fast: 快线 (default 12)
      slow: 慢线 (default 26)
      signal: 信号线 (default 9)
    """
    
    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9):
        self.name = "MACD"
        self.fast = fast
        self.slow = slow
        self.signal = signal
    
    def analyze(self, symbol: str, closes: np.ndarray, highs=None, lows=None,
                volumes=None, dates=None) -> StrategySignal:
        if len(closes) < self.slow + self.signal + 2:
            return StrategySignal(symbol=symbol, strategy_name=self.name, reason="数据不足")
        
        macd_data = macd(closes, self.fast, self.slow, self.signal)
        dif = macd_data["dif"]
        dea = macd_data["dea"]
        hist = macd_data["histogram"]
        
        # 过滤 NaN
        valid = ~np.isnan(dif) & ~np.isnan(dea)
        if valid.sum() < 2:
            return StrategySignal(symbol=symbol, strategy_name=self.name, reason="计算失败")
        
        curr_dif = dif[-1]
        curr_dea = dea[-1]
        curr_hist = hist[-1]
        prev_dif = dif[-2]
        prev_dea = dea[-2]
        price = closes[-1]
        
        # 金叉
        if prev_dif <= prev_dea and curr_dif > curr_dea:
            # 低位金叉加分
            is_low = curr_dif < 0
            confidence = min(90, 55 + (5 if is_low else 0) + abs(curr_hist) * 10)
            strength = SignalStrength.STRONG if is_low else SignalStrength.MODERATE
            
            stop_loss = round(price * 0.95, 2)
            take_profit = round(price * 1.08, 2)
            
            return StrategySignal(
                symbol=symbol, side="BUY",
                strength=strength, confidence=round(confidence, 1),
                price=price, strategy_name=self.name,
                indicators={"dif": round(curr_dif, 4), "dea": round(curr_dea, 4),
                           "histogram": round(curr_hist, 4)},
                stop_loss=stop_loss, take_profit=take_profit,
                reason=f"MACD {'低位' if is_low else ''}金叉 DIF={curr_dif:.4f} DEA={curr_dea:.4f}"
            )
        
        # 死叉
        elif prev_dif >= prev_dea and curr_dif < curr_dea:
            confidence = min(90, 50 + abs(curr_hist) * 10)
            
            return StrategySignal(
                symbol=symbol, side="SELL",
                strength=SignalStrength.MODERATE, confidence=round(confidence, 1),
                price=price, strategy_name=self.name,
                indicators={"dif": round(curr_dif, 4), "dea": round(curr_dea, 4),
                           "histogram": round(curr_hist, 4)},
                reason=f"MACD 死叉 DIF={curr_dif:.4f} DEA={curr_dea:.4f}"
            )
        
        else:
            trend = "多头" if curr_dif > curr_dea else "空头"
            return StrategySignal(symbol=symbol, side="HOLD",
                strategy_name=self.name, price=price,
                indicators={"dif": round(curr_dif, 4), "dea": round(curr_dea, 4)},
                reason=f"MACD {trend} DIF={curr_dif:.4f}")


# ═══════════════════════════════════════
# 策略 4: Bollinger Bands — 对标 TradingSkill
# ═══════════════════════════════════════

class BollingerStrategy:
    """
    布林带策略
    
    买入: 价格触及下轨反弹
    卖出: 价格触及上轨回落
    
    参数:
      period: 中轨周期 (default 20)
      std_dev: 标准差倍数 (default 2.0)
    """
    
    def __init__(self, period: int = 20, std_dev: float = 2.0):
        self.name = "BOLLINGER"
        self.period = period
        self.std_dev = std_dev
    
    def analyze(self, symbol: str, closes: np.ndarray, highs=None, lows=None,
                volumes=None, dates=None) -> StrategySignal:
        if len(closes) < self.period + 2:
            return StrategySignal(symbol=symbol, strategy_name=self.name, reason="数据不足")
        
        bb = bollinger_bands(closes, self.period, self.std_dev)
        upper = bb["upper"]
        middle = bb["middle"]
        lower = bb["lower"]
        width = bb["width"]
        
        curr_price = closes[-1]
        prev_price = closes[-2]
        curr_lower = lower[-1]
        curr_upper = upper[-1]
        curr_mid = middle[-1]
        
        # 触及下轨反弹 → 买入
        if prev_price <= lower[-2] and curr_price > curr_lower:
            confidence = min(90, 50 + abs((curr_mid - curr_price) / curr_mid) * 100)
            strength = SignalStrength.STRONG if curr_price < curr_mid * 0.95 else SignalStrength.MODERATE
            
            stop_loss = round(curr_lower * 0.98, 2)
            take_profit = round(curr_mid, 2)
            
            return StrategySignal(
                symbol=symbol, side="BUY",
                strength=strength, confidence=round(confidence, 1),
                price=curr_price, strategy_name=self.name,
                indicators={"upper": round(curr_upper, 2), "middle": round(curr_mid, 2),
                           "lower": round(curr_lower, 2), "width_pct": round(width[-1], 1)},
                stop_loss=stop_loss, take_profit=take_profit,
                reason=f"布林下轨反弹 价格={curr_price:.2f} 下轨={curr_lower:.2f}"
            )
        
        # 触及上轨回落 → 卖出
        elif prev_price >= upper[-2] and curr_price < curr_upper:
            confidence = min(90, 50 + abs((curr_price - curr_mid) / curr_mid) * 100)
            
            return StrategySignal(
                symbol=symbol, side="SELL",
                strength=SignalStrength.MODERATE, confidence=round(confidence, 1),
                price=curr_price, strategy_name=self.name,
                indicators={"upper": round(curr_upper, 2), "middle": round(curr_mid, 2),
                           "lower": round(curr_lower, 2)},
                reason=f"布林上轨回落 价格={curr_price:.2f} 上轨={curr_upper:.2f}"
            )
        
        else:
            # 带内位置
            pos = (curr_price - curr_lower) / (curr_upper - curr_lower) * 100
            zone = "下轨附近" if pos < 20 else "上轨附近" if pos > 80 else "中轨附近"
            return StrategySignal(symbol=symbol, side="HOLD",
                strategy_name=self.name, price=curr_price,
                indicators={"position_in_band": round(pos, 1)},
                reason=f"布林带内 {zone} ({pos:.0f}%)")


# ═══════════════════════════════════════
# 策略 5: COMBINED — 多指标共识
# ═══════════════════════════════════════

class CombinedStrategy:
    """
    多指标共识策略 — 投票机制
    
    运行全部 4 个策略，按权重投票:
      MA-CROSS  : 30%
      RSI       : 25%
      MACD      : 25%
      BOLLINGER : 20%
    
    买入: ≥2 策略发出买入信号，加权置信度 ≥ 60%
    卖出: ≥2 策略发出卖出信号，加权置信度 ≥ 60%
    
    对标 TradingSkill Combined strategy
    """
    
    def __init__(self):
        self.name = "COMBINED"
        self.strategies = [
            (MACrossoverStrategy(9, 21), 0.30),
            (RSIStrategy(14, 30, 70), 0.25),
            (MACDStrategy(12, 26, 9), 0.25),
            (BollingerStrategy(20, 2.0), 0.20),
        ]
    
    def analyze(self, symbol: str, closes: np.ndarray, highs=None, lows=None,
                volumes=None, dates=None) -> StrategySignal:
        if len(closes) < 30:
            return StrategySignal(symbol=symbol, strategy_name=self.name, reason="数据不足")
        
        buy_score = 0.0
        sell_score = 0.0
        details = []
        
        for strategy, weight in self.strategies:
            signal = strategy.analyze(symbol, closes, highs, lows, volumes, dates)
            
            contrib = signal.confidence * weight
            if signal.side == "BUY":
                buy_score += contrib
            elif signal.side == "SELL":
                sell_score += contrib
            
            details.append({
                "strategy": strategy.name,
                "weight": weight,
                "side": signal.side,
                "confidence": signal.confidence,
                "reason": signal.reason,
            })
        
        price = closes[-1]
        max_score = max(buy_score, sell_score)
        
        if buy_score >= 60.0 and buy_score > sell_score:
            strength = SignalStrength.STRONG if buy_score >= 75 else SignalStrength.MODERATE
            stop_loss = round(price * 0.95, 2)
            take_profit = round(price * 1.08, 2)
            
            return StrategySignal(
                symbol=symbol, side="BUY",
                strength=strength, confidence=round(min(buy_score, 95), 1),
                price=price, strategy_name=self.name,
                indicators={"buy_score": round(buy_score, 1), "sell_score": round(sell_score, 1),
                           "details": details},
                stop_loss=stop_loss, take_profit=take_profit,
                reason=f"多指标共识买入 ({buy_score:.0f}分 > 60)"
            )
        
        elif sell_score >= 60.0 and sell_score > buy_score:
            return StrategySignal(
                symbol=symbol, side="SELL",
                strength=SignalStrength.MODERATE, confidence=round(min(sell_score, 95), 1),
                price=price, strategy_name=self.name,
                indicators={"buy_score": round(buy_score, 1), "sell_score": round(sell_score, 1),
                           "details": details},
                reason=f"多指标共识卖出 ({sell_score:.0f}分 > 60)"
            )
        
        else:
            return StrategySignal(
                symbol=symbol, side="HOLD",
                strategy_name=self.name, price=price,
                indicators={"buy_score": round(buy_score, 1), "sell_score": round(sell_score, 1),
                           "details": details},
                reason=f"无共识信号 (买{buy_score:.0f} 卖{sell_score:.0f})"
            )


# ═══════════════════════════════════════
# 策略工厂
# ═══════════════════════════════════════

STRATEGY_REGISTRY: Dict[str, Any] = {
    "MA-CROSS": MACrossoverStrategy,
    "RSI": RSIStrategy,
    "MACD": MACDStrategy,
    "BOLLINGER": BollingerStrategy,
    "COMBINED": CombinedStrategy,
}


def get_strategy(strategy_id: str, **params):
    """获取策略实例"""
    cls = STRATEGY_REGISTRY.get(strategy_id)
    if cls is None:
        raise ValueError(f"未知策略: {strategy_id}. 可用: {list(STRATEGY_REGISTRY.keys())}")
    return cls(**params) if params else cls()


def list_strategies() -> List[Dict]:
    """列出所有可用策略"""
    return [
        {"id": "MA-CROSS", "name": "双均线交叉", "params": ["fast_period", "slow_period"]},
        {"id": "RSI", "name": "超买超卖", "params": ["period", "oversold", "overbought"]},
        {"id": "MACD", "name": "MACD信号线", "params": ["fast", "slow", "signal"]},
        {"id": "BOLLINGER", "name": "布林带", "params": ["period", "std_dev"]},
        {"id": "COMBINED", "name": "多指标共识", "params": []},
    ]
