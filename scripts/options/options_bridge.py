#!/usr/bin/env python3
"""
期权策略桥接器 CLI — 统一入口

对标 strategy_bridge.py 的命令模式，提供期权专属操作。

用法：
  python3 options_bridge.py list               # 列出活跃持仓
  python3 options_bridge.py open <code> <name> <entry_price>  # 开仓
  python3 options_bridge.py close <position_id>                # 平仓
  python3 options_bridge.py check                              # 保证金检查
  python3 options_bridge.py signal                             # 生成交易信号
  python3 options_bridge.py portfolio                          # 组合汇总
"""

import sys
import os
import json

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, '..'))

from options.otc_call import OTCCallEngine, OTCParams


class OptionsBridge:
    """期权策略桥接器"""

    def __init__(self):
        self.engine = OTCCallEngine()

    # ── list ──────────────────────────────────────────

    def list_positions(self) -> dict:
        """列出所有活跃持仓"""
        active = self.engine.get_active_positions()
        return {
            'count': len(active),
            'positions': [
                {
                    'position_id': p.position_id,
                    'code': p.code,
                    'name': p.name,
                    'entry_price': p.entry_price,
                    'margin': p.margin,
                    'notional': p.notional,
                    'option_fee': p.option_fee,
                    'entry_date': p.entry_date,
                    'status': p.status,
                }
                for p in active
            ],
        }

    # ── open ──────────────────────────────────────────

    def open(self, code: str, name: str, entry_price: float,
             margin: float = None, notional: float = None) -> dict:
        """开立期权仓位"""
        pos = self.engine.open_position(
            code=code,
            name=name,
            entry_price=entry_price,
            margin=margin,
            notional=notional,
        )
        return {
            'action': 'open',
            'position_id': pos.position_id,
            'code': pos.code,
            'name': pos.name,
            'entry_price': pos.entry_price,
            'margin': pos.margin,
            'notional': pos.notional,
            'option_fee': pos.option_fee,
            'message': f"✅ 开仓成功 — {name}({code}) @ ¥{entry_price:.2f}",
        }

    # ── close ─────────────────────────────────────────

    def close(self, position_id: str, close_price: float) -> dict:
        """平仓"""
        pos = self.engine._positions.get(position_id)
        if not pos:
            return {'error': f'持仓 {position_id} 不存在'}
        if pos.status != 'active':
            return {'error': f'持仓 {position_id} 状态为 {pos.status}，无法平仓'}

        result = self.engine.close_position(pos, close_price)
        return {
            'action': 'close',
            'position_id': position_id,
            'code': pos.code,
            'name': pos.name,
            'close_price': close_price,
            'realized_pnl': result['realized_pnl'],
            'message': f"平仓 — {pos.name} 盈亏 ¥{result['realized_pnl']:+,.0f}",
        }

    # ── signal ────────────────────────────────────────

    def signal(self) -> dict:
        """
        生成期权交易信号

        从 daily_pool.json 读取推荐池，结合期权结构给出操作建议。
        返回每只推荐股的期权交易建议（盈亏比 / 是否适合开期权）。
        """
        import json as _json

        # 读推荐池
        pool_path = os.path.join(
            SCRIPT_DIR, '..', 'scripts', 'data', 'daily_pool.json'
        )
        pool_path = os.path.abspath(pool_path)

        recommendations = []
        try:
            with open(pool_path) as f:
                pool = _json.load(f)
            recs = pool.get('recommendations', [])
        except Exception:
            recs = []

        if not recs:
            return {
                'overall': '无推荐池数据',
                'signals': [],
            }

        for rec in recs[:9]:  # Top 9
            code = rec.get('code', '')
            name = rec.get('name', '')
            score = rec.get('total_score', 0)

            # 基于评分判断期权适配度
            if score >= 75:
                suggestion = "🟢 强烈建议"
                reason = "高评分，盈亏比优秀"
            elif score >= 60:
                suggestion = "🟡 谨慎考虑"
                reason = "中评分，需确认技术面"
            else:
                suggestion = "⚪ 暂不建议"
                reason = "评分不足，等待更好时机"

            recommendations.append({
                'code': code,
                'name': name,
                'score': score,
                'suggestion': suggestion,
                'reason': reason,
            })

        return {
            'overall': f"推荐池 {len(recommendations)} 只标的期权评估",
            'signals': recommendations,
        }

    # ── portfolio ─────────────────────────────────────

    def portfolio(self, current_prices: dict = None) -> dict:
        """组合汇总 — 需提供标的最新价"""
        if current_prices is None:
            # 尝试自动拉取
            from options.margin_tracker import MarginTracker
            tracker = MarginTracker(self.engine)
            result = tracker.run_check()
            prices = {}
            for a in result['alerts']:
                if a['current_price'] is not None:
                    prices[a['code']] = a['current_price']
        else:
            prices = current_prices

        return self.engine.get_portfolio_summary(prices)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 options_bridge.py <command> [args]")
        print("Commands: list | open | close | check | signal | portfolio")
        sys.exit(1)

    cmd = sys.argv[1]
    bridge = OptionsBridge()

    if cmd == "list":
        result = bridge.list_positions()
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    elif cmd == "open":
        if len(sys.argv) < 5:
            print("Usage: options_bridge.py open <code> <name> <entry_price> [margin] [notional]")
            sys.exit(1)
        code = sys.argv[2]
        name = sys.argv[3]
        price = float(sys.argv[4])
        margin = float(sys.argv[5]) if len(sys.argv) > 5 else None
        notional = float(sys.argv[6]) if len(sys.argv) > 6 else None
        result = bridge.open(code, name, price, margin, notional)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "close":
        if len(sys.argv) < 4:
            print("Usage: options_bridge.py close <position_id> <close_price>")
            sys.exit(1)
        pid = sys.argv[2]
        price = float(sys.argv[3])
        result = bridge.close(pid, price)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "check":
        from options.margin_tracker import MarginTracker
        tracker = MarginTracker()
        result = tracker.run_check()
        print(tracker.format_report(result))

    elif cmd == "signal":
        result = bridge.signal()
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "portfolio":
        result = bridge.portfolio()
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))

    else:
        print(f"未知命令: {cmd}")
        print("可用命令: list | open | close | check | signal | portfolio")
        sys.exit(1)


if __name__ == "__main__":
    main()
