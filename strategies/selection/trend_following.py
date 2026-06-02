"""
趋势跟随选股策略

策略ID: SEL-001
策略名称: 趋势跟随
策略类别: 选股策略
版本: v1.0.0

策略描述:
识别并跟随主要趋势，筛选出处于上升趋势中的股票

维护者: 小红 🌹
创建时间: 2026-04-10
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any
from datetime import datetime

from ..base import SelectionStrategy


class TrendFollowingStrategy(SelectionStrategy):
    """趋势跟随选股策略"""
    
    def __init__(self):
        super().__init__(
            strategy_id="SEL-001",
            name="趋势跟随",
            category="selection",
            version="1.0.0"
        )
    
    def default_parameters(self) -> Dict[str, Any]:
        """默认参数"""
        params = super().default_parameters()
        params.update({
            "trend_period": 20,           # 趋势判断周期（日）
            "trend_confirmation": 3,      # 趋势确认K线数
            "min_price": 5.0,             # 最低价格（元）
            "max_price": 200.0,           # 最高价格（元）
            "volume_multiplier": 1.5,     # 成交量倍数（相对于均量）
            "sector_filter": True,        # 是否启用板块过滤
            "exclude_st": True,           # 是否排除ST股票
            "max_selections": 10,         # 最大选股数量
            "score_threshold": 60,        # 评分阈值（0-100）
        })
        return params
    
    def parameter_schema(self) -> Dict[str, Dict]:
        """参数模式定义"""
        schema = super().parameter_schema()
        schema.update({
            "trend_period": {
                "type": "integer",
                "default": 20,
                "min": 5,
                "max": 60,
                "description": "趋势判断周期（日）"
            },
            "trend_confirmation": {
                "type": "integer",
                "default": 3,
                "min": 1,
                "max": 10,
                "description": "趋势确认K线数"
            },
            "min_price": {
                "type": "float",
                "default": 5.0,
                "min": 1.0,
                "max": 1000.0,
                "description": "最低价格（元）"
            },
            "max_price": {
                "type": "float",
                "default": 200.0,
                "min": 1.0,
                "max": 1000.0,
                "description": "最高价格（元）"
            },
            "volume_multiplier": {
                "type": "float",
                "default": 1.5,
                "min": 0.5,
                "max": 5.0,
                "description": "成交量倍数（相对于均量）"
            },
            "sector_filter": {
                "type": "boolean",
                "default": True,
                "description": "是否启用板块过滤"
            },
            "exclude_st": {
                "type": "boolean",
                "default": True,
                "description": "是否排除ST股票"
            },
            "max_selections": {
                "type": "integer",
                "default": 10,
                "min": 1,
                "max": 50,
                "description": "最大选股数量"
            },
            "score_threshold": {
                "type": "integer",
                "default": 60,
                "min": 0,
                "max": 100,
                "description": "评分阈值（0-100）"
            }
        })
        return schema
    
    def select(self, stock_pool: List[Dict], **kwargs) -> List[Dict]:
        """
        执行选股
        
        Args:
            stock_pool: 股票池，每只股票包含以下字段：
                - code: 股票代码
                - name: 股票名称
                - price: 当前价格
                - change_pct: 涨跌幅
                - volume: 成交量
                - amount: 成交额
                - market_cap: 市值
                - sector: 所属板块
                - is_st: 是否ST股票
                - historical_data: 历史数据（DataFrame格式）
            
            **kwargs: 选股参数（可覆盖默认参数）
            
        Returns:
            list: 选中的股票列表，每只股票包含：
                - code: 股票代码
                - name: 股票名称
                - score: 综合评分（0-100）
                - trend_strength: 趋势强度（0-100）
                - volume_score: 量能评分（0-100）
                - price_score: 价格评分（0-100）
                - reason: 选中理由
                - signals: 具体信号列表
        """
        # 合并参数（kwargs优先）
        params = self.parameters.copy()
        params.update(kwargs)
        
        selected_stocks = []
        
        for stock in stock_pool:
            try:
                # 基础过滤
                if not self._basic_filter(stock, params):
                    continue
                
                # 趋势分析
                trend_score, trend_signals = self._analyze_trend(stock, params)
                
                # 量能分析
                volume_score, volume_signals = self._analyze_volume(stock, params)
                
                # 价格分析
                price_score, price_signals = self._analyze_price(stock, params)
                
                # 计算综合评分
                composite_score = self._calculate_composite_score(
                    trend_score, volume_score, price_score
                )
                
                # 筛选达标股票
                if composite_score >= params["score_threshold"]:
                    selected_stocks.append({
                        "code": stock["code"],
                        "name": stock["name"],
                        "score": composite_score,
                        "trend_strength": trend_score,
                        "volume_score": volume_score,
                        "price_score": price_score,
                        "reason": self._generate_reason(trend_signals, volume_signals, price_signals),
                        "signals": trend_signals + volume_signals + price_signals,
                        "current_price": stock.get("price", 0),
                        "change_pct": stock.get("change_pct", 0),
                        "sector": stock.get("sector", ""),
                        "analysis_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                    
            except Exception as e:
                print(f"⚠️  分析股票 {stock.get('code', '未知')} 失败: {e}")
                continue
        
        # 按评分排序并限制数量
        selected_stocks.sort(key=lambda x: x["score"], reverse=True)
        selected_stocks = selected_stocks[:params["max_selections"]]
        
        # 记录执行结果
        self.record_execution({
            "total_analyzed": len(stock_pool),
            "selected_count": len(selected_stocks),
            "selection_rate": len(selected_stocks) / len(stock_pool) if stock_pool else 0,
            "average_score": np.mean([s["score"] for s in selected_stocks]) if selected_stocks else 0,
            "selected_codes": [s["code"] for s in selected_stocks],
            "success": True
        }, success=True)
        
        return selected_stocks
    
    def _basic_filter(self, stock: Dict, params: Dict) -> bool:
        """基础过滤"""
        # 价格过滤
        price = stock.get("price", 0)
        if price < params["min_price"] or price > params["max_price"]:
            return False
        
        # ST股票过滤
        if params["exclude_st"] and stock.get("is_st", False):
            return False
        
        # 数据完整性检查
        if "historical_data" not in stock or stock["historical_data"] is None:
            return False
        
        historical_data = stock["historical_data"]
        if len(historical_data) < params["trend_period"]:
            return False
        
        return True
    
    def _analyze_trend(self, stock: Dict, params: Dict) -> tuple:
        """趋势分析"""
        historical_data = stock["historical_data"]
        period = params["trend_period"]
        
        # 计算移动平均线
        if len(historical_data) >= period:
            closes = historical_data["close"].values[-period:]
            
            # 计算短期和长期均线
            short_ma = np.mean(closes[-5:]) if len(closes) >= 5 else closes[-1]
            medium_ma = np.mean(closes[-10:]) if len(closes) >= 10 else closes[-1]
            long_ma = np.mean(closes) if len(closes) >= period else closes[-1]
            
            # 趋势判断
            trend_signals = []
            trend_score = 50  # 基准分
            
            # 1. 均线多头排列
            if short_ma > medium_ma > long_ma:
                trend_score += 20
                trend_signals.append("均线多头排列")
            
            # 2. 价格在均线之上
            current_price = stock.get("price", closes[-1])
            if current_price > short_ma:
                trend_score += 10
                trend_signals.append("价格在短期均线之上")
            
            # 3. 趋势斜率
            if len(closes) >= 5:
                x = np.arange(len(closes))
                slope, _ = np.polyfit(x, closes, 1)
                if slope > 0:
                    trend_score += min(int(slope * 100), 15)
                    trend_signals.append(f"上升趋势斜率: {slope:.4f}")
            
            # 4. 高点突破
            if len(closes) >= 20:
                recent_high = np.max(closes[-5:])
                previous_high = np.max(closes[-20:-5])
                if recent_high > previous_high:
                    trend_score += 10
                    trend_signals.append("突破近期高点")
            
            # 限制分数范围
            trend_score = max(0, min(100, trend_score))
            
            return trend_score, trend_signals
        
        return 0, ["数据不足"]
    
    def _analyze_volume(self, stock: Dict, params: Dict) -> tuple:
        """量能分析"""
        historical_data = stock["historical_data"]
        period = params["trend_period"]
        
        if len(historical_data) >= period:
            volumes = historical_data["volume"].values[-period:]
            
            volume_signals = []
            volume_score = 50  # 基准分
            
            # 1. 成交量放大
            recent_volume = np.mean(volumes[-5:]) if len(volumes) >= 5 else volumes[-1]
            avg_volume = np.mean(volumes)
            
            if avg_volume > 0:
                volume_ratio = recent_volume / avg_volume
                if volume_ratio > params["volume_multiplier"]:
                    volume_score += 20
                    volume_signals.append(f"成交量放大 {volume_ratio:.1f}倍")
                elif volume_ratio > 1.0:
                    volume_score += 10
                    volume_signals.append(f"成交量温和放大 {volume_ratio:.1f}倍")
            
            # 2. 量价配合
            closes = historical_data["close"].values[-period:]
            if len(closes) >= 5:
                price_change = (closes[-1] - closes[-5]) / closes[-5] * 100
                volume_change = (volumes[-1] - np.mean(volumes[-10:-5])) / np.mean(volumes[-10:-5]) * 100
                
                if price_change > 0 and volume_change > 0:
                    volume_score += 15
                    volume_signals.append("量价齐升")
                elif price_change > 0 and volume_change < 0:
                    volume_score -= 10
                    volume_signals.append("价升量缩（需警惕）")
            
            # 限制分数范围
            volume_score = max(0, min(100, volume_score))
            
            return volume_score, volume_signals
        
        return 0, ["数据不足"]
    
    def _analyze_price(self, stock: Dict, params: Dict) -> tuple:
        """价格分析"""
        historical_data = stock["historical_data"]
        period = params["trend_period"]
        
        if len(historical_data) >= period:
            closes = historical_data["close"].values[-period:]
            highs = historical_data["high"].values[-period:]
            lows = historical_data["low"].values[-period:]
            
            price_signals = []
            price_score = 50  # 基准分
            
            current_price = stock.get("price", closes[-1])
            
            # 1. 价格位置
            if len(highs) > 0 and len(lows) > 0:
                price_position = (current_price - np.min(lows)) / (np.max(highs) - np.min(lows)) * 100
                
                if price_position > 70:
                    price_score += 15
                    price_signals.append(f"价格处于高位（{price_position:.1f}%）")
                elif price_position > 30:
                    price_score += 10
                    price_signals.append(f"价格处于中位（{price_position:.1f}%）")
                else:
                    price_score += 5
                    price_signals.append(f"价格处于低位（{price_position:.1f}%）")
            
            # 2. 波动率
            if len(closes) >= 10:
                returns = np.diff(closes) / closes[:-1]
                volatility = np.std(returns) * np.sqrt(252) * 100  # 年化波动率
                
                if volatility < 30:
                    price_score += 10
                    price_signals.append(f"波动率适中（{volatility:.1f}%）")
                elif volatility < 50:
                    price_score += 5
                    price_signals.append(f"波动率较高（{volatility:.1f}%）")
                else:
                    price_score -= 10
                    price_signals.append(f"波动率过高（{volatility:.1f}%）")
            
            # 3. 突破关键价位
            if len(closes) >= 20:
                resistance = np.max(highs[-20:])
                support = np.min(lows[-20:])
                
                if current_price > resistance:
                    price_score += 15
                    price_signals.append(f"突破阻力位 {resistance:.2f}")
                elif current_price < support:
                    price_score -= 15
                    price_signals.append(f"跌破支撑位 {support:.2f}")
            
            # 限制分数范围
            price_score = max(0, min(100, price_score))
            
            return price_score, price_signals
        
        return 0, ["数据不足"]
    
    def _calculate_composite_score(self, trend_score: float, volume_score: float, price_score: float) -> int:
        """计算综合评分"""
        # 权重分配：趋势40%，量能30%，价格30%
        weights = {"trend": 0.4, "volume": 0.3, "price": 0.3}
        
        composite = (
            trend_score * weights["trend"] +
            volume_score * weights["volume"] +
            price_score * weights["price"]
        )
        
        return int(round(composite))
    
    def _generate_reason(self, trend_signals: List[str], volume_signals: List[str], price_signals: List[str]) -> str:
        """生成选中理由"""
        all_signals = trend_signals + volume_signals + price_signals
        
        if not all_signals:
            return "无明显信号"
        
        # 取最重要的几个信号
        important_signals = []
        for signal in all_signals:
            if any(keyword in signal for keyword in ["突破", "放大", "多头", "齐升", "阻力", "支撑"]):
                important_signals.append(signal)
        
        if len(important_signals) > 3:
            important_signals = important_signals[:3]
        
        if important_signals:
            return "；".join(important_signals)
        else:
            return "；".join(all_signals[:2]) if len(all_signals) >= 2 else all_signals[0]
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行策略（兼容基类接口）
        
        Args:
            **kwargs: 策略输入参数
            
        Returns:
            dict: 策略输出结果
        """
        # 这里需要股票池数据，实际使用时需要传入
        stock_pool = kwargs.get("stock_pool", [])
        
        if not stock_pool:
            return {
                "success": False,
                "error": "缺少股票池数据",
                "selected_stocks": []
            }
        
        selected_stocks = self.select(stock_pool, **kwargs)
        
        return {
            "success": True,
            "selected_stocks": selected_stocks,
            "selection_count": len(selected_stocks),
            "strategy_id": self.strategy_id,
            "strategy_name": self.name
        }


# 测试代码
if __name__ == "__main__":
    # 创建策略实例
    strategy = TrendFollowingStrategy()
    
    # 打印策略信息
    print(f"策略ID: {strategy.strategy_id}")
    print(f"策略名称: {strategy.name}")
    print(f"策略版本: {strategy.version}")
    print(f"策略参数: {json.dumps(strategy.parameters, ensure_ascii=False, indent=2)}")
    
    # 获取性能报告
    report = strategy.get_performance_report()
    print(f"\n性能报告:")
    print(f"总执行次数: {report['performance_summary']['total_executions']}")
    print(f"成功次数: {report['performance_summary']['success_count']}")
    print(f"准确率: {report['performance_summary']['accuracy']:.1%}")
    
    print(f"\n✅ 趋势跟随策略加载成功")