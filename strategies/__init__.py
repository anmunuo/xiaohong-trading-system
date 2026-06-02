"""
策略库 - 小红 A 股交易策略库

版本: v1.6.0
维护者: 小红 🌹
创建时间: 2026-04-10
"""

import os
import sys
from pathlib import Path

# 添加策略库路径
STRATEGIES_DIR = Path(__file__).parent
sys.path.insert(0, str(STRATEGIES_DIR))

__version__ = "1.6.0"
__author__ = "小红 🌹"
__email__ = "xiaohong@anmunuo.family"

# 策略类别
STRATEGY_CATEGORIES = {
    "selection": "选股策略",
    "entry": "入场策略", 
    "position": "仓位管理",
    "stop": "止损止盈",
    "exit": "出场策略",
    "composite": "组合策略"
}

# 策略状态
STRATEGY_STATUS = {
    "active": "活跃",
    "testing": "测试中",
    "inactive": "停用",
    "deprecated": "废弃"
}

def list_strategies(category=None):
    """
    列出所有策略
    
    Args:
        category: 策略类别（selection/entry/position/stop/exit/composite）
    
    Returns:
        dict: 策略列表
    """
    strategies = {}
    
    if category and category in STRATEGY_CATEGORIES:
        categories = [category]
    else:
        categories = STRATEGY_CATEGORIES.keys()
    
    for cat in categories:
        cat_dir = STRATEGIES_DIR / cat
        if cat_dir.exists():
            strategies[cat] = []
            for file in cat_dir.glob("*.py"):
                if file.name != "__init__.py":
                    strategies[cat].append(file.stem)
    
    return strategies

def get_strategy(strategy_id):
    """
    获取策略实例
    
    Args:
        strategy_id: 策略ID（如 "SEL-001"）
    
    Returns:
        object: 策略实例
    """
    # 策略ID映射到脚本
    strategy_map = {
        "SEL-001": "selection.trend_following.TrendFollowingStrategy",
        "SEL-002": "selection.breakout_detection.BreakoutDetectionStrategy",
        "SEL-003": "selection.volume_analysis.VolumeAnalysisStrategy",
        "SEL-004": "selection.sector_rotation.SectorRotationStrategy",
        "ENT-001": "entry.price_action.PriceActionEntryStrategy",
        "ENT-002": "entry.technical_buy.TechnicalBuyStrategy",
        "ENT-003": "entry.volume_confirmation.VolumeConfirmationStrategy",
        "POS-001": "position.kelly_position.KellyPositionStrategy",
        "POS-002": "position.r_value_risk.RValueRiskStrategy",
        "POS-003": "position.pyramid_building.PyramidBuildingStrategy",
        "STP-001": "stop.r_value_stop.RValueStopStrategy",
        "STP-002": "stop.trailing_stop.TrailingStopStrategy",
        "STP-003": "stop.technical_stop.TechnicalStopStrategy",
        "STP-004": "stop.volatility_stop.VolatilityStopStrategy",
        "EXT-001": "exit.profit_taking.ProfitTakingStrategy",
        "EXT-002": "exit.loss_cut.LossCutStrategy",
        "EXT-003": "exit.time_exit.TimeExitStrategy",
        "CMP-001": "composite.conservative.ConservativeCompositeStrategy",
        "CMP-002": "composite.moderate.ModerateCompositeStrategy",
        "CMP-003": "composite.aggressive.AggressiveCompositeStrategy",
    }
    
    if strategy_id not in strategy_map:
        raise ValueError(f"未知的策略ID: {strategy_id}")
    
    # 动态导入
    module_path = strategy_map[strategy_id]
    parts = module_path.split(".")
    
    try:
        module = __import__(f"strategies.{parts[0]}.{parts[1]}", fromlist=[parts[2]])
        strategy_class = getattr(module, parts[2])
        return strategy_class()
    except ImportError as e:
        raise ImportError(f"无法导入策略 {strategy_id}: {e}")

def validate_all_strategies():
    """
    验证所有策略
    
    Returns:
        dict: 验证结果
    """
    results = {}
    strategies = list_strategies()
    
    for category, strategy_list in strategies.items():
        results[category] = []
        for strategy_name in strategy_list:
            try:
                # 尝试导入策略模块
                module = __import__(f"strategies.{category}.{strategy_name}",
                                  fromlist=["BaseStrategy"])
                results[category].append({
                    "name": strategy_name,
                    "status": "✅ 正常",
                    "message": "导入成功"
                })
            except ImportError:
                # 模块文件不存在 → 真正的未实现
                results[category].append({
                    "name": strategy_name,
                    "status": "⚠️ 未实现",
                    "message": "策略脚本未完成"
                })
            except Exception as e:
                results[category].append({
                    "name": strategy_name,
                    "status": "❌ 错误",
                    "message": str(e)
                })
    
    return results

if __name__ == "__main__":
    # 命令行接口
    import argparse
    
    parser = argparse.ArgumentParser(description="策略库管理工具")
    parser.add_argument("--list", action="store_true", help="列出所有策略")
    parser.add_argument("--validate", action="store_true", help="验证策略")
    parser.add_argument("--category", help="指定策略类别")
    
    args = parser.parse_args()
    
    if args.list:
        strategies = list_strategies(args.category)
        for category, strategy_list in strategies.items():
            print(f"\n{STRATEGY_CATEGORIES[category]} ({category}):")
            for strategy in strategy_list:
                print(f"  - {strategy}")
    
    if args.validate:
        results = validate_all_strategies()
        for category, strategy_results in results.items():
            print(f"\n{STRATEGY_CATEGORIES[category]}验证结果:")
            for result in strategy_results:
                print(f"  {result['status']} {result['name']}: {result['message']}")