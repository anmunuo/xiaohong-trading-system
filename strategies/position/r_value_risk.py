"""
R值风险管理策略

策略ID: POS-002
策略名称: R值风险管理
策略类别: 仓位管理
版本: v2.0.0

策略描述:
基于R值的固定风险仓位管理策略，每笔交易风险固定为R值

维护者: 小红 🌹
创建时间: 2026-04-10
"""

import json
import numpy as np
from typing import Dict, Any
from datetime import datetime

from ..base import PositionStrategy


class RValueRiskStrategy(PositionStrategy):
    """R值风险管理策略"""
    
    def __init__(self):
        super().__init__(
            strategy_id="POS-002",
            name="R值风险管理",
            category="position",
            version="2.0.0"
        )
    
    def default_parameters(self) -> Dict[str, Any]:
        """默认参数"""
        params = super().default_parameters()
        params.update({
            "r_value_formula": "净值 × 单股最大持仓% × 1/8 凯利值",  # R值计算公式
            "max_position_per_stock": 0.333,  # 单股最大持仓比例
            "per_trade_risk": 0.02,  # 每笔交易风险（净值比例）
            "min_stop_distance": 0.03,  # 最小止损距离（3%）
            "max_stop_distance": 0.15,  # 最大止损距离（15%）
            "position_rounding": 100,  # 仓位取整单位（100股）
            "use_technical_stop": True,  # 是否使用技术面止损位
            "safety_margin": 0.9,  # 安全边际（仓位打9折）
            "net_value": 0.0,  # 当前净值（必须由调用者提供，禁止硬编码）
            "kelly_value": 0.0,  # 凯利值（必须由调用者提供，禁止硬编码）
        })
        return params
    
    def parameter_schema(self) -> Dict[str, Dict]:
        """参数模式定义"""
        schema = super().parameter_schema()
        schema.update({
            "r_value_formula": {
                "type": "string",
                "default": "净值 × 单股最大持仓% × 1/8 凯利值",
                "description": "R值计算公式"
            },
            "max_position_per_stock": {
                "type": "float",
                "default": 0.333,
                "min": 0.01,
                "max": 1.0,
                "description": "单股最大持仓比例"
            },
            "per_trade_risk": {
                "type": "float",
                "default": 0.02,
                "min": 0.005,
                "max": 0.1,
                "description": "每笔交易风险（净值比例）"
            },
            "min_stop_distance": {
                "type": "float",
                "default": 0.03,
                "min": 0.01,
                "max": 0.5,
                "description": "最小止损距离"
            },
            "max_stop_distance": {
                "type": "float",
                "default": 0.15,
                "min": 0.01,
                "max": 0.5,
                "description": "最大止损距离"
            },
            "position_rounding": {
                "type": "integer",
                "default": 100,
                "min": 1,
                "max": 10000,
                "description": "仓位取整单位"
            },
            "use_technical_stop": {
                "type": "boolean",
                "default": True,
                "description": "是否使用技术面止损位"
            },
            "safety_margin": {
                "type": "float",
                "default": 0.9,
                "min": 0.1,
                "max": 1.0,
                "description": "安全边际"
            },
            "net_value": {
                "type": "float",
                "default": 0.0,
                "min": 1000.0,
                "max": 10000000.0,
                "description": "当前净值（必须由调用者提供）"
            },
            "kelly_value": {
                "type": "float",
                "default": 0.0,
                "min": 0.01,
                "max": 1.0,
                "description": "凯利值（必须由调用者提供）"
            }
        })
        return schema
    
    def calculate_r_value(self, net_value: float = None, kelly_value: float = None) -> float:
        """
        计算R值
        
        Args:
            net_value: 净值（如为None则使用参数中的净值）
            kelly_value: 凯利值（如为None则使用参数中的凯利值）
            
        Returns:
            float: R值
        """
        if net_value is None:
            net_value = self.parameters.get("net_value", 0.0)
        
        if kelly_value is None:
            kelly_value = self.parameters.get("kelly_value", 0.0)
        
        # 验证必须参数
        if net_value <= 0:
            raise ValueError("净值必须大于0，请通过参数net_value提供")
        if kelly_value <= 0:
            raise ValueError("凯利值必须大于0，请通过参数kelly_value提供")
        
        max_position_per_stock = self.parameters.get("max_position_per_stock", 0.333)
        per_trade_risk = self.parameters.get("per_trade_risk", 0.02)
        
        # 根据公式计算R值
        formula = self.parameters.get("r_value_formula", "")
        
        if "1/8" in formula:
            # 公式：净值 × 单股最大持仓% × 1/8 凯利值
            r_value = net_value * max_position_per_stock * (1/8) * kelly_value
        else:
            # 默认公式：净值 × 每笔交易风险
            r_value = net_value * per_trade_risk
        
        return round(r_value, 2)
    
    def calculate_position(self, stock_data: Dict, net_value: float, **kwargs) -> Dict[str, Any]:
        """
        计算仓位
        
        Args:
            stock_data: 股票数据，包含以下字段：
                - code: 股票代码
                - name: 股票名称
                - current_price: 当前价格
                - stop_loss_price: 止损价格（可选，如未提供则使用技术分析或默认止损）
                - technical_support: 技术支撑位（可选）
                - volatility: 波动率（可选）
                - sector: 所属板块（可选）
            
            net_value: 净值
            
            **kwargs: 仓位计算参数（可覆盖默认参数）
            
        Returns:
            dict: 仓位计算结果，包含：
                - code: 股票代码
                - name: 股票名称
                - entry_price: 入场价格
                - stop_loss_price: 止损价格
                - stop_distance: 止损距离（百分比）
                - r_value: R值
                - position_value: 建议仓位金额
                - shares: 建议买入股数
                - position_pct: 仓位占比（净值比例）
                - risk_amount: 风险金额
                - take_profit_price: 止盈价格（盈亏比3:1）
                - explanation: 计算说明
                - warnings: 警告信息列表
        """
        # 合并参数（kwargs优先）
        params = self.parameters.copy()
        params.update(kwargs)
        params["net_value"] = net_value
        
        # 获取股票信息
        code = stock_data.get("code", "")
        name = stock_data.get("name", "")
        current_price = stock_data.get("current_price", 0)
        
        if current_price <= 0:
            return {
                "success": False,
                "error": "当前价格无效",
                "code": code,
                "name": name
            }
        
        # 验证必要参数
        kelly_value = params.get("kelly_value")
        if kelly_value is None or kelly_value <= 0:
            return {
                "success": False,
                "error": "凯利值必须大于0，请通过参数kelly_value提供",
                "code": code,
                "name": name
            }
        
        if net_value <= 0:
            return {
                "success": False,
                "error": "净值必须大于0",
                "code": code,
                "name": name
            }
        
        # 计算R值
        try:
            r_value = self.calculate_r_value(net_value, kelly_value)
        except ValueError as e:
            return {
                "success": False,
                "error": str(e),
                "code": code,
                "name": name
            }
        
        # 确定止损价格
        stop_loss_price, stop_source = self._determine_stop_loss(stock_data, current_price, params)
        
        # 计算止损距离
        stop_distance = (current_price - stop_loss_price) / current_price
        
        # 验证止损距离是否在合理范围内
        warnings = []
        if stop_distance < params["min_stop_distance"]:
            warnings.append(f"止损距离过小 ({stop_distance:.1%} < {params['min_stop_distance']:.1%})")
            stop_distance = params["min_stop_distance"]
            stop_loss_price = current_price * (1 - stop_distance)
            stop_source = "adjusted_min"
        
        if stop_distance > params["max_stop_distance"]:
            warnings.append(f"止损距离过大 ({stop_distance:.1%} > {params['max_stop_distance']:.1%})")
            stop_distance = params["max_stop_distance"]
            stop_loss_price = current_price * (1 - stop_distance)
            stop_source = "adjusted_max"
        
        # 计算仓位金额：仓位金额 = R值 ÷ 止损距离
        position_value_raw = r_value / stop_distance
        
        # 应用安全边际
        position_value = position_value_raw * params["safety_margin"]
        
        # 检查是否超过单股最大仓位
        max_position_value = net_value * params["max_position_per_stock"]
        if position_value > max_position_value:
            warnings.append(f"超过单股最大仓位限制 ({position_value:.0f} > {max_position_value:.0f})")
            position_value = max_position_value
        
        # 计算股数
        shares_raw = position_value / current_price
        shares = int(shares_raw // params["position_rounding"] * params["position_rounding"])
        
        # 重新计算实际仓位金额
        position_value = shares * current_price
        
        # 计算实际仓位占比和风险金额
        position_pct = position_value / net_value
        risk_amount = position_value * stop_distance
        
        # 计算止盈价格（盈亏比3:1）
        take_profit_price = current_price + (current_price - stop_loss_price) * 3
        
        # 生成计算说明
        explanation = self._generate_explanation(
            r_value, stop_distance, stop_source, position_value, shares, risk_amount
        )
        
        result = {
            "success": True,
            "code": code,
            "name": name,
            "entry_price": current_price,
            "stop_loss_price": round(stop_loss_price, 3),
            "stop_distance": round(stop_distance, 4),
            "stop_source": stop_source,
            "r_value": r_value,
            "position_value": round(position_value, 2),
            "shares": shares,
            "position_pct": round(position_pct, 4),
            "risk_amount": round(risk_amount, 2),
            "take_profit_price": round(take_profit_price, 3),
            "profit_loss_ratio": 3.0,
            "explanation": explanation,
            "warnings": warnings,
            "calculation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parameters_used": {
                "net_value": net_value,
                "kelly_value": params.get("kelly_value"),
                "safety_margin": params["safety_margin"],
                "max_position_per_stock": params["max_position_per_stock"]
            }
        }
        
        # 记录执行结果
        self.record_execution(result, success=True)
        
        return result
    
    def _determine_stop_loss(self, stock_data: Dict, current_price: float, params: Dict) -> tuple:
        """
        确定止损价格
        
        Returns:
            tuple: (止损价格, 止损来源)
        """
        # 1. 优先使用传入的止损价格
        if "stop_loss_price" in stock_data and stock_data["stop_loss_price"] > 0:
            return stock_data["stop_loss_price"], "provided"
        
        # 2. 使用技术支撑位（如果启用）
        if params["use_technical_stop"] and "technical_support" in stock_data:
            support_price = stock_data["technical_support"]
            if 0 < support_price < current_price * 0.95:  # 支撑位低于当前价格5%以上
                return support_price, "technical_support"
        
        # 3. 基于波动率计算止损（如果可用）
        if "volatility" in stock_data and stock_data["volatility"] > 0:
            volatility = stock_data["volatility"]
            # 使用1.5倍ATR作为止损距离
            atr_stop = current_price * (1 - volatility * 1.5)
            if atr_stop > 0:
                return atr_stop, "volatility_atr"
        
        # 4. 默认止损（5%）
        default_stop_distance = 0.05
        default_stop = current_price * (1 - default_stop_distance)
        return default_stop, "default_5pct"
    
    def _generate_explanation(self, r_value: float, stop_distance: float, stop_source: str, 
                            position_value: float, shares: int, risk_amount: float) -> str:
        """生成计算说明"""
        explanations = []
        
        explanations.append(f"R值: ¥{r_value:,.2f}")
        explanations.append(f"止损距离: {stop_distance:.1%} ({stop_source})")
        
        if stop_source == "technical_support":
            explanations.append("基于技术支撑位设置止损")
        elif stop_source == "volatility_atr":
            explanations.append("基于波动率(ATR)设置止损")
        elif stop_source == "default_5pct":
            explanations.append("使用默认5%止损")
        elif "adjusted" in stop_source:
            explanations.append("止损距离已调整至合理范围")
        
        explanations.append(f"计算仓位: ¥{position_value:,.0f} ({shares:,}股)")
        explanations.append(f"风险金额: ¥{risk_amount:,.0f} (R值: ¥{r_value:,.0f})")
        
        if risk_amount > r_value * 1.1:
            explanations.append("⚠️ 实际风险略高于R值（考虑取整影响）")
        elif risk_amount < r_value * 0.9:
            explanations.append("实际风险低于R值（安全边际或取整影响）")
        
        return "；".join(explanations)
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行策略（兼容基类接口）
        
        Args:
            **kwargs: 策略输入参数，必须包含：
                - stock_data: 股票数据
                - net_value: 净值
            
        Returns:
            dict: 策略输出结果
        """
        stock_data = kwargs.get("stock_data")
        net_value = kwargs.get("net_value")
        
        if stock_data is None or net_value is None:
            return {
                "success": False,
                "error": "缺少必要参数：stock_data 或 net_value",
                "strategy_id": self.strategy_id,
                "strategy_name": self.name
            }
        
        result = self.calculate_position(stock_data, net_value, **kwargs)
        return result


# 测试代码
if __name__ == "__main__":
    # 创建策略实例
    strategy = RValueRiskStrategy()
    
    # 打印策略信息
    print(f"策略ID: {strategy.strategy_id}")
    print(f"策略名称: {strategy.name}")
    print(f"策略版本: {strategy.version}")
    
    # 计算R值
    r_value = strategy.calculate_r_value()
    print(f"\n当前R值: ¥{r_value:,.2f}")
    
    # 测试仓位计算
    test_stock = {
        "code": "300131",
        "name": "英唐智控",
        "current_price": 12.6,
        "technical_support": 11.8,
        "volatility": 0.02
    }
    
    test_net_value = 0.0  # 禁止硬编码，实际使用时从ConfigManager获取
    
    result = strategy.calculate_position(test_stock, test_net_value)
    
    print(f"\n测试仓位计算:")
    print(f"股票: {result['code']} {result['name']}")
    print(f"入场价格: ¥{result['entry_price']}")
    print(f"止损价格: ¥{result['stop_loss_price']} (距离: {result['stop_distance']:.1%})")
    print(f"建议仓位: ¥{result['position_value']:,.0f} ({result['shares']:,}股)")
    print(f"仓位占比: {result['position_pct']:.1%}")
    print(f"风险金额: ¥{result['risk_amount']:,.0f}")
    print(f"止盈价格: ¥{result['take_profit_price']} (盈亏比: {result['profit_loss_ratio']}:1)")
    
    if result['warnings']:
        print(f"\n警告:")
        for warning in result['warnings']:
            print(f"  ⚠️  {warning}")
    
    print(f"\n计算说明: {result['explanation']}")
    
    print(f"\n✅ R值风险管理策略加载成功")