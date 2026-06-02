"""
策略管理器

版本: v1.0.0
维护者: 小红 🌹
创建时间: 2026-04-10

功能:
1. 策略加载和初始化
2. 策略参数管理
3. 策略执行和测试
4. 策略绩效跟踪
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List
from datetime import datetime

# 添加策略库路径
STRATEGIES_DIR = Path(__file__).parent
sys.path.insert(0, str(STRATEGIES_DIR.parent))

from strategies import list_strategies, get_strategy, validate_all_strategies
from strategies.params import get_parameter_manager


class StrategyManager:
    """策略管理器"""
    
    def __init__(self):
        self.strategies_dir = STRATEGIES_DIR
        self.params_manager = get_parameter_manager()
        
        # 策略缓存
        self.strategy_cache = {}
    
    def load_strategy(self, strategy_id: str) -> Any:
        """
        加载策略
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            策略实例
        """
        if strategy_id in self.strategy_cache:
            return self.strategy_cache[strategy_id]
        
        try:
            strategy = get_strategy(strategy_id)
            self.strategy_cache[strategy_id] = strategy
            return strategy
        except Exception as e:
            print(f"❌ 加载策略 {strategy_id} 失败: {e}")
            return None
    
    def list_available_strategies(self) -> Dict[str, List]:
        """
        列出所有可用策略
        
        Returns:
            dict: 按类别分类的策略列表
        """
        return list_strategies()
    
    def execute_strategy(self, strategy_id: str, **kwargs) -> Dict[str, Any]:
        """
        执行策略
        
        Args:
            strategy_id: 策略ID
            **kwargs: 策略参数
            
        Returns:
            dict: 执行结果
        """
        strategy = self.load_strategy(strategy_id)
        
        if not strategy:
            return {
                "success": False,
                "error": f"策略 {strategy_id} 加载失败",
                "strategy_id": strategy_id
            }
        
        print(f"🚀 执行策略: {strategy.name} ({strategy_id})")
        
        try:
            result = strategy.execute(**kwargs)
            return {
                "success": True,
                "strategy_id": strategy_id,
                "strategy_name": strategy.name,
                "result": result,
                "execution_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            error_result = {
                "success": False,
                "error": str(e),
                "strategy_id": strategy_id,
                "strategy_name": strategy.name,
                "execution_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            return error_result
    
    def test_all_strategies(self) -> Dict[str, Any]:
        """
        测试所有策略
        
        Returns:
            dict: 测试结果
        """
        print("🧪 开始测试所有策略...")
        
        strategies = self.list_available_strategies()
        test_results = {}
        
        for category, strategy_list in strategies.items():
            print(f"\n📂 测试类别: {category}")
            test_results[category] = []
            
            for strategy_name in strategy_list:
                # 尝试从策略名推断策略ID
                strategy_id = self._infer_strategy_id(strategy_name, category)
                
                if strategy_id:
                    strategy = self.load_strategy(strategy_id)
                    
                    if strategy:
                        test_results[category].append({
                            "strategy_id": strategy_id,
                            "name": strategy.name,
                            "status": "✅ 加载成功",
                            "parameters": strategy.parameters.get("enabled", False)
                        })
                    else:
                        test_results[category].append({
                            "strategy_name": strategy_name,
                            "status": "❌ 加载失败",
                            "error": "无法实例化策略"
                        })
                else:
                    test_results[category].append({
                        "strategy_name": strategy_name,
                        "status": "⚠️  未实现",
                        "error": "无对应策略ID"
                    })
        
        return test_results
    
    def _infer_strategy_id(self, strategy_name: str, category: str) -> str:
        """从策略名推断策略ID"""
        category_prefix = {
            "selection": "SEL",
            "entry": "ENT", 
            "position": "POS",
            "stop": "STP",
            "exit": "EXT",
            "composite": "CMP"
        }
        
        prefix = category_prefix.get(category, "UNK")
        
        # 已知策略映射
        strategy_map = {
            "trend_following": "001",
            "r_value_risk": "002",
            "r_value_stop": "001",
            "conservative": "001"
        }
        
        suffix = strategy_map.get(strategy_name, "001")
        
        return f"{prefix}-{suffix}"
    
    def get_strategy_performance(self, strategy_id: str) -> Dict[str, Any]:
        """
        获取策略性能报告
        
        Args:
            strategy_id: 策略ID
            
        Returns:
            dict: 性能报告
        """
        strategy = self.load_strategy(strategy_id)
        
        if not strategy:
            return {
                "success": False,
                "error": f"策略 {strategy_id} 未找到"
            }
        
        return strategy.get_performance_report()
    
    def update_strategy_parameters(self, strategy_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """
        更新策略参数
        
        Args:
            strategy_id: 策略ID
            updates: 参数更新
            
        Returns:
            dict: 更新结果
        """
        strategy = self.load_strategy(strategy_id)
        
        if not strategy:
            return {
                "success": False,
                "error": f"策略 {strategy_id} 未找到"
            }
        
        return strategy.update_parameters(updates)
    
    def create_strategy_report(self) -> Dict[str, Any]:
        """
        创建策略库报告
        
        Returns:
            dict: 综合报告
        """
        print("📊 生成策略库报告...")
        
        # 列出所有策略
        strategies = self.list_available_strategies()
        
        # 测试所有策略
        test_results = self.test_all_strategies()
        
        # 统计信息
        total_strategies = 0
        loaded_strategies = 0
        enabled_strategies = 0
        
        for category, results in test_results.items():
            for result in results:
                total_strategies += 1
                if result.get("status") == "✅ 加载成功":
                    loaded_strategies += 1
                if result.get("parameters") is True:
                    enabled_strategies += 1
        
        # 参数文件统计
        param_strategies = self.params_manager.list_all_strategies()
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "summary": {
                "total_strategies_defined": total_strategies,
                "strategies_loaded": loaded_strategies,
                "strategies_enabled": enabled_strategies,
                "strategies_with_params": len(param_strategies),
                "load_rate": loaded_strategies / total_strategies if total_strategies > 0 else 0,
                "enable_rate": enabled_strategies / total_strategies if total_strategies > 0 else 0
            },
            "categories": strategies,
            "test_results": test_results,
            "parameters_available": param_strategies,
            "recommendations": self._generate_recommendations(total_strategies, loaded_strategies, enabled_strategies)
        }
        
        return report
    
    def _generate_recommendations(self, total: int, loaded: int, enabled: int) -> List[str]:
        """生成建议"""
        recommendations = []
        
        if loaded < total:
            recommendations.append(f"建议实现剩余的 {total - loaded} 个策略")
        
        if enabled < loaded:
            recommendations.append(f"建议启用 {loaded - enabled} 个已加载但未启用的策略")
        
        if loaded > 0 and enabled > 0:
            recommendations.append("建议进行策略回测以验证效果")
        
        if not recommendations:
            recommendations.append("策略库状态良好，建议开始实盘测试")
        
        return recommendations
    
    def save_report(self, report: Dict[str, Any], filepath: str = None) -> str:
        """
        保存报告到文件
        
        Args:
            report: 报告数据
            filepath: 文件路径，如为None则自动生成
            
        Returns:
            str: 保存的文件路径
        """
        if filepath is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            reports_dir = self.strategies_dir.parent / "reports"
            reports_dir.mkdir(exist_ok=True)
            filepath = reports_dir / f"strategy_report_{timestamp}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        print(f"📄 报告已保存: {filepath}")
        return str(filepath)


# 命令行接口
def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="策略管理器")
    parser.add_argument("--list", action="store_true", help="列出所有策略")
    parser.add_argument("--test", action="store_true", help="测试所有策略")
    parser.add_argument("--report", action="store_true", help="生成策略报告")
    parser.add_argument("--strategy", help="指定策略ID")
    parser.add_argument("--execute", action="store_true", help="执行策略（需配合--strategy）")
    parser.add_argument("--performance", action="store_true", help="查看策略性能（需配合--strategy）")
    
    args = parser.parse_args()
    
    manager = StrategyManager()
    
    if args.list:
        strategies = manager.list_available_strategies()
        print("📚 可用策略列表:")
        for category, strategy_list in strategies.items():
            print(f"\n{category.upper()}:")
            for strategy in strategy_list:
                print(f"  - {strategy}")
    
    if args.test:
        results = manager.test_all_strategies()
        print("\n🧪 策略测试结果:")
        for category, strategy_results in results.items():
            print(f"\n{category}:")
            for result in strategy_results:
                status = result.get("status", "❓ 未知")
                name = result.get("strategy_id") or result.get("strategy_name", "未知")
                print(f"  {status} {name}")
    
    if args.report:
        report = manager.create_strategy_report()
        filepath = manager.save_report(report)
        
        print("\n📊 策略库报告摘要:")
        summary = report["summary"]
        print(f"定义策略: {summary['total_strategies_defined']} 个")
        print(f"加载成功: {summary['strategies_loaded']} 个 ({summary['load_rate']:.1%})")
        print(f"已启用: {summary['strategies_enabled']} 个 ({summary['enable_rate']:.1%})")
        print(f"有参数文件: {summary['strategies_with_params']} 个")
        
        print("\n💡 建议:")
        for rec in report.get("recommendations", []):
            print(f"  • {rec}")
    
    if args.strategy:
        if args.execute:
            # 简单测试执行
            result = manager.execute_strategy(args.strategy)
            print(f"\n🚀 执行结果:")
            print(f"策略: {result.get('strategy_name', args.strategy)}")
            print(f"成功: {result.get('success', False)}")
            
            if not result.get("success"):
                print(f"错误: {result.get('error', '未知错误')}")
            else:
                print(f"结果类型: {type(result.get('result')).__name__}")
        
        elif args.performance:
            performance = manager.get_strategy_performance(args.strategy)
            print(f"\n📈 策略性能报告:")
            print(f"策略: {args.strategy}")
            
            if performance.get("success", False):
                perf_summary = performance.get("performance_summary", {})
                print(f"总执行次数: {perf_summary.get('total_executions', 0)}")
                print(f"成功次数: {perf_summary.get('success_count', 0)}")
                print(f"准确率: {perf_summary.get('accuracy', 0):.1%}")
                print(f"净收益: ¥{perf_summary.get('net_profit', 0):,.2f}")
            else:
                print(f"错误: {performance.get('error', '未知错误')}")
        
        else:
            # 加载策略信息
            strategy = manager.load_strategy(args.strategy)
            if strategy:
                print(f"\n📋 策略信息:")
                print(f"ID: {strategy.strategy_id}")
                print(f"名称: {strategy.name}")
                print(f"类别: {strategy.category}")
                print(f"版本: {strategy.version}")
                print(f"启用: {strategy.parameters.get('enabled', False)}")
                print(f"参数数量: {len(strategy.parameters)}")
            else:
                print(f"❌ 策略 {args.strategy} 未找到")


if __name__ == "__main__":
    main()