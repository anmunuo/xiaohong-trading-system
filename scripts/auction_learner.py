#!/usr/bin/env python3
"""
auction_learner.py — 竞价贝叶斯学习器 v1.0
===========================================
盘后验证竞价信号准确率，Bayesian 更新五维权重。

核心逻辑:
  每日收盘后：
    1. 读取当日 auction_frames → 提取特征 → 生成信号
    2. 对比当日实际涨跌（收盘 vs 开盘）
    3. 命中: α+1  未命中: β+1
    4. 后验权重 = α/(α+β) → 写入 auction_weights.json

用法:
  python3 auction_learner.py                    # 处理最近交易日
  python3 auction_learner.py --date 20260601    # 指定日期
  python3 auction_learner.py --reset            # 重置权重
  python3 auction_learner.py --show             # 查看当前权重
"""

__version__ = "1.1.0"

import sys, os, json, sqlite3, math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from auction_features import (
    extract_features, score_auction, load_trajectory,
    DEFAULT_WEIGHTS,
)

DB_PATH = SCRIPT_DIR / 'data' / 'auction.db'
WEIGHTS_PATH = SCRIPT_DIR / 'data' / 'auction_weights.json'

# 贝叶斯先验 (α=1, β=1  →  初始 50%)
PRIOR_ALPHA = 1
PRIOR_BETA = 1


# ═══════════════════════════════════════════
# 数据库状态诊断
# ═══════════════════════════════════════════

def diagnose_db(date_str: str) -> Dict:
    """诊断 auction.db 中指定日期的数据状态，返回诊断报告"""
    if not DB_PATH.exists():
        return {
            'status': 'no_db',
            'message': f'❌ auction.db 不存在 ({DB_PATH})',
            'suggestion': '竞价采集器(09:15)可能未运行或DB路径配置错误'
        }

    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 检查表是否存在
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auction_frames'")
    if not cur.fetchone():
        conn.close()
        return {
            'status': 'no_table',
            'message': '❌ auction_frames 表不存在',
            'suggestion': '竞价采集器从未成功创建表，检查 init_db()'
        }

    # 总行数
    cur.execute("SELECT COUNT(*) FROM auction_frames")
    total = cur.fetchone()[0]

    # 当日行数
    cur.execute("SELECT COUNT(*) FROM auction_frames WHERE date = ?", (date_str,))
    today = cur.fetchone()[0]

    # 有数据的最近日期
    cur.execute("SELECT date, COUNT(*) FROM auction_frames GROUP BY date ORDER BY date DESC LIMIT 5")
    recent = cur.fetchall()

    # 当日股票数
    cur.execute("SELECT COUNT(DISTINCT code) FROM auction_frames WHERE date = ?", (date_str,))
    today_stocks = cur.fetchone()[0]

    # 最大seq（帧数）
    cur.execute("SELECT MAX(seq) FROM auction_frames WHERE date = ?", (date_str,))
    max_seq = cur.fetchone()[0]

    conn.close()

    report = {
        'status': 'ok' if today > 0 else 'empty_today',
        'total_rows': total,
        'today_rows': today,
        'today_stocks': today_stocks,
        'today_max_seq': max_seq,
        'recent_dates': [{'date': d, 'rows': c} for d, c in recent],
    }

    if today == 0:
        if total == 0:
            report['message'] = '⚠️ auction.db 完全为空（0行），竞价采集器可能从未成功运行'
            report['suggestion'] = '检查: ① 09:15 cron是否触发 ② 东方财富API是否可达 ③ 默认标的是否有效'
        else:
            last_date = recent[0][0] if recent else '未知'
            report['message'] = f'⚠️ 今日({date_str})无竞价数据（最近: {last_date}）'
            report['suggestion'] = '竞价采集器今日运行失败，检查 09:15 cron 的 stdout/stderr 输出'
    else:
        report['message'] = f'✅ {today}行 {today_stocks}只 {max_seq}帧'

    return report


# ═══════════════════════════════════════════
# 权重读写
# ═══════════════════════════════════════════

def load_weights() -> Dict:
    """加载当前权重（含贝叶斯分布参数）"""
    if WEIGHTS_PATH.exists():
        with open(WEIGHTS_PATH) as f:
            return json.load(f)
    # 初始化
    init = {
        'version': __version__,
        'updated_at': None,
        'total_samples': 0,
        'dimensions': {
            dim: {
                'alpha': PRIOR_ALPHA,
                'beta': PRIOR_BETA,
                'weight': DEFAULT_WEIGHTS[dim],
                'hits': 0,
                'misses': 0,
            }
            for dim in DEFAULT_WEIGHTS
        }
    }
    save_weights(init)
    return init


def save_weights(data: Dict):
    """持久化权重"""
    WEIGHTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WEIGHTS_PATH, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_current_weights() -> Dict:
    """获取当前五维权重（纯数值，供 auction_features 使用）"""
    data = load_weights()
    weights = {}
    for dim, info in data['dimensions'].items():
        weights[dim] = info['weight']
    return weights


# ═══════════════════════════════════════════
# 日内验证
# ═══════════════════════════════════════════

def get_intraday_return(code: str, date: str) -> Optional[float]:
    """
    获取当日实际涨跌（开盘→收盘）。

    优先用 akshare 日线，失败回退东方财富 API。
    返回: 百分比，正值=涨，负值=跌
    """
    # 尝试 data_pipeline
    try:
        from data_pipeline import get_stock_realtime
        rt = get_stock_realtime([code])
        if code in rt:
            return float(rt[code].get('change_pct', 0))
    except Exception:
        pass

    # 回退：东方财富 API
    try:
        import requests
        market = '1' if code.startswith(('6', '9')) else '0'
        url = 'https://push2.eastmoney.com/api/qt/stock/get'
        r = requests.get(url, params={
            'secid': f'{market}.{code}',
            'fields': 'f3',
        }, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://data.eastmoney.com/',
        }, timeout=10)
        d = r.json()
        return float(d.get('data', {}).get('f3', 0))
    except Exception:
        return None


# ═══════════════════════════════════════════
# 学习更新
# ═══════════════════════════════════════════

def learn_from_date(date: str) -> Dict:
    """
    处理指定日期的竞价数据，更新权重。

    返回: 更新后的权重数据
    """
    data = load_weights()

    # ── 先跑诊断 ──
    diag = diagnose_db(date)
    print(f"  {diag['message']}")
    if diag['status'] != 'ok':
        print(f"  💡 {diag.get('suggestion', '')}")
        print(f"  历史: {diag.get('recent_dates', [])}")
        return data

    print(f"  📊 {date}: {diag['today_rows']}行 {diag['today_stocks']}只 {diag['today_max_seq']}帧")

    conn = sqlite3.connect(str(DB_PATH))

    # 获取当日所有采集过的股票
    codes = conn.execute('''
        SELECT DISTINCT code FROM auction_frames WHERE date = ?
    ''', (date,)).fetchall()

    codes = [c[0] for c in codes]
    updated = 0
    for code in codes:
        # 1. 提取特征
        features = extract_features(date, code)
        if 'error' in features:
            continue

        # 2. 生成当天的竞价信号（用当天权重）
        weights = get_current_weights()
        score, signal, dims = score_auction(features, weights)

        # 3. 获取实际涨跌
        actual_return = get_intraday_return(code, date)
        if actual_return is None:
            continue

        # 4. 判断命中
        # strong/moderate 信号预期上涨 → actual > 0 即命中
        # caution 信号预期下跌 → actual < 0 即命中
        # weak/neutral 不参与学习
        if signal in ('strong', 'moderate') and actual_return > 0:
            hit = True
        elif signal == 'caution' and actual_return < 0:
            hit = True
        elif signal in ('weak', 'neutral'):
            continue  # 中性信号不学习
        else:
            hit = False

        # 5. 逐维度更新贝叶斯分布
        for dim in data['dimensions']:
            dim_score = dims.get(dim, 0)
            dim_max = DEFAULT_WEIGHTS[dim] * 100
            # 该维度得分高于 60% 最大值 → 视为该维度发出了看多信号
            threshold = dim_max * 0.6

            if dim_score >= threshold and hit:
                data['dimensions'][dim]['alpha'] += 1
                data['dimensions'][dim]['hits'] += 1
            elif dim_score >= threshold and not hit:
                data['dimensions'][dim]['beta'] += 1
                data['dimensions'][dim]['misses'] += 1

        updated += 1

    # 6. 重新计算权重
    for dim in data['dimensions']:
        info = data['dimensions'][dim]
        alpha = info['alpha']
        beta = info['beta']
        # 后验均值 = α/(α+β)，映射为权重
        posterior = alpha / (alpha + beta)
        info['weight'] = round(posterior * DEFAULT_WEIGHTS[dim] * 2, 4)
        info['accuracy'] = round(posterior, 4)

    # 归一化权重
    total_w = sum(data['dimensions'][d]['weight'] for d in data['dimensions'])
    for dim in data['dimensions']:
        data['dimensions'][dim]['weight'] = round(
            data['dimensions'][dim]['weight'] / total_w, 4
        )

    data['total_samples'] += updated
    data['updated_at'] = datetime.now().isoformat()
    save_weights(data)

    print(f"  ✅ 处理 {updated} 只，总样本 {data['total_samples']}")
    for dim, info in data['dimensions'].items():
        print(f"     {dim:15s} α={info['alpha']:4d} β={info['beta']:4d} "
              f"准确率={info['accuracy']:.2%} 权重={info['weight']:.4f}")

    return data


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description='竞价贝叶斯学习器 v1.1')
    p.add_argument('--date', help='指定日期 YYYYMMDD（默认昨天）')
    p.add_argument('--reset', action='store_true', help='重置所有权重')
    p.add_argument('--show', action='store_true', help='查看当前权重')
    p.add_argument('--diagnose', action='store_true', help='诊断 auction.db 数据状态')
    args = p.parse_args()

    if args.reset:
        WEIGHTS_PATH.unlink(missing_ok=True)
        print("🔄 权重已重置为初始值")
        args.show = True

    if args.diagnose:
        if args.date:
            date_str = args.date
        else:
            yesterday = datetime.now() - timedelta(days=1)
            date_str = yesterday.strftime('%Y%m%d')
        diag = diagnose_db(date_str)
        print(f"\n🔍 竞价数据库诊断  {date_str}")
        print(f"   {'─'*40}")
        print(f"   {diag['message']}")
        if diag.get('suggestion'):
            print(f"   💡 {diag['suggestion']}")
        print(f"   总行数: {diag['total_rows']}  |  当日行数: {diag['today_rows']}")
        print(f"   当日标的: {diag.get('today_stocks', 0)}只  |  帧数: {diag.get('today_max_seq', 0)}")
        if diag.get('recent_dates'):
            print(f"   最近数据:")
            for d in diag['recent_dates']:
                print(f"     {d['date']}: {d['rows']}行")
        return

    if args.show:
        data = load_weights()
        print(f"\n📊 竞价学习权重  v{data['version']}")
        print(f"   更新时间: {data.get('updated_at', '从未')}")
        print(f"   总样本: {data['total_samples']}")
        print(f"   {'─'*45}")
        print(f"   {'维度':12s} {'α':>5s} {'β':>5s} {'准确率':>8s} {'权重':>8s}")
        for dim, info in data['dimensions'].items():
            print(f"   {dim:12s} {info['alpha']:5d} {info['beta']:5d} "
                  f"{info.get('accuracy', 0):8.2%} {info['weight']:8.4f}")
        return

    if args.date:
        date_str = args.date
    else:
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime('%Y%m%d')

    print(f"🧠 竞价学习器 v{__version__}")
    learn_from_date(date_str)


if __name__ == '__main__':
    main()
