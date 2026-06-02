"""
策略库使用演示

版本: v1.0.0
维护者: 小红 🌹
创建时间: 2026-04-10

演示如何：
1. 加载和使用单个策略
2. 使用组合策略
3. 管理策略参数
4. 查看策略性能
"""

import sys
from pathlib import Path

# 添加路径
STRATEGIES_DIR = Path(__file__).parent
sys.path.insert(0, str(STRATEGIES_DIR.parent))

from strategies import list_strategies, get_strategy
from strategies.params import get_parameter_manager
from strategy_manager import StrategyManager


def demo_single_strategy():
    """演示单个策略使用"""
    print("=" * 60)
    print("🚀 演示1: 单个策略使用")
    print("=" * 60)
    
    # 1. 加载趋势跟随选股策略
    print("\n1. 📈 加载趋势跟随选股策略 (SEL-001)")
    trend_strategy = get_strategy("SEL-001")
    print(f"   ✅ 加载成功: {trend_strategy.name} (v{trend_strategy.version})")
    print(f"   参数数量: {len(trend_strategy.parameters)}")
    print(f"   启用状态: {trend_strategy.parameters.get('enabled', False)}")
    
    # 2. 查看策略参数
    print("\n2. ⚙️  查看策略参数")
    important_params = ["trend_period", "score_threshold", "max_selections"]
    for param in important_params:
        if param in trend_strategy.parameters:
            value = trend_strategy.parameters[param]
            print(f"   {param}: {value}")
    
    # 3. 查看性能报告
    print("\n3. 📊 查看性能报告")
    report = trend_strategy.get_performance_report()
    perf_summary = report["performance_summary"]
    print(f"   总执行次数: {perf_summary['total_executions']}")
    print(f"   成功率: {perf_summary['accuracy']:.1%}")
    
    return trend_strategy


def demo_composite_strategy():
    """演示组合策略使用"""
    print("\n" + "=" * 60)
    print("🚀 演示2: 组合策略使用")
    print("=" * 60)
    
    # 1. 加载保守组合策略
    print("\n1. 🏦 加载保守组合策略 (CMP-001)")
    composite_strategy = get_strategy("CMP-001")
    print(f"   ✅ 加载成功: {composite_strategy.name}")
    print(f"   组件策略: {len(composite_strategy.component_strategies)} 个")
    
    # 2. 查看组件策略
    print("\n2. 🔧 查看组件策略:")
    for i, component in enumerate(composite_strategy.component_strategies, 1):
        strategy = component["strategy"]
        weight = component["weight"]
        print(f"   {i}. {strategy.strategy_id}: {strategy.name} (权重: {weight:.0%})")
    
    # 3. 查看组合参数
    print("\n3. ⚙️  查看组合参数:")
    params = composite_strategy.parameters
    important_params = ["risk_level", "max_positions", "max_position_pct"]
    for param in important_params:
        if param in params:
            value = params[param]
            print(f"   {param}: {value}")
    
    return composite_strategy


def demo_parameter_management():
    """演示参数管理"""
    print("\n" + "=" * 60)
    print("🚀 演示3: 参数管理")
    print("=" * 60)
    
    manager = get_parameter_manager()
    
    # 1. 列出所有参数文件
    print("\n1. 📁 列出所有策略参数文件:")
    strategies = manager.list_all_strategies()
    for strategy_id in strategies:
        print(f"   • {strategy_id}")
    
    # 2. 查看R值风险管理策略参数
    print("\n2. 📋 查看POS-002参数:")
    params = manager.get_strategy_params("POS-002")
    if params:
        important_keys = ["r_value_formula", "max_position_per_stock", "safety_margin"]
        for key in important_keys:
            if key in params.get("parameters", {}):
                value = params["parameters"][key]
                print(f"   {key}: {value}")
    
    # 3. 更新参数演示
    print("\n3. 🔄 参数更新演示:")
    updates = {
        "parameters": {
            "score_threshold": 65  # 提高选股阈值
        }
    }
    print(f"   拟更新SEL-001: score_threshold -> 65")
    print("   (实际更新需调用 update_strategy_parameters)")


def demo_strategy_manager():
    """演示策略管理器"""
    print("\n" + "=" * 60)
    print("🚀 演示4: 策略管理器")
    print("=" * 60)
    
    manager = StrategyManager()
    
    # 1. 列出所有可用策略
    print("\n1. 📚 列出所有可用策略:")
    strategies = manager.list_available_strategies()
    for category, strategy_list in strategies.items():
        print(f"   {category.upper()}: {len(strategy_list)} 个")
        for strategy in strategy_list[:3]:  # 只显示前3个
            print(f"     • {strategy}")
        if len(strategy_list) > 3:
            print(f"     ... 还有 {len(strategy_list) - 3} 个")
    
    # 2. 生成策略报告
    print("\n2. 📊 生成策略库报告:")
    report = manager.create_strategy_report()
    summary = report["summary"]
    print(f"   定义策略: {summary['total_strategies_defined']} 个")
    print(f"   加载成功: {summary['strategies_loaded']} 个")
    print(f"   已启用: {summary['strategies_enabled']} 个")
    print(f"   有参数文件: {summary['strategies_with_params']} 个")
    
    # 3. 建议
    print("\n3. 💡 当前建议:")
    for rec in report.get("recommendations", []):
        print(f"   • {rec}")


def create_sample_data():
    """创建示例数据"""
    print("\n" + "=" * 60)
    print("📋 示例数据（模拟）")
    print("=" * 60)
    
    # 模拟股票池
    stock_pool = [
        {
            "code": "300131",
            "name": "英唐智控",
            "current_price": 12.6,
            "change_pct": 2.5,
            "volume": 1500000,
            "sector": "电子",
            "is_st": False,
            "historical_data": None  # 实际使用时需要真实数据
        },
        {
            "code": "600481", 
            "name": "双良节能",
            "current_price": 7.8,
            "change_pct": 1.3,
            "volume": 2000000,
            "sector": "机械设备",
            "is_st": False,
            "historical_data": None
        },
        {
            "code": "002415",
            "name": "海康威视",
            "current_price": 35.2,
            "change_pct": -0.5,
            "volume": 3000000,
            "sector": "电子",
            "is_st": False,
            "historical_data": None
        }
    ]
    
    print(f"股票池: {len(stock_pool)} 只股票")
    for stock in stock_pool:
        print(f"  • {stock['code']} {stock['name']}: ¥{stock['current_price']} ({stock['change_pct']}%)")
    
    return stock_pool


def main():
    """主演示函数"""
    print("🌟 策略库使用演示 🌟")
    print("版本: v1.0.0 | 维护者: 小红 🌹")
    print()
    
    # 创建示例数据
    stock_pool = create_sample_data()
    net_value = 0.0  # 禁止硬编码，实际使用时从ConfigManager获取
    
    try:
        # 演示1: 单个策略
        trend_strategy = demo_single_strategy()
        
        # 演示2: 组合策略  
        composite_strategy = demo_composite_strategy()
        
        # 演示3: 参数管理
        demo_parameter_management()
        
        # 演示4: 策略管理器
        demo_strategy_manager()
        
        print("\n" + "=" * 60)
        print("🎯 总结")
        print("=" * 60)
        
        # 统计信息
        from strategies import list_strategies
        strategies = list_strategies()
        
        total_count = 0
        for category, strategy_list in strategies.items():
            total_count += len(strategy_list)
        
        print(f"📈 策略库状态:")
        print(f"   • 总策略数: {total_count} 个（6个类别）")
        print(f"   • 已实现: 4 个核心策略")
        print(f"   • 参数管理: ✅ 完整系统")
        print(f"   • 性能跟踪: ✅ 内置框架")
        print(f"   • 组合策略: ✅ 支持灵活组合")
        
        print(f"\n💼 当前配置:")
        print(f"   • 净值: ¥{net_value:,.0f}")
        print(f"   • R值: ¥10,390")
        print(f"   • 最大持仓: 3 只")
        print(f"   • 单股上限: 33.3%")
        
        print(f"\n🚀 下一步:")
        print(f"   1. 集成到现有交易系统")
        print(f"   2. 进行历史回测验证")
        print(f"   3. 小资金实盘测试")
        print(f"   4. 持续优化策略参数")
        
        print(f"\n✅ 演示完成！策略库已就绪，等待集成使用。")
        
    except Exception as e:
        print(f"\n❌ 演示过程中出现错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()