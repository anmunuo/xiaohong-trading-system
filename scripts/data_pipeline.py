#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安幕诺家族 - 小红 🌹 统一数据管道
==================================
所有报告脚本的唯一数据来源,杜绝任何硬编码假数据。

功能:
  - get_index_data()              → 全球指数实时数据
  - get_north_flow()              → 北向资金实时数据
  - get_north_flow_tushare()      → Tushare版北向资金
  - get_individual_money_flow()   → 个股资金流向
  - get_sector_flow_rank()        → 板块资金流向排名
  - get_top_flow_stocks()         → 资金流入TOP股票
  - get_stock_candidates()        → 真实选股（基于资金面）

数据来源优先级:
  Tushare Pro > 东方财富API > AKShare > 新浪

数据原则:
  1. 每个函数都是独立获取真实数据
  2. 失败时返回空数据+标记，绝不伪造
  3. 所有数据标注来源(data_source字段）

作者: 弯弯 🌙 (架构统一)
创建: 2026-05-08
版本: 1.0.0
"""

import sys
import os
import json
import time
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging

_log = logging.getLogger(__name__)


# ==================== 配置 ====================

CACHE_EXPIRE_SECONDS = 300  # 5分钟缓存

def _load_tushare_token() -> str:
    """从环境变量加载 Tushare Token（优先级：env > .env文件）"""
    import os
    from pathlib import Path
    token = os.environ.get('TUSHARE_TOKEN', '')
    if not token:
        env_path = Path(__file__).resolve().parent.parent / '.env'
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith('TUSHARE_TOKEN='):
                    token = line.split('=', 1)[1].strip().strip('"').strip("'")
                    break
    return token

TUSHARE_TOKEN = _load_tushare_token()

# ==================== Tushare 初始化 ====================

_tushare_pro = None

def _get_ts_pro():
    """获取Tushare Pro API实例（单例）"""
    global _tushare_pro
    if _tushare_pro is None:
        import tushare as ts
        ts.set_token(TUSHARE_TOKEN)
        _tushare_pro = ts.pro_api()
    return _tushare_pro


# ==================== 缓存 ====================

_cache: Dict[str, Tuple[Any, float]] = {}

def _cached(key: str, expire: int = CACHE_EXPIRE_SECONDS) -> Optional[Any]:
    """检查缓存"""
    if key in _cache:
        data, ts = _cache[key]
        if (datetime.now().timestamp() - ts) < expire:
            return data
    return None

def _set_cache(key: str, data: Any):
    """设置缓存"""
    _cache[key] = (data, datetime.now().timestamp())


# ==================== 指数数据 ====================

def get_index_data() -> Dict[str, Dict]:
    """
    获取全球指数实时数据(真实API,无静态回退)

    Returns:
        {
            'asia': {'nikkei': (价格, 涨跌幅), 'hangseng': (...), 'shanghai': (...)},
            'europe': {'ftse': (...), 'dax': (...)},
            'us': {'dow': (...), 'sp500': (...), 'nasdaq': (...)},
            'data_source': str
        }
    """
    cache_key = 'index_data'
    cached = _cached(cache_key, 120)  # 2分钟缓存
    if cached:
        return cached

    import requests
    import re
    import akshare as ak

    headers = {
        'Referer': 'https://finance.sina.com.cn',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    def _sina_us(sina_symbol):
        url = f'https://hq.sinajs.cn/list={sina_symbol}'
        r = requests.get(url, headers=headers, timeout=15)
        match = re.search(r'\"(.+?)\"', r.text)
        if match:
            parts = match.group(1).split(',')
            if len(parts) >= 3:
                price = float(parts[1])
                change = float(parts[2]) if parts[2] else 0
                return price, change
        return None, None

    def _tushare_sh():
        import tushare as ts
        env_path = Path(__file__).resolve().parent.parent.parent / 'config' / '.env'
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if 'TUSHARE_TOKEN' in line:
                    token = line.split('=')[1].strip().strip("'").strip('"')
                    ts.set_token(token)
                    break
        df = ts.realtime_quote(ts_code='000001.SH')
        if not df.empty:
            price = float(df['PRICE'].iloc[0])
            pre_close = float(df['PRE_CLOSE'].iloc[0])
            change = round(((price - pre_close) / pre_close) * 100, 2)
            return price, change
        return None, None

    result = {'asia': {}, 'europe': {}, 'us': {}}
    sources = []

    # 亚洲
    try:
        df = ak.index_global_hist_sina(symbol='日经225指数')
        if not df.empty and len(df) >= 2:
            price = float(df['close'].iloc[-1])
            prev = float(df['close'].iloc[-2])
            change = round(((price - prev) / prev) * 100, 2)
            result['asia']['nikkei'] = (round(price, 2), change)
            sources.append('nikkei:akshare')
    except Exception:
            pass  # noqa: E722

    try:
        df = ak.stock_hk_index_daily_sina(symbol='HSI')
        if not df.empty and len(df) >= 2:
            price = float(df['close'].iloc[-1])
            prev = float(df['close'].iloc[-2])
            change = round(((price - prev) / prev) * 100, 2)
            result['asia']['hangseng'] = (round(price, 2), change)
            sources.append('hangseng:akshare')
    except Exception:
            pass  # noqa: E722

    try:
        price, change = _tushare_sh()
        if price:
            result['asia']['shanghai'] = (round(price, 2), change)
            sources.append('shanghai:tushare')
    except Exception:
        try:
            df = ak.stock_zh_index_daily(symbol='sh000001')
            if not df.empty and len(df) >= 2:
                price = float(df['close'].iloc[-1])
                prev = float(df['close'].iloc[-2])
                change = round(((price - prev) / prev) * 100, 2)
                result['asia']['shanghai'] = (round(price, 2), change)
                sources.append('shanghai:akshare')
        except Exception:
            pass  # noqa: E722

    # 欧洲
    for sym, label, code in [
        ('ftse', '英国富时100指数', 'ftse'),
        ('dax', '德国DAX 30种股价指数', 'dax'),
    ]:
        try:
            df = ak.index_global_hist_sina(symbol=label)
            if not df.empty and len(df) >= 2:
                price = float(df['close'].iloc[-1])
                prev = float(df['close'].iloc[-2])
                change = round(((price - prev) / prev) * 100, 2)
                result['europe'][code] = (round(price, 2), change)
                sources.append(f'{code}:akshare')
        except Exception:
            pass  # noqa: E722

    # 美股
    us_map = [('gb_dji', 'dow'), ('gb_inx', 'sp500'), ('gb_ixic', 'nasdaq')]
    for sina_sym, code in us_map:
        try:
            price, change = _sina_us(sina_sym)
            if price:
                result['us'][code] = (round(price, 2), change)
                sources.append(f'{code}:sina')
        except Exception:
            pass  # noqa: E722

    result['data_source'] = 'real' if sources else 'no_data'
    _set_cache(cache_key, result)
    return result


# ==================== 北向资金 ====================

def get_north_flow() -> Dict:
    """
    获取北向资金数据（AKShare 优先获取今日数据，Tushare 提供明细回退）

    Returns:
        {'net_flow': 亿, 'status': str, 'detail': str, 'date': str, 'data_type': str, 'data_source': str}
    """
    cache_key = 'north_flow'
    cached = _cached(cache_key, 120)
    if cached:
        return cached

    result = {'net_flow': 0, 'status': '数据获取中', 'detail': '', 'date': '', 'data_type': '', 'data_source': 'no_data'}
    today = datetime.now().strftime('%Y%m%d')
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

    # ---- 1. AKShare 优先（总是返回最新日期）----
    akshare_data = None
    try:
        import akshare as ak
        df = ak.stock_hsgt_fund_flow_summary_em()
        if not df.empty:
            north = df[df['资金方向'] == '北向']
            if not north.empty:
                total_flow = float(north['成交净买额'].sum())
                flow_yi = total_flow / 1e8 if abs(total_flow) > 1e6 else total_flow
                flow_yi = round(flow_yi, 2)
                akshare_data = {
                    'net_flow': flow_yi,
                    'detail': f"沪股通:{float(north.iloc[0]['成交净买额'])/1e8:.1f}亿, 深股通:{float(north.iloc[1]['成交净买额'])/1e8:.1f}亿",
                    'date': str(df.iloc[0].get('交易日', today)),
                    'data_type': '当日盘中（非终值）',
                    'data_source': 'akshare_hsgt'
                }
    except Exception:
        pass

    # ---- 2. Tushare Pro 回退（提供更准确的 T-1 日终数据）----
    tushare_data = None
    try:
        pro = _get_ts_pro()
        df = pro.moneyflow_hsgt(trade_date=yesterday)
        if df.empty:
            cal = pro.trade_cal(exchange='SSE', start_date=(datetime.now() - timedelta(days=7)).strftime('%Y%m%d'), end_date=yesterday)
            trading_days = cal[cal['is_open'] == 1]['cal_date'].tolist()
            if trading_days:
                df = pro.moneyflow_hsgt(trade_date=trading_days[-1])

        if not df.empty:
            row = df.iloc[-1]
            ggt_ss = float(row.get('ggt_ss', 0))
            ggt_sz = float(row.get('ggt_sz', 0))
            north_total = (ggt_ss + ggt_sz) / 1e4
            north_total = round(north_total, 2)
            data_date = str(df.iloc[-1].get('trade_date', ''))

            tushare_data = {
                'net_flow': north_total,
                'detail': f'沪股通:{round(ggt_ss/1e4,2):.1f}亿, 深股通:{round(ggt_sz/1e4,2):.1f}亿',
                'date': data_date,
                'data_type': 'T-1日终（非实时）',
                'data_source': 'tushare_pro'
            }
    except Exception:
        pass

    # ---- 3. 择优使用 ----
    # 策略：AKShare 日期≥yesterday 则优先（数据比 tushare 新鲜），否则用 tushare
    use_akshare = False
    if akshare_data:
        akshare_date = akshare_data.get('date', '')
        if akshare_date >= yesterday or akshare_data['net_flow'] != 0:
            use_akshare = True
        elif not tushare_data:
            use_akshare = True  # tushare 也失败，用 akshare

    if use_akshare and akshare_data:
        emoji = '🟢' if akshare_data['net_flow'] >= 0 else '🔴'
        status = f'{emoji} {abs(akshare_data["net_flow"]):.1f}亿元'
        status += ' 净流入' if akshare_data['net_flow'] >= 0 else ' 净流出'
        result = {
            'net_flow': akshare_data['net_flow'],
            'status': status,
            'detail': akshare_data['detail'],
            'date': akshare_data['date'],
            'data_type': akshare_data['data_type'],
            'data_source': akshare_data['data_source']
        }
    elif tushare_data:
        emoji = '🟢' if tushare_data['net_flow'] >= 0 else '🔴'
        status = f'{emoji} {abs(tushare_data["net_flow"]):.1f}亿元'
        status += ' 净流入' if tushare_data['net_flow'] >= 0 else ' 净流出'
        result = {
            'net_flow': tushare_data['net_flow'],
            'status': status,
            'detail': tushare_data['detail'],
            'date': tushare_data['date'],
            'data_type': tushare_data['data_type'],
            'data_source': tushare_data['data_source']
        }

    _set_cache(cache_key, result)
    return result


# ==================== 市场资金流向 ====================

def get_market_money_flow() -> Dict:
    """
    获取市场整体资金流向(今日)
    优先 AKShare，失败时用 tushare moneyflow 全市场汇总

    Returns:
        {'main_net': 亿, 'retail_net': 亿, 'data_source': str}
    """
    cache_key = 'market_flow'
    cached = _cached(cache_key, 300)
    if cached:
        return cached

    import akshare as ak

    result = {'main_net': 0, 'retail_net': 0, 'data_source': 'no_data'}

    # ---- 1. AKShare 优先 ----
    try:
        df = ak.stock_market_fund_flow()
        if not df.empty:
            last = df.iloc[-1]
            main_net = float(last['主力净流入-净额']) / 1e8
            result = {
                'main_net': round(main_net, 2),
                'main_pct': float(last['主力净流入-净占比']),
                'retail_net': round(float(last['小单净流入-净额']) / 1e8, 2),
                'sh_index': float(last['上证-收盘价']),
                'sh_change': float(last['上证-涨跌幅']),
                'sz_index': float(last['深证-收盘价']),
                'sz_change': float(last['深证-涨跌幅']),
                'data_source': 'akshare_market_flow'
            }
            _set_cache(cache_key, result)
            return result
    except Exception:
        pass

    # ---- 2. Tushare 全市场汇总回退 ----
    try:
        pro = _get_ts_pro()
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
        df = pro.moneyflow(trade_date=yesterday)
        if df.empty:
            # 尝试最近交易日
            cal = pro.trade_cal(exchange='SSE', start_date=(datetime.now() - timedelta(days=7)).strftime('%Y%m%d'), end_date=yesterday)
            trading_days = cal[cal['is_open'] == 1]['cal_date'].tolist()
            if trading_days:
                df = pro.moneyflow(trade_date=trading_days[-1])

        if not df.empty:
            # 汇总：超大单+大单净买入 ≈ 主力净流入
            buy_main = df['buy_elg_amount'].sum() + df['buy_lg_amount'].sum()
            sell_main = df['sell_elg_amount'].sum() + df['sell_lg_amount'].sum()
            main_net = (buy_main - sell_main) / 1e4  # 万元→亿元

            # 小单净买入 ≈ 散户净流入
            buy_retail = df['buy_sm_amount'].sum()
            sell_retail = df['sell_sm_amount'].sum()
            retail_net = (buy_retail - sell_retail) / 1e4

            result = {
                'main_net': round(main_net, 2),
                'retail_net': round(retail_net, 2),
                'stock_count': len(df),
                'trade_date': str(df.iloc[0].get('trade_date', yesterday)),
                'data_source': 'tushare_moneyflow_aggregate'
            }
    except Exception:
        pass

    _set_cache(cache_key, result)
    return result


# ==================== 个股资金流向 ====================

def get_individual_money_flow(stock_code: str, market: str = 'sh') -> Dict:
    """
    获取单只个股资金流向（Tushare Pro 优先）

    Tushare moneyflow 返回（万元）：
      - buy_lg_amount: 大单买入
      - sell_lg_amount: 大单卖出
      - buy_elg_amount: 超大单买入
      - sell_elg_amount: 超大单卖出
      - net_mf_amount: 净流入

    Args:
        stock_code: 股票代码，如 '688012'
        market: sh/sz（仅 AKShare 备用时使用）

    Returns:
        {'main_net': 万, 'main_pct': %, 'date': str, 'close': float, 'change_pct': %, 'data_source': str}
    """
    from datetime import datetime, timedelta

    ts_code = f"{stock_code}.SH" if market == 'sh' else f"{stock_code}.SZ"
    today = datetime.now().strftime('%Y%m%d')
    week_ago = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')

    result = {'main_net': 0, 'main_pct': 0, 'date': '', 'close': 0, 'change_pct': 0, 'data_source': 'no_data'}

    # ---- 1. Tushare Pro ----
    try:
        pro = _get_ts_pro()
        df = pro.moneyflow(ts_code=ts_code, start_date=week_ago, end_date=today)
        if not df.empty:
            last = df.iloc[-1]
            net_mf = float(last['net_mf_amount']) / 1e4 if abs(float(last['net_mf_amount'])) > 0 else 0

            # 计算主力净占比
            buy_lg = float(last.get('buy_lg_amount', 0)) + float(last.get('buy_elg_amount', 0))
            sell_lg = float(last.get('sell_lg_amount', 0)) + float(last.get('sell_elg_amount', 0))
            total = buy_lg + sell_lg
            main_pct = round(((buy_lg - sell_lg) / total) * 100, 2) if total > 0 else 0

            result = {
                'main_net': round(net_mf, 2),
                'main_pct': main_pct,
                'date': str(last['trade_date']),
                'close': 0,
                'change_pct': 0,
                'data_source': 'tushare_pro'
            }
            return result
    except Exception:
            pass  # noqa: E722

    # ---- 2. AKShare 回退 ----
    try:
        import akshare as ak
        df = ak.stock_individual_fund_flow(stock=stock_code, market=market)
        if not df.empty:
            last = df.iloc[-1]
            result = {
                'main_net': round(float(last['主力净流入-净额']) / 1e4, 2),
                'main_pct': float(last['主力净流入-净占比']),
                'date': str(last['日期']),
                'close': float(last['收盘价']),
                'change_pct': float(last['涨跌幅']),
                'data_source': 'akshare_individual_flow'
            }
    except Exception:
            pass  # noqa: E722

    return result


# ==================== 板块资金排名 ====================

def _em_api_get(url: str, params: dict) -> Optional[dict]:
    """东方财富API统一请求(带重试+退避)"""
    import requests
    import time
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Referer': 'https://data.eastmoney.com/'
    }
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=15, headers=headers)
            if r.status_code == 200:
                return r.json()
        except Exception:
            if attempt < 2:
                time.sleep(1 + attempt)
    return None


def get_sector_flow_rank(sector_type: str = '3') -> List[Dict]:
    """
    获取板块资金流向排名(东方财富API优先，tushare 板块涨跌回退)

    Args:
        sector_type: '3'=行业, '4'=概念, '2'=地域

    Returns:
        [{'name': str, 'flow': 万, 'change_pct': %}, ...]
    """
    cache_key = f'sector_flow_{sector_type}'
    cached = _cached(cache_key, 300)
    if cached:
        return cached

    sectors = []

    # ---- 1. 东方财富 API 优先 ----
    try:
        params = {
            'pn': 1, 'pz': 10, 'po': 1, 'np': 1,
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            'fltt': 2, 'invt': 2, 'fid': 'f62',
            'fs': f'm:90+t:{sector_type}',
            'fields': 'f12,f14,f3,f62,f184,f20'
        }
        data = _em_api_get('https://push2.eastmoney.com/api/qt/clist/get', params)
        if data and data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff'][:10]:
                flow = float(item.get('f62', 0)) / 1e4  # 元→万
                sectors.append({
                    'name': item.get('f14', ''),
                    'flow': round(flow, 2),
                    'change_pct': item.get('f3', 0),
                })
    except Exception:
        pass

    # ---- 2. Tushare 同花顺板块回退 ----
    if not sectors:
        try:
            pro = _get_ts_pro()
            # 获取最近交易日板块涨跌排名
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            df = pro.ths_daily(trade_date=yesterday)
            if df.empty:
                cal = pro.trade_cal(exchange='SSE', start_date=(datetime.now() - timedelta(days=7)).strftime('%Y%m%d'), end_date=yesterday)
                trading_days = cal[cal['is_open'] == 1]['cal_date'].tolist()
                if trading_days:
                    df = pro.ths_daily(trade_date=trading_days[-1])

            if not df.empty:
                # 按涨跌幅排序取 top 10
                df['pct_chg'] = df['pct_chg'].astype(float)
                top_sectors = df.nlargest(10, 'pct_chg')
                for _, row in top_sectors.iterrows():
                    sectors.append({
                        'name': row.get('name', str(row.get('ts_code', '?'))),
                        'change_pct': round(float(row['pct_chg']), 2),
                        'flow': 0,  # tushare 板块数据不含资金流
                        'data_source': 'tushare_ths_daily'
                    })
        except Exception:
            pass

    _set_cache(cache_key, sectors)
    return sectors


# ==================== 分时K线 (Sina) ====================

def get_intraday_minutes(stock_code: str, scale: int = 5, count: int = 48) -> List[Dict]:
    """
    获取个股分时K线数据 (Sina API)

    Args:
        stock_code: '000001' 或 '600519' (纯数字，不含前缀)
        scale: 1/5/15/30/60 分钟
        count: 返回K线数量 (max 约 240)

    Returns:
        [{'time': datetime_str, 'open': float, 'high': float, 'low': float,
          'close': float, 'volume': int, 'amount': float}, ...]
    """
    import requests
    import re

    cache_key = f'intraday_{stock_code}_{scale}_{count}'
    cached = _cached(cache_key, 60)  # 分时数据60秒缓存
    if cached:
        return cached

    bars = []

    # 判断市场: 6开头→sh, 0/3开头→sz
    prefix = 'sh' if stock_code.startswith(('6', '9')) else 'sz'
    symbol = f'{prefix}{stock_code}'

    try:
        url = 'https://quotes.sina.cn/cn/api/jsonp_v2.php/data/CN_MarketDataService.getKLineData'
        params = {'symbol': symbol, 'scale': scale, 'ma': 'no', 'datalen': count}
        r = requests.get(url, params=params, timeout=10,
                        headers={'Referer': 'https://finance.sina.com.cn'})
        if r.status_code == 200:
            match = re.search(r'\((.+)\)', r.text)
            if match:
                data = json.loads(match.group(1))
                for d in data:
                    bars.append({
                        'time': d['day'],
                        'open': float(d['open']),
                        'high': float(d['high']),
                        'low': float(d['low']),
                        'close': float(d['close']),
                        'volume': int(d['volume']),
                        'amount': float(d['amount']),
                    })
    except Exception:
        pass

    _set_cache(cache_key, bars)
    return bars


def get_intraday_volume_alert(stock_code: str, scale: int = 5) -> Dict:
    """
    基于分时数据检测量价异动

    Returns:
        {'alert': bool, 'signal': str, 'vol_ratio': float, 'price_chg': float, ...}
    """
    bars = get_intraday_minutes(stock_code, scale=scale, count=48)
    if len(bars) < 10:
        return {'alert': False, 'signal': '数据不足', 'vol_ratio': 0, 'price_chg': 0}

    # 最近2根 vs 前10根均量
    recent_vol = sum(b['volume'] for b in bars[-2:]) / 2
    baseline_vol = sum(b['volume'] for b in bars[-12:-2]) / max(len(bars[-12:-2]), 1)
    vol_ratio = recent_vol / baseline_vol if baseline_vol > 0 else 1.0

    # 价格变化
    price_chg = (bars[-1]['close'] - bars[-12]['close']) / bars[-12]['close'] * 100

    # 判断信号
    signal = ''
    if vol_ratio >= 3.0 and price_chg > 0:
        signal = '放量上涨'
    elif vol_ratio >= 3.0 and price_chg < 0:
        signal = '放量下跌⚠️'
    elif vol_ratio >= 2.0 and abs(price_chg) < 0.5:
        signal = '放量滞涨⚠️'
    elif vol_ratio <= 0.3 and abs(price_chg) > 1.5:
        signal = '缩量异动'

    return {
        'alert': bool(signal and '⚠️' in signal),
        'signal': signal or '正常',
        'vol_ratio': round(vol_ratio, 2),
        'price_chg': round(price_chg, 2),
        'bars_analyzed': len(bars),
    }


# ==================== 财务报表 (tushare) v8.3 ====================

def get_financial_indicator(stock_code: str, period: str = None) -> Dict:
    """
    获取个股核心财务指标 (fina_indicator — 108字段)。

    Args:
        stock_code: '000001.SZ' 格式
        period: '20251231' 最近年度，None=最近一期

    Returns:
        {roe, roa, gross_margin, netprofit_margin, eps, bps,
         debt_to_assets, ocf_ps, fcff, revenue_yoy, profit_yoy, ...}
    """
    if period is None:
        from datetime import datetime
        y = datetime.now().year - 1
        period = f'{y}1231'

    cache_key = f'fin_ind_{stock_code}_{period}'
    cached = _cached(cache_key, 86400)
    if cached:
        return cached

    result = {'data_source': 'no_data'}
    try:
        pro = _get_ts_pro()
        tscode = stock_code if '.' in stock_code else f'{stock_code}.SZ' if stock_code.startswith(('0','3')) else f'{stock_code}.SH'
        df = pro.fina_indicator(ts_code=tscode, period=period)
        if df is not None and not df.empty:
            row = df.iloc[0]
            result = {
                'ts_code': tscode,
                'period': period,
                'eps': _safe_float(row, 'eps'),
                'bps': _safe_float(row, 'bps'),
                'roe': _safe_float(row, 'roe'),
                'roa': _safe_float(row, 'roa_yearly'),
                'gross_margin': _safe_float(row, 'grossprofit_margin'),
                'netprofit_margin': _safe_float(row, 'netprofit_margin'),
                'debt_to_assets': _safe_float(row, 'debt_to_assets'),
                'ocf_ps': _safe_float(row, 'ocfps'),
                'fcff': _safe_float(row, 'fcff'),
                'revenue_yoy': _safe_float(row, 'or_yoy'),
                'profit_yoy': _safe_float(row, 'netprofit_yoy'),
                'roe_yoy': _safe_float(row, 'roe_yoy'),
                'assets_turn': _safe_float(row, 'assets_turn'),
                'data_source': 'tushare_fina_indicator'
            }
    except Exception:
        pass

    _set_cache(cache_key, result)
    return result


def _safe_float(row, col: str) -> Optional[float]:
    try:
        val = row.get(col)
        return round(float(val), 4) if val is not None and val == val else None
    except (ValueError, TypeError):
        return None


def get_financial_summary(stock_code: str) -> Dict:
    """
    财务综合评分 (0-100) — 融合核心财务指标
    """
    fin = get_financial_indicator(stock_code)
    if fin.get('data_source') == 'no_data':
        return {'score': 50, 'data_source': 'no_data', 'highlights': [], 'risks': ['财务数据缺失']}

    score = 50
    highlights = []
    risks = []

    roe = fin.get('roe', 0) or 0
    if roe >= 20:          score += 15; highlights.append(f'ROE优秀({roe:.1f}%)')
    elif roe >= 10:        score += 8
    elif roe >= 5:         score += 2
    elif roe > 0:          risks.append(f'ROE偏低({roe:.1f}%)')
    else:                  score -= 8; risks.append('ROE为负')

    gm = fin.get('gross_margin', 0) or 0
    if gm >= 40:           score += 12; highlights.append(f'高毛利率({gm:.1f}%)')
    elif gm >= 20:         score += 5
    elif 0 < gm < 10:      score -= 5; risks.append(f'毛利率偏低({gm:.1f}%)')

    debt = fin.get('debt_to_assets', 100) or 100
    if debt < 40:          score += 8; highlights.append('低负债率')
    elif debt > 80:        score -= 8; risks.append(f'高负债率({debt:.1f}%)')

    py_ = fin.get('profit_yoy', 0) or 0
    if py_ >= 30:          score += 8; highlights.append(f'利润高增({py_:+.0f}%)')
    elif py_ > 0:          score += 3
    elif py_ < -20:        score -= 10; risks.append(f'利润大幅下滑({py_:+.0f}%)')

    ocf = fin.get('ocf_ps', 0) or 0
    eps = fin.get('eps', 0) or 0
    if eps > 0 and ocf > eps: score += 6; highlights.append('现金流充裕')
    elif ocf < 0:           score -= 5; risks.append('经营现金流为负')

    score = max(0, min(100, score))
    return {
        'score': score, 'roe': roe, 'gross_margin': gm,
        'netprofit_margin': fin.get('netprofit_margin'),
        'debt_to_assets': debt, 'profit_yoy': py_,
        'eps': fin.get('eps'), 'bps': fin.get('bps'), 'ocf_ps': ocf,
        'highlights': highlights, 'risks': risks,
        'data_source': fin.get('data_source', 'unknown')
    }


# ==================== 资金流入TOP股票 ====================

def get_top_flow_stocks(n: int = 10) -> List[Dict]:
    """
    获取资金流入最多的股票(东方财富API)

    Args:
        n: top N

    Returns:
        [{'code': str, 'name': str, 'net_flow': 万, 'change_pct': %}, ...]
    """
    cache_key = 'top_flow_stocks'
    # 盘前兜底：非交易时段用更长 TTL（24h），避免 08:25 冷启动返回空
    from datetime import time
    now = datetime.now()
    is_trading = (
        now.weekday() < 5 and
        time(9, 30) <= now.time() <= time(15, 0)
    )
    cache_ttl = 300 if is_trading else 86400

    cached = _cached(cache_key, cache_ttl)
    if cached:
        return cached[:n]

    stocks = []
    try:
        params = {
            'pn': 1, 'pz': n, 'po': 1, 'np': 1,
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            'fltt': 2, 'invt': 2, 'fid': 'f62',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',
            'fields': 'f12,f14,f2,f3,f62,f184,f66,f69'
        }
        data = _em_api_get('https://push2.eastmoney.com/api/qt/clist/get', params)
        if data and data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                stocks.append({
                    'code': item.get('f12', ''),
                    'name': item.get('f14', ''),
                    'net_flow': round(float(item.get('f62', 0)) / 1e4, 2),
                    'change_pct': item.get('f3', 0),
                })
    except Exception:
            pass  # noqa: E722

    # 盘前兜底：API 返回空时，使用任何可用缓存（即使过期）
    if not stocks:
        expired = _cached(cache_key, 86400 * 7)
        if expired:
            stocks = expired[:n]

    _set_cache(cache_key, stocks)
    return stocks


# ==================== 侦察兵选股已迁移至 scout.py v3.0 ====================
# get_stock_candidates() 已合并到 scout.py，此处不再维护。


# ==================== 观察池(基于持仓+资金流向) ====================

def get_watchlist() -> List[Dict]:
    """
    获取真实观察池(基于当前持仓 + 今日资金流向)

    Returns:
        [{'code': str, 'name': str, 'signal': str, 'action': str}, ...]
    """
    holdings_path = Path(__file__).resolve().parent.parent / 'data' / 'holdings.json'
    watchlist = []

    # 1. 从持仓文件中读取
    if holdings_path.exists():
        try:
            data = json.loads(holdings_path.read_text(encoding='utf-8'))
            holdings = data.get('holdings', [])
            for h in holdings:
                code = h.get('code', '')
                name = h.get('name', '')
                # 尝试获取实时资金流向
                market = 'sh' if code.startswith(('6', '9')) else 'sz'
                flow = get_individual_money_flow(code, market)
                signal = '关注'
                action = '观察'
                if flow.get('main_pct', 0) > 5:
                    signal = '主力流入'
                    action = '持有'
                elif flow.get('main_pct', 0) < -5:
                    signal = '主力流出'
                    action = '减仓观望'

                watchlist.append({
                    'code': code,
                    'name': name if name else code,
                    'signal': signal,
                    'action': action,
                })
        except Exception:
            pass  # noqa: E722

    # 2. 如果持仓为空,取今日资金流入TOP
    if not watchlist:
        top = get_top_flow_stocks(6)
        for s in top:
            watchlist.append({
                'code': s['code'],
                'name': s['name'],
                'signal': '资金流入',
                'action': '关注',
            })

    return watchlist


# ==================== BaoStock 历史K线+MA（预计算） ====================

def get_historical_k_with_ma(codes: List[str], days: int = 30) -> Dict[str, List[Dict]]:
    """
    使用 BaoStock 批量获取历史日K线（含自算 MA5/MA10/MA20 + peTTM/pbMRQ）。

    一次 bs.login() → 逐只 query_history_k_data_plus → bs.logout()。
    无 subprocess 开销，单只 ~0.1s，50 只 ≈ 5s（vs 旧方案 subprocess 94s）。

    注意: BaoStock 日线 API 不支持 MA 指标字段，改用 close 自算 MA。
    rs.data 直接读 list（rs.next() 迭代器有阻塞 bug）。

    Args:
        codes: 股票代码列表，如 ['600519', '000001']
        days: 回溯天数（默认 30）

    Returns:
        {code: [{date, close, volume, amount, turn, peTTM, pbMRQ,
                 ma5, ma10, ma20}, ...], ...}
    """
    import baostock as bs
    from datetime import datetime, timedelta

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days + 15)).strftime('%Y-%m-%d')

    results: Dict[str, List[Dict]] = {}

    try:
        lg = bs.login()
        if lg.error_code != '0':
            _log.warning(f'BaoStock login failed: {lg.error_msg}')
            return results

        for code in codes:
            try:
                bs_code = f"sh.{code}" if code.startswith(('6', '5', '9')) else f"sz.{code}"
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount,turn,peTTM,pbMRQ",
                    start_date=start_date, end_date=end_date,
                    frequency="d", adjustflag="2"
                )
                if rs.error_code != '0' or not rs.data:
                    continue

                bars = []
                for row in rs.data:
                    # fields 顺序: date,open,high,low,close,volume,amount,turn,peTTM,pbMRQ
                    close_v = float(row[4]) if row[4] and row[4] != '' else 0.0
                    volume_v = float(row[5]) if row[5] and row[5] != '' else 0.0
                    amount_v = float(row[6]) if row[6] and row[6] != '' else 0.0
                    turn_v = float(row[7]) if len(row) > 7 and row[7] and row[7] != '' else None
                    pe_v = float(row[8]) if len(row) > 8 and row[8] and row[8] != '' else None
                    pb_v = float(row[9]) if len(row) > 9 and row[9] and row[9] != '' else None
                    bars.append({
                        'date': row[0],
                        'close': close_v,
                        'volume': volume_v,
                        'amount': amount_v,
                        'turn': turn_v,
                        'peTTM': pe_v,
                        'pbMRQ': pb_v,
                    })

                if not bars:
                    continue

                # 截断停牌日（close=0）和超出的回溯天数
                active_bars = [b for b in bars if b['close'] > 0]

                # 自算 MA5 / MA10 / MA20
                closes = [b['close'] for b in active_bars]
                for i, b in enumerate(active_bars):
                    if i >= 4:
                        b['ma5'] = round(sum(closes[i-4:i+1]) / 5, 2)
                    if i >= 9:
                        b['ma10'] = round(sum(closes[i-9:i+1]) / 10, 2)
                    if i >= 19:
                        b['ma20'] = round(sum(closes[i-19:i+1]) / 20, 2)

                results[code] = active_bars[-days:] if len(active_bars) >= days else active_bars
            except Exception:
                continue

        bs.logout()
    except Exception as e:
        _log.warning(f'BaoStock K-line fetch failed: {e}')

    return results


# ==================== Sina 批量实时行情（快路径） ====================

SINA_BATCH_URL = "http://hq.sinajs.cn/list="
_QUOTE_CACHE: Dict[str, Dict] = {}
_QUOTE_CACHE_TIME: float = 0.0
_QUOTE_CACHE_TTL = 120  # 行情缓存 2 分钟


def _code_to_sina(code: str) -> str:
    """将股票代码转换为 Sina 格式"""
    code = str(code).zfill(6)
    if code.startswith(('6', '5', '9')):
        return f"sh{code}"
    elif code.startswith(('0', '3', '2')):
        return f"sz{code}"
    return f"sh{code}"


def _sina_batch_fetch(codes: List[str], timeout: int = 5) -> Dict[str, Dict]:
    """
    Sina 批量实时行情（快路径）。
    单次 HTTP 请求支持 ~800 只股票，无 subprocess 开销。
    """
    if not codes:
        return {}

    sina_codes = [_code_to_sina(c) for c in codes]
    url = SINA_BATCH_URL + ",".join(sina_codes)

    try:
        import urllib.request
        req = urllib.request.Request(url, headers={
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0',
        })
        resp = urllib.request.urlopen(req, timeout=timeout)
        data = resp.read().decode('gbk', errors='ignore')
    except Exception:
        return {}

    results = {}
    code_map = {_code_to_sina(c): c for c in codes}

    for line in data.strip().split('\n'):
        if '=' not in line:
            continue
        try:
            sina_code, rest = line.split('=', 1)
            sina_code = sina_code.strip().split('_')[-1]
            original_code = code_map.get(sina_code)
            if not original_code:
                continue

            quote = rest.strip('";\n ').split(',')
            if len(quote) < 32:
                continue

            name = quote[0].strip()
            open_p = float(quote[1]) if quote[1] else 0
            prev_close = float(quote[2]) if quote[2] else 0
            close = float(quote[3]) if quote[3] else 0
            high = float(quote[4]) if quote[4] else 0
            low = float(quote[5]) if quote[5] else 0
            volume = float(quote[8]) if quote[8] else 0
            amount = float(quote[9]) if quote[9] else 0

            change_pct = ((close - prev_close) / prev_close * 100) if prev_close > 0 else 0
            if close <= 0:
                continue

            results[original_code] = {
                'close': round(close, 2),
                'change_pct': round(change_pct, 2),
                'open': round(open_p, 2),
                'high': round(high, 2),
                'low': round(low, 2),
                'volume': volume,
                'amount': amount,
                'name': name,
                'data_source': 'sina:batch',
                'trade_date': datetime.now().strftime('%Y%m%d'),
            }
        except (ValueError, IndexError):
            continue

    return results


# ==================== Hermes data fetch 桥接 ====================

def get_stock_realtime(stock_codes: list) -> Dict[str, Dict]:
    """
    获取个股实时/最新日线数据。

    快路径: Sina 批量 HTTP（单次请求，秒级返回）
    慢路径: Hermes data fetch CLI（逐只 subprocess，用作 fallback）

    内置 2 分钟内存缓存。

    Args:
        stock_codes: 股票代码列表，如 ['300131', '600481']

    Returns:
        {code: {close, change_pct, open, high, low, volume, amount, name, data_source}, ...}
    """
    global _QUOTE_CACHE, _QUOTE_CACHE_TIME

    now = time.time()
    # 检查缓存
    if _QUOTE_CACHE and (now - _QUOTE_CACHE_TIME) < _QUOTE_CACHE_TTL:
        missing = [c for c in stock_codes if c not in _QUOTE_CACHE]
        if not missing:
            return {c: _QUOTE_CACHE[c] for c in stock_codes if c in _QUOTE_CACHE}
    else:
        missing = list(stock_codes)
        _QUOTE_CACHE.clear()

    # ── 快路径：Sina 批量 ──
    sina_results = _sina_batch_fetch(missing)
    _QUOTE_CACHE.update(sina_results)

    # ── 慢路径：data fetch CLI 补漏 ──
    still_missing = [c for c in missing if c not in sina_results]
    if still_missing:
        import subprocess
        for code in still_missing:
            try:
                proc = subprocess.run(
                    ['data', 'fetch', 'stock', '--symbol', code, '--category', 'quote'],
                    capture_output=True, text=True, timeout=15,
                    env={**os.environ, 'HERMES_PROFILE': 'xiaohong'}
                )
                if proc.returncode == 0:
                    data_raw = json.loads(proc.stdout)
                    for p in data_raw.get('providers_attempted', []):
                        records = p.get('data', [])
                        if isinstance(records, list) and len(records) > 0:
                            latest = records[0]
                            _QUOTE_CACHE[code] = {
                                'close': float(latest.get('close', 0)),
                                'change_pct': float(latest.get('pct_chg', 0)),
                                'open': float(latest.get('open', 0)),
                                'high': float(latest.get('high', 0)),
                                'low': float(latest.get('low', 0)),
                                'volume': float(latest.get('vol', 0)),
                                'amount': float(latest.get('amount', 0)),
                                'name': str(latest.get('name', '')),
                                'data_source': f"hermes:{p['provider']}",
                                'trade_date': str(latest.get('trade_date', '')),
                            }
                            break
            except Exception:
                pass

    _QUOTE_CACHE_TIME = now
    return {c: _QUOTE_CACHE[c] for c in stock_codes if c in _QUOTE_CACHE}


# ==================== 测试入口 ====================

if __name__ == "__main__":
    print("="*60)
    print("🧪 统一数据管道测试")
    print("="*60)

    print("\n1. 全球指数:")
    idx = get_index_data()
    for region in ['asia', 'europe', 'us']:
        for name, (price, change) in idx.get(region, {}).items():
            print(f"   {name}: {price} ({change:+.2f}%)")
    print(f"   数据源: {idx.get('data_source', 'N/A')}")

    print("\n2. 北向资金:")
    nf = get_north_flow()
    print(f"   {nf.get('status', 'N/A')}")
    print(f"   {nf.get('detail', '')}")

    print("\n3. 市场资金流向:")
    mf = get_market_money_flow()
    print(f"   主力净流入: {mf.get('main_net', 'N/A')}亿")
    print(f"   上证: {mf.get('sh_index', 'N/A')} ({mf.get('sh_change', 'N/A'):+.2f}%)")

    print("\n4. 资金流入TOP5:")
    tops = get_top_flow_stocks(5)
    for s in tops:
        print(f"   {s.get('name', '?')}({s.get('code', '?')}): {s.get('net_flow', 0):.0f}万")

    print("\n5. 选股候选（已迁移至 scout.py v3.0）:")
    print("   请运行: python3 scout.py")

    print("\n✅ 测试完成")
