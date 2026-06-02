"""
R值止损策略

策略ID: STP-001
策略名称: R值止损
策略类别: 止损止盈
版本: v2.0.0

策略描述:
基于R值的固定风险止损策略，结合技术面止损位和移动止盈

维护者: 小红 🌹
创建时间: 2026-04-10
"""

import numpy as np
from typing import Dict, Any, List
from datetime import datetime

from ..base import StopStrategy


class RValueStopStrategy(StopStrategy):
    """R值止损策略"""
    
    def __init__(self):
        super().__init__(
            strategy_id="STP-001",
            name="R值止损",
            category="stop",
            version="2.0.0"
        )
    
    def default_parameters(self) -> Dict[str, Any]:
        """默认参数"""
        params = super().default_parameters()
        params.update({
            "r_value": 0.0,  # R值（必须由调用者提供，禁止硬编码）
            "trailing_stop_enabled": True,  # 是否启用移动止盈
            "trailing_start_pct": 0.20,  # 移动止损启动涨幅（20%）
            "trailing_step_pct": 0.10,  # 移动止损步长（10%）
            "use_technical_stop": True,  # 是否使用技术面止损位
            "profit_target_ratio": 3.0,  # 盈亏比目标（3:1）
            "min_stop_distance": 0.03,  # 最小止损距离（3%）
            "max_stop_distance": 0.15,  # 最大止损距离（15%）
            "break_even_enabled": True,  # 是否启用保本止损
            "break_even_pct": 0.10,  # 保本止损启动涨幅（10%）
            "time_stop_enabled": False,  # 是否启用时间止损
            "max_holding_days": 60,  # 最大持仓天数
            "volatility_adjustment": True,  # 是否根据波动率调整
            "sector_adjustment": True,  # 是否根据板块调整
        })
        return params
    
    def parameter_schema(self) -> Dict[str, Dict]:
        """参数模式定义"""
        schema = super().parameter_schema()
        schema.update({
            "r_value": {
                "type": "float",
                "default": 0.0,
                "min": 100.0,
                "max": 100000.0,
                "description": "R值（每笔固定风险，必须由调用者提供）"
            },
            "trailing_stop_enabled": {
                "type": "boolean",
                "default": True,
                "description": "是否启用移动止盈"
            },
            "trailing_start_pct": {
                "type": "float",
                "default": 0.20,
                "min": 0.05,
                "max": 0.5,
                "description": "移动止损启动涨幅"
            },
            "trailing_step_pct": {
                "type": "float",
                "default": 0.10,
                "min": 0.02,
                "max": 0.3,
                "description": "移动止损步长"
            },
            "use_technical_stop": {
                "type": "boolean",
                "default": True,
                "description": "是否使用技术面止损位"
            },
            "profit_target_ratio": {
                "type": "float",
                "default": 3.0,
                "min": 1.0,
                "max": 10.0,
                "description": "盈亏比目标"
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
            "break_even_enabled": {
                "type": "boolean",
                "default": True,
                "description": "是否启用保本止损"
            },
            "break_even_pct": {
                "type": "float",
                "default": 0.10,
                "min": 0.01,
                "max": 0.5,
                "description": "保本止损启动涨幅"
            },
            "time_stop_enabled": {
                "type": "boolean",
                "default": False,
                "description": "是否启用时间止损"
            },
            "max_holding_days": {
                "type": "integer",
                "default": 60,
                "min": 1,
                "max": 365,
                "description": "最大持仓天数"
            },
            "volatility_adjustment": {
                "type": "boolean",
                "default": True,
                "description": "是否根据波动率调整"
            },
            "sector_adjustment": {
                "type": "boolean",
                "default": True,
                "description": "是否根据板块调整"
            }
        })
        return schema
    
    def calculate_stop_loss(self, stock_data: Dict, entry_price: float, **kwargs) -> Dict[str, Any]:
        """
        计算止损位
        
        Args:
            stock_data: 股票数据，包含以下字段：
                - code: 股票代码
                - name: 股票名称
                - current_price: 当前价格
                - technical_support: 技术支撑位（可选）
                - volatility: 波动率（可选）
                - sector: 所属板块（可选）
                - position_data: 持仓数据（可选，包含持仓天数、最高价等）
            
            entry_price: 入场价格
            
            **kwargs: 止损计算参数（可覆盖默认参数）
            
        Returns:
            dict: 止损计算结果，包含：
                - code: 股票代码
                - name: 股票名称
                - entry_price: 入场价格
                - current_price: 当前价格
                - stop_loss_price: 止损价格
                - stop_distance: 止损距离（百分比）
                - stop_type: 止损类型（initial/technical/trailing/break_even）
                - r_value_used: 使用的R值
                - position_value: 建议仓位金额（基于R值反推）
                - risk_amount: 风险金额
                - explanation: 计算说明
                - warnings: 警告信息列表
                - signals: 止损信号列表
        """
        # 合并参数（kwargs优先）
        params = self.parameters.copy()
        params.update(kwargs)
        
        # 获取股票信息
        code = stock_data.get("code", "")
        name = stock_data.get("name", "")
        current_price = stock_data.get("current_price", entry_price)
        
        # 验证价格有效性
        if entry_price is None or entry_price <= 0:
            return {
                "success": False,
                "error": "入场价格无效",
                "code": code,
                "name": name
            }
        
        # 确保current_price有效
        if current_price is None or current_price <= 0:
            current_price = entry_price
        
        # 获取R值（禁止硬编码，必须由调用者提供）
        r_value = params.get("r_value", 0.0)
        if r_value <= 0:
            return {
                "success": False,
                "error": "R值必须大于0，请通过参数r_value提供",
                "code": code,
                "name": name
            }
        
        # 确定止损类型和价格
        stop_result = self._determine_stop_loss(
            stock_data, entry_price, current_price, params
        )
        
        stop_loss_price = stop_result["price"]
        stop_type = stop_result["type"]
        stop_signals = stop_result["signals"]
        
        # 计算止损距离
        stop_distance = (entry_price - stop_loss_price) / entry_price
        
        # 验证止损距离是否在合理范围内
        warnings = []
        adjustments = []
        
        if stop_distance < params["min_stop_distance"]:
            warnings.append(f"止损距离过小 ({stop_distance:.1%} < {params['min_stop_distance']:.1%})")
            stop_distance = params["min_stop_distance"]
            stop_loss_price = entry_price * (1 - stop_distance)
            stop_type = "adjusted_min"
            adjustments.append("调整至最小止损距离")
        
        if stop_distance > params["max_stop_distance"]:
            warnings.append(f"止损距离过大 ({stop_distance:.1%} > {params['max_stop_distance']:.1%})")
            stop_distance = params["max_stop_distance"]
            stop_loss_price = entry_price * (1 - stop_distance)
            stop_type = "adjusted_max"
            adjustments.append("调整至最大止损距离")
        
        # 根据波动率调整（如果启用）
        if params["volatility_adjustment"] and "volatility" in stock_data:
            volatility = stock_data["volatility"]
            if volatility > 0.03:  # 波动率大于3%
                # 高波动股票适当扩大止损距离
                adjustment_factor = min(1.0 + (volatility - 0.03) * 5, 1.5)
                adjusted_distance = stop_distance * adjustment_factor
                
                if adjusted_distance <= params["max_stop_distance"]:
                    stop_distance = adjusted_distance
                    stop_loss_price = entry_price * (1 - stop_distance)
                    adjustments.append(f"根据波动率({volatility:.1%})调整止损距离")
        
        # 根据板块调整（如果启用）
        if params["sector_adjustment"] and "sector" in stock_data:
            sector = stock_data["sector"]
            sector_adjustment = self._get_sector_adjustment(sector)
            
            if sector_adjustment != 1.0:
                adjusted_distance = stop_distance * sector_adjustment
                
                if (adjusted_distance >= params["min_stop_distance"] and 
                    adjusted_distance <= params["max_stop_distance"]):
                    stop_distance = adjusted_distance
                    stop_loss_price = entry_price * (1 - stop_distance)
                    adjustments.append(f"根据板块({sector})调整止损距离")
        
        # 反推仓位金额：仓位金额 = R值 ÷ 止损距离
        position_value = r_value / stop_distance
        
        # 计算风险金额
        risk_amount = position_value * stop_distance
        
        # 生成计算说明
        explanation = self._generate_explanation(
            entry_price, stop_loss_price, stop_type, stop_distance,
            r_value, position_value, risk_amount, adjustments
        )
        
        # 组合所有信号
        all_signals = stop_signals + adjustments
        
        result = {
            "success": True,
            "code": code,
            "name": name,
            "entry_price": entry_price,
            "current_price": current_price,
            "stop_loss_price": round(stop_loss_price, 3),
            "stop_distance": round(stop_distance, 4),
            "stop_type": stop_type,
            "r_value_used": r_value,
            "position_value": round(position_value, 2),
            "risk_amount": round(risk_amount, 2),
            "profit_target_price": round(entry_price + (entry_price - stop_loss_price) * params["profit_target_ratio"], 3),
            "profit_target_ratio": params["profit_target_ratio"],
            "explanation": explanation,
            "warnings": warnings,
            "signals": all_signals,
            "calculation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parameters_used": {
                "r_value": r_value,
                "trailing_stop_enabled": params["trailing_stop_enabled"],
                "use_technical_stop": params["use_technical_stop"],
                "profit_target_ratio": params["profit_target_ratio"]
            }
        }
        
        # 记录执行结果
        self.record_execution(result, success=True)
        
        return result
    
    def calculate_take_profit(self, stock_data: Dict, entry_price: float, **kwargs) -> Dict[str, Any]:
        """
        计算止盈位
        
        Args:
            stock_data: 股票数据
            entry_price: 入场价格
            
            **kwargs: 止盈计算参数
            
        Returns:
            dict: 止盈计算结果
        """
        # 首先计算止损位
        stop_result = self.calculate_stop_loss(stock_data, entry_price, **kwargs)
        
        if not stop_result["success"]:
            return stop_result
        
        # 基于止损位计算止盈位（盈亏比目标）
        params = self.parameters.copy()
        params.update(kwargs)
        
        profit_target_ratio = params.get("profit_target_ratio", 3.0)
        stop_loss_price = stop_result["stop_loss_price"]
        
        # 计算止盈价格
        take_profit_price = entry_price + (entry_price - stop_loss_price) * profit_target_ratio
        
        # 如果启用移动止盈，考虑当前价格
        current_price = stock_data.get("current_price", entry_price)
        profit_pct = (current_price - entry_price) / entry_price
        
        trailing_stop_price = None
        if params.get("trailing_stop_enabled", True) and profit_pct > params.get("trailing_start_pct", 0.20):
            # 计算移动止盈价格
            trailing_stop_price = self._calculate_trailing_stop(
                stock_data, entry_price, current_price, params
            )
        
        result = {
            "success": True,
            "code": stop_result["code"],
            "name": stop_result["name"],
            "entry_price": entry_price,
            "current_price": current_price,
            "profit_pct": profit_pct,
            "take_profit_price": round(take_profit_price, 3),
            "profit_target_ratio": profit_target_ratio,
            "trailing_stop_enabled": params.get("trailing_stop_enabled", True),
            "trailing_stop_price": round(trailing_stop_price, 3) if trailing_stop_price else None,
            "stop_loss_price": stop_loss_price,
            "risk_reward_ratio": profit_target_ratio,
            "explanation": f"基于{profit_target_ratio}:1盈亏比计算止盈位",
            "calculation_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return result
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行策略（兼容基类接口）
        
        Args:
            **kwargs: 策略输入参数，必须包含：
                - stock_data: 股票数据
                - entry_price: 入场价格
            
        Returns:
            dict: 策略输出结果
        """
        stock_data = kwargs.get("stock_data")
        entry_price = kwargs.get("entry_price")
        
        if stock_data is None or entry_price is None:
            return {
                "success": False,
                "error": "缺少必要参数：stock_data 或 entry_price",
                "strategy_id": self.strategy_id,
                "strategy_name": self.name
            }
        
        # 默认执行止损计算
        return self.calculate_stop_loss(stock_data, entry_price, **kwargs)
    
    def _determine_stop_loss(self, stock_data: Dict, entry_price: float, 
                           current_price: float, params: Dict) -> Dict[str, Any]:
        """确定止损价格和类型"""
        # 检查持仓数据
        position_data = stock_data.get("position_data", {})
        holding_days = position_data.get("holding_days", 0)
        highest_price = position_data.get("highest_price", entry_price)
        
        signals = []
        stop_price = entry_price
        stop_type = "initial"
        
        # 1. 优先使用技术面止损（如果启用）
        if params["use_technical_stop"] and "technical_support" in stock_data:
            support_price = stock_data["technical_support"]
            if support_price and support_price > 0 and support_price < entry_price:
                stop_price = support_price
                stop_type = "technical_support"
                signals.append(f"技术支撑位: ¥{support_price:.2f}")
        
        # 2. 如果启用移动止盈且已上涨超过启动幅度
        profit_pct = (current_price - entry_price) / entry_price
        if (params["trailing_stop_enabled"] and 
            profit_pct > params["trailing_start_pct"] and
            "highest_price" in position_data):
            
            highest_price = position_data["highest_price"]
            # 计算移动止损：从最高价回撤10%
            trailing_stop = highest_price * (1 - params["trailing_step_pct"])
            
            if trailing_stop > stop_price:
                stop_price = trailing_stop
                stop_type = "trailing_stop"
                signals.append(f"移动止损: ¥{trailing_stop:.2f} (从最高价¥{highest_price:.2f}回撤{params['trailing_step_pct']:.0%})")
        
        # 3. 如果启用保本止损且已上涨超过保本幅度
        if (params["break_even_enabled"] and 
            profit_pct > params["break_even_pct"]):
            
            break_even_price = entry_price * 1.001  # 略高于入场价，覆盖交易成本
            if break_even_price > stop_price:
                stop_price = break_even_price
                stop_type = "break_even"
                signals.append(f"保本止损: ¥{break_even_price:.2f}")
        
        # 4. 如果启用时间止损且持仓超过最大天数
        if (params["time_stop_enabled"] and 
            holding_days > params["max_holding_days"]):
            
            time_stop_type = "time_stop"
            signals.append(f"时间止损: 持仓{holding_days}天超过{params['max_holding_days']}天限制")
            # 时间止损不改变价格，但标记类型
        
        # 5. 如果以上都没有，使用默认百分比止损
        if stop_type == "initial":
            default_stop_distance = 0.05  # 默认5%
            stop_price = entry_price * (1 - default_stop_distance)
            stop_type = "default_5pct"
            signals.append(f"默认止损: {default_stop_distance:.0%}")
        
        return {
            "price": stop_price,
            "type": stop_type,
            "signals": signals
        }
    
    def _calculate_trailing_stop(self, stock_data: Dict, entry_price: float, 
                               current_price: float, params: Dict) -> float:
        """计算移动止损价格"""
        position_data = stock_data.get("position_data", {})
        highest_price = position_data.get("highest_price", entry_price)
        
        # 更新最高价
        if current_price > highest_price:
            highest_price = current_price
        
        # 计算移动止损：从最高价回撤指定步长
        trailing_stop = highest_price * (1 - params.get("trailing_step_pct", 0.1))
        
        # 移动止损不能低于初始止损
        initial_stop = entry_price * (1 - params.get("min_stop_distance", 0.03))
        trailing_stop = max(trailing_stop, initial_stop)
        
        return trailing_stop
    
    def _get_sector_adjustment(self, sector: str) -> float:
        """根据板块调整止损距离"""
        # 板块调整因子（基于历史波动性）
        sector_adjustments = {
            # 高波动板块：扩大止损距离
            "科技": 1.2,
            "电子": 1.2,
            "医药": 1.1,
            "新能源": 1.3,
            "半导体": 1.4,
            # 中波动板块：保持不变
            "消费": 1.0,
            "金融": 0.9,
            "地产": 0.9,
            "工业": 1.0,
            # 低波动板块：缩小止损距离
            "公用事业": 0.8,
            "能源": 0.9,
            "材料": 1.0
        }
        
        # 查找匹配的板块（支持模糊匹配）
        sector_lower = sector.lower()
        for key, adjustment in sector_adjustments.items():
            if key in sector_lower or sector_lower in key.lower():
                return adjustment
        
        # 默认调整因子
        return 1.0
    
    def _generate_explanation(self, entry_price: float, stop_loss_price: float, 
                            stop_type: str, stop_distance: float, r_value: float,
                            position_value: float, risk_amount: float, adjustments: List[str]) -> str:
        """生成计算说明"""
        explanations = []
        
        explanations.append(f"入场价: ¥{entry_price:.2f}")
        explanations.append(f"止损价: ¥{stop_loss_price:.2f} ({stop_type})")
        explanations.append(f"止损距离: {stop_distance:.1%}")
        explanations.append(f"R值: ¥{r_value:,.0f}")
        
        if position_value > 0:
            explanations.append(f"建议仓位: ¥{position_value:,.0f}")
            explanations.append(f"风险金额: ¥{risk_amount:,.0f}")
        
        if adjustments:
            explanations.append("调整: " + ", ".join(adjustments))
        
        return "；".join(explanations)