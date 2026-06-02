#!/usr/bin/env python3
"""
auction_collector.py — 竞价采集器 v1.0
=====================================
09:15-09:25 每3秒轮询东方财富API，采集竞价轨迹存入SQLite。

数据字段: 虚拟匹配价(f43) · 竞价量(f19) · 竞价额(f20) · 涨跌幅(f3)
采集目标: 每日推荐池(daily_pool.json)中的股票
存储格式: data/auction.db → auction_frames 表

用法:
  python3 auction_collector.py              # 单次采集一帧（测试用）
  python3 auction_collector.py --live       # 实时模式：09:15-09:25持续采集
  python3 auction_collector.py --dry-run    # 只打印不写入DB
"""

__version__ = "1.2.0"

import sys, os, json, sqlite3, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import requests

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(SCRIPT_DIR))

POOL_PATH = SCRIPT_DIR / 'data' / 'daily_pool.json'
DB_PATH = SCRIPT_DIR / 'data' / 'auction.db'

# 东方财富 API 参数
EM_URL = 'https://push2.eastmoney.com/api/qt/stock/get'
EM_FIELDS = 'f12,f14,f2,f3,f19,f20,f43,f44,f45,f46,f60'
EM_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://data.eastmoney.com/',
}

# 竞价时段
AUCTION_START = (9, 15)   # 09:15
AUCTION_END = (9, 25)     # 09:25
POLL_INTERVAL = 3          # 秒


# ═══════════════════════════════════════════
# SQLite 管理
# ═══════════════════════════════════════════

def init_db():
    """初始化数据库和表"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute('''
        CREATE TABLE IF NOT EXISTS auction_frames (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            seq INTEGER NOT NULL,
            price REAL,
            volume REAL,
            amount REAL,
            change_pct REAL,
            open_price REAL,
            prev_close REAL,
            recorded_at TEXT NOT NULL,
            UNIQUE(date, code, seq)
        )
    ''')
    conn.execute('''
        CREATE INDEX IF NOT EXISTS idx_auction_date_code
        ON auction_frames(date, code)
    ''')
    conn.commit()
    return conn


# ═══════════════════════════════════════════
# 标的获取
# ═══════════════════════════════════════════

def load_target_stocks() -> List[Dict]:
    """从推荐池加载目标股票，池空时降级到默认蓝筹+TOP资金流"""
    stocks = []
    if POOL_PATH.exists():
        try:
            with open(POOL_PATH) as f:
                data = json.load(f)
            recs = data.get('recommendations', [])
            if recs:
                stocks = [{'code': str(r['code']), 'name': str(r['name'])} for r in recs]
        except Exception:
            pass

    if not stocks:
        # 降级：默认蓝筹 + 资金流入 TOP4
        stocks = [
            {'code': '600519', 'name': '贵州茅台'},
            {'code': '000858', 'name': '五粮液'},
            {'code': '300750', 'name': '宁德时代'},
            {'code': '601318', 'name': '中国平安'},
            {'code': '000333', 'name': '美的集团'},
            {'code': '002594', 'name': '比亚迪'},
        ]
        try:
            from data_pipeline import get_top_flow_stocks
            tops = get_top_flow_stocks(6)
            existing = {s['code'] for s in stocks}
            for t in tops:
                if str(t['code']) not in existing:
                    stocks.append({'code': str(t['code']), 'name': str(t['name'])})
                    existing.add(str(t['code']))
        except Exception:
            pass

    return stocks


# ═══════════════════════════════════════════
# 多通道竞价采集 (v1.2)
# ═══════════════════════════════════════════

# 备用通道
TENCENT_URL = 'https://qt.gtimg.cn/q='
SINA_URL = 'https://hq.sinajs.cn/list='

# 通道统计
_channel_stats = {'em': 0, 'tencent': 0, 'sina': 0, 'fail': 0}


def fetch_one_em(code: str) -> Optional[Dict]:
    """东方财富 push2 竞价采集"""
    market = '1' if code.startswith(('6', '9')) else '0'
    secid = f'{market}.{code}'
    try:
        r = requests.get(EM_URL, params={
            'secid': secid,
            'fields': EM_FIELDS,
        }, headers=EM_HEADERS, timeout=8)
        d = r.json()
        data = d.get('data', {})
        if not data:
            return None
        return {
            'code': str(data.get('f12', code)),
            'name': str(data.get('f14', '')),
            'price': float(data.get('f43', 0) or data.get('f2', 0) or 0) / 100,
            'change_pct': float(data.get('f3', 0) or 0),
            'volume': float(data.get('f19', 0) or data.get('f47', 0) or 0),
            'amount': float(data.get('f20', 0) or 0),
            'open_price': float(data.get('f46', 0) or 0) / 100,
            'prev_close': float(data.get('f60', 0) or 0) / 100,
            'channel': 'em',
        }
    except Exception:
        return None


def fetch_one_tencent(code: str) -> Optional[Dict]:
    """腾讯行情 竞价采集 (47+字段)"""
    prefix = 'sh' if code.startswith(('6', '9')) else 'sz'
    symbol = f'{prefix}{code}'
    try:
        r = requests.get(TENCENT_URL + symbol, timeout=8)
        if r.status_code != 200 or not r.text or len(r.text) < 20:
            return None
        # 格式: v_sz000001="51~平安银行~000001~现价~昨收~开盘~成交量~..."
        # 双引号内的内容用 ~ 分隔
        content = r.text.split('\"')[1] if '\"' in r.text else r.text.split('=')[1] if '=' in r.text else ''
        if not content:
            return None
        parts = content.split('~')
        if len(parts) < 36:
            return None

        # 腾讯字段映射 (从0开始):
        # 0=市场 1=名称 2=代码 3=现价 4=昨收 5=开盘
        # 6=成交量(手) 7=外盘 8=内盘
        # 9-18=买一~五价量 19-28=卖一~五价量
        # 30=时间 31=涨跌额 32=涨跌幅 33=最高 34=最低
        # 36=成交额(万) 37=换手率 38=市盈率
        return {
            'code': str(parts[2]),
            'name': str(parts[1]),
            'price': float(parts[3] or 0),
            'change_pct': float(parts[32] or 0),
            'volume': float(parts[6] or 0) * 100,  # 手→股
            'amount': float(parts[36] or parts[37] or 0) * 10000,  # 万→元
            'open_price': float(parts[5] or 0),
            'prev_close': float(parts[4] or 0),
            'channel': 'tencent',
        }
    except Exception:
        return None


def fetch_one_sina(code: str) -> Optional[Dict]:
    """Sina 行情 竞价采集 (竞价期 parts[1]=虚拟匹配价)"""
    prefix = 'sh' if code.startswith(('6', '9')) else 'sz'
    symbol = f'{prefix}{code}'
    try:
        r = requests.get(SINA_URL + symbol, timeout=8,
                        headers={'Referer': 'https://finance.sina.com.cn'})
        if r.status_code != 200:
            return None
        import re
        match = re.search(r'\"(.+?)\"', r.text)
        if not match:
            return None
        parts = match.group(1).split(',')
        if len(parts) < 30:
            return None
        return {
            'code': code,
            'name': str(parts[0]),
            'price': float(parts[3] or 0),
            'change_pct': float(parts[3] and parts[2] and (float(parts[3])/float(parts[2])-1)*100 or 0),
            'volume': float(parts[8] or 0),
            'amount': float(parts[9] or 0),
            'open_price': float(parts[1] or 0),
            'prev_close': float(parts[2] or 0),
            'channel': 'sina',
        }
    except Exception:
        return None


def fetch_one(code: str) -> Optional[Dict]:
    """多通道竞价采集：东方财富 → 腾讯 → Sina 自动降级"""
    # 1. 东方财富 (主)
    result = fetch_one_em(code)
    if result and result.get('price', 0) > 0:
        _channel_stats['em'] += 1
        return result

    # 2. 腾讯 (备1)
    result = fetch_one_tencent(code)
    if result and result.get('price', 0) > 0:
        _channel_stats['tencent'] += 1
        return result

    # 3. Sina (备2)
    result = fetch_one_sina(code)
    if result and result.get('price', 0) > 0:
        _channel_stats['sina'] += 1
        return result

    _channel_stats['fail'] += 1
    return None


def fetch_batch(codes: List[str]) -> Dict[str, Dict]:
    """批量采集（顺序请求，避免限流）"""
    results = {}
    for code in codes:
        data = fetch_one(code)
        if data:
            results[code] = data
        time.sleep(0.15)  # 150ms间隔，避免触发东方财富限流
    return results


# ═══════════════════════════════════════════
# 存储
# ═══════════════════════════════════════════

def save_frame(conn, date_str: str, seq: int, stock_data: Dict):
    """保存一帧竞价数据"""
    now = datetime.now().isoformat()
    conn.execute('''
        INSERT OR REPLACE INTO auction_frames
        (date, code, name, seq, price, volume, amount, change_pct, open_price, prev_close, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        date_str,
        stock_data['code'],
        stock_data['name'],
        seq,
        stock_data['price'],
        stock_data['volume'],
        stock_data['amount'],
        stock_data['change_pct'],
        stock_data.get('open_price', 0),
        stock_data.get('prev_close', 0),
        now,
    ))


# ═══════════════════════════════════════════
# 时间检查
# ═══════════════════════════════════════════

def is_auction_time() -> bool:
    """判断当前是否在竞价时段"""
    now = datetime.now()
    h, m = now.hour, now.minute
    return (h == 9 and 15 <= m <= 25)


def sleep_until_auction():
    """阻塞直到竞价开始"""
    while True:
        now = datetime.now()
        target = now.replace(hour=9, minute=15, second=1, microsecond=0)
        if now >= target:
            return
        wait = (target - now).total_seconds()
        if wait > 60:
            print(f"  ⏳ 距竞价开始还有 {int(wait//60)}分{int(wait%60)}秒...")
            time.sleep(min(wait, 60))
        else:
            print(f"  ⏳ {int(wait)}秒后进入竞价采集...")
            time.sleep(max(wait, 1))


# ═══════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════

def run_live():
    """实时竞价采集模式（v1.1 加固：API预热 + 异常隔离 + 降级标的）"""
    stocks = load_target_stocks()
    codes = [s['code'] for s in stocks]
    date_str = datetime.now().strftime('%Y%m%d')

    print(f"🎯 竞价采集器 v{__version__}")
    print(f"   日期: {date_str}  |  标的: {len(codes)}只  |  间隔: {POLL_INTERVAL}s")
    print(f"   时段: 09:15 - 09:25  |  预计: ~{(10*60//POLL_INTERVAL)}帧/只")
    print()

    # ── API 预热：多轮尝试 + 指数退避，东方财富 09:15 冷启动很慢 ──
    warm_ok = False
    for attempt in range(6):
        test = fetch_one(codes[0])
        if test and test.get('price', 0) > 0:
            warm_ok = True
            print(f"  🔥 API预热成功 (尝试{attempt+1}/6, {codes[0]} ¥{test['price']:.2f})")
            break
        print(f"  ⏳ API预热重试 {attempt+1}/6...")
        time.sleep(2 * (attempt + 1))  # 2s→4s→6s→8s→10s→12s, 总计60s
    if not warm_ok:
        # 最后一次：尝试 fetch_batch 整体拉取
        print(f"  ⚠️ 单票预热失败，尝试批量拉取...")
        batch = fetch_batch(codes[:3])
        if batch:
            warm_ok = True
            print(f"  🔥 批量拉取成功 ({len(batch)}/3只)")
    if not warm_ok:
        print(f"  ❌ API不可用（非交易时段或东方财富限流），退出采集")
        print(f"  💡 提示：竞价采集器仅在 09:15-09:25 交易时段运行")
        return  # 干净退出，不返回error

    conn = init_db()
    seq = 0
    start_time = time.time()
    consecutive_failures = 0
    max_consecutive_fail = 10  # 连续失败10轮后告警但不退出

    while is_auction_time():
        seq += 1
        tick_start = time.time()

        # ── 整轮 try/except 隔离，单轮失败不中断采集 ──
        try:
            batch = fetch_batch(codes)
            ok_count = len(batch)

            for sd in batch.values():
                save_frame(conn, date_str, seq, sd)

            conn.commit()

            if ok_count > 0:
                consecutive_failures = 0
                sample = list(batch.values())[0]
                ch = sample.get('channel', '?')
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                      f"帧 {seq:3d}  |  成功 {ok_count}/{len(codes)}只 [{ch}]  |  "
                      f"例: {sample['name']} ¥{sample['price']:.2f} {sample['change_pct']:+.2f}%  |  "
                      f"耗时 {time.time()-tick_start:.1f}s")
            else:
                consecutive_failures += 1
                if consecutive_failures <= 3 or consecutive_failures % 5 == 0:
                    print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                          f"帧 {seq:3d}  |  ❌ 全部失败 ({consecutive_failures}连败)  |  "
                          f"耗时 {time.time()-tick_start:.1f}s")
        except Exception as e:
            consecutive_failures += 1
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] "
                  f"帧 {seq:3d}  |  💥 异常: {str(e)[:60]}  |  继续下一轮...")
            try:
                conn.rollback()
            except Exception:
                pass

        if consecutive_failures >= max_consecutive_fail:
            print(f"  ⚠️ 连续 {max_consecutive_fail} 轮失败，API可能已不可用，退出采集")
            break

        # 动态调整等间隔
        elapsed = time.time() - tick_start
        wait = max(0.2, POLL_INTERVAL - elapsed)
        time.sleep(wait)

    conn.close()

    total_time = time.time() - start_time
    print(f"\n✅ 竞价采集完成  |  总帧: {seq}  |  耗时: {total_time:.0f}s  |  "
          f"DB: {DB_PATH}")
    stats = _channel_stats
    total_ok = stats['em'] + stats['tencent'] + stats['sina']
    if total_ok > 0:
        print(f"   通道分布: 东方财富={stats['em']} | 腾讯={stats['tencent']} | Sina={stats['sina']} | 失败={stats['fail']}")
    # 重置统计
    for k in _channel_stats:
        _channel_stats[k] = 0


def run_once(dry_run: bool = False):
    """单次采集（测试用）"""
    stocks = load_target_stocks()
    if not stocks:
        print("⚠️ 无推荐池标的，使用默认")
        stocks = [{'code': '600519', 'name': '贵州茅台'}]

    codes = [s['code'] for s in stocks]
    date_str = datetime.now().strftime('%Y%m%d')

    print(f"🎯 竞价采集器 v{__version__} — 单次采集")
    print(f"   标的: {len(codes)}只  |  dry_run={dry_run}")

    batch = fetch_batch(codes)
    print(f"\n  成功: {len(batch)}/{len(codes)}只\n")

    for code, sd in batch.items():
        print(f"  {sd['code']} {sd['name']:8s}  "
              f"¥{sd['price']:.2f}  {sd['change_pct']:+.2f}%  "
              f"量:{sd['volume']:.0f}手 额:{sd['amount']:.0f}万")

    if not dry_run and batch:
        conn = init_db()
        for sd in batch.values():
            save_frame(conn, date_str, 0, sd)
        conn.commit()
        conn.close()
        print(f"\n✅ 已写入 DB: {DB_PATH}")


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description='竞价采集器 v1.0')
    p.add_argument('--live', action='store_true', help='实时模式（09:15-09:25持续采集）')
    p.add_argument('--dry-run', action='store_true', help='只打印不写入DB')
    p.add_argument('--wait', action='store_true', help='阻塞等待竞价开始后进入live模式')
    args = p.parse_args()

    if args.live or args.wait:
        if args.wait or not is_auction_time():
            sleep_until_auction()
        run_live()
    else:
        run_once(dry_run=args.dry_run)


if __name__ == '__main__':
    main()
