#!/usr/bin/env python3
"""
狙击手 · 日内监控 v3.0
======================
09:35 起每 30 分钟扫描持仓 + 推荐池，输出分级交易信号。

v3.0 升级:
  · 止损监控 — 实时价格 vs 止损线，触发/逼近分级告警
  · 多维信号 — 涨跌 + 量比 + MA偏离 + 板块相对强弱
  · V8.0 集成 — 标记持仓是否在今日推荐池
  · 入场信号 — 推荐池标的达到建仓条件时提醒
  · 竞价叠加 — 早盘复用 auction_features
  · 四级优先级 — P0🔴止损 P1🟡逼近 P2🔵变动 P3⚪常规

用法:
  python3 sniper.py [--push] [--auction]
"""

__version__ = "3.1.0"

import sys, os, json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(SCRIPT_DIR))

from data_pipeline import get_stock_realtime, get_top_flow_stocks, get_market_money_flow

HOLDINGS_PATH = WORKSPACE / 'data' / 'holdings.json'
POOL_PATH = SCRIPT_DIR / 'data' / 'daily_pool.json'
TARGET_POOL_PATH = SCRIPT_DIR / 'data' / 'target_pool.json'

# ═══════════════════════════════════════════
# 1. 数据加载
# ═══════════════════════════════════════════
# ═══════════════════════════════════════════

def load_holdings() -> Dict:
    """加载持仓数据"""
    if not HOLDINGS_PATH.exists():
        return {'positions': [], 'net_value': 0, 'available_cash': 0, 'alerts': []}

    try:
        data = json.loads(HOLDINGS_PATH.read_text(encoding='utf-8'))
        positions = []
        for h in data.get('holdings', []):
            for b in h.get('batches', []):
                positions.append({
                    'code': h['code'],
                    'name': h.get('name', h['code']),
                    'cost': b.get('costPrice', 0),
                    'stop_loss': b.get('stopLoss', 0),
                    'quantity': b.get('quantity', 0),
                    'trailing_stop': b.get('trailingStopPrice', 0),
                    'unrealized_pnl': b.get('unrealizedPnL', 0),
                })
        return {
            'positions': positions,
            'net_value': data.get('currentNetValue', 0),
            'available_cash': data.get('availableCash', 0),
            'alerts': [],
        }
    except Exception:
        return {'positions': [], 'net_value': 0, 'available_cash': 0, 'alerts': []}


def load_pool_codes() -> set:
    """加载今日推荐池代码"""
    codes = set()
    if POOL_PATH.exists():
        try:
            with open(POOL_PATH) as f:
                data = json.load(f)
            for r in data.get('recommendations', []):
                codes.add(str(r['code']))
        except Exception:
            pass
    return codes


def load_target_pool() -> Dict:
    """🆕 加载目标池 (当日可操作 3 只)"""
    if not TARGET_POOL_PATH.exists():
        return {"stocks": []}
    try:
        return json.loads(TARGET_POOL_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {"stocks": []}


# ═══════════════════════════════════════════
# 2. 持仓分析
# ═══════════════════════════════════════════

def analyze_position(pos: Dict, quote: Dict, pool_codes: set) -> Dict:
    """
    对单个持仓做多维分析，返回信号级别和操作建议。
    """
    code = pos['code']
    name = pos['name']
    cost = pos['cost']
    stop_loss = pos['stop_loss']
    trailing_stop = pos.get('trailing_stop', 0)

    close = float(quote.get('close', 0))
    change = float(quote.get('change_pct', 0))
    volume = float(quote.get('volume', 0))
    avg_vol = float(quote.get('avg_volume_5', 0))
    ma20 = float(quote.get('ma20', 0))

    # 有效性检查
    if close <= 0:
        return {
            'code': code, 'name': name, 'priority': 'P3',
            'signal': '等待数据', 'action': '—',
            'detail': '实时数据未就绪',
            'in_pool': code in pool_codes,
        }

    # ═══ P0: 止损触发 ═══
    effective_stop = trailing_stop if trailing_stop > stop_loss else stop_loss
    if effective_stop > 0 and close <= effective_stop:
        pnl_pct = (close - cost) / cost * 100 if cost > 0 else 0
        return {
            'code': code, 'name': name, 'priority': 'P0',
            'signal': '🔴 止损触发',
            'action': '立即清仓',
            'detail': f'现价 {close:.2f} ≤ 止损 {effective_stop:.2f}，浮亏 {pnl_pct:+.1f}%',
            'in_pool': code in pool_codes,
            'price': close, 'change': change,
        }

    # ═══ P1: 逼近止损（3% 以内） ═══
    if effective_stop > 0 and close > 0:
        distance = (close - effective_stop) / close * 100
        if 0 < distance <= 3:
            return {
                'code': code, 'name': name, 'priority': 'P1',
                'signal': '🟡 逼近止损',
                'action': '准备减仓',
                'detail': f'距止损 {distance:.1f}%（{close:.2f} vs {effective_stop:.2f}）',
                'in_pool': code in pool_codes,
                'price': close, 'change': change,
            }

    # ═══ P2: 显著变动 ═══
    vol_ratio = volume / avg_vol if avg_vol > 0 else 1
    ma_dev = (close - ma20) / ma20 * 100 if ma20 > 0 else 0

    if abs(change) > 5 or vol_ratio > 3:
        # 构建详细信号
        parts = []
        if change > 5:
            parts.append(f'大涨 {change:+.1f}%')
        elif change < -5:
            parts.append(f'大跌 {change:+.1f}%')

        if vol_ratio > 3:
            parts.append(f'爆量 {vol_ratio:.1f}x')

        pnl = (close - cost) / cost * 100 if cost > 0 else 0

        if change > 5 and vol_ratio > 2:
            action = '移动止盈上移'
        elif change < -5:
            action = '查基本面利空'
        else:
            action = '密切关注'

        return {
            'code': code, 'name': name, 'priority': 'P2',
            'signal': '🔵 ' + ' · '.join(parts),
            'action': action,
            'detail': f'量比 {vol_ratio:.1f}x · MA20偏离 {ma_dev:+.1f}% · 浮盈 {pnl:+.1f}%',
            'in_pool': code in pool_codes,
            'price': close, 'change': change,
        }

    # ═══ P3: 常规 ═══
    pnl = (close - cost) / cost * 100 if cost > 0 else 0
    sig = '📈 温和上涨' if change > 1 else ('📉 小幅回调' if change < -1 else '➖ 横盘')

    return {
        'code': code, 'name': name, 'priority': 'P3',
        'signal': sig,
        'action': '持有' if pnl >= 0 else '观察',
        'detail': f'{change:+.1f}% · 浮盈 {pnl:+.1f}%',
        'in_pool': code in pool_codes,
        'price': close, 'change': change,
    }


# ═══════════════════════════════════════════
# 3. 入场信号（目标池标的 → 量比 + 分时K线）
# ═══════════════════════════════════════════

def analyze_entries(target_pool_stocks: List[Dict], holdings_codes: set) -> List[Dict]:
    """
    🆕 v3.1 从目标池中分析入场信号。

    使用量比 + 分时K线技术面决定开仓:
      · 量比 > 1.5 → 放量，看方向
      · 分时K线形态 → V型反转/突破前高/缩量回踩MA
      · 综合判断 → 建仓/等信号/观望
    """
    entries = []

    if not target_pool_stocks:
        return entries

    # 过滤已持仓
    codes = [s["code"] for s in target_pool_stocks if s["code"] not in holdings_codes]
    if not codes:
        return entries

    # 获取实时行情
    try:
        quotes = get_stock_realtime(codes)
    except Exception:
        return entries

    # 逐只分析
    for s in target_pool_stocks:
        code = s["code"]
        if code in holdings_codes:
            continue

        q = quotes.get(code, {})
        if not q or not q.get("close"):
            continue

        close = float(q.get("close", 0))
        change = float(q.get("change_pct", 0))
        if close <= 0:
            continue

        # ── 量比分析 ──
        vol_ratio = _get_volume_ratio(code, q)

        # ── 分时K线分析 ──
        intraday_signal = _analyze_intraday_kline(code, close)

        # ── 综合入场判断 ──
        entry_reason, entry_ready = _build_entry_signal(
            code, q.get("name", code), close, change, vol_ratio, intraday_signal, s
        )

        entries.append({
            "code": code,
            "name": q.get("name", code),
            "price": close,
            "change": round(change, 1),
            "vol_ratio": round(vol_ratio, 1),
            "intraday_signal": intraday_signal,
            "reason": entry_reason,
            "entry_ready": entry_ready,
            "target_score": s.get("score", 0),
            "parliament": s.get("parliament", {}).get("bias", "?"),
        })

    # 按 entry_ready 排序
    entries.sort(key=lambda x: (x["entry_ready"], x.get("target_score", 0)), reverse=True)
    return entries


def _get_volume_ratio(code: str, quote: dict) -> float:
    """获取量比"""
    vol = float(quote.get("volume", 0))
    # 从挂载的 K 线数据中获取
    try:
        kline_vol = float(quote.get("avg_volume_5", 0))
    except Exception:
        kline_vol = 0
    if kline_vol > 0:
        return round(vol / kline_vol, 2)
    # Fallback: 使用 quote 中的成交量比
    return float(quote.get("volume_ratio", 1.0))


def _analyze_intraday_kline(code: str, current_price: float) -> dict:
    """
    🆕 分时K线技术面分析。

    拉取 5 分钟分时K线 (48 根 = 4小时)，判断:
      · 趋势: 均线上行/下行/横盘
      · 形态: V反/突破/回踩/冲高回落
      · 量价: 放量涨/缩量跌/放量滞涨
    """
    signal = {"pattern": "横盘", "trend": "neutral", "volume_ok": False, "ready": False}

    try:
        from data_pipeline import get_intraday_minutes
        bars = get_intraday_minutes(code, scale=5, count=48)
    except Exception:
        return signal

    if not bars or len(bars) < 10:
        return signal

    closes = [b.get("close", 0) for b in bars if b.get("close", 0) > 0]
    volumes = [b.get("volume", 0) for b in bars if b.get("volume", 0) > 0]

    if len(closes) < 10:
        return signal

    # 计算短期均线 (前5根/前10根)
    ma5 = sum(closes[-5:]) / len(closes[-5:])
    ma10 = sum(closes[-10:]) / len(closes[-10:])
    last_close = closes[-1]

    # 趋势判断
    if ma5 > ma10 and last_close > ma5:
        signal["trend"] = "up"
    elif ma5 < ma10 and last_close < ma5:
        signal["trend"] = "down"
    else:
        signal["trend"] = "neutral"

    # 形态识别
    recent_3 = closes[-3:]
    if len(recent_3) == 3:
        if recent_3[0] > recent_3[1] and recent_3[1] < recent_3[2]:
            signal["pattern"] = "V型反转"
        elif recent_3[0] < recent_3[1] < recent_3[2]:
            signal["pattern"] = "连续上攻"
        elif recent_3[0] > recent_3[1] > recent_3[2]:
            signal["pattern"] = "连续回落"

    # 量价关系
    if len(volumes) >= 5:
        recent_vol = sum(volumes[-3:]) / 3
        avg_vol = sum(volumes) / len(volumes)
        if recent_vol > avg_vol * 1.3:
            signal["volume_ok"] = True

    # 综合入场判断
    if (signal["trend"] == "up" and signal["pattern"] in ("V型反转", "连续上攻")
            and signal["volume_ok"]):
        signal["ready"] = True

    return signal


def _build_entry_signal(code: str, name: str, close: float, change: float,
                        vol_ratio: float, kline: dict, target: dict) -> tuple:
    """
    综合量比 + 分时K线 + 目标池评分 → 入场建议。
    返回 (reason, entry_ready)
    """
    parliament_bias = target.get("parliament", {}).get("bias", "未知")
    score = target.get("score", 0)

    reasons = []

    # 量比判断
    if vol_ratio > 2.0:
        reasons.append(f"强放量{vol_ratio:.1f}x")
    elif vol_ratio > 1.5:
        reasons.append(f"放量{vol_ratio:.1f}x")
    elif vol_ratio < 0.8:
        reasons.append(f"缩量{vol_ratio:.1f}x")

    # 分时K线
    reasons.append(f"分时{kline['trend']}/{kline['pattern']}")

    # 议会信号
    if "偏多" in parliament_bias:
        reasons.append("议会偏多")
    elif parliament_bias == "偏空":
        reasons.append("⚠️议会偏空")

    reason = " · ".join(reasons) if reasons else "数据不足"

    # 入场决策
    ready = False
    if kline.get("ready") and vol_ratio > 1.2 and change > -3:
        ready = True
        if vol_ratio > 1.5:
            reason += f" → 🟢 放量突破 · 可建底仓"
        else:
            reason += f" → 🟢 形态确认 · 等回踩入场"

    return reason, ready


# ═══════════════════════════════════════════
# 4. 报告生成
# ═══════════════════════════════════════════

def format_report(holdings_data: Dict, results: List[Dict],
                  entries: List[Dict], auction_enabled: bool = False) -> str:
    ts = datetime.now().strftime('%H:%M')

    # 按优先级排序
    results.sort(key=lambda x: {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}[x['priority']])

    p0 = [r for r in results if r['priority'] == 'P0']
    p1 = [r for r in results if r['priority'] == 'P1']
    nv = holdings_data['net_value']

    lines = []
    lines.append(f"🎯 狙击手 · 日内监控")
    lines.append(f"")
    lines.append(f"**时间**: {ts}  |  净值: ¥{nv:,.0f}  |  "
                 f"P0:{len(p0)} P1:{len(p1)}  |  推荐池入场: {len(entries)}只")
    lines.append(f"")

    # ═══ P0 告警 ═══
    if p0:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"### 🔴 P0 · 立即处理（{len(p0)}条）")
        lines.append(f"")
        for r in p0:
            pool_tag = " ⭐池" if r['in_pool'] else ""
            lines.append(f"**{r['code']} {r['name']}**{pool_tag}")
            lines.append(f"> {r['detail']}")
            lines.append(f"> 操作: **{r['action']}**")
            lines.append(f"")

    # ═══ P1 预警 ═══
    if p1:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"### 🟡 P1 · 需要关注（{len(p1)}条）")
        lines.append(f"")
        for r in p1:
            pool_tag = " ⭐池" if r['in_pool'] else ""
            lines.append(f"**{r['code']} {r['name']}**{pool_tag} — {r['detail']}")
            lines.append(f"> {r['action']}")
            lines.append(f"")

    # ═══ 持仓总览 ═══
    if results:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"### 持仓总览（{len(results)}只）")
        lines.append(f"")
        lines.append(f"| 代码 | 名称 | 现价 | 涨跌 | 信号 | 操作 | 池 |")
        lines.append(f"|------|------|------|------|------|------|:--:|")
        for r in results:
            price = r.get('price', 0)
            change = r.get('change', 0)
            pool_mark = '⭐' if r['in_pool'] else ''
            lines.append(
                f"| {r['code']} | {r['name']} | {price:.2f} | {change:+.1f}% | "
                f"{r['signal']} | {r['action']} | {pool_mark} |"
            )
        lines.append(f"")

    # ═══ 入场信号 ═══
    if entries:
        ready_count = sum(1 for e in entries if e.get("entry_ready"))
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"### 🎯 目标池入场（{len(entries)}只，{ready_count}只就绪）")
        lines.append(f"")
        lines.append(f"> 目标池标的 · 量比 + 分时K线 + 议会信号")
        lines.append(f"")
        for e in entries:
            status = '🟢' if e.get('entry_ready') else '⏳'
            code = e.get('code','')
            name = e.get('name','')
            price = e.get('price',0)
            change = e.get('change',0)
            vol_ratio = e.get('vol_ratio',1.0)
            parliament = e.get('parliament','?')
            target_score = e.get('target_score',0)
            reason = e.get('reason','')
            lines.append(f"{status} **{code} {name}**  "
                        f"{price:.2f} {change:+.1f}%  "
                        f"量比:{vol_ratio:.1f}  "
                        f"议会:{parliament}  评分:{target_score:.0f}")
            lines.append(f"> {reason}")
            lines.append(f"")
    # ═══ 市场环境 ═══
    try:
        mf = get_market_money_flow()
        if mf.get('data_source') != 'no_data':
            lines.append(f"---")
            lines.append(f"")
            lines.append(f"### 市场")
            lines.append(f"")
            lines.append(f"上证 {mf.get('sh_index','?')} {mf.get('sh_change',0):+.2f}%  |  "
                         f"主力 {mf.get('main_net',0):+.0f}亿")
            lines.append(f"")
    except Exception:
        pass

    lines.append(f"---")
    lines.append(f"")
    lines.append(f"*狙击手 v3.1 · {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return '\n'.join(lines)


# ═══════════════════════════════════════════
# 5. 主逻辑
# ═══════════════════════════════════════════

def run_sniper() -> tuple:
    """执行狙击手扫描，返回 (holdings_data, results, entries)"""
    holdings_data = load_holdings()
    positions = holdings_data['positions']
    pool_codes = load_pool_codes()

    results = []
    if positions:
        codes = [p['code'] for p in positions]
        try:
            quotes = get_stock_realtime(codes)
        except Exception:
            quotes = {}

        for pos in positions:
            quote = quotes.get(pos['code'], {})
            result = analyze_position(pos, quote, pool_codes)
            results.append(result)

    # 🆕 入场信号 — 从目标池分析
    holdings_codes = {p['code'] for p in positions}
    target_pool = load_target_pool()
    target_stocks = target_pool.get('stocks', [])
    entries = analyze_entries(target_stocks, holdings_codes)

    return holdings_data, results, entries


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description='狙击手 v3.1 · 日内监控')
    p.add_argument('--push', action='store_true', help='推送飞书')
    p.add_argument('--auction', action='store_true', help='叠加竞价信号')
    args = p.parse_args()

    holdings_data, results, entries = run_sniper()

    auction_enabled = args.auction
    report = format_report(holdings_data, results, entries, auction_enabled)
    print(report)

    if args.push:
        try:
            from feishu_push import push_sniper
            ok = push_sniper(title='🎯 狙击手 · 日内监控', content=report)
            print(f"\n{'✅' if ok else '❌'} 推送{'成功' if ok else '失败'}")
        except Exception as e:
            print(f"\n❌ 推送失败: {e}")


if __name__ == '__main__':
    main()
