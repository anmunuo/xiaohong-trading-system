"""
策略基类 - 所有策略的基类

版本: v1.0
维护者: 小红 🌹
创建时间: 2026-04-10
"""

import json
import os
import inspect
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
import pandas as pd

# ========== 配置加载 ==========
# Hermes 环境: Tushare token 从环境变量或 data_pipeline 获取
# 兼容旧 global config（如果存在）
try:
    # 尝试旧路径
    global_scripts = Path(__file__).resolve().parent.parent.parent / 'global' / 'global' / 'scripts'
    if str(global_scripts) not in sys.path and global_scripts.exists():
        sys.path.insert(0, str(global_scripts))
    from config_loader import get_config, get_tushare_token, get_feishu_app_info
    config = get_config()
    TUSHARE_TOKEN = get_tushare_token()
except:
    # Hermes 降级模式
    config = None
    TUSHARE_TOKEN = os.environ.get('TUSHARE_TOKEN', '')


class BaseStrategy(ABC):
    """
    策略基类 - 所有策略必须继承此类
    
    设计原则:
    1. 单一职责: 每个策略只做一件事
    2. 参数化: 所有参数可配置
    3. 可验证: 策略效果可量化
    4. 可组合: 策略可灵活组合
    5. 可进化: 策略参数可优化
    """
    
    def __init__(self, strategy_id: str, name: str, category: str, version: str = "1.0.0"):
        """
        初始化策略
        
        Args:
            strategy_id: 策略ID（如 "SEL-001"）
            name: 策略名称
            category: 策略类别
            version: 策略版本
        """
        self.strategy_id = strategy_id
        self.name = name
        self.category = category
        self.version = version
        
        # 参数管理
        self.parameters = self.default_parameters()
        self.performance = {}
        
        # 路径配置
        self.strategies_dir = Path(__file__).parent.parent
        self.params_dir = self.strategies_dir / "params"
        self.params_dir.mkdir(exist_ok=True)
        
        # 性能记录
        self.performance_dir = self.strategies_dir / "performance"
        self.performance_dir.mkdir(exist_ok=True)
        
        # 加载配置
        self.load_parameters()
        self.load_performance()
    
    def default_parameters(self) -> Dict[str, Any]:
        """
        默认参数 - 子类必须覆盖
        
        Returns:
            dict: 默认参数
        """
        return {
            "enabled": True,
            "weight": 1.0,  # 策略权重（组合策略使用）
            "description": self.name,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    
    def parameter_schema(self) -> Dict[str, Dict]:
        """
        参数模式定义 - 子类可选覆盖
        
        Returns:
            dict: 参数模式定义
        """
        return {
            "enabled": {
                "type": "boolean",
                "default": True,
                "description": "是否启用策略"
            },
            "weight": {
                "type": "float",
                "default": 1.0,
                "min": 0.0,
                "max": 10.0,
                "description": "策略权重"
            }
        }
    
    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行策略 - 子类必须实现
        
        Args:
            **kwargs: 策略输入参数
            
        Returns:
            dict: 策略输出结果
        """
        pass
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> List[str]:
        """
        验证参数
        
        Args:
            parameters: 待验证的参数
            
        Returns:
            list: 错误消息列表（空列表表示验证通过）
        """
        errors = []
        schema = self.parameter_schema()
        
        for param_name, param_value in parameters.items():
            if param_name in schema:
                param_schema = schema[param_name]
                
                # 类型检查
                expected_type = param_schema.get("type")
                if expected_type == "boolean" and not isinstance(param_value, bool):
                    errors.append(f"参数 {param_name} 应为布尔类型")
                elif expected_type == "float" and not isinstance(param_value, (int, float)):
                    errors.append(f"参数 {param_name} 应为数值类型")
                elif expected_type == "integer" and not isinstance(param_value, int):
                    errors.append(f"参数 {param_name} 应为整数类型")
                elif expected_type == "string" and not isinstance(param_value, str):
                    errors.append(f"参数 {param_name} 应为字符串类型")
                
                # 范围检查
                if "min" in param_schema and param_value < param_schema["min"]:
                    errors.append(f"参数 {param_name} 不能小于 {param_schema['min']}")
                if "max" in param_schema and param_value > param_schema["max"]:
                    errors.append(f"参数 {param_name} 不能大于 {param_schema['max']}")
                
                # 枚举检查
                if "enum" in param_schema and param_value not in param_schema["enum"]:
                    errors.append(f"参数 {param_name} 必须是 {param_schema['enum']} 中的一个")
        
        return errors
    
    def load_parameters(self):
        """加载参数"""
        param_file = self.params_dir / f"{self.strategy_id}.json"
        
        if param_file.exists():
            try:
                with open(param_file, 'r', encoding='utf-8') as f:
                    saved_params = json.load(f)
                
                # 合并参数（保存的优先，默认值补充）
                for key, value in saved_params.items():
                    self.parameters[key] = value
                
                # 验证参数
                errors = self.validate_parameters(self.parameters)
                if errors:
                    print(f"⚠️  策略 {self.strategy_id} 参数验证警告:")
                    for error in errors:
                        print(f"    - {error}")
                
            except Exception as e:
                print(f"❌ 加载策略 {self.strategy_id} 参数失败: {e}")
                # 使用默认参数
        else:
            # 保存默认参数
            self.save_parameters()
    
    def save_parameters(self):
        """保存参数"""
        param_file = self.params_dir / f"{self.strategy_id}.json"
        
        try:
            # 更新更新时间
            self.parameters["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(param_file, 'w', encoding='utf-8') as f:
                json.dump(self.parameters, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 策略 {self.strategy_id} 参数已保存: {param_file}")
        except Exception as e:
            print(f"❌ 保存策略 {self.strategy_id} 参数失败: {e}")
    
    def update_parameters(self, new_parameters: Dict[str, Any]):
        """
        更新参数
        
        Args:
            new_parameters: 新参数
            
        Returns:
            bool: 是否更新成功
        """
        # 验证新参数
        errors = self.validate_parameters(new_parameters)
        if errors:
            print(f"❌ 策略 {self.strategy_id} 参数验证失败:")
            for error in errors:
                print(f"    - {error}")
            return False
        
        # 更新参数
        self.parameters.update(new_parameters)
        self.save_parameters()
        return True
    
    def load_performance(self):
        """加载性能数据"""
        perf_file = self.performance_dir / f"{self.strategy_id}_performance.json"
        
        if perf_file.exists():
            try:
                with open(perf_file, 'r', encoding='utf-8') as f:
                    self.performance = json.load(f)
            except:
                self.performance = {}
        else:
            self.performance = {
                "total_executions": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_profit": 0.0,
                "total_loss": 0.0,
                "accuracy": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "execution_log": []
            }
    
    def save_performance(self):
        """保存性能数据"""
        perf_file = self.performance_dir / f"{self.strategy_id}_performance.json"
        
        try:
            with open(perf_file, 'w', encoding='utf-8') as f:
                json.dump(self.performance, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存策略 {self.strategy_id} 性能数据失败: {e}")
    
    def record_execution(self, result: Dict[str, Any], success: bool = True):
        """
        记录执行结果
        
        Args:
            result: 执行结果
            success: 是否成功
        """
        # 确保性能字典有所有必要的键
        if not self.performance:
            self.performance = {
                "total_executions": 0,
                "success_count": 0,
                "failure_count": 0,
                "total_profit": 0.0,
                "total_loss": 0.0,
                "accuracy": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "execution_log": []
            }
        
        # 确保所有必要的键都存在
        required_keys = ["total_executions", "success_count", "failure_count", 
                        "total_profit", "total_loss", "accuracy", "execution_log"]
        for key in required_keys:
            if key not in self.performance:
                if key == "execution_log":
                    self.performance[key] = []
                elif key in ["total_profit", "total_loss", "accuracy"]:
                    self.performance[key] = 0.0
                else:
                    self.performance[key] = 0
        
        # 更新统计
        self.performance["total_executions"] += 1
        
        if success:
            self.performance["success_count"] += 1
            if "profit" in result:
                self.performance["total_profit"] += result["profit"]
        else:
            self.performance["failure_count"] += 1
            if "loss" in result:
                self.performance["total_loss"] += result["loss"]
        
        # 计算准确率
        if self.performance["total_executions"] > 0:
            self.performance["accuracy"] = (
                self.performance["success_count"] / self.performance["total_executions"]
            )
        
        # 记录执行日志
        execution_log = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "strategy_id": self.strategy_id,
            "success": success,
            "result": result
        }
        
        self.performance["execution_log"].append(execution_log)
        
        # 限制日志长度
        if len(self.performance["execution_log"]) > 1000:
            self.performance["execution_log"] = self.performance["execution_log"][-1000:]
        
        # 保存
        self.save_performance()
    
    def get_performance_report(self) -> Dict[str, Any]:
        """
        获取性能报告
        
        Returns:
            dict: 性能报告
        """
        report = {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "category": self.category,
            "version": self.version,
            "parameters": self.parameters,
            "performance_summary": {
                "total_executions": self.performance.get("total_executions", 0),
                "success_count": self.performance.get("success_count", 0),
                "failure_count": self.performance.get("failure_count", 0),
                "accuracy": self.performance.get("accuracy", 0.0),
                "total_profit": self.performance.get("total_profit", 0.0),
                "total_loss": self.performance.get("total_loss", 0.0),
                "net_profit": self.performance.get("total_profit", 0.0) - self.performance.get("total_loss", 0.0)
            },
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return report
    
    def backtest(self, historical_data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        回测策略
        
        Args:
            historical_data: 历史数据
            **kwargs: 回测参数
            
        Returns:
            dict: 回测结果
        """
        print(f"🔍 开始回测策略 {self.strategy_id} ({self.name})")
        
        try:
            # 执行回测（子类可覆盖此方法）
            result = self._execute_backtest(historical_data, **kwargs)
            
            # 记录回测结果
            self.record_execution(result, success=True)
            
            print(f"✅ 策略 {self.strategy_id} 回测完成")
            return result
            
        except Exception as e:
            error_result = {
                "error": str(e),
                "success": False
            }
            self.record_execution(error_result, success=False)
            
            print(f"❌ 策略 {self.strategy_id} 回测失败: {e}")
            return error_result
    
    def _execute_backtest(self, historical_data: pd.DataFrame, **kwargs) -> Dict[str, Any]:
        """
        执行回测 - 子类可覆盖
        
        Args:
            historical_data: 历史数据
            **kwargs: 回测参数
            
        Returns:
            dict: 回测结果
        """
        # 默认实现：简单遍历执行
        results = []
        
        for i in range(len(historical_data)):
            data_slice = historical_data.iloc[:i+1]
            
            try:
                result = self.execute(data=data_slice, **kwargs)
                results.append(result)
            except Exception as e:
                results.append({"error": str(e), "success": False})
        
        # 汇总结果
        successful = [r for r in results if r.get("success", False)]
        
        return {
            "total_trades": len(results),
            "successful_trades": len(successful),
            "success_rate": len(successful) / len(results) if results else 0.0,
            "results": results[:10],  # 只返回前10条结果
            "success": True
        }
    
    def optimize(self, historical_data: pd.DataFrame, param_ranges: Dict[str, List], **kwargs) -> Dict[str, Any]:
        """
        优化策略参数
        
        Args:
            historical_data: 历史数据
            param_ranges: 参数范围 {参数名: [最小值, 最大值]}
            **kwargs: 优化参数
            
        Returns:
            dict: 优化结果
        """
        print(f"🔧 开始优化策略 {self.strategy_id} ({self.name})")
        
        try:
            # 简单网格搜索（子类可覆盖）
            best_params = self.parameters.copy()
            best_score = -float('inf')
            
            # 这里实现简单的参数优化逻辑
            # 实际应用中可以使用更高级的优化算法
            
            result = {
                "best_parameters": best_params,
                "best_score": best_score,
                "optimization_method": "grid_search",
                "iterations": 1,
                "success": True
            }
            
            print(f"✅ 策略 {self.strategy_id} 优化完成")
            return result
            
        except Exception as e:
            print(f"❌ 策略 {self.strategy_id} 优化失败: {e}")
            return {
                "error": str(e),
                "success": False
            }
    
    def __str__(self):
        """字符串表示"""
        return f"{self.strategy_id}: {self.name} (v{self.version})"
    
    def __repr__(self):
        """repr表示"""
        return f"<{self.__class__.__name__} {self.strategy_id} at {hex(id(self))}>"


class SelectionStrategy(BaseStrategy):
    """选股策略基类"""
    
    @abstractmethod
    def select(self, stock_pool: List[Dict], **kwargs) -> List[Dict]:
        """
        选股 - 子类必须实现
        
        Args:
            stock_pool: 股票池
            **kwargs: 选股参数
            
        Returns:
            list: 选中的股票列表
        """
        pass


class EntryStrategy(BaseStrategy):
    """入场策略基类"""
    
    @abstractmethod
    def should_enter(self, stock_data: Dict, **kwargs) -> Dict[str, Any]:
        """
        判断是否应该入场 - 子类必须实现
        
        Args:
            stock_data: 股票数据
            **kwargs: 入场参数
            
        Returns:
            dict: 入场决策
        """
        pass


class PositionStrategy(BaseStrategy):
    """仓位管理策略基类"""
    
    @abstractmethod
    def calculate_position(self, stock_data: Dict, net_value: float, **kwargs) -> Dict[str, Any]:
        """
        计算仓位 - 子类必须实现
        
        Args:
            stock_data: 股票数据
            net_value: 净值
            **kwargs: 仓位参数
            
        Returns:
            dict: 仓位计算结果
        """
        pass


class StopStrategy(BaseStrategy):
    """止损止盈策略基类"""
    
    @abstractmethod
    def calculate_stop_loss(self, stock_data: Dict, entry_price: float, **kwargs) -> Dict[str, Any]:
        """
        计算止损位 - 子类必须实现
        
        Args:
            stock_data: 股票数据
            entry_price: 入场价格
            **kwargs: 止损参数
            
        Returns:
            dict: 止损计算结果
        """
        pass
    
    @abstractmethod
    def calculate_take_profit(self, stock_data: Dict, entry_price: float, **kwargs) -> Dict[str, Any]:
        """
        计算止盈位 - 子类必须实现
        
        Args:
            stock_data: 股票数据
            entry_price: 入场价格
            **kwargs: 止盈参数
            
        Returns:
            dict: 止盈计算结果
        """
        pass


class ExitStrategy(BaseStrategy):
    """出场策略基类"""
    
    @abstractmethod
    def should_exit(self, position_data: Dict, **kwargs) -> Dict[str, Any]:
        """
        判断是否应该出场 - 子类必须实现
        
        Args:
            position_data: 持仓数据
            **kwargs: 出场参数
            
        Returns:
            dict: 出场决策
        """
        pass


class CompositeStrategy(BaseStrategy):
    """组合策略基类"""
    
    def __init__(self, strategy_id: str, name: str, version: str = "1.0.0"):
        super().__init__(strategy_id, name, "composite", version)
        self.component_strategies = []
    
    def add_strategy(self, strategy: BaseStrategy, weight: float = 1.0):
        """
        添加组件策略
        
        Args:
            strategy: 组件策略
            weight: 策略权重
        """
        self.component_strategies.append({
            "strategy": strategy,
            "weight": weight
        })
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        执行组合策略
        
        Args:
            **kwargs: 策略输入参数
            
        Returns:
            dict: 组合策略输出结果
        """
        results = []
        total_weight = sum(s["weight"] for s in self.component_strategies)
        
        for component in self.component_strategies:
            strategy = component["strategy"]
            weight = component["weight"]
            
            try:
                result = strategy.execute(**kwargs)
                result["weight"] = weight
                result["weighted_score"] = result.get("score", 0) * (weight / total_weight)
                results.append(result)
            except Exception as e:
                results.append({
                    "strategy_id": strategy.strategy_id,
                    "error": str(e),
                    "success": False,
                    "weight": weight,
                    "weighted_score": 0
                })
        
        # 汇总结果
        successful = [r for r in results if r.get("success", False)]
        total_score = sum(r.get("weighted_score", 0) for r in successful)
        
        return {
            "component_results": results,
            "total_score": total_score,
            "success_rate": len(successful) / len(results) if results else 0.0,
            "success": len(successful) > 0
        }