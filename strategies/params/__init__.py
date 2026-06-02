"""
策略参数管理模块

版本: v1.0.0
维护者: 小红 🌹
创建时间: 2026-04-10
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime


class ParameterManager:
    """策略参数管理器"""
    
    def __init__(self, params_dir: str = None):
        """
        初始化参数管理器
        
        Args:
            params_dir: 参数目录路径，如为None则使用默认路径
        """
        if params_dir is None:
            base_dir = Path(__file__).parent.parent.parent
            self.params_dir = base_dir / "params"
        else:
            self.params_dir = Path(params_dir)
        
        # 确保目录存在
        self.params_dir.mkdir(exist_ok=True)
        
        # 参数验证器注册表
        self.validators = {
            "integer": self._validate_integer,
            "float": self._validate_float,
            "boolean": self._validate_boolean,
            "string": self._validate_string,
            "enum": self._validate_enum,
        }
    
    def get_strategy_params(self, strategy_id: str) -> Dict[str, Any]:
        """
        获取策略参数
        
        Args:
            strategy_id: 策略ID（如 "SEL-001"）
            
        Returns:
            dict: 策略参数，如文件不存在则返回空字典
        """
        param_file = self.params_dir / f"{strategy_id}.json"
        
        if param_file.exists():
            try:
                with open(param_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                return {}
        return {}
    
    def save_strategy_params(self, strategy_id: str, params: Dict[str, Any]) -> bool:
        """
        保存策略参数
        
        Args:
            strategy_id: 策略ID
            params: 参数字典
            
        Returns:
            bool: 是否保存成功
        """
        try:
            # 添加元数据
            enriched_params = params.copy()
            enriched_params["_metadata"] = {
                "strategy_id": strategy_id,
                "last_updated": datetime.now().isoformat(),
                "version": "1.0.0"
            }
            
            param_file = self.params_dir / f"{strategy_id}.json"
            
            with open(param_file, 'w', encoding='utf-8') as f:
                json.dump(enriched_params, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"❌ 保存策略 {strategy_id} 参数失败: {e}")
            return False
    
    def update_strategy_params(self, strategy_id: str, updates: Dict[str, Any], 
                              schema: Dict[str, Dict] = None) -> Dict[str, Any]:
        """
        更新策略参数
        
        Args:
            strategy_id: 策略ID
            updates: 要更新的参数
            schema: 参数模式定义（用于验证）
            
        Returns:
            dict: 更新后的参数，如包含错误则返回错误信息
        """
        # 获取现有参数
        current_params = self.get_strategy_params(strategy_id)
        
        # 应用更新
        updated_params = current_params.copy()
        updated_params.update(updates)
        
        # 验证参数（如果提供了模式）
        if schema:
            errors = self.validate_parameters(updated_params, schema)
            if errors:
                return {
                    "success": False,
                    "errors": errors,
                    "current_params": current_params
                }
        
        # 保存更新后的参数
        if self.save_strategy_params(strategy_id, updated_params):
            return {
                "success": True,
                "updated_params": updated_params,
                "changes": updates
            }
        else:
            return {
                "success": False,
                "error": "保存失败",
                "current_params": current_params
            }
    
    def validate_parameters(self, params: Dict[str, Any], schema: Dict[str, Dict]) -> List[str]:
        """
        根据模式验证参数
        
        Args:
            params: 待验证的参数
            schema: 参数模式定义
            
        Returns:
            list: 错误消息列表（空列表表示验证通过）
        """
        errors = []
        
        for param_name, param_value in params.items():
            if param_name in schema:
                param_schema = schema[param_name]
                
                # 获取验证器
                validator_type = param_schema.get("type")
                if validator_type in self.validators:
                    error = self.validators[validator_type](param_name, param_value, param_schema)
                    if error:
                        errors.append(error)
        
        return errors
    
    def _validate_integer(self, name: str, value: Any, schema: Dict[str, Any]) -> str:
        """验证整数类型"""
        if not isinstance(value, int):
            return f"参数 {name} 应为整数类型"
        
        if "min" in schema and value < schema["min"]:
            return f"参数 {name} 不能小于 {schema['min']}"
        
        if "max" in schema and value > schema["max"]:
            return f"参数 {name} 不能大于 {schema['max']}"
        
        return ""
    
    def _validate_float(self, name: str, value: Any, schema: Dict[str, Any]) -> str:
        """验证浮点数类型"""
        if not isinstance(value, (int, float)):
            return f"参数 {name} 应为数值类型"
        
        if "min" in schema and value < schema["min"]:
            return f"参数 {name} 不能小于 {schema['min']}"
        
        if "max" in schema and value > schema["max"]:
            return f"参数 {name} 不能大于 {schema['max']}"
        
        return ""
    
    def _validate_boolean(self, name: str, value: Any, schema: Dict[str, Any]) -> str:
        """验证布尔类型"""
        if not isinstance(value, bool):
            return f"参数 {name} 应为布尔类型 (True/False)"
        return ""
    
    def _validate_string(self, name: str, value: Any, schema: Dict[str, Any]) -> str:
        """验证字符串类型"""
        if not isinstance(value, str):
            return f"参数 {name} 应为字符串类型"
        
        if "min_length" in schema and len(value) < schema["min_length"]:
            return f"参数 {name} 长度不能小于 {schema['min_length']}"
        
        if "max_length" in schema and len(value) > schema["max_length"]:
            return f"参数 {name} 长度不能大于 {schema['max_length']}"
        
        return ""
    
    def _validate_enum(self, name: str, value: Any, schema: Dict[str, Any]) -> str:
        """验证枚举类型"""
        if "enum" in schema and value not in schema["enum"]:
            return f"参数 {name} 必须是 {schema['enum']} 中的一个"
        return ""
    
    def list_all_strategies(self) -> List[str]:
        """
        列出所有有参数文件的策略
        
        Returns:
            list: 策略ID列表
        """
        strategies = []
        
        for file in self.params_dir.glob("*.json"):
            if file.stem.startswith("_") or file.stem.endswith("_performance"):
                continue
            
            strategies.append(file.stem)
        
        return sorted(strategies)
    
    def backup_all_params(self, backup_dir: str = None) -> Dict[str, Any]:
        """
        备份所有策略参数
        
        Args:
            backup_dir: 备份目录，如为None则创建时间戳目录
            
        Returns:
            dict: 备份结果
        """
        if backup_dir is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = self.params_dir.parent / "backups" / f"params_backup_{timestamp}"
        
        backup_path = Path(backup_dir)
        backup_path.mkdir(parents=True, exist_ok=True)
        
        backed_up = []
        errors = []
        
        for file in self.params_dir.glob("*.json"):
            try:
                # 读取参数
                with open(file, 'r', encoding='utf-8') as f:
                    params = json.load(f)
                
                # 保存到备份目录
                backup_file = backup_path / file.name
                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(params, f, ensure_ascii=False, indent=2)
                
                backed_up.append(file.stem)
            except Exception as e:
                errors.append(f"{file.stem}: {e}")
        
        return {
            "backup_dir": str(backup_path),
            "backed_up_count": len(backed_up),
            "backed_up_strategies": backed_up,
            "errors": errors,
            "success": len(errors) == 0
        }
    
    def restore_params(self, strategy_id: str, backup_file: str) -> bool:
        """
        从备份恢复策略参数
        
        Args:
            strategy_id: 策略ID
            backup_file: 备份文件路径
            
        Returns:
            bool: 是否恢复成功
        """
        try:
            # 读取备份
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_params = json.load(f)
            
            # 保存到当前参数目录
            param_file = self.params_dir / f"{strategy_id}.json"
            with open(param_file, 'w', encoding='utf-8') as f:
                json.dump(backup_params, f, ensure_ascii=False, indent=2)
            
            return True
        except Exception as e:
            print(f"❌ 恢复策略 {strategy_id} 参数失败: {e}")
            return False


# 全局参数管理器实例
_param_manager = None

def get_parameter_manager() -> ParameterManager:
    """获取全局参数管理器实例"""
    global _param_manager
    if _param_manager is None:
        _param_manager = ParameterManager()
    return _param_manager


# 测试代码
if __name__ == "__main__":
    manager = ParameterManager()
    
    print("🔧 策略参数管理器测试")
    print(f"参数目录: {manager.params_dir}")
    print(f"目录存在: {manager.params_dir.exists()}")
    
    # 测试保存和读取
    test_params = {
        "strategy_id": "TEST-001",
        "name": "测试策略",
        "enabled": True,
        "weight": 1.0,
        "test_param": 100
    }
    
    # 保存测试参数
    success = manager.save_strategy_params("TEST-001", test_params)
    print(f"保存测试参数: {'✅ 成功' if success else '❌ 失败'}")
    
    # 读取测试参数
    loaded_params = manager.get_strategy_params("TEST-001")
    print(f"读取测试参数: {len(loaded_params)} 个参数")
    
    # 列出所有策略
    strategies = manager.list_all_strategies()
    print(f"所有策略: {strategies}")
    
    # 验证测试
    test_schema = {
        "enabled": {"type": "boolean", "default": True},
        "weight": {"type": "float", "default": 1.0, "min": 0.0, "max": 10.0},
        "test_param": {"type": "integer", "default": 100, "min": 0, "max": 1000}
    }
    
    errors = manager.validate_parameters(test_params, test_schema)
    print(f"参数验证: {'✅ 通过' if not errors else f'❌ 失败: {errors}'}")
    
    print("\n✅ 参数管理器测试完成")