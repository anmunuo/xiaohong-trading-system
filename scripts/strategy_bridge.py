#!/usr/bin/env python3
"""
策略桥接器 - v1.0
================
LLM ↔ 策略引擎的统一入口。所有输出 JSON，方便程序化消费。

用法:
  python3 strategy_bridge.py list                          # 列出所有策略
  python3 strategy_bridge.py run CMP-001 --stock 300131   # 运行保守策略
  python3 strategy_bridge.py risk 300131 600481            # 风控分析
  python3 strategy_bridge.py signal                       # 生成交易决策信号
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(BASE_DIR))


def get_holdings_data() -> dict:
    path = BASE_DIR / "data" / "holdings.json"
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return {}


def cmd_list() -> dict:
    """列出所有可用策略"""
    try:
        from strategies import list_strategies, validate_all_strategies
        strategies = list_strategies()
        return {"success": True, "strategies": strategies, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def cmd_run(strategy_id: str, stock_code: str = None) -> dict:
    """运行指定策略"""
    try:
        from strategies import get_strategy
        strategy = get_strategy(strategy_id)
        info = {
            "id": strategy.strategy_id,
            "name": strategy.name,
            "category": strategy.category,
            "version": strategy.version,
            "parameters": strategy.parameters,
        }

        # 如果指定了股票且策略支持执行
        if stock_code and hasattr(strategy, 'execute'):
            # 获取该股票的日线数据
            from data_pipeline import get_stock_realtime
            quotes = get_stock_realtime([stock_code])
            stock_data = quotes.get(stock_code, {})
            if stock_data:
                # 构造简化的股票池
                stock_pool = [{
                    "code": stock_code,
                    "name": "",
                    "price": stock_data.get("close", 0),
                    "change_pct": stock_data.get("change_pct", 0),
                    "volume": stock_data.get("volume", 0),
                    "amount": stock_data.get("amount", 0),
                }]
                result = strategy.execute(stock_pool=stock_pool)
                info["execution"] = result
            else:
                info["execution"] = {"success": False, "error": f"无法获取 {stock_code} 数据"}

        return {"success": True, "strategy": info, "timestamp": datetime.now().isoformat()}
    except Exception as e:
        return {"success": False, "error": str(e), "strategy_id": strategy_id}


def cmd_risk(codes: List[str] = None) -> dict:
    """风控分析：给定股票代码，计算当前止损状态和建议"""
    holdings_data = get_holdings_data()
    holdings = holdings_data.get("holdings", [])
    rules = holdings_data.get("rules", {})
    risk_mgmt = rules.get("riskManagement", {})
    r_value = risk_mgmt.get("currentRValue", 0)
    net_value = holdings_data.get("accountInfo", {}).get("currentNetValue", 0)
    # 动态读取仓位上限
    max_pos_pct = float(rules.get("maxPositionPerStock", 33.3))

    # 获取实时行情
    all_codes = codes if codes else [h['code'] for h in holdings]
    from data_pipeline import get_stock_realtime
    quotes = get_stock_realtime(all_codes)

    results = []
    for code in all_codes:
        q = quotes.get(code, {})
        holding = next((h for h in holdings if h['code'] == code), None)

        entry = {
            "code": code,
            "name": holding['name'] if holding else "",
            "price": q.get('close', 0),
            "change_pct": q.get('change_pct', 0),
            "data_source": q.get('data_source', 'N/A'),
        }

        if holding:
            entry["shares"] = holding.get('shares', 0)
            entry["cost_price"] = holding.get('costPrice', 0)
            entry["total_cost"] = holding.get('totalCost', 0)
            if q.get('close'):
                entry["market_value"] = round(q['close'] * holding['shares'], 2)
                entry["unrealized_pnl"] = round(entry['market_value'] - entry['total_cost'], 2)
                entry["pnl_pct"] = round(entry['unrealized_pnl'] / entry['total_cost'] * 100, 2)
                entry["position_pct"] = round(entry['market_value'] / net_value * 100, 2) if net_value else 0

            # 止损状态
            stop_status = []
            for trade in holding.get('trades', []):
                stop_loss = trade.get('stopLoss', 0)
                if stop_loss and q.get('close'):
                    dist = round((q['close'] - stop_loss) / stop_loss * 100, 2)
                    triggered = q['close'] <= stop_loss
                    stop_status.append({
                        "batch": trade.get('batchId'),
                        "stop_loss": stop_loss,
                        "current_price": q['close'],
                        "distance_pct": dist,
                        "triggered": triggered,
                        "severity": "critical" if triggered else ("warning" if dist < 5 else "ok"),
                    })
            entry["stop_checks"] = stop_status

        results.append(entry)

    # 汇总
    total_alerts = sum(1 for r in results for s in r.get('stop_checks', []) if s['triggered'])
    total_cost = sum(r.get('total_cost', 0) for r in results)
    total_mv = sum(r.get('market_value', 0) for r in results)

    return {
        "success": True,
        "net_value": net_value,
        "r_value": r_value,
        "total_cost": round(total_cost, 2),
        "total_market_value": round(total_mv, 2),
        "total_pnl": round(total_mv - total_cost, 2),
        "alerts_triggered": total_alerts,
        "positions": results,
        "timestamp": datetime.now().isoformat(),
    }


def cmd_signal() -> dict:
    """生成综合交易决策信号"""
    risk = cmd_risk()
    if not risk.get("success"):
        return risk

    positions = risk.get("positions", [])
    alerts = risk.get("alerts_triggered", 0)
    total_pnl = risk.get("total_pnl", 0)

    # 逐股决策建议
    recommendations = []
    for pos in positions:
        rec = {
            "code": pos["code"],
            "name": pos.get("name", ""),
            "pnl_pct": pos.get("pnl_pct", 0),
            "position_pct": pos.get("position_pct", 0),
            "action": "持有",
            "reason": "",
        }

        stop_checks = pos.get("stop_checks", [])
        triggered = [s for s in stop_checks if s["triggered"]]
        close_to_stop = [s for s in stop_checks if s.get("severity") == "warning"]

        if triggered:
            rec["action"] = "立即卖出"
            rec["reason"] = f"{len(triggered)} 个批次已触发止损"
            rec["severity"] = "critical"
        elif close_to_stop:
            rec["action"] = "准备减仓"
            rec["reason"] = f"{len(close_to_stop)} 个批次靠近止损线"
            rec["severity"] = "warning"
        elif pos.get("position_pct", 0) > max_pos_pct:
            rec["action"] = "减仓"
            rec["reason"] = f"仓位 {pos['position_pct']:.1f}% 超过 {max_pos_pct:.1f}% 上限"
            rec["severity"] = "warning"
        elif pos.get("pnl_pct", 0) > 30:
            rec["action"] = "移动止盈"
            rec["reason"] = f"浮盈 {pos['pnl_pct']:.1f}%，建议上移止盈位"
            rec["severity"] = "info"
        elif pos.get("pnl_pct", 0) > 0:
            rec["action"] = "持有"
            rec["reason"] = "浮盈中，趋势良好"
            rec["severity"] = "ok"
        else:
            rec["action"] = "观察"
            rec["reason"] = "浮亏但未触及止损"
            rec["severity"] = "info"

        recommendations.append(rec)

    # 整体建议
    if alerts > 0:
        overall = f"🔴 发现 {alerts} 个止损警报，建议立即处理"
    elif total_pnl < 0:
        overall = "🟡 整体浮亏，密切监控止损位"
    else:
        overall = "🟢 整体浮盈，按计划持有"

    return {
        "success": True,
        "overall_assessment": overall,
        "total_pnl": total_pnl,
        "alerts": alerts,
        "recommendations": recommendations,
        "timestamp": datetime.now().isoformat(),
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "用法: strategy_bridge.py <list|run|risk|signal> [...]"}, ensure_ascii=False))
        return

    cmd = sys.argv[1]

    if cmd == "list":
        print(json.dumps(cmd_list(), ensure_ascii=False, indent=2))
    elif cmd == "run":
        strategy_id = sys.argv[2] if len(sys.argv) > 2 else "CMP-001"
        stock_code = sys.argv[3] if len(sys.argv) > 3 else None
        print(json.dumps(cmd_run(strategy_id, stock_code), ensure_ascii=False, indent=2))
    elif cmd == "risk":
        codes = sys.argv[2:] if len(sys.argv) > 2 else None
        print(json.dumps(cmd_risk(codes), ensure_ascii=False, indent=2))
    elif cmd == "signal":
        print(json.dumps(cmd_signal(), ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"error": f"未知命令: {cmd}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
