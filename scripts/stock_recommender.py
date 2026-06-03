#!/usr/bin/env python3
"""
stock_recommender.py — 选股推荐引擎 v2.0 (V8.0 瞭望塔)

多因子综合打分 → 排除过滤 → 板块归类 → 每日推荐池 (每日重置)

用法:
  python3 stock_recommender.py              # 生成推荐池 (默认9只)
  python3 stock_recommender.py --top 6      # 指定输出数量
  python3 stock_recommender.py --json       # JSON输出

排除规则:
  1. ST / *ST
  2. 连板股 (≥2连板，保留首板)
  3. 市值 < 50亿 或 > 3000亿
"""

import json, os, sys, math, re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
KB_ROOT = Path(os.environ.get('XIAOHONG_KB_ROOT', str(SCRIPT_DIR.parent / 'data' / 'kb')))
POOL_PATH = SCRIPT_DIR / 'data' / 'daily_pool.json'


# ──────────────────────────────────────────────
# 板块关键词映射
# ──────────────────────────────────────────────

SECTOR_KEYWORDS = {
    '电力':        ['电力', '电网', '发电', '能源', '风电', '光伏', '太阳能', '核电', '水电', '火电', '绿电'],
    '通信光缆':    ['光纤', '光缆', '通信', '光通信', '亨通', '长飞', '中天'],
    '半导体':      ['半导体', '芯片', '晶圆', '封测', '光刻', '集成电路'],
    '新能源':      ['锂电', '电池', '储能', '氢能', '新能源车', '充电桩', '风电', '光伏'],
    '消费':        ['白酒', '食品', '饮料', '家电', '零售', '旅游', '免税', '医美'],
    '医药':        ['医药', '制药', '生物', '医疗器械', '疫苗', '中药', 'CXO'],
    'AI/科技':     ['AI', '人工智能', '大模型', '算力', '机器人', '自动驾驶', '软件'],
    '专用设备':    ['设备', '装备', '制造', '机械', '机床', '自动化'],
    '有色金属':    ['铜', '铝', '黄金', '稀土', '锂矿', '钴', '镍', '有色'],
    '化工':        ['化工', '化学', '农药', '化肥', '新材料', '合成'],
    '房地产':      ['地产', '房地产', '物业', '开发'],
    '金融':        ['银行', '证券', '保险', '信托'],
    '电力设备':    ['线缆', '电缆', '变压器', '开关', '配电', '特高压'],
    '军工':        ['军工', '航天', '航空', '导弹', '雷达', '卫星'],
    '汽车':        ['汽车', '整车', '零部件', '轮胎'],
    '环保':        ['环保', '水务', '固废', '碳'],
}


def _guess_sector(name: str, code: str = '', kb_modules: Dict = None) -> str:
    """根据股票名称/代码和知识库事件猜测所属板块"""
    if kb_modules is None:
        kb_modules = {}
    ann_data = kb_modules.get('announcements', {}).get('data', [])
    broker_data = kb_modules.get('broker_views', {}).get('data', [])

    # ── 优先级 1: tushare 官方行业分类 ──
    if code:
        try:
            from ammo_risk import classify_industry
            sector = classify_industry(code, name)
            if sector and sector != '综合':
                return sector
        except Exception:
            pass

    # ── 优先级 2: KB 公告/研报匹配 ──
    sector_hits = {}
    for entry in ann_data + broker_data:
        title = str(entry.get('title', ''))
        for sector, keywords in SECTOR_KEYWORDS.items():
            for kw in keywords:
                if kw in title or kw in str(entry.get('sector', '')):
                    sector_hits[sector] = sector_hits.get(sector, 0) + 1
                    break

    if sector_hits:
        return max(sector_hits, key=sector_hits.get)

    # ── 优先级 3: 名称关键词匹配 ──
    for sector, keywords in SECTOR_KEYWORDS.items():
        for kw in keywords:
            if kw in name:
                return sector

    return '综合'


# _gen_operation / _assess_risk 已迁移为 StockRecommender 的方法（v2.2 多维决策矩阵）
# 见 _calc_stop_loss 之后的 _gen_operation_v2 / _assess_risk_v2


class StockRecommender:
    """选股推荐引擎 v2.2 — 六类因子（五因子+新增因子）"""

    def __init__(self):
        self.date_str = datetime.now().strftime('%Y%m%d')
        self.recommendations = []
        self.excluded = {'st': [], 'lianban': [], 'suspended': [], 'large_cap': [], 'small_cap': [], 'no_data': []}
        self._quote_cache = {}
        self._indicators = {}      # 预计算技术指标
        self._insights_index = {}  # KB LLM 洞察索引
        self._new_factors = {}     # 🆕 新增因子面板 {code: {factor_id: value}}
        self._factor_weights = {}  # 🆕 IC 动态权重

    # ═══════════════════════════════════════════
    # 主流程
    # ═══════════════════════════════════════════

    def run(self, top_n: int = 9) -> List[Dict]:
        """生成每日推荐池"""
        kb = self._load_kb()
        self._load_insights()      # 🆕 加载 LLM 洞察
        self._load_factor_weights() # 🆕 加载 IC 动态权重

        # Step 1: 候选池
        candidates = self._get_candidates(kb)

        # ── 批量预取实时行情 + 技术指标 ──
        all_codes = [c['code'] for c in candidates]
        if all_codes:
            from data_pipeline import get_stock_realtime
            self._quote_cache = get_stock_realtime(all_codes)
            self._prefetch_indicators(all_codes)  # MA20/均量/PE
            self._prefetch_new_factors(all_codes) # 🆕 新因子面板
        else:
            self._quote_cache = {}
            self._indicators = {}
            self._new_factors = {}

        # Step 2: 排除过滤
        valid = self._apply_filters(candidates)

        # Step 3: 多因子打分
        scored = self._score_candidates(valid, kb)

        # Step 4: 排序取 Top N
        scored.sort(key=lambda x: x['total_score'], reverse=True)
        self.recommendations = scored[:top_n]

        # Step 5: 附加止损位
        for rec in self.recommendations:
            rec['stop_loss'] = self._calc_stop_loss(rec)

        # Step 6: 板块归类 + 操作策略 + 风险等级
        self._enrich_recommendations(kb)

        # Step 6.5: 🆕 研究员议会 — 多视角交叉验证推荐池
        self._parliament_consult()

        # Step 7: 持久化（保留盘中侦察兵新增的标的）
        self._save_pool()

        return self.recommendations

    def _parliament_consult(self):
        """研究员议会 — 对推荐池做多视角交叉验证（非阻塞）"""
        if not self.recommendations:
            return
        try:
            from researchers import Parliament
            parliament = Parliament()
            context = parliament.load_context()
            context["topic"] = f"推荐引擎选股验证 ({len(self.recommendations)}只)"
            context["pool_stocks"] = self.recommendations
            result = parliament.execute(topic=context["topic"])
            # 将议会结论注入推荐池元数据
            verdict = result.get("round3", {}).get("verdict", {})
            self._parliament_verdict = verdict
        except Exception:
            pass  # 议会失败不影响选股流程

    # ═══════════════════════════════════════════
    # 1. 加载知识库
    # ═══════════════════════════════════════════

    def _load_kb(self) -> Dict:
        kb = {}
        latest = KB_ROOT / "mega_latest.json"
        if latest.exists():
            with open(latest) as f:
                kb = json.load(f)
        return kb

    def _load_insights(self):
        """加载 KB LLM 消化洞察，按 code 建立快速索引"""
        insights_path = KB_ROOT / "kb_insights.json"
        self._insights_index = {}
        if not insights_path.exists():
            return
        try:
            with open(insights_path) as f:
                raw = json.load(f)
            entries = raw if isinstance(raw, list) else raw.get('insights', [])
            for entry_wrapper in entries:
                # 支持两种格式: {timestamp, insights:[...]} 或直接是 insight dict
                items = entry_wrapper.get('insights', [entry_wrapper]) if isinstance(entry_wrapper, dict) else []
                for item in items:
                    body = str(item.get('body', ''))
                    title = str(item.get('title', ''))
                    text = title + ' ' + body
                    # 提取股票代码
                    codes_found = re.findall(r'\b(\d{6})\b', text)
                    for code in codes_found:
                        if code not in self._insights_index:
                            self._insights_index[code] = []
                        self._insights_index[code].append(item)
        except Exception:
            pass

    def _prefetch_indicators(self, codes: List[str]):
        """
        批量拉取历史日线，预计算 MA20 和 5 日均量。
        同时获取 tushare 基本面数据（PE/PB/ROE）。

        v8.4: BaoStock 优先（预计算 MA，~10s/50只），subprocess fallback。
        """
        self._indicators = {}
        if not codes:
            return

        import subprocess, math, time
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # ── 快路径：BaoStock 历史K线+预计算MA ──
        bs_fetched = set()
        t0 = time.time()
        try:
            from data_pipeline import get_historical_k_with_ma
            bs_data = get_historical_k_with_ma(codes, days=30)
            for code, bars in bs_data.items():
                closes = [b['close'] for b in bars if b['close'] > 0]
                volumes = [b['volume'] for b in bars if b['volume'] > 0]
                ind = {}
                if len(closes) >= 20:
                    ind['ma20'] = round(sum(closes[-20:]) / 20, 2)
                    # BaoStock 预计算的 MA20（最近一日）作为交叉验证
                    if bars[-1].get('ma20'):
                        ind['ma20_bs'] = bars[-1]['ma20']
                if len(volumes) >= 5:
                    ind['avg_vol_5'] = round(sum(volumes[-5:]) / 5, 0)
                if closes:
                    ind['close_history'] = closes
                self._indicators[code] = ind
                bs_fetched.add(code)
            print(f'   [BaoStock] {len(bs_fetched)}/{len(codes)} codes fetched in {time.time()-t0:.1f}s')
        except Exception as e:
            print(f'   [BaoStock] fallback triggered: {e}')

        # ── 慢路径：subprocess 补漏 ──
        remaining = [c for c in codes if c not in bs_fetched]
        if not remaining:
            # 全部被 BaoStock 覆盖，直接跳到 tushare 基本面
            pass
        else:
            print(f'   [subprocess] pulling {len(remaining)} remaining codes...')
            def _fetch_one(code):
                """拉取单只股票日线，返回 (code, indicators_dict)"""
                try:
                    proc = subprocess.run(
                        ['data', 'fetch', 'stock', '--symbol', code, '--category', 'daily', '--days', '30'],
                        capture_output=True, text=True, timeout=25,
                        env={**os.environ, 'HERMES_PROFILE': 'xiaohong'}
                    )
                    if proc.returncode != 0:
                        return (code, None)
                    data = json.loads(proc.stdout)
                    closes = []
                    volumes = []
                    for p in data.get('providers_attempted', []):
                        records = p.get('data', [])
                        if isinstance(records, list) and records:
                            for r in records:
                                closes.append(float(r.get('close', 0)))
                                volumes.append(float(r.get('vol', 0)))
                            break
                    ind = {}
                    if len(closes) >= 20:
                        ind['ma20'] = round(sum(closes[-20:]) / 20, 2)
                    if len(volumes) >= 5:
                        ind['avg_vol_5'] = round(sum(volumes[-5:]) / 5, 0)
                    if closes:
                        ind['close_history'] = closes
                    return (code, ind)
                except Exception:
                    return (code, None)

            with ThreadPoolExecutor(max_workers=8) as ex:
                futures = {ex.submit(_fetch_one, c): c for c in remaining}
                for fut in as_completed(futures):
                    code, ind = fut.result()
                    if ind is not None:
                        self._indicators[code] = ind

        # ── tushare 基本面 PE/PB/市值 ──
        # 注意: daily_basic 不支持 roe 字段，且多码批量查询不稳定，逐只查询
        # v8.5: ThreadPoolExecutor 并行（10 workers，避免触发 tushare 限流）
        try:
            import tushare as ts
            token = os.environ.get('TUSHARE_TOKEN', '')
            if token:
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')

                def _fetch_fundamental(code):
                    """单只查询基本面（独立 pro_api 实例，线程安全）"""
                    try:
                        _pro = ts.pro_api(token)
                        ts_code = code + '.SZ' if code.startswith(('0','3')) else code + '.SH'
                        df = _pro.daily_basic(
                            ts_code=ts_code, trade_date=yesterday,
                            fields='ts_code,pe_ttm,pb,total_mv,circ_mv'
                        )
                        if df is not None and not df.empty:
                            row = df.iloc[0]
                            return (code, {
                                'pe': float(row.get('pe_ttm', 0) or 0),
                                'pb': float(row.get('pb', 0) or 0),
                                'total_mv': float(row.get('total_mv', 0) or 0) / 1e4,  # 万元→亿元
                                'circ_mv': float(row.get('circ_mv', 0) or 0) / 1e4,
                            })
                    except Exception:
                        pass
                    return (code, None)

                with ThreadPoolExecutor(max_workers=10) as ex:
                    futures = {ex.submit(_fetch_fundamental, c): c for c in codes}
                    for fut in as_completed(futures):
                        code, fund = fut.result()
                        if fund and code in self._indicators:
                            self._indicators[code].update(fund)
        except Exception:
            pass

    def _prefetch_new_factors(self, codes: List[str]):
        """🆕 从已预取的 indicators 中直接计算新增因子（避免重复拉K线）"""
        if not codes:
            return
        self._new_factors = {}
        try:
            for code in codes:
                ind = self._indicators.get(code, {})
                closes = ind.get('close_history', [])
                if not closes or len(closes) < 20:
                    continue

                n = len(closes)
                nf = {}

                # ── 动量 ──
                if n >= 6 and closes[-6] > 0:
                    nf['mom_5d'] = round((closes[-1] / closes[-6] - 1) * 100, 2)
                if n >= 21 and closes[-21] > 0:
                    nf['mom_20d'] = round((closes[-1] / closes[-21] - 1) * 100, 2)
                if n >= 61 and closes[-61] > 0:
                    nf['mom_60d'] = round((closes[-1] / closes[-61] - 1) * 100, 2)

                # ── 波动（简化：从 close 算日内振幅代理）──
                if n >= 21:
                    rets = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(n-20, n)]
                    if rets:
                        mu = sum(rets) / len(rets)
                        var = sum((r - mu) ** 2 for r in rets) / len(rets)
                        nf['vol_20d'] = round(var ** 0.5 * 100, 2)

                # ── 筹码 ──
                ma20 = ind.get('ma20', 0)
                if ma20 > 0:
                    nf['ma20_deviation'] = round((closes[-1] / ma20 - 1) * 100, 2)

                avg_vol_5 = ind.get('avg_vol_5', 0)
                if avg_vol_5 > 0 and n >= 21:
                    avg_vol_all = sum(ind.get('close_history', [])[-21:]) / 21  # 简化为价格
                    pass  # 量比需在 indicators 中有 volumes

                if nf:
                    self._new_factors[code] = nf

            print(f'   [NewFactors] {len(self._new_factors)}/{len(codes)} codes enriched from indicators')
        except Exception as e:
            print(f'   [NewFactors] skipped: {e}')

    def _score_new_factors_bonus(self, c: Dict) -> float:
        """🆕 新增因子加分：动量/波动 0-100 分"""
        code = str(c.get('code', ''))
        nf = self._new_factors.get(code, {})
        if not nf:
            return 0

        bonus = 0
        n_signals = 0

        # ── 动量：短中期趋势确认 ──
        mom_5 = nf.get('mom_5d')
        mom_20 = nf.get('mom_20d')
        if mom_5 is not None and mom_20 is not None:
            if 0 < mom_5 < 15 and 0 < mom_20 < 30:
                bonus += 25
                n_signals += 1
            elif mom_5 > 15:
                bonus += 10
                n_signals += 1
            elif mom_5 < -5:
                bonus -= 15

        # ── 波动 ──
        vol20 = nf.get('vol_20d')
        if vol20 is not None:
            if 2 < vol20 < 5:
                bonus += 20
                n_signals += 1
            elif vol20 > 8:
                bonus -= 10

        # ── MA20偏离 ──
        dev = nf.get('ma20_deviation')
        if dev is not None:
            if -3 < dev < 3:
                bonus += 20  # 贴近MA20，安全
                n_signals += 1
            elif dev > 10:
                bonus -= 10  # 偏离过大

        if n_signals == 0:
            return 0
        return min(max(bonus, 0), 100)

    def _load_factor_weights(self):
        """🆕 从 factor_ic.json 加载 IC 动态权重"""
        self._factor_weights = {}
        ic_path = SCRIPT_DIR / 'data' / 'factor_ic.json'
        if not ic_path.exists():
            return
        try:
            data = json.loads(ic_path.read_text())
            records = data.get('records', [])
            if not records:
                return
            from collections import defaultdict
            by_factor = defaultdict(list)
            for r in records:
                by_factor[r['factor_id']].append(r.get('rank_ic', 0))
            for fid, ics in by_factor.items():
                recent = ics[-20:]
                if len(recent) < 5:
                    continue
                mean_ic = sum(recent) / len(recent)
                std_ic = (sum((x - mean_ic)**2 for x in recent) / len(recent)) ** 0.5
                icir = mean_ic / std_ic if std_ic > 0 else 0
                weight = max(0.5, min(1.5, 1.0 + icir))
                self._factor_weights[fid] = round(weight, 3)
        except Exception:
            pass

    # ═══════════════════════════════════════════
    # 2. 候选池
    # ═══════════════════════════════════════════

    def _get_candidates(self, kb: Dict) -> List[Dict]:
        candidates = {}
        modules = kb.get('modules', {})

        # 2a. 资金流入 TOP50
        try:
            from data_pipeline import get_top_flow_stocks
            top_flow = get_top_flow_stocks(50)
            for s in top_flow:
                code = str(s.get('code', ''))
                if code:
                    candidates[code] = {
                        'code': code,
                        'name': str(s.get('name', '')),
                        'net_flow': float(s.get('net_flow', 0)),
                        'change_pct': float(s.get('change_pct', 0)),
                        'source': 'fund_flow'
                    }
        except Exception:
            pass

        # 2b. 热点事件股
        hot_data = modules.get('hot_events', {}).get('data', [])
        for h in hot_data:
            code = str(h.get('code', ''))
            if code and code not in candidates:
                candidates[code] = {
                    'code': code,
                    'name': str(h.get('name', '')),
                    'change_pct': float(h.get('change_pct', 0)),
                    'source': 'hot_event'
                }

        # 2c. 公告事件股
        ann_data = modules.get('announcements', {}).get('data', [])
        for a in ann_data:
            code = str(a.get('code', ''))
            if code and code not in candidates:
                candidates[code] = {
                    'code': code,
                    'name': str(a.get('name', '')),
                    'event_weight': float(a.get('event_weight', 0)),
                    'source': 'announcement'
                }
            elif code in candidates:
                candidates[code]['event_weight'] = candidates[code].get('event_weight', 0) + \
                    float(a.get('event_weight', 0))

        # 2d. 券商买入评级股
        broker_data = modules.get('broker_views', {}).get('data', [])
        for b in broker_data:
            code = str(b.get('code', ''))
            if code and code not in candidates:
                candidates[code] = {
                    'code': code,
                    'name': str(b.get('name', '')),
                    'source': 'broker_buy'
                }
            elif code in candidates:
                candidates[code]['broker_buy'] = True

        # 2e. 昨日涨停首板（连板数=1）— 🆕 候选源
        first_board = self._get_first_board_codes()
        for fb in first_board:
            code = str(fb.get('code', ''))
            if code and code not in candidates:
                candidates[code] = fb
            elif code in candidates:
                candidates[code]['source'] = candidates[code].get('source', '') + '+limit_up'

        return list(candidates.values())

    # ═══════════════════════════════════════════
    # 3. 排除过滤
    # ═══════════════════════════════════════════

    def _apply_filters(self, candidates: List[Dict]) -> List[Dict]:
        """四重排除：ST → 连板(≥2板) → 停牌 → 市值(50-3000亿)"""
        valid = candidates.copy()
        st_codes = self._get_st_codes()
        multi_lianban_codes = self._get_multi_lianban_codes()
        suspended_codes = self._get_suspended_codes()

        filtered = []
        for c in valid:
            code = str(c.get('code', ''))

            # 排除 ST
            if code in st_codes or 'ST' in str(c.get('name', '')):
                self.excluded['st'].append(c)
                continue

            # 排除 ≥2连板（保留首板）
            if code in multi_lianban_codes:
                self.excluded['lianban'].append(c)
                continue

            # 排除 停牌
            if code in suspended_codes:
                self.excluded['suspended'].append(c)
                continue

            # 排除 市值 < 50亿 或 > 3000亿
            mkt_cap = self._get_market_cap(code)
            if mkt_cap is not None:
                if mkt_cap < 50.0:
                    c['market_cap'] = mkt_cap
                    self.excluded['small_cap'].append(c)
                    continue
                if mkt_cap > 3000.0:
                    c['market_cap'] = mkt_cap
                    self.excluded['large_cap'].append(c)
                    continue

            c['market_cap'] = mkt_cap or 0
            filtered.append(c)

        return filtered

    def _get_st_codes(self) -> set:
        st_codes = set()
        try:
            from resource_pool import fetch_corporate_announcements
            raw = fetch_corporate_announcements(self.date_str)
            for e in raw:
                name = str(e.get('name', ''))
                if 'ST' in name:
                    st_codes.add(str(e.get('code', '')))
        except Exception:
            pass
        return st_codes

    def _get_suspended_codes(self) -> set:
        """检测停牌股：KB洞察含「停牌」关键词 + 行情数据 (change_pct==0 且 close==0)"""
        suspended = set()
        # 方法1：KB 洞察索引中的停牌标记
        for code, insights in self._insights_index.items():
            for ins in insights:
                text = str(ins.get('title', '')) + ' ' + str(ins.get('body', ''))
                if '停牌' in text:
                    suspended.add(code)
                    break
        # 方法2：实时行情中涨跌幅和收盘价均为0（经典停牌信号）
        for code, q in getattr(self, '_quote_cache', {}).items():
            change_pct = float(q.get('change_pct', 1))
            close = float(q.get('close', 1))
            if change_pct == 0 and close == 0:
                suspended.add(code)
        return suspended

    def _get_multi_lianban_codes(self) -> set:
        """获取 ≥2 连板的股票代码（排除连续涨停的过热标的，保留首板）"""
        multi_lianban = set()
        try:
            import akshare as ak
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            df = ak.stock_zt_pool_em(date=yesterday)
            if df is not None and not df.empty and '代码' in df.columns:
                for _, row in df.iterrows():
                    lb = int(row.get('连板数', 1)) if '连板数' in df.columns else 1
                    if lb >= 2:
                        multi_lianban.add(str(row.get('代码', '')))
        except Exception:
            pass
        return multi_lianban

    def _get_first_board_codes(self) -> List[Dict]:
        """获取昨日首板涨停股（连板数=1），作为候选源"""
        first_board = []
        try:
            import akshare as ak
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
            df = ak.stock_zt_pool_em(date=yesterday)
            if df is not None and not df.empty and '代码' in df.columns:
                has_lb_col = '连板数' in df.columns
                for _, row in df.iterrows():
                    lb = int(row.get('连板数', 1)) if has_lb_col else 1
                    if lb == 1:
                        first_board.append({
                            'code': str(row.get('代码', '')),
                            'name': str(row.get('名称', '')),
                            'change_pct': 10.0,
                            'source': 'limit_up_first'
                        })
        except Exception:
            pass
        return first_board

    def _get_market_cap(self, code: str) -> Optional[float]:
        """获取市值(亿元) — 优先用预取 indicators 中的 total_mv"""
        # 快路径：从预取的 tushare 数据读取
        ind = self._indicators.get(code, {})
        mv = ind.get('total_mv', 0)
        if mv > 0:
            return float(mv)

        # 次路径：从行情缓存读取
        cached = getattr(self, '_quote_cache', {}).get(code, {})
        mc = cached.get('market_cap', 0)
        if mc and mc > 0:
            return float(mc)

        # 慢路径：单票查询 fallback
        try:
            from data_pipeline import get_stock_realtime
            realtime = get_stock_realtime([code])
            if code in realtime:
                mc = float(realtime[code].get('market_cap', 0))
                if mc > 0:
                    return mc
        except Exception:
            pass

        try:
            import tushare as ts
            token = os.environ.get('TUSHARE_TOKEN', '')
            if token:
                pro = ts.pro_api(token)
                df = pro.daily_basic(ts_code=code, trade_date=self.date_str)
                if df is not None and not df.empty:
                    return float(df.iloc[0].get('total_mv', 0)) / 1e4
        except Exception:
            pass

        return None

    # ═══════════════════════════════════════════
    # 4. 多因子打分
    # ═══════════════════════════════════════════

    def _score_candidates(self, candidates: List[Dict], kb: Dict) -> List[Dict]:
        modules = kb.get('modules', {})

        for c in candidates:
            scores = {}
            scores['event'] = self._score_event(c, modules)
            scores['fund'] = self._score_fund(c, modules)
            scores['sentiment'] = self._score_sentiment(c, modules)
            scores['technical'] = self._score_technical(c)
            scores['research'] = self._score_research(c, modules)

            # 🆕 新因子加分：动量/波动/筹码 → 独立模块，加权叠加
            new_factor_bonus = self._score_new_factors_bonus(c)

            c['factor_scores'] = scores

            # 五因子 + 新因子加权融合 (新因子权重~15%)
            base_score = (
                scores['event'] * 0.30 +
                scores['fund'] * 0.25 +
                scores['sentiment'] * 0.18 +
                scores['technical'] * 0.15 +
                scores['research'] * 0.07
            )
            # 新因子加成：最高 +15 分
            new_bonus = round(new_factor_bonus * 0.15, 1)

            c['total_score'] = round(base_score + new_bonus, 1)
            # 记录已加权的新因子贡献（方便显示和调试）
            scores['new_factors'] = new_bonus

        # 🆕 ML 预测批量增强：模型预测分流入 Total Score
        self._apply_ml_boost(candidates)

        return candidates

    def _apply_ml_boost(self, candidates: List[Dict]):
        """🆕 用 ML 预测器给候选池批量打分"""
        try:
            from ml_predictor import MLPredictor
            predictor = MLPredictor()
            if predictor.model is None:
                return  # 模型未训练，静默跳过

            codes = [c['code'] for c in candidates]
            # 构建因子面板
            factor_panels = {}
            for c in candidates:
                code = str(c['code'])
                fp = self._new_factors.get(code, {})
                # 补充 PE/PB 到因子面板
                ind = self._indicators.get(code, {})
                fp['pe'] = ind.get('pe', 0)
                fp['pb'] = ind.get('pb', 0)
                fp['total_mv'] = ind.get('total_mv', 0)
                factor_panels[code] = fp

            preds = predictor.predict_batch(codes, factor_panels, self._indicators)

            boosted = 0
            for c in candidates:
                code = str(c['code'])
                pred = preds.get(code)
                if pred and pred.score_boost != 0:
                    c['total_score'] = round(c['total_score'] + pred.score_boost, 1)
                    c['factor_scores']['ml_boost'] = round(pred.score_boost, 1)
                    c['ml_signal'] = pred.signal
                    c['ml_prob'] = pred.up_prob
                    boosted += 1

            if boosted:
                print(f'   [ML] {boosted}/{len(candidates)} boosted')
        except ImportError:
            pass  # lightgbm 未安装
        except Exception as e:
            print(f'   [ML] skipped: {e}')

    def _score_event(self, c: Dict, modules: Dict) -> float:
        score = 50
        code = str(c.get('code', ''))

        # 🆕 LLM 洞察：风险告警扣分，正面事件加分
        insights = self._insights_index.get(code, [])
        for ins in insights:
            itype = str(ins.get('type', ''))
            if 'risk' in itype:
                score -= 10
            elif 'signal' in itype or 'anomaly' in itype:
                score += 5

        # 公告/研报覆盖
        ann_data = modules.get('announcements', {}).get('data', [])
        ann_count = sum(1 for a in ann_data if str(a.get('code', '')) == code)
        score += min(ann_count * 5, 15)

        # 龙虎榜
        dragon_data = modules.get('dragon_tiger', {}).get('data', [])
        for d in dragon_data:
            if str(d.get('code', '')) == code:
                net = float(d.get('net_amount', 0))
                if net > 0:
                    score += min(net / 1e6, 15)
                break

        # 🆕 行业新闻：所属行业是否有事件驱动
        sector = c.get('sector', '')
        industry_data = modules.get('industry_news', {}).get('data', [])
        for news in industry_data:
            title = str(news.get('title', ''))
            nsector = str(news.get('sector', ''))
            if sector and (sector in title or sector in nsector or nsector in sector):
                score += 8
                break

        # 🆕 宏观政策：方向性量化
        policy_data = modules.get('policy_macro', {}).get('data', [])
        if isinstance(policy_data, list) and len(policy_data) > 50:
            pos_kw = ['降息','降准','宽松','刺激','减税','补贴','放开','支持','鼓励','加大']
            neg_kw = ['收紧','加息','调控','遏制','限制','监管','处罚','风险']
            pos = sum(1 for p in policy_data if any(kw in str(p.get('title','')) for kw in pos_kw))
            neg = sum(1 for p in policy_data if any(kw in str(p.get('title','')) for kw in neg_kw))
            if pos > neg * 2:
                score += 5
            elif neg > pos:
                score -= 5

        return min(max(score, 0), 100)

    def _score_fund(self, c: Dict, modules: Dict = None) -> float:
        code = str(c.get('code', ''))
        ind = self._indicators.get(code, {})

        # ── PE/PB 基础评分 ──
        pe = ind.get('pe', 0)
        pb = ind.get('pb', 0)

        if pe > 0:
            score = 40
            if 10 <= pe <= 30:
                score += 20
            elif 30 < pe <= 60:
                score += 10
            elif pe > 100:
                score -= 10
            if pb > 0 and pb <= 3:
                score += 10
        else:
            net_flow = float(c.get('net_flow', 0))
            if net_flow <= 0:
                return 30
            import math
            score = 30 + min(math.log10(max(net_flow / 1e4, 1)) * 25, 70)

        # ── 财务数据增强 (v8.3) ──
        try:
            from data_pipeline import get_financial_summary
            fin = get_financial_summary(code)
            if fin.get('data_source') != 'no_data':
                fin_score = fin.get('score', 50)
                # 融合：财务评分占40%权重
                score = score * 0.6 + fin_score * 0.4
                # 严重风险扣分
                if fin.get('risks'):
                    if len(fin['risks']) >= 3:
                        score -= 10
                    elif any('ROE为负' in r or '大幅下滑' in r for r in fin['risks']):
                        score -= 8
        except Exception:
            pass

        # ── 宏观：北向资金方向 ──
        if modules:
            nf = modules.get('north_flow', {}).get('data', {})
            nf_net = float(nf.get('summary', {}).get('net_flow', 0) or 0)
            if nf_net > 50:
                score += 8
            elif nf_net > 20:
                score += 5
            elif nf_net > 0:
                score += 3
            elif nf_net < -20:
                score -= 5

        return min(max(score, 0), 100)

    def _score_sentiment(self, c: Dict, modules: Dict) -> float:
        score = 50
        code = str(c.get('code', ''))

        # 🆕 LLM 洞察信号
        insights = self._insights_index.get(code, [])
        for ins in insights:
            itype = str(ins.get('type', ''))
            if 'sentiment' in itype or 'signal' in itype:
                score += 10

        # 热度排名
        hot_data = modules.get('hot_events', {}).get('data', [])
        for h in hot_data:
            if str(h.get('code', '')) == code:
                rank = int(h.get('hot_rank', 999))
                if rank <= 5:
                    score += 25
                elif rank <= 10:
                    score += 15
                elif rank <= 20:
                    score += 8
                break

        # 🆕 板块资金方向：所属板块是否受资金追捧
        sector = c.get('sector', '')
        sector_flow = modules.get('sector_flow', {}).get('data', {})
        if sector and sector_flow:
            for sname, sflow in sector_flow.items():
                if sector in sname or sname in sector:
                    net = float(sflow.get('net_flow', 0)) if isinstance(sflow, dict) else 0
                    if net > 1e8:
                        score += 15
                    elif net > 5e7:
                        score += 8
                    elif net > 0:
                        score += 3
                    elif net < -5e7:
                        score -= 5
                    break

        # 🆕 市场整体情绪：外盘期货方向
        ext = modules.get('external_futures', {}).get('data', {})
        asia = ext.get('asia_pacific', {}) or ext.get('asia', {})
        us = ext.get('us', {})
        asia_positive = sum(1 for v in asia.values() if isinstance(v, list) and len(v)>1 and v[1]>0)
        us_positive = sum(1 for v in us.values() if isinstance(v, list) and len(v)>1 and v[1]>0)
        market_score = asia_positive + us_positive
        if market_score >= 5:
            score += 10
        elif market_score >= 3:
            score += 5
        elif market_score <= 1:
            score -= 5

        # 涨跌幅（从实时行情）
        q = self._quote_cache.get(code, {})
        change_pct = float(q.get('change_pct', 0)) or float(c.get('change_pct', 0))
        if 1 <= change_pct <= 5:
            score += 10
        elif 5 < change_pct <= 9:
            score += 5
        elif change_pct > 9:
            score -= 5
        elif change_pct < -5:
            score += 10

        return min(max(score, 0), 100)

    def _score_technical(self, c: Dict) -> float:
        score = 50
        code = str(c.get('code', ''))
        ind = self._indicators.get(code, {})

        # 🆕 用预计算的 MA20 和均量
        q = self._quote_cache.get(code, {})
        close = float(q.get('close', 0))
        ma20 = ind.get('ma20', close)

        if close > 0 and ma20 > 0:
            dev = (close - ma20) / ma20 * 100
            if -3 <= dev <= 2:
                score += 20
            elif 2 < dev <= 5:
                score += 10
            elif 5 < dev <= 10:
                score += 5
            elif dev > 10:
                score -= 5
            elif dev < -8:
                score += 10

        vol = float(q.get('volume', 0))
        avg_vol = ind.get('avg_vol_5', vol)
        if avg_vol > 0 and vol > 0 and avg_vol != vol:
            vol_ratio = vol / avg_vol
            if 1.2 <= vol_ratio <= 3:
                score += 15
            elif 0.5 <= vol_ratio < 0.8:
                score += 5
            elif vol_ratio > 3:
                score -= 5

        return min(max(score, 0), 100)

    def _score_research(self, c: Dict, modules: Dict) -> float:
        score = 50
        code = str(c.get('code', ''))

        broker_data = modules.get('broker_views', {}).get('data', [])
        buy_count = sum(1 for b in broker_data if str(b.get('code', '')) == code and b.get('rating') == '买入')
        score += min(buy_count * 10, 30)

        if buy_count > 0:
            score += 10

        return min(max(score, 0), 100)

    # ═══════════════════════════════════════════
    # 5. 止损位计算
    # ═══════════════════════════════════════════

    def _calc_stop_loss(self, rec: Dict) -> Dict:
        code = str(rec.get('code', ''))
        # 创业板（300xxx/301xxx）波动大，止损放宽至 -7%
        is_chinext = code.startswith('300') or code.startswith('301')
        default_ratio = -7.0 if is_chinext else -5.0
        stop_ratio_factor = 0.93 if is_chinext else 0.95
        stop_info = {'method': 'default', 'price': None, 'ratio': default_ratio}

        # 优先用预取缓存
        rt = getattr(self, '_quote_cache', {}).get(code, {})
        if not rt:
            try:
                from data_pipeline import get_stock_realtime
                realtime = get_stock_realtime([code])
                rt = realtime.get(code, {})
            except Exception:
                rt = {}

        try:
            close = float(rt.get('close', 0))
            if close > 0:
                stop_info['price'] = round(close * stop_ratio_factor, 2)
                stop_info['ratio'] = default_ratio

                ma20 = float(rt.get('ma20', 0))
                if ma20 > 0 and abs(close - ma20) / close < 0.08:
                    # MA20附近时，止损设在MA20下方3%（替代固定比例）
                    ma20_stop_factor = 0.97
                    stop_info['price'] = round(ma20 * ma20_stop_factor, 2)
                    stop_info['method'] = 'ma20'
                    stop_info['ratio'] = round((ma20 * ma20_stop_factor - close) / close * 100, 1)
        except Exception:
            pass

        return stop_info

    # ═══════════════════════════════════════════
    # 5b. 操作策略生成 v2.2（多维决策矩阵）
    # ═══════════════════════════════════════════

    def _gen_operation_v2(self, rec: Dict) -> str:
        """多维决策：MA20偏离 × KB洞察情绪 × 涨跌幅 → 差异化策略"""
        code = str(rec.get('code', ''))
        sl = rec.get('stop_loss', {})
        stop_ratio = sl.get('ratio', -5.0)
        change_pct = float(rec.get('change_pct', 0))

        # 1. 价格相对MA20位置
        q = getattr(self, '_quote_cache', {}).get(code, {})
        ind = getattr(self, '_indicators', {}).get(code, {})
        close = float(q.get('close', 0))
        ma20 = ind.get('ma20', close)
        dev = ((close - ma20) / ma20 * 100) if close > 0 and ma20 > 0 else 0

        # 2. KB洞察情绪
        insights = getattr(self, '_insights_index', {}).get(code, [])
        insight_bias = 'neutral'
        if insights:
            bodies = ' '.join(str(i.get('body', '')) for i in insights)
            titles = ' '.join(str(i.get('title', '')) for i in insights)
            text = titles + ' ' + bodies
            positive_kw = ['回购', '增持', '利好', '突破', '中标', '订单', '增长', '注销', '激励']
            negative_kw = ['减持', '终止', '亏损', '爆雷', '诉讼', '处罚', '退市', '警示', '冻结']
            pos = sum(1 for kw in positive_kw if kw in text)
            neg = sum(1 for kw in negative_kw if kw in text)
            if pos > neg:
                insight_bias = 'positive'
            elif neg > pos:
                insight_bias = 'negative'

        # 3. 特殊状态：停牌检测（无涨跌+有收盘价+洞察含停牌，或无数据）
        insight_text = ' '.join(str(i.get('title','')) + ' ' + str(i.get('body','')) for i in insights)
        is_suspended = ('停牌' in insight_text) or (change_pct == 0 and close == 0)
        if is_suspended:
            return f"停牌中，复牌首日观察竞价方向与量能，止损按复牌价{stop_ratio:+.0f}%"

        if change_pct > 7:
            return f"高开{change_pct:+.1f}%不追，等回踩5日线缩量企稳后轻仓试仓，止损{stop_ratio:+.0f}%"

        # 4. 多维决策矩阵（dev × insight_bias）
        is_chinext = code.startswith('300') or code.startswith('301')
        prefix = "创业板" if is_chinext else ""

        if dev > 5:
            if insight_bias == 'positive':
                return f"{prefix}强势偏离MA20 +{dev:.0f}%，等回踩MA20不破建底仓11.1%，止损{stop_ratio:+.0f}%"
            else:
                return f"{prefix}偏离MA20 +{dev:.0f}%偏高，等回踩MA20缩量确认后低吸，止损{stop_ratio:+.0f}%"
        elif dev >= -2:
            if insight_bias == 'positive':
                return f"{prefix}MA20附近(偏离{dev:+.0f}%)+利好信号密集，建底仓11.1%，止损{stop_ratio:+.0f}%"
            else:
                return f"{prefix}MA20附近(偏离{dev:+.0f}%)整理，侦察兵⭐确认后建底仓11.1%，止损{stop_ratio:+.0f}%"
        else:
            if insight_bias == 'negative':
                return f"{prefix}跌破MA20 {dev:+.0f}%，利空信号未消化，观望等止跌企稳"
            else:
                return f"{prefix}MA20下方{dev:+.0f}%，超跌等放量止跌信号后轻仓博弈，止损{stop_ratio:+.0f}%"

    # ═══════════════════════════════════════════
    # 5c. 风险评估 v2.2（多维打分）
    # ═══════════════════════════════════════════

    def _assess_risk_v2(self, rec: Dict) -> str:
        """多维评估：市值 + 波动 + 板别 + 技术 + 消息面 → 高/中/低"""
        code = str(rec.get('code', ''))
        scores = rec.get('factor_scores', {})
        change_pct = abs(float(rec.get('change_pct', 0)))

        # 市值（_quote_cache 优先，修复 market_cap=0 bug）
        q = getattr(self, '_quote_cache', {}).get(code, {})
        mkt_cap = float(q.get('market_cap', 0) or rec.get('market_cap', 0))
        is_chinext = code.startswith('300') or code.startswith('301')

        # 消息面风险
        insights = getattr(self, '_insights_index', {}).get(code, [])
        insight_risk = 0
        for ins in insights:
            if ins.get('type') == 'risk_alert':
                insight_risk += 1
            elif ins.get('confidence') == 'high' and ins.get('type') in ('fund_signal',):
                insight_risk -= 0.5

        # 综合评分（0-100，越高越危险）
        score = 50

        # 市值：小盘 → 高风险
        if mkt_cap == 0:
            score += 15
        elif mkt_cap < 80:
            score += 20
        elif mkt_cap > 800:
            score -= 15
        elif mkt_cap > 300:
            score -= 5

        # 波动：高波动 → 高风险
        if change_pct > 8:
            score += 20
        elif change_pct > 5:
            score += 10

        # 创业板 → 波动容忍度低，风险高
        if is_chinext:
            score += 10

        # 技术面弱 → 趋势不稳
        if scores.get('technical', 50) < 50:
            score += 10

        # 消息面
        score += insight_risk * 5

        # 映射
        if score >= 70:
            return '高'
        elif score >= 45:
            return '中'
        else:
            return '低'

    # ═══════════════════════════════════════════
    # 6. 板块归类 + 操作策略 + 风险等级 （v2.0 新增）
    # ═══════════════════════════════════════════

    def _enrich_recommendations(self, kb: Dict):
        """为每只推荐股附加板块、操作策略、风险等级"""
        modules = kb.get('modules', {})
        for rec in self.recommendations:
            name = str(rec.get('name', ''))
            rec['sector'] = _guess_sector(name, str(rec.get('code', '')), modules)
            rec['operation'] = self._gen_operation_v2(rec)
            rec['risk_level'] = self._assess_risk_v2(rec)

    # ═══════════════════════════════════════════
    # 7. 持久化
    # ═══════════════════════════════════════════

    def _save_pool(self):
        POOL_PATH.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有池，仅保留当日盘中侦察兵新增（08:25 推荐引擎生成新池，旧日 intraday 自然清除）
        existing = {'scout_additions': [], 'scout_last_update': None}
        if POOL_PATH.exists():
            try:
                with open(POOL_PATH) as f:
                    old = json.load(f)
                # 只保留今天的 intraday（date 匹配或 今天才添加的）
                if old.get('date') == self.date_str:
                    existing['scout_additions'] = old.get('scout_additions', [])
                    existing['scout_last_update'] = old.get('scout_last_update')
            except Exception:
                pass

        # 议会结论（如果有）
        parliament_verdict = getattr(self, '_parliament_verdict', None)
        parliament_field = {}
        if parliament_verdict:
            parliament_field = {
                'bias': parliament_verdict.get('bias', 'neutral'),
                'confidence': parliament_verdict.get('overall_confidence', 0.5),
                'bull_signals': parliament_verdict.get('bull_strength', 0),
                'bear_signals': parliament_verdict.get('bear_strength', 0),
                'red_flags': parliament_verdict.get('critical_flags', []),
                'recommendation': parliament_verdict.get('recommendation', ''),
                'timestamp': parliament_verdict.get('timestamp', '')
            }

        output = {
            'date': self.date_str,
            'generated_at': datetime.now().isoformat(),
            'version': 'v2.3',
            'recommendations': self.recommendations,
            'excluded': {k: len(v) for k, v in self.excluded.items()},
            'scout_additions': existing['scout_additions'],
            'scout_last_update': existing['scout_last_update'],
            'parliament': parliament_field,
            'methodology': {
                'factors': {
                    'event': 0.30,
                    'fund': 0.25,
                    'sentiment': 0.20,
                    'technical': 0.15,
                    'research': 0.10
                },
                'data_sources': [
                    'Sina批量行情', 'tushare PE/ROE', '历史日线MA20/均量',
                    'KB LLM洞察', 'mega_collector公告/龙虎榜'
                ],
                'filters': ['ST/*ST', '连板(≥2板)', '停牌', '市值<50亿', '市值>3000亿'],
                'max_picks': 9,
                'reset': 'daily'
            }
        }

        with open(POOL_PATH, 'w') as f:
            json.dump(output, f, ensure_ascii=False, indent=2, default=str)

        # 🆕 同步写入跟踪系统
        try:
            from stock_tracker import StockTracker
            tracker = StockTracker()
            tracker.add_pool(pool_date=self.date_str, recommendations=self.recommendations)
        except Exception:
            pass  # 跟踪失败不影响选股流程


# ──────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────

def main():
    import argparse
    p = argparse.ArgumentParser(description='Stock Recommender v2.0 — 选股推荐引擎')
    p.add_argument('--top', type=int, default=9, help='推荐数量 (默认9)')
    p.add_argument('--json', action='store_true', help='JSON格式输出')
    args = p.parse_args()

    rec = StockRecommender()
    results = rec.run(top_n=args.top)

    if args.json:
        print(json.dumps({
            'date': rec.date_str,
            'version': 'v2.2',
            'recommendations': results,
            'excluded': rec.excluded
        }, ensure_ascii=False, indent=2, default=str))
    else:
        total_excluded = sum(len(v) for v in rec.excluded.values())
        print(f"\n{'='*60}")
        print(f"  🌹 安幕诺家族 · 每日推荐池  {rec.date_str[:4]}-{rec.date_str[4:6]}-{rec.date_str[6:]}")
        print(f"  {'='*60}")
        print(f"  排除: ST {len(rec.excluded['st'])} | 连板 {len(rec.excluded['lianban'])} | 停牌 {len(rec.excluded['suspended'])} "
              f"| 小盘 {len(rec.excluded['small_cap'])} | 大盘 {len(rec.excluded['large_cap'])} | 共 {total_excluded}只")
        print(f"  {'='*60}\n")
        for i, r in enumerate(results, 1):
            sl = r.get('stop_loss', {})
            print(f"  {i:2d}. {r['code']:6s} {r['name']:8s}  "
                  f"板块: {r.get('sector','?'):8s}  风险: {r.get('risk_level','?')}  "
                  f"总分:{r['total_score']:5.1f}")
            print(f"      逻辑: {r.get('operation','?')}")
            print(f"      止损: {sl.get('price','?')} ({sl.get('ratio',0):+.1f}%)  "
                  f"市值: {r.get('market_cap',0):.0f}亿  涨跌: {r.get('change_pct',0):+.2f}%")
        print()


if __name__ == '__main__':
    main()
