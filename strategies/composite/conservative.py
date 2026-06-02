"""
保守组合策略

策略ID: CMP-001
策略名称: 保守组合策略
策略类别: 组合策略
版本: v1.0.0

策略描述:
保守型策略组合，适合低风险偏好的投资者
包含：趋势跟随选股 + R值仓位管理 + R值止损止盈

维护者: 小红 🌹
创建时间: 2026-04-10
"""

from typing import Dict, Any, List
from datetime import datetime

from ..base import CompositeStrategy
from ..selection.trend_following import TrendFollowingStrategy
from ..position.r_value_risk import RValueRiskStrategy
from ..stop.r_value_stop import RValueStopStrategy


class ConservativeCompositeStrategy(CompositeStrategy):
    """保守组合策略"""
    
    def __init__(self):
        super().__init__(
            strategy_id="CMP-001",
            name="保守组合策略",
            version="1.0.0"
        )
        
        # 初始化组件策略
        self._initialize_components()
    
    def _initialize_components(self):
        """初始化组件策略"""
        # 1. 趋势跟随选股策略（权重：40%）
        trend_strategy = TrendFollowingStrategy()
        self.add_strategy(trend_strategy, weight=0.4)
        
        # 2. R值仓位管理策略（权重：30%）
        position_strategy = RValueRiskStrategy()
        self.add_strategy(position_strategy, weight=0.3)
        
        # 3. R值止损止盈策略（权重：30%）
        stop_strategy = RValueStopStrategy()
        self.add_strategy(stop_strategy, weight=0.3)
    
    def default_parameters(self) -> Dict[str, Any]:
        """默认参数"""
        params = super().default_parameters()
        params.update({
            "risk_level": "low",  # 风险等级：low/moderate/high
            "max_positions": 3,  # 最大持仓数
            "max_position_pct": 0.333,  # 单股最大仓位
            "min_cash_ratio": 0.2,  # 最小现金比例
            "rebalance_frequency": "weekly",  # 再平衡频率
            "performance_threshold": 0.6,  # 绩效阈值（低于此值触发调整）
            "component_weights": {
                "selection": 0.4,
                "position": 0.3,
                "stop": 0.3
            }
        })
        return params
    
    def parameter_schema(self) -> Dict[str, Dict]:
        """参数模式定义"""
        schema = super().parameter_schema()
        schema.update({
            "risk_level": {
                "type": "enum",
                "default": "low",
                "enum": ["low", "moderate", "high"],
                "description": "风险等级"
            },
            "max_positions": {
                "type": "integer",
                "default": 3,
                "min": 1,
                "max": 10,
                "description": "最大持仓数"
            },
            "max_position_pct": {
                "type": "float",
                "default": 0.333,
                "min": 0.1,
                "max": 1.0,
                "description": "单股最大仓位"
            },
            "min_cash_ratio": {
                "type": "float",
                "default": 0.2,
                "min": 0.05,
                "max": 0.5,
                "description": "最小现金比例"
            },
            "rebalance_frequency": {
                "type": "enum",
                "default": "weekly",
                "enum": ["daily", "weekly", "monthly", "quarterly"],
                "description": "再平衡频率"
            },
            "performance_threshold": {
                "type": "float",
                "default": 0.6,
                "min": 0.0,
                "max": 1.0,
                "description": "绩效阈值"
            }
        })
        return schema
    
    def execute_full_pipeline(self, stock_pool: List[Dict], net_value: float, **kwargs) -> Dict[str, Any]:
        """
        执行完整策略流水线
        
        Args:
            stock_pool: 股票池
            net_value: 净值
            
            **kwargs: 其他参数
            
        Returns:
            dict: 完整策略结果
        """
        # 记录开始时间
        start_time = datetime.now()
        
        try:
            # 1. 选股阶段
            selection_result = self._execute_selection(stock_pool, **kwargs)
            
            if not selection_result["success"] or not selection_result["selected_stocks"]:
                return {
                    "success": False,
                    "error": "选股阶段无结果",
                    "pipeline_stage": "selection"
                }
            
            # 2. 对每只选中的股票执行仓位和止损计算
            detailed_results = []
            for stock in selection_result["selected_stocks"][:self.parameters.get("max_positions", 3)]:
                stock_result = self._process_single_stock(stock, net_value, **kwargs)
                detailed_results.append(stock_result)
            
            # 3. 生成综合建议
            recommendation = self._generate_recommendation(detailed_results, net_value)
            
            # 记录执行结果
            execution_result = {
                "success": True,
                "pipeline_executed": True,
                "selection_result": selection_result,
                "detailed_results": detailed_results,
                "recommendation": recommendation,
                "execution_time": (datetime.now() - start_time).total_seconds(),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            self.record_execution(execution_result, success=True)
            
            return execution_result
            
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "execution_time": (datetime.now() - start_time).total_seconds(),
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            self.record_execution(error_result, success=False)
            return error_result
    
    def _execute_selection(self, stock_pool: List[Dict], **kwargs) -> Dict[str, Any]:
        """执行选股阶段"""
        # 获取选股策略
        selection_strategy = None
        for component in self.component_strategies:
            if component["strategy"].category == "selection":
                selection_strategy = component["strategy"]
                break
        
        if not selection_strategy:
            return {
                "success": False,
                "error": "未找到选股策略",
                "selected_stocks": []
            }
        
        # 执行选股 - 使用 execute 方法，它返回标准格式
        try:
            result = selection_strategy.execute(stock_pool=stock_pool, **kwargs)
            return result
        except Exception as e:
            return {
                "success": False,
                "error": f"选股策略执行失败: {e}",
                "selected_stocks": []
            }
    
    def _process_single_stock(self, stock: Dict, net_value: float, **kwargs) -> Dict[str, Any]:
        """处理单只股票（仓位+止损计算）"""
        result = {
            "stock_info": {
                "code": stock.get("code"),
                "name": stock.get("name"),
                "current_price": stock.get("current_price", 0)
            },
            "position_calculation": None,
            "stop_loss_calculation": None,
            "composite_score": 0
        }
        
        # 1. 仓位计算
        position_strategy = None
        for component in self.component_strategies:
            if component["strategy"].category == "position":
                position_strategy = component["strategy"]
                break
        
        if position_strategy:
            position_result = position_strategy.calculate_position(stock, net_value, **kwargs)
            result["position_calculation"] = position_result
            
            if position_result.get("success", False):
                result["composite_score"] += 30  # 仓位计算占30分
        
        # 2. 止损计算
        stop_strategy = None
        for component in self.component_strategies:
            if component["strategy"].category == "stop":
                stop_strategy = component["strategy"]
                break
        
        if stop_strategy and "entry_price" in stock:
            stop_result = stop_strategy.calculate_stop_loss(stock, stock["entry_price"], **kwargs)
            result["stop_loss_calculation"] = stop_result
            
            if stop_result.get("success", False):
                result["composite_score"] += 30  # 止损计算占30分
        
        # 3. 选股评分（已包含在stock中）
        if "score" in stock:
            result["composite_score"] += stock["score"] * 0.4  # 选股评分占40分
        
        return result
    
    def _generate_recommendation(self, detailed_results: List[Dict], net_value: float) -> Dict[str, Any]:
        """生成综合建议"""
        # 过滤有效结果
        valid_results = []
        for result in detailed_results:
            if (result["position_calculation"] and result["position_calculation"].get("success") and
                result["stop_loss_calculation"] and result["stop_loss_calculation"].get("success")):
                valid_results.append(result)
        
        if not valid_results:
            return {
                "recommendation": "暂无推荐",
                "reason": "无符合条件的股票",
                "suggested_action": "等待更好的机会"
            }
        
        # 按综合评分排序
        valid_results.sort(key=lambda x: x["composite_score"], reverse=True)
        
        # 计算建议仓位
        total_position_value = 0
        positions = []
        
        for result in valid_results:
            position_info = result["position_calculation"]
            stop_info = result["stop_loss_calculation"]
            
            position = {
                "code": result["stock_info"]["code"],
                "name": result["stock_info"]["name"],
                "entry_price": position_info["entry_price"],
                "position_value": position_info["position_value"],
                "shares": position_info["shares"],
                "position_pct": position_info["position_pct"],
                "stop_loss_price": stop_info["stop_loss_price"],
                "take_profit_price": stop_info.get("take_profit_price", 0),
                "composite_score": result["composite_score"],
                "risk_amount": position_info["risk_amount"]
            }
            
            positions.append(position)
            total_position_value += position_info["position_value"]
        
        # 生成建议
        total_position_pct = total_position_value / net_value
        
        if total_position_pct < 0.3:
            action = "可分批建仓"
            confidence = "高"
        elif total_position_pct < 0.6:
            action = "谨慎建仓"
            confidence = "中"
        else:
            action = "等待回调"
            confidence = "低"
        
        return {
            "recommendation": action,
            "confidence": confidence,
            "total_position_value": total_position_value,
            "total_position_pct": total_position_pct,
            "suggested_positions": positions,
            "position_count": len(positions),
            "top_stock": positions[0] if positions else None,
            "max_positions_reached": len(positions) >= self.parameters.get("max_positions", 3)
        }
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行策略（兼容基类接口）
        
        Args:
            **kwargs: 策略输入参数，必须包含：
                - stock_pool: 股票池
                - net_value: 净值
            
        Returns:
            dict: 策略输出结果
        """
        stock_pool = kwargs.get("stock_pool")
        net_value = kwargs.get("net_value")
        
        if stock_pool is None or net_value is None:
            return {
                "success": False,
                "error": "缺少必要参数：stock_pool 或 net_value",
                "strategy_id": self.strategy_id,
                "strategy_name": self.name
            }
        
        # 从 kwargs 中删除已提取的参数，避免重复传递
        filtered_kwargs = kwargs.copy()
        filtered_kwargs.pop("stock_pool", None)
        filtered_kwargs.pop("net_value", None)
        
        return self.execute_full_pipeline(stock_pool, net_value, **filtered_kwargs)


# 测试代码
if __name__ == "__main__":
    # 创建策略实例
    strategy = ConservativeCompositeStrategy()
    
    # 打印策略信息
    print(f"策略ID: {strategy.strategy_id}")
    print(f"策略名称: {strategy.name}")
    print(f"策略版本: {strategy.version}")
    print(f"组件策略: {len(strategy.component_strategies)} 个")
    
    for i, component in enumerate(strategy.component_strategies, 1):
        comp_strategy = component["strategy"]
        weight = component["weight"]
        print(f"  {i}. {comp_strategy.strategy_id}: {comp_strategy.name} (权重: {weight:.0%})")
    
    # 获取性能报告
    report = strategy.get_performance_report()
    print(f"\n性能报告:")
    print(f"总执行次数: {report['performance_summary']['total_executions']}")
    print(f"风险等级: {strategy.parameters.get('risk_level', 'unknown')}")
    
    print(f"\n✅ 保守组合策略加载成功")