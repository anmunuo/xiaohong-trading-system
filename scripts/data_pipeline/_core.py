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


# ==================== Bronze 层写入钩子 ====================

BRONZE_ENABLED = os.environ.get('XIAOHONG_BRONZE', '1') == '1'

def _bronze_write(data, source: str, category: str, fields: list = None, notes: str = ""):
    """非阻塞 Bronze 写入。失败不抛异常，不影响主流程。"""
    if not BRONZE_ENABLED:
        return
    try:
        from bronze_ingest import BronzeWriter
        writer = BronzeWriter()
        writer.write(data, source=source, category=category,
                     fields=fields, notes=notes)
    except Exception:
        pass  # Bronze 写入失败不影响核心业务


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
    _bronze_write(result, 'akshare', 'market_index', fields=['asia','europe','us'])
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
            # 扩大回退窗口到30天，数据可能滞后一周以上
            cal = pro.trade_cal(exchange='SSE', start_date=(datetime.now() - timedelta(days=30)).strftime('%Y%m%d'), end_date=yesterday)
            trading_days = cal[cal['is_open'] == 1]['cal_date'].tolist()
            if trading_days:
                # 从最近到最远逐日尝试
                for td in reversed(trading_days[-10:]):
                    df = pro.moneyflow_hsgt(trade_date=td)
                    if not df.empty:
                        break

        if not df.empty:
            row = df.iloc[-1]
            # 🔧 v8.11 修复: ggt_ss/ggt_sz 是南向(港股通), 不能当北向!
            # 正确字段: north_money=北向合计(万元), hgt=沪股通, sgt=深股通
            north_money = float(row.get('north_money', 0))
            north_total = round(north_money / 1e4, 2)  # 万元→亿
            hgt_flow = float(row.get('hgt', 0)) / 1e4
            sgt_flow = float(row.get('sgt', 0)) / 1e4
            data_date = str(df.iloc[-1].get('trade_date', ''))

            tushare_data = {
                'net_flow': north_total,
                'detail': f'沪股通:{hgt_flow:.1f}亿, 深股通:{sgt_flow:.1f}亿',
                'date': data_date,
                'data_type': 'T-1日终（非实时）',
                'data_source': 'tushare_pro'
            }
    except Exception:
        pass

    # ---- 3. 择优使用 ----
    # 策略变更 (v8.10): 2024年5月起交易所不再实时披露北向资金，
    # AKShare 日期虽新但 net_flow 恒为 0（实时通道已关闭）。
    # 因此：AKShare net_flow!=0 才可信，否则回退 tushare T-1 日终数据。
    use_akshare = False
    if akshare_data:
        if akshare_data['net_flow'] != 0:
            use_akshare = True  # AKShare 有实际数据 → 可信
        elif not tushare_data:
            use_akshare = True  # tushare 也失败，用 akshare（至少日期对）
        # else: AKShare=0 且 tushare 可用 → 用 tushare（优选日终数据）

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
            'data_source': akshare_data['data_source'],
            '_quality': 'realtime',
        }
    elif tushare_data:
        emoji = '🟢' if tushare_data['net_flow'] >= 0 else '🔴'
        status = f'{emoji} {abs(tushare_data["net_flow"]):.1f}亿元'
        status += ' 净流入' if tushare_data['net_flow'] >= 0 else ' 净流出'
        # 🆕 计算数据滞后天数
        data_date = tushare_data['date']
        days_lag = (datetime.now() - datetime.strptime(data_date, '%Y%m%d')).days if data_date else '?'
        result = {
            'net_flow': tushare_data['net_flow'],
            'status': status,
            'detail': tushare_data['detail'],
            'date': tushare_data['date'],
            'data_type': tushare_data['data_type'] + f' (滞后{days_lag}天)',
            'data_source': tushare_data['data_source'],
            '_quality': f'T-{days_lag}',
        }

    # 🆕 v8.12 数据真实性印章
    try:
        from data_quality import verify as qv
        qs = qv(result, "north_flow", "get_north_flow")
        result["_quality_stamp"] = qs.to_dict()
        if qs.failed_gates:
            result["_quality_alert"] = [fg["detail"] for fg in qs.failed_gates]
            result["_quality_repair"] = qs.repair_hint
    except ImportError:
        pass

    _set_cache(cache_key, result)
    _bronze_write(result, 'tushare', 'fund_flow', fields=['net_flow','status'])
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
    _bronze_write(result, 'tushare', 'fund_flow', fields=['main_net','retail_net','stock_count'])
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
    _bronze_write(bars, 'sina', 'intraday',
                  fields=['time','open','high','low','close','volume','amount'],
                  notes=f'{stock_code} scale={scale}')
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
        y = datetime.now().year
        candidates = []
        for yr in [y, y-1]:
            for q in ['1231', '0930', '0630', '0331']:
                candidates.append(f'{yr}{q}')
        candidates.sort(reverse=True)
        period = candidates[0]
    else:
        candidates = [period]  # 指定 period 时只尝试这一个

    cache_key = f'fin_ind_{stock_code}_{period}'
    cached = _cached(cache_key, 86400)
    if cached:
        return cached

    result = {'data_source': 'no_data'}
    try:
        pro = _get_ts_pro()
        tscode = stock_code if '.' in stock_code else f'{stock_code}.SZ' if stock_code.startswith(('0','3')) else f'{stock_code}.SH'

        # 尝试一系列 period，从最新到最旧
        tried = []
        df = None
        for p in candidates:
            try:
                df = pro.fina_indicator(ts_code=tscode, period=p)
                if df is not None and not df.empty:
                    period = p  # 记录实际成功的 period
                    break
                tried.append(p)
            except Exception:
                tried.append(p)
                continue

        if df is not None and not df.empty:
            row = df.iloc[0]
            result = {
                'ts_code': tscode,
                'period': period,
                'eps': _safe_float(row, 'eps'),
                'bps': _safe_float(row, 'bps'),
                'roe': _safe_float(row, 'roe'),
                'roe_yearly': _safe_float(row, 'roe_yearly'),  # 🆕 v8.12: 滚动12月ROE
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

    # 🔧 v8.12: 优先 roe_yearly (滚动12个月，更反映当前经营)，而非单季roe
    roe = fin.get('roe_yearly', fin.get('roe', 0)) or 0
    if roe >= 20:          score += 15; highlights.append(f'ROE优秀({roe:.1f}%)')
    elif roe >= 10:        score += 8
    elif roe >= 5:         score += 2
    elif roe > 0:          risks.append(f'ROE偏低({roe:.1f}%)')
    else:                  score -= 8; risks.append('ROE为负')

    # 🔧 v8.12: gross_margin=None 时不参与评分 (不是0!)
    gm = fin.get('gross_margin')
    if gm is not None:
        if gm >= 40:           score += 12; highlights.append(f'高毛利率({gm:.1f}%)')
        elif gm >= 20:         score += 5
        elif gm > 0:           score -= 5; risks.append(f'毛利率偏低({gm:.1f}%)')
    else:
        gm = None  # 明确标记无数据

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
        'score': score, 'period': fin.get('period'),  # 🆕: 标注数据所属期
        'roe': roe, 'gross_margin': gm,
        'netprofit_margin': fin.get('netprofit_margin'),
        'debt_to_assets': debt, 'profit_yoy': py_,
        'eps': fin.get('eps'), 'bps': fin.get('bps'), 'ocf_ps': ocf,
        'highlights': highlights, 'risks': risks,
        'data_source': fin.get('data_source', 'unknown')
    }


# ==================== 资金流入TOP股票 ====================

def get_top_flow_stocks(n: int = 10, no_cache: bool = False) -> List[Dict]:
    """
    获取资金流入最多的股票(东方财富API)

    v4.1: f62 字段健康检测 → 盘中使用涨跌幅+量比排序 fallback
          新增 _quality 标记数据源可靠性

    Args:
        n: top N
        no_cache: 跳过缓存（健康检查用）

    Returns:
        [{'code': str, 'name': str, 'net_flow': 万, 'change_pct': %,
          '_quality': 'ok'|'fallback'}, ...]
    """
    cache_key = 'top_flow_stocks'
    if not no_cache:
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
            'pn': 1, 'pz': max(n * 2, 20), 'po': 1, 'np': 1,
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            'fltt': 2, 'invt': 2, 'fid': 'f62',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',
            'fields': 'f12,f14,f2,f3,f62,f66,f69,f184,f8,f10,f20'
        }
        data = _em_api_get('https://push2.eastmoney.com/api/qt/clist/get', params)
        if data and data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                stocks.append({
                    'code': item.get('f12', ''),
                    'name': item.get('f14', ''),
                    'net_flow': round(float(item.get('f62', 0)) / 1e4, 2),
                    'change_pct': item.get('f3', 0),
                    'turnover': item.get('f8', 0),       # 换手率
                    'volume_ratio': item.get('f10', 0),  # 量比
                    'total_mv': float(item.get('f20', 0) or 0) / 1e8,  # 总市值(元→亿)
                    '_quality': 'ok',
                })
    except Exception:
        pass

    # ── f62 健康检测：如果 Top N 的 net_flow 全为 0 → 数据源异常 ──
    if stocks:
        non_zero_flows = [s for s in stocks if s['net_flow'] != 0]
        if not non_zero_flows:
            # f62 失效 → 改用涨跌幅 + 量比作为动量代理排序
            _log.warning('东方财富 f62 字段全为 0，数据源可能异常，切换动量 fallback')
            for s in stocks:
                s['_quality'] = 'fallback'
                # 合成动量分 = 涨跌幅% × 0.7 + 换手率% × 0.2 + 量比 × 0.1
                s['_momentum_score'] = (
                    abs(float(s.get('change_pct', 0))) * 0.7 +
                    float(s.get('turnover', 0) or 0) * 0.2 +
                    float(s.get('volume_ratio', 0) or 0) * 0.1
                )
            stocks.sort(key=lambda x: x['_momentum_score'], reverse=True)
            # 动量模式下 net_flow 置为 None（不可用）
            for s in stocks:
                if s['_quality'] == 'fallback':
                    s['net_flow'] = None

    # 盘前兜底：API 返回空时，使用任何可用缓存
    if not stocks:
        expired = _cached(cache_key, 86400 * 7)
        if expired:
            stocks = expired[:n]

    _set_cache(cache_key, stocks)
    _bronze_write(stocks[:n], 'eastmoney', 'fund_flow',
                  fields=['code','name','net_flow','change_pct','turnover','volume_ratio'])
    return stocks[:n]


# ==================== 数据源健康检查 ====================

def check_data_health() -> Dict:
    """
    检查各数据源 API 字段可用性，探测 f62/f66/f69/f184 哪个有值。

    降级策略自动选择可用的资金流字段。

    Returns:
        {'status': 'ok'|'degraded'|'down',
         'flow_field': 'f62'|'f184'|'momentum'|'none',
         'detail': {...}}
    """
    import requests
    result = {
        'status': 'ok',
        'flow_field': 'f62',
        'detail': {},
        'checked_at': datetime.now().isoformat(),
    }

    # ── 检测 1: 东方财富 push2 list API f62 ──
    try:
        params = {
            'pn': 1, 'pz': 10, 'po': 1, 'np': 1,
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            'fltt': 2, 'invt': 2, 'fid': 'f62',
            'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',
            'fields': 'f12,f62,f184,f66,f69'
        }
        data = _em_api_get('https://push2.eastmoney.com/api/qt/clist/get', params)
        if data and data.get('data') and data['data'].get('diff'):
            items = data['data']['diff']
            total = len(items)
            f62_ok = sum(1 for i in items if float(i.get('f62', 0) or 0) != 0)
            f184_ok = sum(1 for i in items if float(i.get('f184', 0) or 0) != 0)
            f66_ok = sum(1 for i in items if float(i.get('f66', 0) or 0) != 0)
            result['detail']['list_api'] = {
                'total': total,
                'f62_valid': f62_ok, 'f184_valid': f184_ok, 'f66_valid': f66_ok,
            }
            if f62_ok < total * 0.3:
                result['status'] = 'degraded'
                if f184_ok >= total * 0.3:
                    result['flow_field'] = 'f184'
                elif f66_ok >= total * 0.3:
                    result['flow_field'] = 'f66'
                else:
                    result['flow_field'] = 'momentum'
                    result['status'] = 'degraded'
    except Exception as e:
        result['detail']['list_api'] = {'error': str(e)}
        result['status'] = 'degraded'
        result['flow_field'] = 'momentum'

    # ── 检测 2: 新浪行情 API ──
    try:
        r = requests.get('http://hq.sinajs.cn/list=sh000001', timeout=8,
                         headers={'Referer': 'https://finance.sina.com.cn'})
        result['detail']['sina_api'] = 'ok' if r.status_code == 200 else f'http_{r.status_code}'
    except Exception as e:
        result['detail']['sina_api'] = f'error: {e}'

    return result


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

def _baostock_batch_worker(args):
    """进程隔离 worker：独立 bs.login → 批量查询 → bs.logout（给 ProcessPoolExecutor 用）"""
    batch_codes, start_d, end_d, day_limit = args
    import baostock as bs
    batch_results = {}
    try:
        lg = bs.login()
        if lg.error_code != '0':
            return batch_results

        for code in batch_codes:
            try:
                bs_code = f"sh.{code}" if code.startswith(('6', '5', '9')) else f"sz.{code}"
                rs = bs.query_history_k_data_plus(
                    bs_code,
                    "date,open,high,low,close,volume,amount,turn,peTTM,pbMRQ",
                    start_date=start_d, end_date=end_d,
                    frequency="d", adjustflag="2"
                )
                if rs.error_code != '0' or not rs.data:
                    continue

                bars = []
                for row in rs.data:
                    close_v = float(row[4]) if row[4] and row[4] != '' else 0.0
                    volume_v = float(row[5]) if row[5] and row[5] != '' else 0.0
                    amount_v = float(row[6]) if row[6] and row[6] != '' else 0.0
                    turn_v = float(row[7]) if len(row) > 7 and row[7] and row[7] != '' else None
                    pe_v = float(row[8]) if len(row) > 8 and row[8] and row[8] != '' else None
                    pb_v = float(row[9]) if len(row) > 9 and row[9] and row[9] != '' else None
                    bars.append({
                        'date': row[0], 'close': close_v, 'volume': volume_v,
                        'amount': amount_v, 'turn': turn_v,
                        'peTTM': pe_v, 'pbMRQ': pb_v,
                    })

                if not bars:
                    continue

                active_bars = [b for b in bars if b['close'] > 0]
                closes = [b['close'] for b in active_bars]
                for i, b in enumerate(active_bars):
                    if i >= 4:
                        b['ma5'] = round(sum(closes[i-4:i+1]) / 5, 2)
                    if i >= 9:
                        b['ma10'] = round(sum(closes[i-9:i+1]) / 10, 2)
                    if i >= 19:
                        b['ma20'] = round(sum(closes[i-19:i+1]) / 20, 2)

                batch_results[code] = active_bars[-day_limit:] if len(active_bars) >= day_limit else active_bars
            except Exception:
                continue

        bs.logout()
    except Exception:
        pass
    return batch_results


def get_historical_k_with_ma(codes: List[str], days: int = 30) -> Dict[str, List[Dict]]:
    """
    使用 BaoStock 批量获取历史日K线（含自算 MA5/MA10/MA20 + peTTM/pbMRQ）。

    v8.5: ProcessPoolExecutor 并行（baostock 非线程安全，需进程隔离）。
    每进程独立 bs.login() → 查一批代码 → bs.logout()。

    注意: BaoStock 日线 API 不支持 MA 指标字段，改用 close 自算 MA。
    rs.data 直接读 list（rs.next() 迭代器有阻塞 bug）。

    Args:
        codes: 股票代码列表，如 ['600519', '000001']
        days: 回溯天数（默认 30）

    Returns:
        {code: [{date, close, volume, amount, turn, peTTM, pbMRQ,
                 ma5, ma10, ma20}, ...], ...}
    """
    from datetime import datetime, timedelta
    from concurrent.futures import ProcessPoolExecutor, as_completed
    import multiprocessing

    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days + 15)).strftime('%Y-%m-%d')

    # 分批：每进程处理约 50 只，最多 8 个进程
    batch_size = max(50, len(codes) // max(1, multiprocessing.cpu_count()))
    batches = [codes[i:i+batch_size] for i in range(0, len(codes), batch_size)]
    # 打包 args 为 tuple（Picklable）
    tasks = [(b, start_date, end_date, days) for b in batches]

    results: Dict[str, List[Dict]] = {}

    try:
        with ProcessPoolExecutor(max_workers=min(8, len(batches))) as ex:
            futures = {ex.submit(_baostock_batch_worker, t): t for t in tasks}
            for fut in as_completed(futures):
                batch_results = fut.result()
                results.update(batch_results)
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

    # ── v8.7: 跳过 data fetch CLI 慢路径（每只启动 agent，不可行）──
    # Sina 覆盖 A 股主力，缺失的码由上层容错处理
    still_missing = [c for c in missing if c not in sina_results]
    if still_missing:
        _log.info(f'get_stock_realtime: {len(still_missing)} codes not covered by Sina, skipping slow path')

    _QUOTE_CACHE_TIME = now
    result = {c: _QUOTE_CACHE[c] for c in stock_codes if c in _QUOTE_CACHE}
    _bronze_write(result, 'sina', 'daily_kline',
                  fields=['code','close','change_pct','open','high','low','volume','name'],
                  notes=f'{len(result)} stocks')
    return result


# ==================== 因子面板批量计算 ====================

def get_factor_panel(codes: List[str], days: int = 65) -> Dict[str, Dict]:
    """
    批量计算多只股票的新增因子面板。

    与 get_historical_k_with_ma 返回的 K线数据结合使用，
    由 factor_evaluator.py / stock_recommender.py 调用。

    Args:
        codes: 股票代码列表
        days: 历史日线回溯天数（需足够长以计算60日动量等）

    Returns:
        {code: {factor_id: value, ...}, ...}
        缺失的因子键为 None
    """
    if not codes:
        return {}

    # 拉历史日线
    try:
        bs_data = get_historical_k_with_ma(codes, days=days)
    except Exception:
        return {}

    panel = {}
    for code, bars in bs_data.items():
        if not bars or len(bars) < 20:
            panel[code] = {}
            continue

        closes = [b['close'] for b in bars]
        highs  = [b['high'] for b in bars]
        lows   = [b['low'] for b in bars]
        volumes = [b.get('volume', 0) for b in bars]
        turns  = [b.get('turn', 0) for b in bars]

        factors = {}
        n = len(closes)

        # ── 动量 ──
        if n >= 6:
            factors['mom_5d'] = round((closes[-1] / closes[-6] - 1) * 100, 2) if closes[-6] > 0 else None
        if n >= 21:
            factors['mom_20d'] = round((closes[-1] / closes[-21] - 1) * 100, 2) if closes[-21] > 0 else None
        if n >= 61:
            factors['mom_60d'] = round((closes[-1] / closes[-61] - 1) * 100, 2) if closes[-61] > 0 else None

        # ── 波动 ──
        if n >= 15 and closes[-1] > 0:
            tr_list = []
            for i in range(max(1, n - 14), n):
                hl = highs[i] - lows[i]
                hc = abs(highs[i] - closes[i-1])
                lc = abs(lows[i] - closes[i-1])
                tr_list.append(max(hl, hc, lc))
            atr = sum(tr_list) / len(tr_list) if tr_list else 0
            factors['atr_14'] = round(atr / closes[-1] * 100, 2)

        if n >= 21:
            rets = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(n-20, n)]
            if rets:
                mu = sum(rets) / len(rets)
                var = sum((r - mu) ** 2 for r in rets) / len(rets)
                factors['vol_20d'] = round(var ** 0.5 * 100, 2)
                neg_rets = [r for r in rets if r < 0]
                if neg_rets:
                    neg_mu = sum(neg_rets) / len(neg_rets)
                    neg_var = sum((r - neg_mu) ** 2 for r in neg_rets) / len(neg_rets)
                    factors['downside_vol'] = round(neg_var ** 0.5 * 100, 2)

        # ── 筹码 ──
        if n >= 21 and turns and turns[-1] > 0:
            recent_turns = turns[-21:]
            mean_turn = sum(recent_turns) / len(recent_turns)
            std_turn = (sum((t - mean_turn) ** 2 for t in recent_turns) / len(recent_turns)) ** 0.5
            factors['turnover_zscore'] = round((turns[-1] - mean_turn) / std_turn, 2) if std_turn > 0 else 0.0

        if n >= 21 and any(v > 0 for v in volumes):
            avg_vol_5 = sum(volumes[-5:]) / 5 if volumes[-5:] else 0
            avg_vol_20 = sum(volumes[-20:]) / 20 if volumes[-20:] else 0
            factors['vol_ratio_trend'] = round(avg_vol_5 / avg_vol_20, 2) if avg_vol_20 > 0 else 1.0

        if n >= 6 and closes[-1] > 0:
            amps = [(highs[i] - lows[i]) / closes[i] * 100 for i in range(-5, 0)]
            factors['amplitude_5d'] = round(sum(amps) / len(amps), 2)

        # ── 资金/估值/质量（需外部注入，此处标 None 占位）──
        factors['main_net_buy'] = None
        factors['retail_net_buy'] = None
        factors['northbound_5d'] = None
        factors['pe_percentile'] = None
        factors['pb_percentile'] = None
        factors['roe_stability'] = None
        factors['cf_profit_ratio'] = None

        panel[code] = factors

    return panel


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
