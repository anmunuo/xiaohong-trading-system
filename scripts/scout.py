#!/usr/bin/env python3
"""
侦察兵 · 开盘确认 + 盘中池更新 v4.0
====================================
基于 V8.0 推荐池 + 实时资金流的交叉验证选股。

v4.0 新增:
  · 盘中推荐池更新 — 交易时段(9:30-14:30)发现优质标的自动加入 daily_pool
  · 板块约束 — 资金流入 TOP3 板块各 ≤2 只
  · 基本面快筛 — PE 有效性检查
  · pool_additions — 记录侦察兵新增的标的

用法:
  python3 scout.py [--push] [--auction] [--intraday]
"""

__version__ = "4.0.0"

import sys, os, json, math
from pathlib import Path
from datetime import datetime


SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(SCRIPT_DIR))

from data_pipeline import get_top_flow_stocks, get_market_money_flow, check_data_health

POOL_PATH = SCRIPT_DIR / 'data' / 'daily_pool.json'


# ═══════════════════════════════════════════
# 1. 加载 V8.0 推荐池
# ═══════════════════════════════════════════

def load_daily_pool() -> dict:
    """加载 V8.0 每日推荐池，返回 {code: stock_info}"""
    pool = {}
    if POOL_PATH.exists():
        try:
            with open(POOL_PATH) as f:
                data = json.load(f)
            for r in data.get('recommendations', []):
                pool[str(r['code'])] = {
                    'name': r['name'],
                    'sector': r.get('sector', ''),
                    'operation': r.get('operation', ''),
                    'risk_level': r.get('risk_level', '中'),
                    'stop_loss': r.get('stop_loss', {}),
                    'total_score': r.get('total_score', 0),
                    'source': r.get('source', 'recommender'),
                }
        except Exception:
            pass
    return pool


# ═══════════════════════════════════════════
# 2. 排除规则（对齐 V8.0）
# ═══════════════════════════════════════════

def get_lianban_codes() -> set:
    """获取昨日涨停板代码集合"""
    lianban = set()
    try:
        import akshare as ak
        from datetime import timedelta
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        df = ak.stock_zt_pool_em(date=yesterday)
        if df is not None and not df.empty and '代码' in df.columns:
            for _, row in df.iterrows():
                lianban.add(str(row['代码']))
    except Exception:
        pass
    return lianban


def is_st(name: str) -> bool:
    """检查是否 ST"""
    return 'ST' in str(name)


def is_market_cap_ok(code: str, pre_fetched_mv: float = None) -> bool:
    """市值过滤：排除 < 50亿 或 > 3000亿

    v4.1: 优先使用预取市值（东方财富 f20），无预取时 fallback 实时行情"""
    if pre_fetched_mv is not None and pre_fetched_mv > 0:
        return 50 <= pre_fetched_mv <= 3000
    try:
        from data_pipeline import get_stock_realtime
        rt = get_stock_realtime([code])
        if code in rt:
            mkt_cap = float(rt[code].get('market_cap', 0) or 0)
            if mkt_cap > 0:
                return 50 <= mkt_cap <= 3000
    except Exception:
        pass
    # 无法获取市值 → 通过（避免误杀）
    return True

# ═══════════════════════════════════════════
# 3. 市场自适应资金门槛
# ═══════════════════════════════════════════

def adaptive_flow_threshold() -> float:
    """
    根据大盘环境动态调整资金门槛（单位：万元）

    强势市场(上证涨>1%):  门槛 3000万  — 水涨船高，降低门槛捕捉跟风
    中性市场(-1%~1%):     门槛 5000万  — 正常筛选
    弱势市场(上证跌>1%)： 门槛 8000万  — 只取真金白银流入
    """
    try:
        mf = get_market_money_flow()
        sh_change = float(mf.get('sh_change', 0))
    except Exception:
        sh_change = 0

    if sh_change > 1.0:
        return 3000   # 强势：放低门槛
    elif sh_change < -1.0:
        return 8000   # 弱势：提高门槛
    else:
        return 5000   # 中性


# ═══════════════════════════════════════════
# 4. 止损计算
# ═══════════════════════════════════════════

def calc_stop_loss(code: str, change_pct: float) -> dict:
    """快速止损位计算"""
    stop_pct = -7.0 if code.startswith('688') else -5.0  # 科创板放宽
    return {'ratio': stop_pct, 'method': 'fixed'}


# ═══════════════════════════════════════════
# 5. 风险判定
# ═══════════════════════════════════════════

def assess_risk(change_pct: float, code: str) -> str:
    if abs(change_pct) > 8 or code.startswith('688'):
        return '高'
    elif abs(change_pct) > 5:
        return '中高'
    return '中'


# ═══════════════════════════════════════════
# 6. 板块猜测
# ═══════════════════════════════════════════

SECTOR_KW = {
    '通信光缆': ['光', '通信', '缆', '亨通', '长飞', '中天'],
    '新能源':   ['风', '光伏', '锂', '电池', '储', '氢', '绿'],
    '半导体':   ['芯', '半导', '晶', '微', '电'],
    '电力设备': ['电', '缆', '变压', '开关', '配'],
    'AI/科技':  ['AI', '智能', '算', '机器', '软'],
    '消费':     ['酒', '食品', '饮', '家', '零售'],
    '医药':     ['药', '医', '生物'],
    '专用设备': ['设备', '装备', '机械', '机床'],
    '化工':     ['化工', '化学', '材料', '新材'],
    '有色':     ['铜', '铝', '金', '稀土', '矿'],
    '房地产':   ['地产', '物业', '开发'],
}


def guess_sector(name: str) -> str:
    for sector, kws in SECTOR_KW.items():
        for kw in kws:
            if kw in name:
                return sector
    return '综合'


# ═══════════════════════════════════════════
# 7. 主逻辑
# ═══════════════════════════════════════════

def run_scout() -> dict:
    """执行侦察兵选股，返回结构化结果"""
    pool = load_daily_pool()
    pool_codes = set(pool.keys())

    # 🆕 数据源健康检查
    health = check_data_health()
    flow_mode = health.get('flow_field', 'momentum')
    data_status = health.get('status', 'degraded')

    threshold = adaptive_flow_threshold()
    lianban_codes = get_lianban_codes()

    raw_stocks = get_top_flow_stocks(40)

    double_confirm = []  # ⭐ pool ∩ scout
    new_alert = []       # 🆕 scout − pool
    pending = []         # ⏳ pool − scout (待确认)

    seen_codes = set()

    # ── 扫描实时资金流 ──
    for s in raw_stocks:
        code = str(s.get('code', ''))
        name = str(s.get('name', ''))
        flow = s.get('net_flow')         # 可能为 None (fallback模式)
        change = float(s.get('change_pct', 0))
        quality = s.get('_quality', 'ok')

        # 排除
        if code in seen_codes:
            continue
        if is_st(name) or code in lianban_codes:
            continue
        if not is_market_cap_ok(code, s.get('total_mv')):
            continue

        # 资金门槛：fallback模式下放宽（net_flow 不可信）
        if flow_mode == 'momentum':
            # 动量模式：用涨跌幅替代资金流，门槛放宽到 ±3%
            if abs(change) < 3:
                continue
            if change < -7 or change > 9:
                continue
        else:
            if flow is not None and flow < threshold:
                continue
            if change < -3 or change > 9:
                continue

        seen_codes.add(code)
        stop = calc_stop_loss(code, change)
        risk = assess_risk(change, code)
        sector = guess_sector(name)

        entry = {
            'code': code, 'name': name,
            'net_flow': flow or 0, 'change_pct': change,
            'sector': sector, 'risk_level': risk,
            'stop_loss': stop,
            'operation': pool.get(code, {}).get('operation', ''),
            '_quality': quality,
        }

        if code in pool_codes:
            entry['signal_type'] = 'double'
            entry['pool_score'] = pool[code].get('total_score', 0)
            double_confirm.append(entry)
        else:
            entry['signal_type'] = 'new'
            new_alert.append(entry)

    # ── 推荐池中未被资金确认的 ──
    for code, info in pool.items():
        if code not in seen_codes:
            pending.append({
                'code': code, 'name': info['name'],
                'sector': info.get('sector', '综合'),
                'operation': info.get('operation', ''),
                'risk_level': info.get('risk_level', '中'),
                'signal_type': 'pending',
            })

    # 排序: 双重确认按资金排序, 新增按资金排序
    double_confirm.sort(key=lambda x: x['net_flow'], reverse=True)
    new_alert.sort(key=lambda x: x['net_flow'], reverse=True)

    # 去重：新增异动中去掉已经在双重确认里的
    dc_codes = {d['code'] for d in double_confirm}
    new_alert = [n for n in new_alert if n['code'] not in dc_codes]

    # 限制数量
    double_confirm = double_confirm[:6]
    new_alert = new_alert[:4]
    pending = pending[:5]

    return {
        'timestamp': datetime.now().strftime('%H:%M'),
        'threshold': threshold,
        'double_confirm': double_confirm,
        'new_alert': new_alert,
        'pending': pending,
        'pool_total': len(pool),
        'flow_mode': flow_mode,        # 🆕
        'data_status': data_status,    # 🆕
    }


# ═══════════════════════════════════════════
# 8. 盘中推荐池更新 (v4.0)
# ═══════════════════════════════════════════

# ── 盘中多因子评分权重（可进化）──
INTRA_FUND_WEIGHT = 0.40      # 资金流权重
INTRA_TECH_WEIGHT = 0.30      # 技术面权重
INTRA_SENT_WEIGHT = 0.20      # 情绪面权重
INTRA_SECTOR_WEIGHT = 0.10    # 板块热度权重
INTRA_VOLUME_BONUS = 8        # 分时放量加分上限 (v8.3)


def get_sector_flow_rank_top3() -> list:
    """获取今日资金流入 TOP3 板块名称"""
    try:
        from data_pipeline import get_sector_flow_rank
        sectors = get_sector_flow_rank('3')
        return [s['name'] for s in sectors[:3]]
    except Exception:
        return []


def quick_fundamental_check(code: str) -> bool:
    """基本面快筛：检查 PE 是否合理"""
    try:
        from data_pipeline import get_stock_realtime
        rt = get_stock_realtime([code])
        if code in rt:
            pe = float(rt[code].get('pe_ttm', 0) or 0)
            if pe > 0 and pe < 200:
                return True
            if pe == 0:
                return True
        return True
    except Exception:
        return True


def score_intraday_candidate(s: dict, hot_sectors: list) -> float:
    """
    盘中多因子综合评分（对标推荐引擎五因子，适配盘中实时数据）。

    四因子:
      fund (40%):  主力净流入归一化
      tech (30%):  MA20偏离 + 量比
      sent (20%):  涨跌幅区间
      sector(10%): 是否属于今日热门板块
    """
    # ── 资金流 (0-100) ──
    net_flow = float(s.get('net_flow', 0))
    if net_flow <= 0:
        fund = 20
    elif net_flow >= 50000:
        fund = 100
    else:
        fund = 20 + (net_flow / 50000) * 80

    # ── 技术面 (0-100) ──
    tech = 50
    code = str(s.get('code', ''))
    try:
        from data_pipeline import get_stock_realtime
        rt = get_stock_realtime([code])
        if code in rt:
            r = rt[code]
            close = float(r.get('close', 0))
            ma20 = float(r.get('ma20', close))
            vol = float(r.get('volume', 0))
            avg_vol = float(r.get('avg_volume_5', vol))

            if close > 0 and ma20 > 0:
                dev = (close - ma20) / ma20 * 100
                if -3 <= dev <= 2:
                    tech += 20  # 回踩MA20附近
                elif 2 < dev <= 5:
                    tech += 5   # 略高于MA20
                elif dev < -5:
                    tech += 10  # 超跌反弹潜力

            if avg_vol > 0 and vol > 0:
                vr = vol / avg_vol
                if 1.2 <= vr <= 3:
                    tech += 15  # 温和放量
                elif vr > 3:
                    tech -= 5   # 过度放量
                elif vr < 0.5:
                    tech -= 10  # 缩量冷门
    except Exception:
        pass
    tech = max(0, min(100, tech))

    # ── 情绪面 (0-100) ──
    change = float(s.get('change_pct', 0))
    if 1 <= change <= 5:
        sent = 75  # 温和上涨最佳
    elif 5 < change <= 9:
        sent = 55  # 偏强但有追高风险
    elif 0 <= change < 1:
        sent = 50  # 横盘
    elif -3 <= change < 0:
        sent = 60  # 小幅回调机会
    elif change < -3:
        sent = 30  # 大跌谨慎
    else:
        sent = 40  # change > 9 涨停

    # ── 板块热度 (0-100) ──
    sector = s.get('sector', '综合')
    if any(hs in sector or sector in hs for hs in hot_sectors):
        sector_score = 80
    else:
        sector_score = 40

    # ── 分时放量加分 (v8.3 新增) ──
    volume_bonus = 0
    try:
        from data_pipeline import get_intraday_volume_alert
        va = get_intraday_volume_alert(code, scale=5)
        if va.get('alert') and va['vol_ratio'] >= 2.0:
            volume_bonus = min(INTRA_VOLUME_BONUS, int(va['vol_ratio'] * 2))
            if '上涨' in va.get('signal', ''):
                volume_bonus += 2  # 放量上涨额外加分
    except Exception:
        pass

    total = (fund * INTRA_FUND_WEIGHT +
             tech * INTRA_TECH_WEIGHT +
             sent * INTRA_SENT_WEIGHT +
             sector_score * INTRA_SECTOR_WEIGHT +
             volume_bonus)

    return round(total, 1)


def feed_intraday_pool(new_alert: list, pool_codes: set) -> list:
    """
    盘中推荐池动态更新 (v4.0)。

    规则:
      · 无板块上限 — 让系统自然竞争
      · 无数量上限 — 由池总容量 9 只自然约束
      · 高资金流入标的替换低分标的
      · 基本面快筛通过
      · 标记 source: "scout_intraday"

    返回: 新加入池中的标的列表
    """
    if not new_alert:
        return []

    # 获取今日热门板块
    hot_sectors = get_sector_flow_rank_top3()

    # 基本面快筛 + 多因子综合评分
    candidates = []
    for s in new_alert:
        # 只跳过推荐引擎标的，盘中标的可被更新
        if s['code'] in pool_codes:
            continue
        if not quick_fundamental_check(s['code']):
            continue
        if not is_market_cap_ok(s['code'], s.get('total_mv')):
            continue
        score = score_intraday_candidate(s, hot_sectors)
        candidates.append((score, s))

    if not candidates:
        return []

    # 按综合评分降序
    candidates.sort(key=lambda x: x[0], reverse=True)

    # 读取现有池
    pool = {'date': datetime.now().strftime('%Y%m%d'), 'recommendations': [],
            'scout_additions': [], 'scout_last_update': None}
    if POOL_PATH.exists():
        try:
            with open(POOL_PATH) as f:
                pool = json.load(f)
        except Exception:
            pass

    existing_recs = pool.get('recommendations', [])
    recommender_recs = [r for r in existing_recs if r.get('source') != 'scout_intraday']
    intraday_recs = [r for r in existing_recs if r.get('source') == 'scout_intraday']

    # 构建新 entry
    ts = datetime.now().strftime('%H:%M')
    seen = set()
    new_entries = []
    for score, s in candidates:
        code = str(s['code'])
        if code in seen:
            continue
        seen.add(code)
        new_entries.append({
            'code': code,
            'name': s['name'],
            'net_flow': s.get('net_flow', 0),
            'change_pct': s.get('change_pct', 0),
            'sector': s.get('sector', '综合'),
            'operation': f"盘中侦察兵发现 · 综合评分{score:.1f}",
            'risk_level': s.get('risk_level', '中'),
            'stop_loss': s.get('stop_loss', {}),
            'total_score': score,
            'source': 'scout_intraday',
            'added_at': ts,
            '_quality': s.get('_quality', 'ok'),
        })

    # 合并：推荐引擎标的 + (盘中标的 ∪ 新候选) → 按 score 排序 → 截取前 9
    all_intraday = intraday_recs + new_entries
    # 去重
    uniq_intraday = {}
    for r in all_intraday:
        code = r['code']
        if code not in uniq_intraday or r.get('total_score', 0) > uniq_intraday[code].get('total_score', 0):
            uniq_intraday[code] = r
    all_intraday = sorted(uniq_intraday.values(), key=lambda x: x.get('total_score', 0), reverse=True)

    # 推荐引擎标的 + 前 N 个盘中标的，总数 ≤ 9
    available_slots = max(0, 9 - len(recommender_recs))
    selected_intraday = all_intraday[:available_slots]

    # 组装最终推荐池
    merged = list(recommender_recs) + selected_intraday
    merged.sort(key=lambda x: x.get('total_score', 0), reverse=True)

    # 哪些是本次新增的？
    new_codes = {e['code'] for e in new_entries}
    actually_added = [r for r in selected_intraday if r['code'] in new_codes]

    # 🆕 研究员全链路 — 对新加入股逐只跑 6 位研究员分析
    for entry in actually_added:
        try:
            from researchers import analyze_stock
            code = entry.get('code', '')
            name = entry.get('name', '')
            entry['researcher_analysis'] = analyze_stock(code, name)
        except Exception:
            entry['researcher_analysis'] = {'timestamp': datetime.now().isoformat(), 'error': '分析失败'}

    # 持久化
    pool['recommendations'] = merged
    pool.setdefault('scout_additions', [])
    for a in actually_added:
        pool['scout_additions'].append({
            'code': a['code'], 'name': a['name'],
            'score': a.get('total_score', 0), 'added_at': ts
        })
    pool['scout_last_update'] = ts
    POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(POOL_PATH, 'w') as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)

    return actually_added


# ═══════════════════════════════════════════
# 9. 盘中池更新报告
# ═══════════════════════════════════════════

def is_intraday_time() -> bool:
    """判断是否在盘中交易时段（09:30-14:30）"""
    now = datetime.now()
    h, m = now.hour, now.minute
    return (h == 9 and m >= 30) or (10 <= h <= 13) or (h == 14 and m <= 30)

def add_auction_overlay(result: dict) -> dict:
    """在侦察兵结果上叠加竞价信号"""
    try:
        from auction_features import auction_signal
    except ImportError:
        return result

    date_str = datetime.now().strftime('%Y%m%d')

    # 对所有侦察兵标的计算竞价评分
    all_entries = (result.get('double_confirm', []) +
                   result.get('new_alert', []))

    auction_scores = {}
    for entry in all_entries:
        code = entry.get('code', '')
        if code:
            sig = auction_signal(date_str, code)
            auction_scores[code] = sig

    # 叠加到 entry
    for entry in all_entries:
        code = entry['code']
        if code in auction_scores:
            entry['auction'] = auction_scores[code]
        else:
            entry['auction'] = {'score': 0, 'signal': 'no_data'}

    result['auction_enabled'] = True
    return result


def auction_icon(signal: str) -> str:
    """竞价信号图标"""
    return {
        'strong':   '🔥',
        'moderate': '📈',
        'weak':     '📊',
        'neutral':  '➖',
        'caution':  '⚠️',
        'no_data':  '',
    }.get(signal, '')


# ═══════════════════════════════════════════
# 9. 输出
# ═══════════════════════════════════════════

def format_report(result: dict) -> str:
    ts = result['timestamp']
    threshold = result['threshold']
    dc = result['double_confirm']
    na = result['new_alert']
    pd = result['pending']
    pool_total = result['pool_total']
    additions = result.get('pool_additions', [])
    is_intraday = result.get('intraday', False)

    mode_label = "🔍 侦察兵 · 盘中扫描" if is_intraday else "🔍 侦察兵 · 开盘确认"

    lines = []
    lines.append(mode_label)
    lines.append(f"")
    auction_note = " · 竞价分析" if result.get('auction_enabled') else ""
    lines.append(f"**时间**: {ts}{auction_note}  |  资金门槛: {threshold:.0f}万  |  推荐池: {pool_total}只")
    # 🆕 数据源状态提示
    flow_mode = result.get('flow_mode', 'unknown')
    data_status = result.get('data_status', 'degraded')
    if flow_mode == 'momentum':
        lines.append(f"⚠️ 数据源降级: 资金流字段不可用，使用涨跌幅+量比替代")
    elif flow_mode == 'fallback':
        lines.append(f"⚠️ 数据源降级: 使用fallback字段  |  健康: {data_status}")
    lines.append(f"")

    # ═══ ⭐ 双重确认 ═══
    lines.append(f"---")
    lines.append(f"")
    if dc:
        lines.append(f"### ⭐ 双重确认（{len(dc)}只）")
        lines.append(f"")
        lines.append(f"> V8.0推荐池 + 资金流入同时命中，今日最强信号")
        lines.append(f"")
        if result.get('auction_enabled'):
            lines.append(f"| 代码 | 名称 | 板块 | 资金 | 涨跌 | 竞价 | 操作策略 | 风险 |")
            lines.append(f"|------|------|------|------|------|:--:|------|:--:|")
            for s in dc:
                sl = s['stop_loss']
                op = s.get('operation', '') or f"回踩分时均线介入"
                if len(op) > 25:
                    op = op[:23] + '..'
                auc = s.get('auction', {})
                auc_score = auc.get('score', 0)
                auc_icon_str = auction_icon(auc.get('signal', ''))
                auc_str = f"{auc_icon_str} {auc_score:.0f}" if auc_score > 0 else '-'
                lines.append(
                    f"| {s['code']} | {s['name']} | {s['sector']} | "
                    f"{s['net_flow']:.0f}万 | {s['change_pct']:+.1f}% | "
                    f"{auc_str} | {op} 止损{sl['ratio']:+.0f}% | {s['risk_level']} |"
                )
        else:
            lines.append(f"| 代码 | 名称 | 板块 | 资金 | 涨跌 | 操作策略 | 风险 |")
            lines.append(f"|------|------|------|------|------|------|:--:|")
            for s in dc:
                sl = s['stop_loss']
                op = s.get('operation', '') or f"回踩分时均线介入"
                if len(op) > 30:
                    op = op[:28] + '..'
                lines.append(
                    f"| {s['code']} | {s['name']} | {s['sector']} | "
                    f"{s['net_flow']:.0f}万 | {s['change_pct']:+.1f}% | "
                    f"{op} 止损{sl['ratio']:+.0f}% | {s['risk_level']} |"
                )
        lines.append(f"")
    else:
        lines.append(f"### ⭐ 双重确认（0只）")
        lines.append(f"")
        lines.append(f"> 无推荐池+资金流同时命中的标的")
        lines.append(f"")

    # ═══ 🆕 新增异动 ═══
    lines.append(f"---")
    lines.append(f"")
    if na:
        lines.append(f"### 🆕 新增异动（{len(na)}只）")
        lines.append(f"")
        lines.append(f"> 推荐池外，资金显著流入。需自行判断基本面和催化剂")
        lines.append(f"")
        lines.append(f"| 代码 | 名称 | 板块 | 资金 | 涨跌 | 操作建议 | 风险 |")
        lines.append(f"|------|------|------|------|------|------|:--:|")
        for s in na:
            sl = s['stop_loss']
            if s['change_pct'] > 5:
                op = f"高开不追，等回踩 止损{sl['ratio']:+.0f}%"
            else:
                op = f"回踩分时均线轻仓 止损{sl['ratio']:+.0f}%"
            lines.append(
                f"| {s['code']} | {s['name']} | {s['sector']} | "
                f"{s['net_flow']:.0f}万 | {s['change_pct']:+.1f}% | "
                f"{op} | {s['risk_level']} |"
            )
        lines.append(f"")
    else:
        lines.append(f"### 🆕 新增异动（0只）")
        lines.append(f"")
        lines.append(f"> 暂无明显的新增资金异动标的")
        lines.append(f"")

    # ═══ 🔄 盘中池更新 (v4.0) ═══
    if additions:
        lines.append(f"---")
        lines.append(f"")
        lines.append(f"### 🔄 盘中池更新（{len(additions)}只）")
        lines.append(f"")
        lines.append(f"> 侦察兵盘中发现的优质标的，已自动加入 daily_pool.json · 标记 source:scout_intraday")
        lines.append(f"")
        lines.append(f"| 代码 | 名称 | 板块 | 资金 | 涨跌 | 风险 |")
        lines.append(f"|------|------|------|------|------|:--:|")
        for a in additions:
            lines.append(
                f"| {a['code']} | {a['name']} | {a.get('feed_sector', a.get('sector', ''))} | "
                f"{a['net_flow']:.0f}万 | {a['change_pct']:+.1f}% | {a.get('risk_level', '中')} |"
            )
        lines.append(f"")

    # ═══ ⏳ 待确认 ═══
    lines.append(f"---")
    lines.append(f"")
    if pd:
        lines.append(f"### ⏳ 待确认（{len(pd)}只）")
        lines.append(f"")
        lines.append(f"> 推荐池内但资金暂未明显流入，继续观察等放量")
        lines.append(f"")
        lines.append(f"| 代码 | 名称 | 板块 | 操作策略 | 风险 |")
        lines.append(f"|------|------|------|------|:--:|")
        for s in pd:
            op = s.get('operation', '观望') or '观望'
            if len(op) > 30:
                op = op[:28] + '..'
            lines.append(
                f"| {s['code']} | {s['name']} | {s['sector']} | "
                f"{op} | {s['risk_level']} |"
            )
    lines.append(f"")

    lines.append(f"---")
    lines.append(f"")
    lines.append(f"⚠️ 机器筛选仅供参考，不构成投资建议")
    lines.append(f"")
    lines.append(f"*侦察兵 v4.0 · {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    return '\n'.join(lines)


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description='侦察兵 v4.0 · 开盘确认 + 盘中池更新')
    p.add_argument('--push', action='store_true', help='推送飞书')
    p.add_argument('--auction', action='store_true', help='叠加竞价信号分析')
    p.add_argument('--intraday', action='store_true', help='盘中模式：扫描+自动更新推荐池')
    args = p.parse_args()

    result = run_scout()
    result['intraday'] = args.intraday

    if args.auction:
        result = add_auction_overlay(result)

    # ── 盘中池更新 ──
    pool_additions = []
    if args.intraday:
        # 只保护推荐引擎标的，盘中标的可被更高分候选取代
        pool = load_daily_pool()
        recommender_codes = {c for c, info in pool.items()
                            if info.get('source') != 'scout_intraday'}
        pool_additions = feed_intraday_pool(result.get('new_alert', []), recommender_codes)
    result['pool_additions'] = pool_additions

    report = format_report(result)
    print(report)

    if args.push:
        try:
            from feishu_push import push_scout
            ok = push_scout(title='🔍 侦察兵 · 开盘确认', content=report)
            print(f"\n{'✅' if ok else '❌'} 推送{'成功' if ok else '失败'}")
        except Exception as e:
            print(f"\n❌ 推送失败: {e}")


if __name__ == '__main__':
    main()
