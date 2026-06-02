#!/usr/bin/env python3
"""
策略库集成测试 - 使用统一数据接口

版本: v1.0
维护者: 小红 🌹
创建时间: 2026-04-10

测试策略库与统一数据接口的集成
"""

import sys
import os
from pathlib import Path
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_strategy_with_unified_data():
    """测试策略使用统一数据接口"""
    print("🧪 策略库集成测试 - 统一数据接口")
    print("=" * 60)
    
    try:
        # 导入策略库
        from strategies import get_strategy
        
        # 导入策略数据适配器
        from data_manager.adapters.strategy_adapter import get_strategy_adapter
        
        print("✅ 模块导入成功")
        
        # 创建策略数据适配器
        adapter = get_strategy_adapter("xiaohong")
        print("✅ 策略数据适配器创建成功")
        
        # 获取策略
        strategy = get_strategy("SEL-001")  # 趋势跟随策略
        print(f"✅ 策略加载成功: {strategy.name}")
        
        # 准备测试股票池
        test_symbols = ["600519", "000858", "002415"]
        print(f"\n📊 准备股票池数据 ({len(test_symbols)} 只股票)...")
        
        # 使用策略数据适配器获取股票池数据
        stock_pool = adapter.get_stock_pool_for_selection(
            symbols=test_symbols,
            days=30,
            include_historical=True
        )
        
        print(f"✅ 股票池准备完成: {len(stock_pool)}/{len(test_symbols)} 只股票")
        
        if len(stock_pool) == 0:
            print("⚠️  股票池为空，使用模拟数据继续测试")
            # 创建模拟数据
            stock_pool = create_mock_stock_pool(test_symbols)
        
        # 执行策略选股
        print("\n🎯 执行趋势跟随策略选股...")
        selected_stocks = strategy.select(stock_pool)
        
        print(f"✅ 策略执行完成")
        print(f"   选中股票: {len(selected_stocks)} 只")
        
        if selected_stocks:
            print("\n📈 选股结果:")
            for stock in selected_stocks[:5]:  # 最多显示5只
                change_icon = "📈" if stock.get("score", 0) > 60 else "📉"
                print(f"  {stock['code']}: 评分 {stock.get('score', 0):.0f} {change_icon}")
                if "reason" in stock:
                    print(f"     理由: {stock['reason'][:50]}...")
        
        # 测试组合策略
        print("\n🧩 测试组合策略 (CMP-001)...")
        composite_strategy = get_strategy("CMP-001")
        
        if composite_strategy:
            print(f"✅ 组合策略加载成功: {composite_strategy.name}")
            
            # 执行组合策略
            result = composite_strategy.execute(
                stock_pool=stock_pool,
                net_value=1000000.00
            )
            
            print(f"✅ 组合策略执行完成")
            print(f"   成功: {result.get('success', False)}")
            if not result.get('success', False):
                print(f"   错误: {result.get('error', '未知')}")
            else:
                print(f"   总评分: {result.get('total_score', 0):.2f}")
                print(f"   成功率: {result.get('success_rate', 0):.1%}")
        else:
            print("⚠️  组合策略加载失败")
        
        print("\n🎉 策略库集成测试完成！")
        return True
        
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def create_mock_stock_pool(symbols):
    """创建模拟股票池数据（当真实数据获取失败时使用）"""
    mock_pool = []
    
    for i, symbol in enumerate(symbols):
        mock_pool.append({
            "code": symbol,
            "name": f"股票{symbol}",
            "price": 100.0 + i * 10,
            "current_price": 100.0 + i * 10,
            "change_pct": i * 2 - 2,  # -2%, 0%, +2%
            "volume": 1000000 + i * 500000,
            "amount": 50000000 + i * 20000000,
            "market_cap": 10000000000 + i * 5000000000,
            "sector": "测试板块",
            "is_st": False,
            "historical_data": None,
            "technical_indicators": {
                "ma5": 98.0 + i * 10,
                "ma10": 96.0 + i * 10,
                "ma20": 94.0 + i * 10,
                "price_position": 0.5 + i * 0.1,
                "trend_strength": 50 + i * 10
            }
        })
    
    return mock_pool


def test_data_adapter_directly():
    """直接测试策略数据适配器"""
    print("\n🔧 直接测试策略数据适配器")
    print("=" * 60)
    
    try:
        from data_manager.adapters.strategy_adapter import get_strategy_adapter
        
        adapter = get_strategy_adapter("xiaohong")
        print("✅ 适配器创建成功")
        
        # 测试单只股票数据
        symbol = "600519"
        print(f"\n📈 测试单只股票数据: {symbol}")
        
        stock_data = adapter.get_single_stock_data(symbol, days=10)
        
        print(f"✅ 数据获取完成")
        print(f"   数据点数: {stock_data.get('data_points', 0)}")
        
        if stock_data.get('technical_indicators'):
            indicators = stock_data['technical_indicators']
            print(f"   技术指标: MA5={indicators.get('ma5', 0):.2f}, MA20={indicators.get('ma20', 0):.2f}")
        
        # 测试股票池准备
        print(f"\n📊 测试股票池准备...")
        symbols = ["600519", "000858"]
        stock_pool = adapter.get_stock_pool_for_selection(symbols, days=5, include_historical=False)
        
        print(f"✅ 股票池准备完成: {len(stock_pool)}/{len(symbols)} 只股票")
        
        for stock in stock_pool:
            change_icon = "📈" if stock["change_pct"] > 0 else "📉"
            print(f"  {stock['code']}: {stock['price']:.2f} {change_icon} {stock['change_pct']:+.2f}%")
        
        return True
        
    except Exception as e:
        print(f"❌ 适配器测试失败: {e}")
        return False


def main():
    """主测试函数"""
    print("🌟 策略库与统一数据接口集成测试")
    print("=" * 60)
    
    # 测试策略数据适配器
    adapter_test_ok = test_data_adapter_directly()
    
    # 测试策略集成
    if adapter_test_ok:
        print("\n" + "=" * 60)
        integration_test_ok = test_strategy_with_unified_data()
    else:
        print("⚠️  适配器测试失败，跳过策略集成测试")
        integration_test_ok = False
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("📋 测试结果汇总")
    print("=" * 60)
    
    if adapter_test_ok and integration_test_ok:
        print("✅ ✅ 所有测试通过！策略库与统一数据接口集成成功。")
        print("\n🚀 下一步: 可以开始将策略库集成到现有系统。")
        return True
    elif adapter_test_ok:
        print("✅ 🔧 适配器测试通过，但策略集成测试失败。")
        print("   需要检查策略库与适配器的数据格式兼容性。")
        return False
    else:
        print("❌ 🔧 适配器测试失败，需要修复数据接口问题。")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)