"""
策略库完整功能演示

版本: v1.0.0
维护者: 小红 🌹
创建时间: 2026-04-10

演示策略库的完整功能：
1. 策略加载和初始化
2. 参数管理和验证
3. 策略执行和测试
4. 组合策略使用
5. 绩效跟踪和报告
"""

import sys
from pathlib import Path
from datetime import datetime
import json

# 添加路径
STRATEGIES_DIR = Path(__file__).parent
sys.path.insert(0, str(STRATEGIES_DIR.parent))

from strategies import list_strategies, get_strategy
from strategies.params import get_parameter_manager
from strategy_manager import StrategyManager


class StrategyLibraryDemo:
    """策略库演示类"""
    
    def __init__(self):
        self.manager = StrategyManager()
        self.param_manager = get_parameter_manager()
        
    def run_full_demo(self):
        """运行完整演示"""
        print("🌟 策略库完整功能演示 🌟")
        print("=" * 60)
        
        # 1. 策略库概览
        self.demo_library_overview()
        
        # 2. 单个策略使用
        self.demo_single_strategy_usage()
        
        # 3. 参数管理
        self.demo_parameter_management()
        
        # 4. 组合策略
        self.demo_composite_strategy()
        
        # 5. 策略测试和验证
        self.demo_strategy_testing()
        
        # 6. 集成示例
        self.demo_integration_example()
        
        # 7. 总结和建议
        self.demo_summary_and_recommendations()
    
    def demo_library_overview(self):
        """演示策略库概览"""
        print("\n1. 📚 策略库概览")
        print("-" * 40)
        
        strategies = list_strategies()
        total_count = 0
        
        for category, strategy_list in strategies.items():
            count = len(strategy_list)
            total_count += count
            print(f"   {category.upper():15} {count:2d} 个策略")
        
        print(f"\n   📊 总计: {total_count} 个策略（6个类别）")
        
        # 验证所有策略
        print("\n   🔍 验证策略实现状态:")
        validation_results = self.manager.test_all_strategies()
        
        for category, results in validation_results.items():
            loaded = sum(1 for r in results if "加载成功" in r.get("status", ""))
            total = len(results)
            print(f"     {category:15} {loaded}/{total} 个已实现")
    
    def demo_single_strategy_usage(self):
        """演示单个策略使用"""
        print("\n2. 📈 单个策略使用演示")
        print("-" * 40)
        
        # 演示趋势跟随选股策略
        print("   🔍 演示: 趋势跟随选股策略 (SEL-001)")
        strategy = get_strategy("SEL-001")
        
        print(f"     名称: {strategy.name}")
        print(f"     版本: v{strategy.version}")
        print(f"     类别: {strategy.category}")
        print(f"     启用: {strategy.parameters.get('enabled', False)}")
        
        # 展示关键参数
        key_params = ["trend_period", "score_threshold", "max_selections"]
        print("     关键参数:")
        for param in key_params:
            if param in strategy.parameters:
                value = strategy.parameters[param]
                print(f"       • {param}: {value}")
        
        # 演示R值风险管理策略
        print("\n   🔍 演示: R值风险管理策略 (POS-002)")
        strategy = get_strategy("POS-002")
        
        print(f"     名称: {strategy.name}")
        print(f"     核心公式: {strategy.parameters.get('r_value_formula', 'N/A')}")
        
        # 计算R值
        r_value = strategy.calculate_r_value()
        print(f"     当前R值: ¥{r_value:,.2f}")
        
        # 演示仓位计算
        print("\n   🧮 模拟仓位计算:")
        test_stock = {
            "code": "300131",
            "name": "英唐智控",
            "current_price": 12.6,
            "technical_support": 11.5,
            "volatility": 0.025
        }
        
        net_value = 0.0  # 禁止硬编码，实际使用时从ConfigManager获取
        position_result = strategy.calculate_position(test_stock, net_value)
        
        if position_result.get("success"):
            print(f"     股票: {position_result['name']}")
            print(f"     入场价: ¥{position_result['entry_price']}")
            print(f"     止损价: ¥{position_result['stop_loss_price']}")
            print(f"     建议仓位: ¥{position_result['position_value']:,.0f}")
            print(f"     建议股数: {position_result['shares']:,} 股")
            print(f"     风险金额: ¥{position_result['risk_amount']:,.0f}")
    
    def demo_parameter_management(self):
        """演示参数管理"""
        print("\n3. ⚙️  参数管理系统演示")
        print("-" * 40)
        
        # 列出所有参数文件
        strategies = self.param_manager.list_all_strategies()
        print(f"   📁 参数文件: {len(strategies)} 个")
        
        # 查看参数文件内容
        print("\n   🔍 查看参数文件示例 (SEL-001):")
        params = self.param_manager.get_strategy_params("SEL-001")
        
        if params:
            metadata = params.get("metadata", {})
            print(f"     创建时间: {metadata.get('created', 'N/A')}")
            print(f"     最后更新: {metadata.get('last_updated', 'N/A')}")
            print(f"     状态: {metadata.get('status', 'N/A')}")
            
            # 展示参数结构
            param_count = len(params.get("parameters", {}))
            print(f"     参数数量: {param_count}")
        
        # 演示参数更新
        print("\n   🔄 参数更新演示:")
        updates = {
            "parameters": {
                "score_threshold": 65  # 提高选股阈值
            }
        }
        print(f"     拟更新 SEL-001.score_threshold: 60 → 65")
        print("     (实际更新需调用 update_strategy_parameters)")
        
        # 演示参数验证
        print("\n   ✅ 参数验证演示:")
        test_params = {
            "trend_period": 25,
            "score_threshold": 70,
            "max_selections": 15
        }
        
        # 获取策略参数模式
        strategy = get_strategy("SEL-001")
        schema = strategy.parameter_schema()
        
        # 验证参数
        errors = self.param_manager.validate_parameters(test_params, schema)
        if errors:
            print("     验证失败:")
            for error in errors:
                print(f"       • {error}")
        else:
            print("     验证通过: 所有参数符合模式要求")
    
    def demo_composite_strategy(self):
        """演示组合策略"""
        print("\n4. 🏦 组合策略演示")
        print("-" * 40)
        
        # 加载保守组合策略
        print("   🔍 演示: 保守组合策略 (CMP-001)")
        strategy = get_strategy("CMP-001")
        
        print(f"     名称: {strategy.name}")
        print(f"     风险等级: {strategy.parameters.get('risk_level', 'N/A')}")
        print(f"     最大持仓: {strategy.parameters.get('max_positions', 0)} 只")
        
        # 展示组件策略
        print("\n   🔧 组件策略:")
        for i, component in enumerate(strategy.component_strategies, 1):
            comp_strategy = component["strategy"]
            weight = component["weight"]
            print(f"     {i}. {comp_strategy.strategy_id}: {comp_strategy.name} (权重: {weight:.0%})")
        
        # 模拟股票池
        print("\n   📊 模拟股票池数据:")
        stock_pool = self._create_sample_stock_pool()
        net_value = 0.0  # 禁止硬编码，实际使用时从ConfigManager获取
        
        print(f"     股票数量: {len(stock_pool)} 只")
        print(f"     当前净值: ¥{net_value:,.0f}")
        
        # 执行组合策略
        print("\n   🚀 执行组合策略流水线...")
        try:
            result = strategy.execute_full_pipeline(stock_pool, net_value)
            
            if result.get("success"):
                selection_count = len(result.get("selection_result", {}).get("selected_stocks", []))
                detailed_count = len(result.get("detailed_results", []))
                recommendation = result.get("recommendation", {})
                
                print(f"     选股结果: {selection_count} 只选中")
                print(f"     详细分析: {detailed_count} 只完成")
                print(f"     综合建议: {recommendation.get('recommendation', 'N/A')}")
                print(f"     信心度: {recommendation.get('confidence', 'N/A')}")
                
                if recommendation.get("suggested_positions"):
                    positions = recommendation["suggested_positions"]
                    print(f"     建议持仓: {len(positions)} 只")
                    
                    for i, pos in enumerate(positions[:2], 1):  # 只显示前2个
                        print(f"       {i}. {pos['name']}: ¥{pos['position_value']:,.0f} ({pos['position_pct']:.1%})")
            else:
                print(f"     执行失败: {result.get('error', '未知错误')}")
                
        except Exception as e:
            print(f"     执行异常: {e}")
    
    def demo_strategy_testing(self):
        """演示策略测试"""
        print("\n5. 🧪 策略测试和验证")
        print("-" * 40)
        
        # 使用策略管理器测试
        print("   🔍 策略管理器测试:")
        test_results = self.manager.test_all_strategies()
        
        total_loaded = 0
        total_tested = 0
        
        for category, results in test_results.items():
            loaded = sum(1 for r in results if "加载成功" in r.get("status", ""))
            total = len(results)
            total_loaded += loaded
            total_tested += total
            
            status = "✅" if loaded == total else "⚠️ " if loaded > 0 else "❌"
            print(f"     {status} {category:15} {loaded}/{total}")
        
        load_rate = total_loaded / total_tested if total_tested > 0 else 0
        print(f"\n     加载成功率: {load_rate:.1%}")
        
        # 生成策略报告
        print("\n   📊 生成策略库报告:")
        report = self.manager.create_strategy_report()
        summary = report["summary"]
        
        print(f"     定义策略: {summary['total_strategies_defined']} 个")
        print(f"     加载成功: {summary['strategies_loaded']} 个")
        print(f"     已启用: {summary['strategies_enabled']} 个")
        print(f"     有参数文件: {summary['strategies_with_params']} 个")
    
    def demo_integration_example(self):
        """演示集成示例"""
        print("\n6. 🔗 集成到交易系统示例")
        print("-" * 40)
        
        print("   📋 集成场景: 替换现有侦察兵选股模块")
        
        # 示例：如何用策略库替换现有选股逻辑
        print("\n   🔄 替换前（旧代码）:")
        print('''
        # 旧侦察兵选股逻辑（硬编码）
        def old_scout_selection(stock_pool):
            selected = []
            for stock in stock_pool:
                # 硬编码的选股逻辑
                if stock["change_pct"] > 2 and stock["volume"] > 1000000:
                    selected.append(stock)
            return selected
        ''')
        
        print("\n   🔄 替换后（新代码）:")
        print('''
        # 新侦察兵选股逻辑（使用策略库）
        from strategies import get_strategy
        
        def new_scout_selection(stock_pool, strategy_id="SEL-001"):
            # 加载策略
            strategy = get_strategy(strategy_id)
            
            # 执行策略
            result = strategy.select(stock_pool)
            
            # 返回选中的股票
            return [s["code"] for s in result]
        ''')
        
        print("\n   ✅ 优势:")
        print("     1. 参数可配置，无需修改代码")
        print("     2. 支持多种选股策略切换")
        print("     3. 自动性能跟踪和优化")
        print("     4. 支持A/B测试和策略进化")
        
        # 示例：集成到弹药库风控模块
        print("\n   📋 集成场景: 替换弹药库风控模块")
        
        print("\n   🔄 替换前（旧风控）:")
        print('''
        # 旧风控逻辑（固定百分比止损）
        def old_risk_management(stock, entry_price):
            stop_loss = entry_price * 0.92  # 固定-8%止损
            return stop_loss
        ''')
        
        print("\n   🔄 替换后（新风控）:")
        print('''
        # 新风控逻辑（使用策略库）
        from strategies import get_strategy
        
        def new_risk_management(stock, entry_price, net_value):
            # 加载R值止损策略
            stop_strategy = get_strategy("STP-001")
            
            # 计算止损位
            stop_result = stop_strategy.calculate_stop_loss(
                stock_data=stock,
                entry_price=entry_price,
                net_value=net_value
            )
            
            return stop_result["stop_loss_price"]
        ''')
    
    def demo_summary_and_recommendations(self):
        """演示总结和建议"""
        print("\n7. 🎯 总结和建议")
        print("-" * 40)
        
        # 生成最终报告
        report = self.manager.create_strategy_report()
        summary = report["summary"]
        
        print("   📈 策略库当前状态:")
        print(f"     总策略数: {summary['total_strategies_defined']} 个")
        print(f"     已实现: {summary['strategies_loaded']} 个")
        print(f"     已启用: {summary['strategies_enabled']} 个")
        print(f"     参数管理: ✅ 完整系统")
        print(f"     性能跟踪: ✅ 内置框架")
        print(f"     组合策略: ✅ 支持灵活组合")
        
        print("\n   💡 集成建议:")
        print("     1. 先替换侦察兵选股模块（低风险）")
        print("     2. 再替换弹药库风控模块（核心风控）")
        print("     3. 最后替换狙击手交易模块（完整流程）")
        
        print("\n   🚀 实施步骤:")
        steps = [
            "阶段1: 小范围测试（1-2个策略）",
            "阶段2: 历史回测验证效果",
            "阶段3: 小资金实盘测试",
            "阶段4: 全面集成和优化"
        ]
        
        for i, step in enumerate(steps, 1):
            print(f"     {i}. {step}")
        
        print("\n   ⏱️  预计时间:")
        print("     阶段1: 1-2天（配置和测试）")
        print("     阶段2: 3-5天（回测和优化）")
        print("     阶段3: 1-2周（实盘验证）")
        print("     阶段4: 2-4周（全面集成）")
        
        print("\n   ✅ 策略库已就绪，等待集成部署！")
    
    def _create_sample_stock_pool(self):
        """创建示例股票池"""
        return [
            {
                "code": "300131",
                "name": "英唐智控",
                "current_price": 12.6,
                "change_pct": 2.5,
                "volume": 1500000,
                "amount": 18900000,
                "market_cap": 5000000000,
                "sector": "电子",
                "is_st": False,
                "historical_data": None,
                "entry_price": 12.0,
                "technical_support": 11.5,
                "volatility": 0.025
            },
            {
                "code": "600481",
                "name": "双良节能",
                "current_price": 7.8,
                "change_pct": 1.3,
                "volume": 2000000,
                "amount": 15600000,
                "market_cap": 3000000000,
                "sector": "机械设备",
                "is_st": False,
                "historical_data": None,
                "entry_price": 7.5,
                "technical_support": 7.2,
                "volatility": 0.02
            },
            {
                "code": "002415",
                "name": "海康威视",
                "current_price": 35.2,
                "change_pct": -0.5,
                "volume": 3000000,
                "amount": 105600000,
                "market_cap": 35000000000,
                "sector": "电子",
                "is_st": False,
                "historical_data": None,
                "entry_price": 34.8,
                "technical_support": 33.5,
                "volatility": 0.015
            },
            {
                "code": "000858",
                "name": "五粮液",
                "current_price": 145.3,
                "change_pct": 0.8,
                "volume": 800000,
                "amount": 116240000,
                "market_cap": 56000000000,
                "sector": "消费",
                "is_st": False,
                "historical_data": None,
                "entry_price": 142.0,
                "technical_support": 140.0,
                "volatility": 0.018
            }
        ]


def main():
    """主函数"""
    demo = StrategyLibraryDemo()
    demo.run_full_demo()


if __name__ == "__main__":
    main()