#!/usr/bin/env python3
"""
保证金追踪器 — 实时监控期权持仓保证金健康度

功能：
  1. 加载活跃期权持仓
  2. 拉取标的最新价（复用 data_pipeline）
  3. 逐笔检查保证金健康度
  4. 分级告警（关注/危险/强平）
  5. 生成结构化报告 → 飞书推送

用法：
  python3 margin_tracker.py              # 全量检查 → 格式化报告
  python3 margin_tracker.py --json       # JSON 输出
  python3 margin_tracker.py --alerts-only # 仅输出告警持仓
"""

import sys
import os
import json
from datetime import datetime
from typing import Optional, List, Dict

# 添加 scripts 目录到 path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(SCRIPT_DIR, '..'))

from options.otc_call import OTCCallEngine, OTCPosition

try:
    from report_formatter import Report
    HAS_REPORT = True
except ImportError:
    HAS_REPORT = False


class MarginTracker:
    """保证金追踪器"""

    def __init__(self, engine: OTCCallEngine = None):
        self.engine = engine or OTCCallEngine()

    # ── 价格拉取 ──────────────────────────────────────

    def _fetch_prices(self, codes: list) -> dict:
        """
        拉取标的最新价
        优先用 data_pipeline Sina 批量快路径，失败回退到 akshare
        """
        if not codes:
            return {}

        try:
            from data_pipeline.market import get_stock_realtime
            result = get_stock_realtime(codes)
            prices = {}
            for code, info in result.items():
                close = info.get('close', 0)
                if close and close > 0:
                    prices[code] = close
            return prices
        except Exception as e:
            print(f"[MarginTracker] data_pipeline 拉取失败: {e}", file=sys.stderr)

        # Fallback: akshare 逐只查询
        try:
            import akshare as ak
            prices = {}
            for code in codes:
                try:
                    df = ak.stock_zh_a_spot_em()
                    row = df[df['代码'] == code]
                    if not row.empty:
                        prices[code] = float(row['最新价'].iloc[0])
                except Exception:
                    continue
            return prices
        except Exception as e:
            print(f"[MarginTracker] akshare fallback 失败: {e}", file=sys.stderr)

        return {}

    # ── 保证金检查 ────────────────────────────────────

    def run_check(self) -> dict:
        """全量保证金检查"""
        active = self.engine.get_active_positions()
        if not active:
            return {
                'timestamp': datetime.now().isoformat(),
                'position_count': 0,
                'alerts': [],
                'summary': {'ok': 0, 'warning': 0, 'danger': 0, 'liquidate': 0},
            }

        codes = list(set(p.code for p in active))
        prices = self._fetch_prices(codes)

        alerts = []
        summary = {'ok': 0, 'warning': 0, 'danger': 0, 'liquidate': 0}

        for pos in active:
            price = prices.get(pos.code)
            if price is None:
                # 无法获取价格 → 标记为未知
                alerts.append({
                    'code': pos.code,
                    'name': pos.name,
                    'position_id': pos.position_id,
                    'entry_price': pos.entry_price,
                    'current_price': None,
                    'status': 'unknown',
                    'level': -1,
                    'message': '⚠️ 无法获取最新价',
                    'action': '检查数据源',
                    'margin_health': None,
                    'unrealized_pnl': None,
                })
                continue

            check = self.engine.check_margin(pos, price)
            alerts.append({
                'code': pos.code,
                'name': pos.name,
                'position_id': pos.position_id,
                'entry_price': pos.entry_price,
                'current_price': price,
                **{k: v for k, v in check.items() if k != 'code'},
            })
            summary[check['status']] = summary.get(check['status'], 0) + 1

        return {
            'timestamp': datetime.now().isoformat(),
            'position_count': len(active),
            'prices_fetched': len(prices),
            'alerts': alerts,
            'summary': summary,
        }

    # ── 报告生成 ──────────────────────────────────────

    def format_report(self, result: dict) -> str:
        """生成格式化报告"""
        if HAS_REPORT:
            return self._format_report_rich(result)
        return self._format_report_plain(result)

    def _format_report_rich(self, result: dict) -> str:
        """富文本报告（report_formatter）"""
        s = result['summary']
        total_alerts = s.get('liquidate', 0) + s.get('danger', 0) + s.get('warning', 0)

        color = 'red' if s.get('liquidate', 0) > 0 else \
                'orange' if s.get('danger', 0) > 0 else \
                'yellow' if s.get('warning', 0) > 0 else 'green'

        r = Report(
            title="期权保证金追踪",
            icon="🛡️",
            color=color
        )
        r.header_meta(
            时间=datetime.now().strftime("%H:%M:%S"),
            持仓=f"{result['position_count']}笔",
            告警=f"{total_alerts}个",
            强平=f"{s.get('liquidate', 0)}个",
        )

        alerts = result['alerts']
        if not alerts:
            r.section("状态")
            r.text("✅ 暂无活跃期权持仓")
            return r.markdown()

        # 按告警级别排序：强平 > 危险 > 关注 > ok
        alerts_sorted = sorted(alerts, key=lambda a: a['level'], reverse=True)

        r.section("保证金明细")
        rows = []
        for a in alerts_sorted:
            icon_map = {3: '🔴', 2: '🟠', 1: '🟡', 0: '🟢', -1: '⚪'}
            icon = icon_map.get(a['level'], '⚪')

            health_str = f"{a['margin_health']*100:.0f}%" if a['margin_health'] is not None else "N/A"
            pnl_str = f"¥{a['unrealized_pnl']:+,.0f}" if a['unrealized_pnl'] is not None else "N/A"
            price_str = f"¥{a['current_price']:.2f}" if a['current_price'] else "N/A"

            short_code = a['code'].replace('.SZ', '').replace('.SH', '')[-6:]

            rows.append([
                f"{icon} {short_code}",
                a['name'][:6],
                price_str,
                health_str,
                pnl_str,
                a.get('message', '')[:12],
            ])

        r.table(
            ["代码", "名称", "现价", "保证金", "浮动盈亏", "状态"],
            rows
        )

        # 告警详情
        critical = [a for a in alerts_sorted if a['level'] >= 2]
        if critical:
            r.section("⚠️ 需处理")
            for a in critical:
                r.alert(
                    f"{a['code']} {a['name']} — {a.get('message', '')}\n"
                    f"保证金仅剩 {a['margin_health']*100:.0f}%，{a.get('action', '')}",
                    "critical" if a['level'] >= 3 else "warning"
                )

        r.footer(f"数据 data_pipeline · {result['timestamp'][:19]}")
        return r.markdown()

    def _format_report_plain(self, result: dict) -> str:
        """纯文本报告（无 report_formatter 时）"""
        lines = [f"🛡️ 期权保证金追踪 | {result['timestamp'][:19]}",
                 f"持仓 {result['position_count']} 笔"]
        for a in result['alerts']:
            icon = {3: '🔴', 2: '🟠', 1: '🟡', 0: '🟢', -1: '⚪'}[a['level']]
            pnl = f"¥{a['unrealized_pnl']:+,.0f}" if a['unrealized_pnl'] else "N/A"
            health = f"{a['margin_health']*100:.0f}%" if a['margin_health'] else "?"
            lines.append(f"  {icon} {a['code']} {a['name']} | 保证金{health} | {pnl}")
        return "\n".join(lines)

    # ── JSON 输出 ─────────────────────────────────────

    def to_json(self, result: dict) -> str:
        return json.dumps(result, indent=2, ensure_ascii=False, default=str)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="保证金追踪器")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--alerts-only", action="store_true",
                        help="仅输出告警持仓 (level >= 1)")
    args = parser.parse_args()

    tracker = MarginTracker()
    result = tracker.run_check()

    if args.alerts_only:
        result['alerts'] = [a for a in result['alerts'] if a['level'] >= 1]
        # ── 无告警时静默：cron no_agent 模式下 stdout 空 = 不发消息 ──
        if not result['alerts']:
            return  # 静默退出，零输出

    if args.json:
        print(tracker.to_json(result))
    else:
        print(tracker.format_report(result))

    # 退出码：有强平风险 → exit 1（cron 告警）
    if result['summary'].get('liquidate', 0) > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
