#!/usr/bin/env python3
"""
auction_features.py — 竞价特征提取 v1.0
=======================================
从 auction_frames 表中读取竞价轨迹，提取五维特征。

特征维度:
  1. 价格轨迹斜率   — 竞价期间价格走向（正=抢筹，负=抛压，W型=分歧转一致）
  2. 量能加速度     — 09:20后量能集中度（不可撤单后的真实意图）
  3. 委托不平衡     — 竞价量/(竞价量+前日平均量) 的标准化
  4. 开盘溢价率     — 开盘价 vs 前收盘
  5. 板块偏离度     — 个股 vs 板块平均的价格偏离

用法:
  from auction_features import extract_features, score_auction
  features = extract_features('20260601', '600487')
  score = score_auction(features)
"""

import sqlite3, json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

DB_PATH = Path(__file__).resolve().parent / 'data' / 'auction.db'

# 五维权重（初始等权，后续由 learner 动态调整）
DEFAULT_WEIGHTS = {
    'price_slope': 0.28,
    'volume_accel': 0.3,
    'imbalance': 0.180,
    'premium': 0.14,
    'sector_dev': 0.130,
}


# ═══════════════════════════════════════════
# 数据读取
# ═══════════════════════════════════════════

def load_trajectory(date: str, code: str) -> List[Dict]:
    """加载某只股票某日的竞价轨迹帧"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT seq, price, volume, amount, change_pct, open_price, prev_close
        FROM auction_frames
        WHERE date = ? AND code = ?
        ORDER BY seq
    ''', (date, code)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_sector_trajectories(date: str, sector: str) -> List[Dict]:
    """加载某板块所有股票的轨迹（需要外部传入板块映射）"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute('''
        SELECT code, seq, price, change_pct
        FROM auction_frames
        WHERE date = ?
        ORDER BY code, seq
    ''', (date,)).fetchall()
    conn.close()

    # 简化：返回所有帧，由调用方做板块过滤
    return [dict(r) for r in rows]


# ═══════════════════════════════════════════
# 特征 1：价格轨迹斜率
# ═══════════════════════════════════════════

def calc_price_slope(frames: List[Dict]) -> float:
    """
    计算竞价期间价格轨迹的整体走向和形态。

    取 09:15-09:18（可撤单期）和 09:20-09:25（不可撤单期）
    的正规化斜率差。

    返回: -1.0 ~ 1.0，正值=上行趋势，且值越大越强
    """
    if len(frames) < 5:
        return 0.0

    n = len(frames)
    early = frames[:n//3]    # 前 1/3：可撤单试探期
    late = frames[2*n//3:]   # 后 1/3：不可撤单真实期

    if not early or not late:
        return 0.0

    early_prices = [f['price'] for f in early if f['price'] > 0]
    late_prices = [f['price'] for f in late if f['price'] > 0]

    if not early_prices or not late_prices:
        return 0.0

    early_avg = sum(early_prices) / len(early_prices)
    late_avg = sum(late_prices) / len(late_prices)

    if early_avg == 0:
        return 0.0

    # 斜率: (后期均价 - 前期均价) / 前期均价
    slope = (late_avg - early_avg) / early_avg

    # W 型检测：中期价格先跌破前期再回升
    mid = frames[n//3:2*n//3]
    mid_prices = [f['price'] for f in mid if f['price'] > 0]
    if mid_prices and len(late_prices) >= 2:
        mid_min = min(mid_prices)
        if mid_min < early_avg * 0.995 and late_prices[-1] > early_avg * 1.002:
            # W型反转：加分
            slope += 0.003

    return round(max(-0.05, min(0.05, slope)), 6)


# ═══════════════════════════════════════════
# 特征 2：量能加速度
# ═══════════════════════════════════════════

def calc_volume_accel(frames: List[Dict]) -> float:
    """
    计算竞价尾段量能爆发度。

    逻辑: 09:20 后不可撤单，此时涌入的资金代表真实买入意愿。
    accel = 后期量增速 / 前期量增速

    返回: >1.0 表示尾段爆量（强烈信号），<0.5 表示无人问津
    """
    if len(frames) < 6:
        return 1.0

    n = len(frames)
    split = n // 2

    first_half = frames[:split]
    second_half = frames[split:]

    v1 = [f['volume'] for f in first_half if f['volume'] > 0]
    v2 = [f['volume'] for f in second_half if f['volume'] > 0]

    if not v1 or not v2:
        return 1.0

    # 量增速：后半段均值 / 前半段均值
    v1_avg = sum(v1) / len(v1)
    v2_avg = sum(v2) / len(v2)

    if v1_avg < 100:
        return 1.0  # 量太小，不做判断

    accel = v2_avg / v1_avg
    return round(accel, 4)


# ═══════════════════════════════════════════
# 特征 3：委托不平衡
# ═══════════════════════════════════════════

def calc_imbalance(frames: List[Dict]) -> float:
    """
    竞价量 / 前日量的标准化比例。

    东方财富 f19/f20 是虚拟匹配量，直接反映竞价期间的供需。
    用最后一帧的量 / 平均帧量 = 尾段集中度。

    返回: 0.5~2.5，>1.5 表示竞价尾段明显有资金抢筹
    """
    if len(frames) < 5:
        return 1.0

    vols = [f['volume'] for f in frames if f['volume'] > 0]
    if not vols:
        return 1.0

    avg_vol = sum(vols) / len(vols)
    last_vol = vols[-1]

    if avg_vol < 50:
        return 1.0

    imbalance = last_vol / avg_vol
    return round(min(3.0, max(0.3, imbalance)), 4)


# ═══════════════════════════════════════════
# 特征 4：开盘溢价率
# ═══════════════════════════════════════════

def calc_premium(frames: List[Dict]) -> float:
    """
    开盘价相对前收盘的溢价率。

    返回: 百分比，2-5% 最佳，>7% 风险偏高，<0 低开弱
    """
    if not frames:
        return 0.0

    last = frames[-1]
    prev_close = last.get('prev_close', 0)
    open_price = last.get('open_price', 0) or last.get('price', 0)

    if prev_close <= 0:
        return 0.0

    premium = (open_price - prev_close) / prev_close * 100
    return round(premium, 2)


# ═══════════════════════════════════════════
# 特征 5：板块偏离度
# ═══════════════════════════════════════════

def calc_sector_deviation(frames: List[Dict], sector_frames: List[Dict]) -> float:
    """
    个股竞价涨跌幅 vs 板块平均涨跌幅的偏离。

    返回: 百分点偏离，正值=强于板块，负值=弱于板块
    """
    if not frames or not sector_frames:
        return 0.0

    # 个股最终涨跌幅
    stock_chg = frames[-1].get('change_pct', 0)

    # 板块平均涨跌幅
    by_code = {}
    for f in sector_frames:
        code = f['code']
        if code not in by_code or f['seq'] > by_code[code]['seq']:
            by_code[code] = f

    if not by_code:
        return 0.0

    sector_chgs = [v['change_pct'] for v in by_code.values()]
    sector_avg = sum(sector_chgs) / len(sector_chgs)

    return round(stock_chg - sector_avg, 2)


# ═══════════════════════════════════════════
# 综合打分
# ═══════════════════════════════════════════

def extract_features(date: str, code: str,
                     sector_frames: List[Dict] = None) -> Dict:
    """提取五维特征"""
    frames = load_trajectory(date, code)
    if not frames:
        return {'error': 'no_data', 'code': code}

    feats = {
        'code': code,
        'frames': len(frames),
        'price_slope': calc_price_slope(frames),
        'volume_accel': calc_volume_accel(frames),
        'imbalance': calc_imbalance(frames),
        'premium': calc_premium(frames),
        'sector_dev': calc_sector_deviation(frames, sector_frames or []),
    }
    return feats


def score_auction(features: Dict,
                  weights: Dict = None) -> Tuple[float, str, Dict]:
    """
    综合打分，返回 (分数, 信号, 各维度得分)

    分数: 0-100
    信号: strong / moderate / weak / neutral / caution
    """
    if 'error' in features:
        return 0, 'neutral', {}

    w = weights or DEFAULT_WEIGHTS
    dim_scores = {}

    # 1. 价格斜率 → 映射到 0-25
    slope = features.get('price_slope', 0)
    if slope > 0.005:
        dim_scores['price_slope'] = 20 + min(slope * 1000, 5)
    elif slope > 0:
        dim_scores['price_slope'] = 10 + slope * 1000
    elif slope > -0.003:
        dim_scores['price_slope'] = 8
    else:
        dim_scores['price_slope'] = max(0, 5 + slope * 1000)

    # 2. 量能加速度 → 映射到 0-25
    accel = features.get('volume_accel', 1.0)
    if accel > 2.0:
        dim_scores['volume_accel'] = 23
    elif accel > 1.5:
        dim_scores['volume_accel'] = 20
    elif accel > 1.2:
        dim_scores['volume_accel'] = 15
    elif accel > 0.8:
        dim_scores['volume_accel'] = 10
    else:
        dim_scores['volume_accel'] = 5

    # 3. 委托不平衡 → 映射到 0-20
    imb = features.get('imbalance', 1.0)
    if imb > 2.0:
        dim_scores['imbalance'] = 18
    elif imb > 1.5:
        dim_scores['imbalance'] = 15
    elif imb > 1.2:
        dim_scores['imbalance'] = 12
    else:
        dim_scores['imbalance'] = 6

    # 4. 开盘溢价 → 映射到 0-15
    premium = features.get('premium', 0)
    if 2 <= premium <= 5:
        dim_scores['premium'] = 14
    elif 1 <= premium < 2 or 5 < premium <= 7:
        dim_scores['premium'] = 10
    elif 0 <= premium < 1:
        dim_scores['premium'] = 7
    elif premium > 7:
        dim_scores['premium'] = 4  # 高开太多，风险
    else:
        dim_scores['premium'] = 3

    # 5. 板块偏离 → 映射到 0-15
    dev = features.get('sector_dev', 0)
    if dev > 2:
        dim_scores['sector_dev'] = 14
    elif dev > 1:
        dim_scores['sector_dev'] = 12
    elif dev > 0:
        dim_scores['sector_dev'] = 10
    elif dev > -1:
        dim_scores['sector_dev'] = 7
    else:
        dim_scores['sector_dev'] = 3

    # 归一化到 0-100
    raw = sum(dim_scores.get(k, 0) * w.get(k, 0.2) / 0.25 for k in w)
    total = round(raw, 1)

    if total >= 65:
        signal = 'strong'
    elif total >= 50:
        signal = 'moderate'
    elif total >= 35:
        signal = 'weak'
    elif features.get('price_slope', 0) < -0.003:
        signal = 'caution'
    else:
        signal = 'neutral'

    return total, signal, dim_scores


# ═══════════════════════════════════════════
# 侦察兵集成接口
# ═══════════════════════════════════════════

def auction_signal(date: str, code: str,
                   weights: Dict = None) -> Dict:
    """
    提供给侦察兵的调用接口。

    返回: {'score': 72.5, 'signal': 'strong', 'features': {...}}
    """
    features = extract_features(date, code)
    score, signal, dims = score_auction(features, weights)
    return {
        'code': code,
        'score': score,
        'signal': signal,
        'features': features,
        'dim_scores': dims,
    }


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description='竞价特征提取 v1.0')
    p.add_argument('date', help='日期 YYYYMMDD')
    p.add_argument('code', help='股票代码')
    p.add_argument('--json', action='store_true', help='JSON输出')
    args = p.parse_args()

    features = extract_features(args.date, args.code)
    score, signal, dims = score_auction(features)

    if args.json:
        print(json.dumps({
            'code': args.code, 'date': args.date,
            'score': score, 'signal': signal,
            'features': features, 'dim_scores': dims,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"\n🔬 竞价特征: {args.code} ({args.date})")
        print(f"   帧数: {features.get('frames', 0)}")
        print(f"   价格斜率: {features.get('price_slope', 0):.6f}")
        print(f"   量能加速度: {features.get('volume_accel', 0):.2f}")
        print(f"   委托不平衡: {features.get('imbalance', 0):.2f}")
        print(f"   开盘溢价: {features.get('premium', 0):.2f}%")
        print(f"   板块偏离: {features.get('sector_dev', 0):.2f}%")
        print(f"   {'─'*30}")
        print(f"   综合评分: {score}/100  信号: {signal}")
        if dims:
            print(f"   维度得分: {json.dumps(dims, ensure_ascii=False)}")


if __name__ == '__main__':
    main()
