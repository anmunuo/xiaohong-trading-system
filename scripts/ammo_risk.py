#!/usr/bin/env python3
"""
弹药库风控 v4.1
===============
盘后风控检查：持仓同步 → 止盈追踪 → 回撤监控 → 行业集中度 → 风险报告。

v4.1 修复 (2026-06-01):
  · P0-1: cron 自动 --update，不再手工触发
  · P0-2: 净值单一真相源 (accountInfo.currentNetValue)
  · P1-3: R值自动计算 = 净值 × 仓位上限% × 1/8 × 凯利系数
  · P1-4: 流动性检查改用 5 日均量
  · P1-5: 行业分类 tushare 官方优先 + 关键词 fallback
  · P1-6: 移动止盈加 ATR 动态缓冲选项
  · P2-7: --update 模式增加 V8.0 池交叉标记
  · P2-8: 净值历史数组（替代正则解析报告）
  · P2-9: update/report 共享行情缓存，避免重复拉取

用法:
  python3 ammo_risk.py              # Markdown 报告（含自动 update）
  python3 ammo_risk.py --update     # 仅同步持仓数据
  python3 ammo_risk.py --report     # 仅生成报告（不复读行情）
"""

__version__ = "4.1.0"

import sys, json, os, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from data_pipeline import get_market_money_flow, get_stock_realtime
from report_formatter import Report
from feishu_push import push_report as _push_report

HOLDINGS_PATH = BASE_DIR / "data" / "holdings.json"
POOL_PATH = SCRIPT_DIR / "data" / "daily_pool.json"
MAX_NV_HISTORY = 30  # 保留最近 30 天净值历史

# ── 行业关键词 fallback（tushare 不可用时使用）──
SECTOR_KW_FALLBACK = {
    '通信':   ['光', '通信', '缆', '亨通', '长飞', '中天'],
    '新能源': ['风', '光伏', '锂', '电池', '储', '氢', '绿'],
    '半导体': ['芯', '半导', '晶', '微'],
    '电气设备': ['电', '变压', '开关', '配', '电网'],
    'IT服务': ['AI', '智能', '算', '机器', '软', '数据'],
    '食品饮料': ['酒', '食品', '饮', '乳'],
    '医药生物': ['药', '医', '生物'],
    '机械设备': ['设备', '装备', '机械', '机床'],
    '基础化工': ['化工', '化学', '材料', '新材'],
    '有色金属': ['铜', '铝', '金', '稀土', '矿'],
}

# ── 全局行情缓存（update → report 复用）──
_quote_cache: Dict = {}
_cache_time: float = 0.0


# ═══════════════════════════════════════════
# 1. 数据加载 / 保存
# ═══════════════════════════════════════════

def load_holdings() -> Dict:
    if HOLDINGS_PATH.exists():
        return json.loads(HOLDINGS_PATH.read_text(encoding='utf-8'))
    return {}


def save_holdings(data: Dict):
    data["updateTime"] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S+08:00')
    HOLDINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_pool() -> Dict:
    """加载 V8.0 推荐池 → {code: info}"""
    if POOL_PATH.exists():
        try:
            with open(POOL_PATH) as f:
                data = json.load(f)
            return {str(r['code']): r for r in data.get('recommendations', [])}
        except Exception:
            pass
    return {}


# ═══════════════════════════════════════════
# 2. 净值单一真相源
# ═══════════════════════════════════════════

def get_net_value(data: Dict) -> float:
    """从 accountInfo 读取净值（单一真相源）"""
    return float(data.get('accountInfo', {}).get('currentNetValue', 0))


def set_net_value(data: Dict, nv: float):
    """写入净值（唯一入口）"""
    if 'accountInfo' not in data:
        data['accountInfo'] = {}
    data['accountInfo']['currentNetValue'] = round(nv, 2)
    # 同步到 riskManagement（兼容旧代码读取）
    if 'rules' not in data:
        data['rules'] = {}
    if 'riskManagement' not in data['rules']:
        data['rules']['riskManagement'] = {}
    data['rules']['riskManagement']['currentNetValue'] = round(nv, 2)


def calc_r_value(data: Dict) -> float:
    """R 值 = 净值 × 仓位上限% × 1/R_DENOMINATOR × 凯利值"""
    nv = get_net_value(data)
    rules = data.get('rules', {})
    max_pct = float(rules.get('maxPositionPerStock', 33.3))
    kelly = float(rules.get('riskManagement', {}).get('kellyValue', 0.2))
    r_val = nv * (max_pct / 100) * 0.125 * kelly  # 0.125 = 1/R_DENOMINATOR
    return round(r_val, 2)


# ═══════════════════════════════════════════
# 3. 净值历史
# ═══════════════════════════════════════════

def update_nv_history(data: Dict, nv: float):
    """追加今日净值到历史数组"""
    today = datetime.now().strftime('%Y-%m-%d')
    history = data.get('netValueHistory', [])
    # 去重同日
    if history and history[-1].get('date') == today:
        history[-1] = {'date': today, 'value': round(nv, 2)}
    else:
        history.append({'date': today, 'value': round(nv, 2)})
    # 截断
    if len(history) > MAX_NV_HISTORY:
        history = history[-MAX_NV_HISTORY:]
    data['netValueHistory'] = history


def get_weekly_change(data: Dict) -> Optional[Dict]:
    """从净值历史计算 5 日变化"""
    history = data.get('netValueHistory', [])
    if len(history) < 5:
        return None
    curr = history[-1]['value']
    prev = history[-5]['value']
    change = (curr - prev) / prev * 100 if prev else 0
    return {
        'prev_nv': prev,
        'change': round(change, 2),
        'date': history[-5]['date'],
    }


# ═══════════════════════════════════════════
# 4. 行业分类（tushare 优先 + 关键词 fallback）
# ═══════════════════════════════════════════

_industry_cache: Dict[str, str] = {}
_industry_cache_loaded = False


def _load_tushare_industries() -> Dict[str, str]:
    """从 tushare 加载全市场行业分类"""
    global _industry_cache_loaded
    if _industry_cache_loaded:
        return _industry_cache
    _industry_cache_loaded = True

    try:
        import tushare as ts
        from data_pipeline import _load_tushare_token
        token = _load_tushare_token()
        if not token:
            return {}
        pro = ts.pro_api(token)
        df = pro.stock_basic(
            exchange='', list_status='L',
            fields='ts_code,industry'
        )
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                code = str(row['ts_code']).split('.')[0]
                industry = str(row.get('industry', '')).strip()
                if industry and industry != 'nan':
                    _industry_cache[code] = industry
        return _industry_cache
    except Exception:
        return {}


def classify_industry(code: str, name: str = '') -> str:
    """行业分类：tushare 官方 → 关键词 fallback → '综合'"""
    industries = _load_tushare_industries()
    if code in industries:
        return industries[code]

    # fallback: 名称关键词
    for sector, kws in SECTOR_KW_FALLBACK.items():
        for kw in kws:
            if kw in name:
                return sector
    return '综合'


# ═══════════════════════════════════════════
# 5. 行情缓存（update → report 复用）
# ═══════════════════════════════════════════

def get_cached_quotes(codes: List[str], force_refresh: bool = False) -> Dict:
    """带缓存的行情查询"""
    global _quote_cache, _cache_time
    now = time.time()
    if not force_refresh and _quote_cache and (now - _cache_time) < 120:
        # 2 分钟内复用
        missing = [c for c in codes if c not in _quote_cache]
        if not missing:
            return _quote_cache
    else:
        missing = codes

    if missing:
        fresh = get_stock_realtime(missing)
        _quote_cache.update(fresh)
        _cache_time = now

    return {c: _quote_cache.get(c, {}) for c in codes}


# ═══════════════════════════════════════════
# 6. 回撤追踪
# ═══════════════════════════════════════════

def update_drawdown(data: Dict, nv: float):
    peak = data.get('peakNetValue', 0)
    if nv > peak:
        data['peakNetValue'] = nv
        data['peakNetValueDate'] = datetime.now().strftime('%Y-%m-%d')
        data['currentDrawdown'] = 0
    elif peak > 0:
        data['currentDrawdown'] = round((peak - nv) / peak * 100, 2)


# ═══════════════════════════════════════════
# 7. 移动止盈（v4.1 增加动态缓冲）
# ═══════════════════════════════════════════

def update_trailing_stops(holdings: List[Dict], quotes: Dict, data: Dict) -> int:
    """
    移动止盈：涨 20% 启动，每涨 10% 上移 10%（基于成本）。
    增加动态缓冲：止损距现价至少保留 5%（基于 ATR 估算）。
    """
    risk_mgmt = data.get('rules', {}).get('riskManagement', {})
    trail_cfg = risk_mgmt.get('stopLossStrategies', {}).get('trailingStopLoss', {})
    initial_trigger = float(trail_cfg.get('initialTrigger', 0.20))
    trigger_step = float(trail_cfg.get('triggerStep', 0.10))
    move_step = float(trail_cfg.get('moveStep', 0.10))
    today = datetime.now().strftime('%Y-%m-%d')

    updates = 0
    for h in holdings:
        code = h['code']
        q = quotes.get(code, {})
        price = float(q.get('close', 0))
        if price <= 0:
            continue

        for trade in h.get('trades', []):
            cost = float(trade.get('open_price', 0) or trade.get('price', 0))
            if cost <= 0:
                continue

            profit_pct = (price - cost) / cost
            old_stop = float(trade.get('stopLoss', 0))

            if profit_pct >= initial_trigger:
                extra = profit_pct - initial_trigger
                steps = int(extra / trigger_step) + 1
                new_stop = round(cost * (1 + move_step * steps), 2)

                # 动态缓冲：止损距现价至少 3%
                min_distance = price * 0.03
                max_allowed_stop = price - min_distance
                if new_stop > max_allowed_stop:
                    new_stop = round(max_allowed_stop, 2)

                if old_stop == 0 or new_stop > old_stop:
                    trade['stopLoss'] = new_stop
                    trade['trailingStop'] = new_stop
                    trade['trailingStopUpdated'] = today
                    updates += 1

    return updates


# ═══════════════════════════════════════════
# 8. 行业集中度
# ═══════════════════════════════════════════

def calc_sector_concentration(holdings: List[Dict], quotes: Dict,
                              net_value: float) -> Dict:
    sectors = {}
    for h in holdings:
        code = h['code']
        name = h.get('name', code)
        sector = classify_industry(code, name)
        q = quotes.get(code, {})
        price = float(q.get('close', 0))
        shares = int(h.get('shares', 0))
        mv = price * shares if price and shares else float(h.get('totalCost', 0))

        if sector not in sectors:
            sectors[sector] = {'mv': 0, 'stocks': [], 'codes': []}
        sectors[sector]['mv'] += mv
        sectors[sector]['stocks'].append(name)
        sectors[sector]['codes'].append(code)

    if net_value > 0:
        for s in sectors:
            sectors[s]['pct'] = round(sectors[s]['mv'] / net_value * 100, 1)

    return sectors


# ═══════════════════════════════════════════
# 9. 流动性风险（v4.1: 5日均量）
# ═══════════════════════════════════════════

def _get_avg_amount_5d(codes: List[str]) -> Dict[str, float]:
    """获取 5 日均成交额（万元）"""
    result = {}
    import subprocess
    for code in codes:
        try:
            proc = subprocess.run(
                ['data', 'fetch', 'stock', '--symbol', code, '--category', 'daily', '--days', '7'],
                capture_output=True, text=True, timeout=20,
                env={**os.environ, 'HERMES_PROFILE': 'xiaohong'}
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                for p in data.get('providers_attempted', []):
                    records = p.get('data', [])
                    if isinstance(records, list) and len(records) >= 5:
                        amounts = [float(r.get('amount', 0)) for r in records[-5:]]
                        avg = sum(amounts) / len(amounts)
                        result[code] = round(avg, 0)
                        break
        except Exception:
            pass
    return result


def check_liquidity(holdings: List[Dict], quotes: Dict,
                    avg_amounts: Dict[str, float]) -> List[Dict]:
    """检查持仓规模 vs 5日均成交额"""
    warnings = []
    for h in holdings:
        code = h['code']
        q = quotes.get(code, {})
        avg_amt = avg_amounts.get(code, 0)
        if avg_amt <= 0:
            continue

        price = float(q.get('close', 0))
        shares = int(h.get('shares', 0))
        mv = price * shares if price and shares else 0
        if mv <= 0:
            continue

        # 卖出 20% 持仓的冲击成本
        sell_amount = mv * 0.2 / 1e4  # 万元
        impact = sell_amount / avg_amt * 100
        if impact > 5:
            warnings.append({
                'code': code,
                'name': h.get('name', code),
                'impact': round(impact, 1),
                'detail': (
                    f'卖出20%持仓约¥{sell_amount:.0f}万，'
                    f'占5日均量{avg_amt:.0f}万的{impact:.1f}%'
                ),
            })
    return warnings


# ═══════════════════════════════════════════
# 10. --update 模式
# ═══════════════════════════════════════════

def run_update() -> Tuple[Dict, Dict]:
    """
    同步持仓数据 → 返回 (data, quotes) 供报告复用。

    五项操作:
      1. 市值同步
      2. 净值修正（单一真相源）
      3. 移动止盈
      4. 回撤追踪
      5. R 值更新
      6. V8.0 池交叉标记 (v4.1)
      7. 净值历史追加 (v4.1)
    """
    data = load_holdings()
    if not data:
        print("⚠️ holdings.json 不存在或为空")
        return data, {}

    holdings = data.get('holdings', [])
    codes = [h['code'] for h in holdings]
    quotes = get_cached_quotes(codes, force_refresh=True)
    today = datetime.now().strftime('%Y-%m-%d')
    pool = load_pool()
    pool_codes = set(pool.keys())

    total_mv = 0.0

    for h in holdings:
        code = h['code']
        q = quotes.get(code, {})
        price = float(q.get('close', 0))
        if price <= 0:
            continue

        shares = int(h.get('shares', 0))
        cost_total = float(h.get('totalCost', 0))

        # 1. 市值同步
        h['lastPrice'] = price
        h['marketValue'] = round(price * shares, 2)
        h['unrealizedPnL'] = round(h['marketValue'] - cost_total, 2)
        h['pnlPct'] = round(h['unrealizedPnL'] / cost_total * 100, 2) if cost_total else 0
        h['lastUpdate'] = q.get('trade_date', today)
        total_mv += h['marketValue']

        # V8.0 池交叉标记
        h['inPool'] = code in pool_codes
        h['poolCheckedAt'] = today

    # 2. 净值修正
    available = float(data.get('accountInfo', {}).get('availableCash', 0))
    new_nv = round(available + total_mv, 2)
    set_net_value(data, new_nv)

    # 3. 移动止盈
    trailing_updates = update_trailing_stops(holdings, quotes, data)

    # 4. 回撤追踪
    update_drawdown(data, new_nv)

    # 5. R 值计算
    r_val = calc_r_value(data)
    data['rules']['riskManagement']['currentRValue'] = r_val
    data['rules']['riskManagement']['rValueUpdateTime'] = today

    # 6. 净值历史
    update_nv_history(data, new_nv)

    save_holdings(data)

    dd = data.get('currentDrawdown', 0)
    peak = data.get('peakNetValue', 0)
    print(f"✅ 持仓已同步 | 净值 ¥{new_nv:,.0f} | "
          f"止盈更新 {trailing_updates}批次 | "
          f"R值 ¥{r_val:,.0f} | "
          f"峰值 ¥{peak:,.0f} | 回撤 {dd:.2f}%")

    return data, quotes


# ═══════════════════════════════════════════
# 11. 报告生成
# ═══════════════════════════════════════════

def build_risk_report(holdings_data: Dict = None,
                      cached_quotes: Dict = None) -> Report:
    """
    生成风控报告。
    如果传入 cached_quotes（来自 run_update），不再重复拉取行情。
    """
    if holdings_data is None:
        holdings_data = load_holdings()

    account = holdings_data.get('accountInfo', {})
    holdings = holdings_data.get('holdings', [])
    rules = holdings_data.get('rules', {})
    risk_mgmt = rules.get('riskManagement', {})

    net_value = get_net_value(holdings_data)
    initial = float(account.get('initialCapital', 100000))
    r_value = float(risk_mgmt.get('currentRValue', 0))
    max_pos_pct = float(rules.get('maxPositionPerStock', 33.3))
    peak_nv = float(holdings_data.get('peakNetValue', 0))
    drawdown = float(holdings_data.get('currentDrawdown', 0))
    pool = load_pool()
    pool_codes = set(pool.keys())

    now = datetime.now()
    date_str = now.strftime('%Y-%m-%d')
    time_str = now.strftime('%H:%M')
    total_return = ((net_value - initial) / initial * 100) if initial else 0
    color = "green" if total_return >= 0 else "red"

    r = Report(title="弹药库 · 收盘风控", icon="🛡️", color=color)
    r.header_meta(
        日期=date_str,
        净值=f"¥{net_value:,.0f}",
        总收益=f"{total_return:+.2f}%",
        R值=f"¥{r_value:,.0f}",
        回撤=f"{drawdown:.1f}%" if drawdown else "—",
    )

    # ── 大盘 ──
    market_flow = get_market_money_flow()
    if market_flow.get('data_source') != 'no_data':
        main_net = market_flow.get('main_net', 0)
        emoji = "🟢" if main_net >= 0 else "🔴"
        r.text(f"📊 {emoji} 主力 {main_net:+.1f}亿 | "
               f"上证 {market_flow.get('sh_index','?')} "
               f"({market_flow.get('sh_change',0):+.2f}%)")
    else:
        r.text("📊 盘后非交易时段")

    # ── 周度趋势（从净值历史）──
    week = get_weekly_change(holdings_data)
    if week:
        w_emoji = "🟢" if week['change'] >= 0 else "🔴"
        r.text(f"📈 5日变化: {w_emoji} {week['change']:+.2f}% "
               f"(¥{week['prev_nv']:,.0f} → ¥{net_value:,.0f})")

    # ── 行情（复用缓存或新拉）──
    codes = [h['code'] for h in holdings]
    quotes = cached_quotes if cached_quotes else get_cached_quotes(codes)

    # ── 行业集中度 ──
    sectors = calc_sector_concentration(holdings, quotes, net_value)
    if sectors:
        r.divider()
        r.section("行业分布")
        rows = []
        for s, info in sorted(sectors.items(),
                              key=lambda x: x[1].get('pct', 0), reverse=True):
            pct = info.get('pct', 0)
            flag = "⚠️" if pct > 30 else ("·" if pct > 15 else "")
            names = " · ".join(info['stocks'][:3])
            rows.append([f"{flag} {s}", f"{pct:.1f}%", names])
        r.table(["行业", "占比", "标的"], rows)

        for s, info in sectors.items():
            if info.get('pct', 0) > 30:
                r.alert(f"⚡ {s} 行业集中度 {info['pct']:.1f}%，建议 ≤30%", "warning")

    # ── 持仓明细 ──
    r.divider()
    r.section("持仓明细")

    total_cost = 0.0
    total_mv = 0.0
    alerts = []

    for h in holdings:
        code = h['code']
        name = h.get('name', code)
        shares = int(h.get('shares', 0))
        cost_price = float(h.get('costPrice', 0))
        total_cost_stock = float(h.get('totalCost', 0))
        total_cost += total_cost_stock

        q = quotes.get(code, {})
        last_price = float(q.get('close', h.get('lastPrice', 0)))
        change_pct = float(q.get('change_pct', 0))
        market_value = last_price * shares if last_price and shares else total_cost_stock
        total_mv += market_value
        unrealized_pnl = market_value - total_cost_stock
        pnl_pct = (unrealized_pnl / total_cost_stock * 100) if total_cost_stock else 0
        position_pct = (market_value / net_value * 100) if net_value else 0

        # V8.0 池标记（优先用 holdings 中的标记，否则现场查）
        in_pool = h.get('inPool', code in pool_codes)
        pool_mark = " ⭐" if in_pool else " ⚡不在池"

        pnl_emoji = "🟢" if unrealized_pnl >= 0 else "🔴"
        change_emoji = "🔴" if change_pct < -3 else ""

        main_val = (f"{pnl_emoji} ¥{last_price:.2f} | "
                    f"浮亏 ¥{unrealized_pnl:+,.0f} ({pnl_pct:+.1f}%){pool_mark}")
        sub_info = (f"{shares}股 · 成本¥{cost_price:.3f} · "
                    f"仓位{position_pct:.1f}%  {change_emoji}今日 {change_pct:+.2f}%")
        r.kv(f"{name} {code}", main_val, sub_info)

        # 退出计划
        exit_parts = []
        for trade in h.get('trades', []):
            stop = float(trade.get('stopLoss', 0))
            if stop and last_price:
                dist = (last_price - stop) / stop * 100
                exit_parts.append(f"止损 ¥{stop:.2f}(距{dist:+.1f}%)")
        if exit_parts:
            r.text(f"  🎯 退出: {' | '.join(exit_parts[:2])}")

        # 不在推荐池告警
        if not in_pool:
            r.alert(f"{name} 不在今日 V8.0 推荐池，检查是否继续持有", "info")

        # 仓位告警
        if position_pct > max_pos_pct:
            r.alert(f"{name} 仓位 {position_pct:.1f}% 超标（上限{max_pos_pct:.1f}%）", "warning")

        # 止损检查
        if last_price:
            triggered = 0
            close_count = 0
            for trade in h.get('trades', []):
                stop_loss = float(trade.get('stopLoss', 0))
                if not stop_loss:
                    continue
                distance = (last_price - stop_loss) / stop_loss * 100
                batch_id = trade.get('batchId', '?')
                if last_price <= stop_loss:
                    triggered += 1
                    r.alert(
                        f"{name} {batch_id} 🔴 止损触发 "
                        f"¥{last_price:.2f}≤¥{stop_loss:.2f}", "critical")
                elif distance < 5:
                    close_count += 1
                    r.alert(
                        f"{name} {batch_id} 距止损仅 {distance:+.1f}% "
                        f"（¥{stop_loss:.2f}）", "warning")

            if triggered:
                alerts.append(f"🔴 {name} {triggered}批次止损触发")
            if close_count:
                alerts.append(f"🟡 {name} {close_count}批次靠近止损")

    # ── 流动性风险 ──
    avg_amounts = _get_avg_amount_5d(codes) if holdings else {}
    liq_warnings = check_liquidity(holdings, quotes, avg_amounts)
    if liq_warnings:
        r.divider()
        r.section("流动性风险")
        for lw in liq_warnings:
            r.alert(lw['detail'], "warning" if lw['impact'] < 10 else "critical")

    # ── 组合层面风控 (v8.6) ──
    try:
        from portfolio_risk import run_daily_risk_check
        pr = run_daily_risk_check()
        if pr.criticals or pr.warnings or pr.var:
            r.divider()
            r.section("组合风控")

            if pr.criticals:
                for c in pr.criticals:
                    r.alert(c, "critical")
            if pr.warnings:
                for w in pr.warnings:
                    r.alert(w, "warning")

            if pr.var:
                r.kv('VaR (95%)', f'¥{abs(pr.var.var_95):,.0f}', f'{abs(pr.var.var_pct):.1f}% 净值')
                r.kv('CVaR (95%)', f'¥{abs(pr.var.cvar_95):,.0f}', f'{abs(pr.var.cvar_pct):.1f}%')
                r.kv('历史最大回撤', f'{pr.var.max_drawdown_hist:.1f}%')
    except Exception:
        pass

    # ── 汇总 ──
    r.divider()
    r.section("持仓汇总")

    actual_total_pct = (total_mv / net_value * 100) if net_value else 0
    total_unrealized = total_mv - total_cost
    available = float(account.get('availableCash', 0))

    r.table(
        ["项目", "金额", "占比"],
        [
            ["可用资金", f"¥{available:,.0f}", "—"],
            ["成本合计", f"¥{total_cost:,.0f}", "—"],
            ["市值合计", f"¥{total_mv:,.0f}", f"{actual_total_pct:.1f}%"],
            ["浮动盈亏", f"¥{total_unrealized:+,.0f}",
             f"{'🟢' if total_unrealized>=0 else '🔴'}"],
            ["峰值净值", f"¥{peak_nv:,.0f}",
             f"回撤 {drawdown:.1f}%" if drawdown else "—"],
        ]
    )

    if not alerts:
        r.alert("✅ 无告警，风控正常", "info")

    r.footer(f"v{__version__} · data_pipeline · {time_str}")
    return r


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    data = None
    quotes = None

    if "--update" in sys.argv:
        data, quotes = run_update()

    # 默认（无参数）或明确 --report-only 都生成报告
    # 只有 --update-only 时只同步不报告
    if "--update-only" not in sys.argv:
        report = build_risk_report(data, quotes)
        if "--card" in sys.argv:
            print(json.dumps(report.card(), ensure_ascii=False, indent=2))
        else:
            print(report.markdown())

        # 保存
        date_str = datetime.now().strftime('%Y-%m-%d')
        reports_dir = BASE_DIR / "reports" / "daily"
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / f"弹药库风控-{date_str}.md").write_text(
            report.markdown(), encoding='utf-8')

        if "--push" in sys.argv:
            ok = _push_report(
                'ammo',
                f"🛡️ 弹药库风控-{date_str}",
                report.markdown()
            )
            print(f"{'✅' if ok else '❌'} 推送", file=sys.stderr)


if __name__ == "__main__":
    main()
