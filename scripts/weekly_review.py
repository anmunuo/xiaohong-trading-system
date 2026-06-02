#!/usr/bin/env python3
"""
周度复盘 - v2.0
=============
每周六 09:00 生成周度交易总结。

从 holdings.json 的已平仓记录和实时持仓计算：
- 本周胜率/盈亏比
- 持仓概览
- 重大决策回顾
"""

import sys
import json
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from data_pipeline import get_stock_realtime


def load_holdings():
    path = BASE_DIR / "data" / "holdings.json"
    if path.exists():
        return json.loads(path.read_text(encoding='utf-8'))
    return {}


def generate_weekly():
    data = load_holdings()
    account = data.get("accountInfo", {})
    holdings = data.get("holdings", [])
    closed = data.get("closedPositions", [])

    now = datetime.now()
    week_start = now - timedelta(days=now.weekday())  # 本周一
    week_start_str = week_start.strftime('%Y-%m-%d')
    date_str = now.strftime('%Y-%m-%d')

    # 本周平仓
    week_closed = [t for t in closed if t.get('sellDate', '') >= week_start_str]

    wins = [t for t in week_closed if t.get('profit', 0) > 0]
    losses = [t for t in week_closed if t.get('profit', 0) <= 0]
    win_rate = len(wins) / len(week_closed) * 100 if week_closed else 0
    avg_win = sum(t['profit'] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t['profit'] for t in losses) / len(losses) if losses else 0
    total_pnl = sum(t.get('profit', 0) for t in week_closed)

    # 实时持仓
    codes = [h['code'] for h in holdings]
    quotes = get_stock_realtime(codes) if codes else {}
    total_mv = 0
    for h in holdings:
        q = quotes.get(h['code'], {})
        h['_price'] = q.get('close', h.get('lastPrice', 0))
        h['_mv'] = round(h['_price'] * h['shares'], 2)
        total_mv += h['_mv']

    available = account.get('availableCash', 0)
    net = available + total_mv
    total_pnl_all = net - account.get('initialCapital', net)

    lines = []
    lines.append("=" * 60)
    lines.append(f"📊 文工团 · 周度复盘 | {week_start_str} ~ {date_str}")
    lines.append("=" * 60)
    lines.append("")
    lines.append("━━━  一、本周交易统计  ━━━")
    lines.append(f"交易笔数：{len(week_closed)} 笔")
    lines.append(f"胜率：{win_rate:.1f}%（盈 {len(wins)} / 亏 {len(losses)}）")
    lines.append(f"平均盈利：¥{avg_win:,.0f} | 平均亏损：¥{abs(avg_loss):,.0f}")
    lines.append(f"盈亏比：{abs(avg_win/avg_loss):.2f}:1" if avg_loss else "盈亏比：N/A")
    lines.append(f"已实现盈亏：¥{total_pnl:+,.0f}")
    lines.append("")

    lines.append("━━━  二、当前持仓  ━━━")
    for h in holdings:
        pnl = h.get('unrealizedPnL', 0)
        pnl_pct = h.get('pnlPct', 0)
        emoji = "🟢" if pnl >= 0 else "🔴"
        price = h.get('_price', h.get('lastPrice', 0))
        lines.append(f"  {emoji} {h['name']} ({h['code']})")
        lines.append(f"     ¥{price:.2f} × {h['shares']}股 = ¥{h.get('_mv',0):,.0f} | {pnl_pct:+.1f}%")
    lines.append("")

    lines.append("━━━  三、账户总览  ━━━")
    lines.append(f"当前净值：¥{net:,.0f}")
    lines.append(f"本周总盈亏：¥{total_pnl_all:+,.0f}（含浮动）")
    lines.append(f"总收益率：{(net/account.get('initialCapital',1)-1)*100:+.2f}%")
    lines.append("")

    lines.append("━━━  四、反思与改进  ━━━")
    if losses:
        loss_names = {t.get('name','?') for t in losses}
        lines.append(f"亏损标的：{', '.join(loss_names)}")
    if win_rate < 50 and week_closed:
        lines.append("⚠️ 本周胜率偏低，复盘选股和入场时机")
    if total_pnl < 0:
        lines.append("⚠️ 本周净亏损，检查止损执行是否到位")
    if not week_closed:
        lines.append("本周无交易记录")
    lines.append("")

    lines.append(f"═══ 数据来源：holdings.json + data fetch | {date_str} ═══")

    return "\n".join(lines)


def main():
    print("📊 文工团 · 周度复盘 v2.0")
    report = generate_weekly()
    print(report)

    date_str = datetime.now().strftime('%Y-%m-%d')
    reports_dir = BASE_DIR / "reports" / "daily"
    reports_dir.mkdir(parents=True, exist_ok=True)
    md_path = reports_dir / f"文工团周复盘-{date_str}.md"
    md_path.write_text(report, encoding='utf-8')
    print(f"\n✅ 报告已保存: {md_path}")


if __name__ == "__main__":
    main()
