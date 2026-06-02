#!/usr/bin/env python3
"""
mega_collector.py — 统一采集器 v1.0
9个子采集模块，覆盖14类数据源，输出标准JSON到知识库

用法:
  python3 mega_collector.py              # 全量采集
  python3 mega_collector.py --quiet      # 静默模式 (cron用)
  python3 mega_collector.py --date 20260601  # 指定日期
"""

import json, os, sys, hashlib, logging
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('mega_collector')

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# 知识库根目录
KB_ROOT = Path(os.environ.get('XIAOHONG_KB_ROOT', str(SCRIPT_DIR.parent / 'data' / 'kb')))
os.makedirs(KB_ROOT, exist_ok=True)


class MegaCollector:
    """统一采集器 —— 每个子模块独立容错，互不影响"""

    def __init__(self, date_str: str = None):
        self.date_str = date_str or datetime.now().strftime('%Y%m%d')
        self.date_display = f"{self.date_str[:4]}-{self.date_str[4:6]}-{self.date_str[6:]}"
        self.output = {
            'timestamp': datetime.now().isoformat(),
            'date': self.date_str,
            'modules': {}
        }

    # ──────────────────────────────────────────────
    # 主入口
    # ──────────────────────────────────────────────

    def collect_all(self) -> dict:
        """全量采集，每模块独立 try/except"""
        modules = [
            ('hot_events',           self._collect_hot_events),
            ('policy_macro',         self._collect_policy_macro),
            ('industry_news',        self._collect_industry_news),
            ('announcements',        self._collect_announcements),
            ('broker_views',         self._collect_broker_views),
            ('dragon_tiger',         self._collect_dragon_tiger),
            ('st_risk',              self._collect_st_risk),
            ('north_flow',           self._collect_north_flow),
            ('external_futures',     self._collect_external_futures),
        ]

        for name, func in modules:
            try:
                data = func()
                count = len(data) if isinstance(data, list) else (1 if data else 0)
                self.output['modules'][name] = {'status': 'ok', 'count': count, 'data': data}
            except Exception as e:
                self.output['modules'][name] = {'status': 'error', 'error': str(e)[:200]}
                log.warning(f"  ❌ {name}: {e}")

        self._save()
        return self.output

    # ──────────────────────────────────────────────
    # 1. 热点事件 TOP20 (东方财富热搜 + 市场新闻)
    # ──────────────────────────────────────────────

    def _collect_hot_events(self) -> List[dict]:
        events = []

        # 1a. 东方财富热搜榜
        try:
            import akshare as ak
            df = ak.stock_hot_rank_em()
            if df is not None and not df.empty:
                for _, row in df.head(25).iterrows():
                    events.append({
                        'code': str(row.get('代码', '')),
                        'name': str(row.get('名称', '')),
                        'hot_rank': int(row.get('排名', row.get('rank', 999))),
                        'hot_score': self._safe_float(row.get('热度', row.get('score', 0))),
                        'change_pct': self._safe_float(row.get('涨跌幅', row.get('change', 0))),
                        'source': 'eastmoney_hot_rank',
                        'event_type': 'hot_rank',
                        'event_label': '🔥 热搜'
                    })
        except Exception as e:
            log.debug(f"Hot rank: {e}")

        # 1b. 东方财富市场新闻
        try:
            import akshare as ak
            df = ak.stock_news_em()
            if df is not None and not df.empty:
                for _, row in df.head(40).iterrows():
                    title = str(row.get('标题', row.get('title', '')))
                    if title and len(title) > 6:
                        events.append({
                            'title': title,
                            'source': 'eastmoney_news',
                            'event_type': 'market_news',
                            'event_label': '📰 市场新闻'
                        })
        except Exception as e:
            log.debug(f"Market news: {e}")

        return events

    # ──────────────────────────────────────────────
    # 2. 宏观政策 / 央行操作
    # ──────────────────────────────────────────────

    def _collect_policy_macro(self) -> List[dict]:
        events = []

        # 2a. 经济数据日历
        try:
            import akshare as ak
            df = ak.news_economic_baidu(date=self.date_str)
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    imp = str(row.get('重要性', '2'))
                    if imp in ('1', '2'):
                        events.append({
                            'title': str(row.get('事件', '')),
                            'country': str(row.get('地区', '')),
                            'actual': str(row.get('公布', '')),
                            'expected': str(row.get('预期', '')),
                            'importance': '高' if imp == '1' else '中',
                            'event_type': 'macro',
                            'event_label': '📋 宏观数据'
                        })
        except Exception as e:
            log.debug(f"Economic calendar: {e}")

        # 2b. 中国宏观政策新闻 (东方财富)
        try:
            import akshare as ak
            df = ak.stock_news_em()
            if df is not None and not df.empty:
                policy_kw = ['央行', 'MLF', 'LPR', '降准', '降息', '逆回购', '财政部',
                             '发改委', '国务院', '国常会', '证监会', '银保监', '金融委']
                for _, row in df.iterrows():
                    title = str(row.get('标题', row.get('title', '')))
                    if any(kw in title for kw in policy_kw):
                        events.append({
                            'title': title,
                            'source': 'eastmoney_news',
                            'event_type': 'policy',
                            'event_label': '🏛️ 政策动向'
                        })
        except Exception as e:
            log.debug(f"Policy news: {e}")

        return events

    # ──────────────────────────────────────────────
    # 3. 行业重大新闻
    # ──────────────────────────────────────────────

    def _collect_industry_news(self) -> List[dict]:
        events = []
        try:
            from resource_pool import SECTOR_KEYWORD_MAP, build_resource_pool
            pool = build_resource_pool()
            sector_analysis = pool.get('sector_analysis', [])

            for sa in sector_analysis:
                if sa.get('events_count', 0) > 0:
                    events.append({
                        'sector': sa.get('sector', ''),
                        'events_count': sa.get('events_count', 0),
                        'event_types': sa.get('event_types', []),
                        'details': sa.get('event_details', [])[:5],
                        'source': 'resource_pool',
                        'event_type': 'sector_news',
                        'event_label': f"📊 {sa.get('sector', '')}"
                    })
        except Exception as e:
            log.debug(f"Industry news: {e}")
        return events

    # ──────────────────────────────────────────────
    # 4. 公司公告 (持仓股优先)
    # ──────────────────────────────────────────────

    def _collect_announcements(self) -> List[dict]:
        """公告采集：先拉全量，持仓股排最前"""
        events = []

        # 读取持仓
        holdings_codes = set()
        try:
            hp = SCRIPT_DIR / 'holdings.json'
            if hp.exists():
                with open(hp) as f:
                    h = json.load(f)
                    for pos in h.get('positions', []):
                        holdings_codes.add(str(pos.get('code', '')))
        except Exception:
            pass

        try:
            from resource_pool import fetch_corporate_announcements
            raw = fetch_corporate_announcements(self.date_str)

            # 分成持仓 / 非持仓，持仓优先
            holdings_events = []
            other_events = []
            for e in raw:
                if str(e.get('code', '')) in holdings_codes:
                    e['is_holding'] = True
                    e['event_label'] = '⭐ ' + str(e.get('event_label', '公告'))
                    holdings_events.append(e)
                else:
                    other_events.append(e)

            events = holdings_events + other_events
        except Exception as e:
            log.debug(f"Announcements: {e}")

        return events

    # ──────────────────────────────────────────────
    # 5. 券商晨会观点精选
    # ──────────────────────────────────────────────

    def _collect_broker_views(self) -> List[dict]:
        events = []
        try:
            from resource_pool import fetch_research_reports, get_top_flow_stocks

            hot_codes = []
            try:
                top = get_top_flow_stocks(20)
                hot_codes = [s.get('code', '') for s in top]
            except Exception:
                pass

            if hot_codes:
                reports = fetch_research_reports(hot_codes[:20])
                events = [r for r in reports if r.get('rating') == '买入'][:15]
        except Exception as e:
            log.debug(f"Broker views: {e}")
        return events

    # ──────────────────────────────────────────────
    # 6. 龙虎榜复盘 (前日)
    # ──────────────────────────────────────────────

    def _collect_dragon_tiger(self) -> List[dict]:
        events = []
        try:
            import akshare as ak
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            df = ak.stock_lhb_detail_em(start_date=yesterday, end_date=yesterday)

            if df is not None and not df.empty:
                for _, row in df.head(60).iterrows():
                    events.append({
                        'code': str(row.get('代码', '')),
                        'name': str(row.get('名称', '')),
                        'close': self._safe_float(row.get('收盘价', 0)),
                        'change_pct': self._safe_float(row.get('涨跌幅', 0)),
                        'net_amount': self._safe_float(row.get('净买额', 0)),
                        'buy_amount': self._safe_float(row.get('买入额', 0)),
                        'sell_amount': self._safe_float(row.get('卖出额', 0)),
                        'reason': str(row.get('上榜原因', '')),
                        'event_type': 'dragon_tiger',
                        'event_label': '🐉 龙虎榜'
                    })
        except Exception as e:
            log.debug(f"Dragon tiger: {e}")
        return events

    # ──────────────────────────────────────────────
    # 7. ST / 退市风险公告
    # ──────────────────────────────────────────────

    def _collect_st_risk(self) -> List[dict]:
        events = []
        try:
            from resource_pool import fetch_corporate_announcements
            raw = fetch_corporate_announcements(self.date_str)
            st_kw = ['ST', '*ST', '退市', '终止上市', '风险警示', '暂停上市']
            for e in raw:
                title = str(e.get('title', ''))
                if any(kw in title for kw in st_kw):
                    e['event_type'] = 'st_risk'
                    e['event_label'] = '⚠️ 风险警示'
                    events.append(e)
        except Exception as e:
            log.debug(f"ST risk: {e}")
        return events

    # ──────────────────────────────────────────────
    # 8. 北向资金详情
    # ──────────────────────────────────────────────

    def _collect_north_flow(self) -> Dict:
        try:
            from data_pipeline import get_north_flow
            flow = get_north_flow()

            # 补充北向成交活跃股
            active_stocks = []
            try:
                import akshare as ak
                df = ak.stock_hsgt_top10_em(symbol='北向')
                if df is not None and not df.empty:
                    for _, row in df.head(15).iterrows():
                        active_stocks.append({
                            'code': str(row.get('代码', '')),
                            'name': str(row.get('名称', '')),
                            'net_flow': self._safe_float(row.get('净买额', 0)),
                        })
            except Exception:
                pass

            return {
                'summary': flow,
                'active_stocks': active_stocks
            }
        except Exception as e:
            return {'error': str(e)}

    # ──────────────────────────────────────────────
    # 9. 隔夜外盘 + 期货
    # ──────────────────────────────────────────────

    def _collect_external_futures(self) -> Dict:
        result = {
            'us': {},
            'europe': {},
            'asia_pacific': {},
            'china_concept': {},
            'futures': {},
            'alerts': []
        }

        # 9a. 美股 + 欧股 + 亚太
        try:
            from data_pipeline import get_index_data
            idx = get_index_data()

            us = idx.get('us', {})
            result['us'] = {
                'dow': list(us.get('dow', (0, 0))),
                'sp500': list(us.get('sp500', (0, 0))),
                'nasdaq': list(us.get('nasdaq', (0, 0))),
            }

            eu = idx.get('europe', {})
            result['europe'] = {
                'ftse': list(eu.get('ftse', (0, 0))),
                'dax': list(eu.get('dax', (0, 0))),
            }

            asia = idx.get('asia', {})
            result['asia_pacific'] = {
                'nikkei': list(asia.get('nikkei', (0, 0))),
                'hangseng': list(asia.get('hangseng', (0, 0))),
                'shanghai': list(asia.get('shanghai', (0, 0))),
            }

            # 传导规则: 纳指涨跌 > ±2% → 强外盘影响日
            nasdaq_change = result['us']['nasdaq'][1] if len(result['us'].get('nasdaq', [])) > 1 else 0
            if abs(nasdaq_change) > 2:
                direction = 'bullish' if nasdaq_change > 0 else 'bearish'
                result['alerts'].append({
                    'type': 'external_impact',
                    'level': '🔴 强外盘影响日',
                    'detail': f"纳指{'涨' if nasdaq_change > 0 else '跌'}{abs(nasdaq_change):.1f}%，科技板块预判联动",
                    'direction': direction
                })
        except Exception as e:
            log.debug(f"External indices: {e}")

        # 9b. 期货: 原油 + 黄金
        try:
            import akshare as ak

            # 原油
            try:
                crude = ak.futures_foreign_hist(symbol='原油')
                if crude is not None and not crude.empty:
                    latest = crude.iloc[-1]
                    change = self._safe_float(latest.get('涨跌幅', 0) or 0)
                    result['futures']['crude_oil'] = {
                        'price': self._safe_float(latest.get('收盘价', 0)),
                        'change_pct': round(change, 2)
                    }
                    if abs(change) > 3:
                        result['alerts'].append({
                            'type': 'futures_crude',
                            'level': '🟡 能源化工影响',
                            'detail': f"原油{'涨' if change > 0 else '跌'}{abs(change):.1f}%，标记能源/化工板块",
                        })
            except Exception:
                pass

            # 黄金
            try:
                gold = ak.futures_foreign_hist(symbol='黄金')
                if gold is not None and not gold.empty:
                    latest = gold.iloc[-1]
                    change = self._safe_float(latest.get('涨跌幅', 0) or 0)
                    result['futures']['gold'] = {
                        'price': self._safe_float(latest.get('收盘价', 0)),
                        'change_pct': round(change, 2)
                    }
                    if abs(change) > 2:
                        result['alerts'].append({
                            'type': 'futures_gold',
                            'level': '🟡 贵金属影响',
                            'detail': f"黄金{'涨' if change > 0 else '跌'}{abs(change):.1f}%，标记贵金属板块",
                        })
            except Exception:
                pass
        except Exception as e:
            log.debug(f"Futures: {e}")

        return result

    # ──────────────────────────────────────────────
    # 存储
    # ──────────────────────────────────────────────

    def _save(self):
        KB_ROOT.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime('%Y%m%d_%H%M')
        filepath = KB_ROOT / f"mega_{ts}.json"
        with open(filepath, 'w') as f:
            json.dump(self.output, f, ensure_ascii=False, indent=2, default=str)

        latest = KB_ROOT / "mega_latest.json"
        with open(latest, 'w') as f:
            json.dump(self.output, f, ensure_ascii=False, indent=2, default=str)

    # ──────────────────────────────────────────────
    # 工具
    # ──────────────────────────────────────────────

    @staticmethod
    def _safe_float(val, default=0.0) -> float:
        try:
            return float(val)
        except (TypeError, ValueError):
            return default


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description='Mega Collector — 统一数据采集器')
    p.add_argument('--date', help='YYYYMMDD')
    p.add_argument('--quiet', action='store_true', help='静默模式')
    p.add_argument('--module', help='只跑单个模块 (debug)')
    args = p.parse_args()

    mc = MegaCollector(date_str=args.date)

    if args.module:
        fn = getattr(mc, f'_collect_{args.module}', None)
        if fn is None:
            print(f"Unknown module: {args.module}")
            sys.exit(1)
        data = fn()
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return

    result = mc.collect_all()

    if not args.quiet:
        summary = {
            'status': 'ok',
            'date': result['date'],
            'modules': {k: v['status'] for k, v in result['modules'].items()},
            'alerts': result['modules'].get('external_futures', {}).get('data', {}).get('alerts', [])
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
