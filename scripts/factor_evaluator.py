#!/usr/bin/env python3
"""
factor_evaluator.py — 因子有效性评估引擎
==========================================
每日计算因子 Rank IC / ICIR，月度自动淘汰低效因子。

用法:
  python3 factor_evaluator.py              # 计算今日IC，更新factor_ic.json
  python3 factor_evaluator.py --report     # 输出因子报告
  python3 factor_evaluator.py --purge      # 月度淘汰

数据流:
  daily_pool.json + BaoStock 历史日线 → 因子面板 → IC计算 → factor_ic.json
"""

import sys, os, json, math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

IC_PATH = SCRIPT_DIR / 'data' / 'factor_ic.json'
POOL_PATH = SCRIPT_DIR / 'data' / 'daily_pool.json'
IC_HISTORY_MAX = 252  # 保留最近一年交易日数据


# ═══════════════════════════════════════
# 因子注册表
# ═══════════════════════════════════════

FACTOR_REGISTRY = {
    # ── 动量类 ──
    'mom_5d':          {'label': '5日动量',          'class': 'momentum',   'min_icir': 0.02},
    'mom_20d':         {'label': '20日动量',         'class': 'momentum',   'min_icir': 0.02},
    'mom_60d':         {'label': '60日动量',         'class': 'momentum',   'min_icir': 0.01},
    'alpha_idx':       {'label': '超额收益(20日)',    'class': 'momentum',   'min_icir': 0.02},
    # ── 波动类 ──
    'atr_14':          {'label': 'ATR波动率(14日)',   'class': 'volatility', 'min_icir': 0.01},
    'vol_20d':         {'label': '20日波动率',        'class': 'volatility', 'min_icir': 0.01},
    'downside_vol':    {'label': '下行波动率',        'class': 'volatility', 'min_icir': 0.02},
    # ── 资金类 ──
    'main_net_buy':    {'label': '主力净买比',        'class': 'flow',       'min_icir': 0.03},
    'retail_net_buy':  {'label': '散户净买比',        'class': 'flow',       'min_icir': 0.02},
    'northbound_5d':   {'label': '北向持仓5日变化',   'class': 'flow',       'min_icir': 0.02},
    # ── 筹码类 ──
    'turnover_zscore': {'label': '换手率Z-score',     'class': 'position',   'min_icir': 0.02},
    'vol_ratio_trend': {'label': '量比趋势(5/20)',    'class': 'position',   'min_icir': 0.02},
    'amplitude_5d':    {'label': '5日平均振幅',       'class': 'position',   'min_icir': 0.01},
    # ── 估值类 ──
    'pe_percentile':   {'label': 'PE分位数(5年)',     'class': 'valuation',  'min_icir': 0.03},
    'pb_percentile':   {'label': 'PB分位数(5年)',     'class': 'valuation',  'min_icir': 0.03},
    # ── 质量类 ──
    'roe_stability':   {'label': 'ROE稳定性(3年CV)',  'class': 'quality',    'min_icir': 0.02},
    'cf_profit_ratio': {'label': '现金流/净利润比',    'class': 'quality',    'min_icir': 0.02},
}

# 原有五因子（保留兼容）
LEGACY_FACTORS = {
    'event_score':     {'label': '事件因子',          'class': 'event',       'min_icir': 0.02},
    'fund_score':      {'label': '基本面因子',        'class': 'fund',        'min_icir': 0.03},
    'sentiment_score': {'label': '情绪因子',          'class': 'sentiment',   'min_icir': 0.02},
    'technical_score': {'label': '技术面因子',        'class': 'technical',   'min_icir': 0.03},
    'research_score':  {'label': '研报因子',          'class': 'research',    'min_icir': 0.02},
}


# ═══════════════════════════════════════
# 因子计算引擎
# ═══════════════════════════════════════

class FactorCalculator:
    """批量因子计算。接收历史日线 + 资金数据 → 输出因子面板。"""

    def __init__(self):
        self._cache: Dict[str, np.ndarray] = {}

    def compute_panel(self, code: str, bars: List[Dict],
                      flow_data: Dict = None, index_returns: List[float] = None) -> Dict[str, float]:
        """
        对单只股票计算全部因子。

        Args:
            code: 股票代码
            bars: 历史K线 [{'close':..., 'volume':..., 'high':..., 'low':..., 'turn':...}, ...]
            flow_data: {'main_net_buy': ..., 'retail_net_buy': ..., 'northbound_change_5d': ...}
            index_returns: 沪深300同期日收益率列表 (用于alpha计算)

        Returns:
            {factor_id: value, ...} 缺失的因子为 None
        """
        factors = {}
        if not bars or len(bars) < 20:
            return factors

        closes = np.array([b['close'] for b in bars], dtype=float)
        highs  = np.array([b['high'] for b in bars], dtype=float)
        lows   = np.array([b['low'] for b in bars], dtype=float)
        volumes = np.array([b.get('volume', 0) for b in bars], dtype=float)
        turns  = np.array([b.get('turn', 0) for b in bars], dtype=float)

        # ── 动量因子 ──
        if len(closes) >= 6:
            factors['mom_5d'] = round(float((closes[-1] / closes[-6] - 1) * 100), 2)
        if len(closes) >= 21:
            factors['mom_20d'] = round(float((closes[-1] / closes[-21] - 1) * 100), 2)
        if len(closes) >= 61:
            factors['mom_60d'] = round(float((closes[-1] / closes[-61] - 1) * 100), 2)

        # alpha: 20日超额收益 vs 沪深300
        if index_returns and len(closes) >= 21 and len(index_returns) >= 20:
            stock_ret_20 = closes[-1] / closes[-21] - 1
            idx_ret_20 = np.prod(1 + np.array(index_returns[-20:])) - 1
            factors['alpha_idx'] = round(float((stock_ret_20 - idx_ret_20) * 100), 2)

        # ── 波动因子 ──
        if len(closes) >= 15:
            tr_list = []
            for i in range(max(1, len(closes) - 14), len(closes)):
                hl = highs[i] - lows[i]
                hc = abs(highs[i] - closes[i-1])
                lc = abs(lows[i] - closes[i-1])
                tr_list.append(max(hl, hc, lc))
            atr = np.mean(tr_list) if tr_list else 0
            factors['atr_14'] = round(float(atr / closes[-1] * 100), 2) if closes[-1] > 0 else None

        if len(closes) >= 21:
            returns = np.diff(closes[-21:]) / closes[-21:-1]
            factors['vol_20d'] = round(float(np.std(returns) * 100), 2)
            neg_returns = returns[returns < 0]
            factors['downside_vol'] = round(float(np.std(neg_returns) * 100), 2) if len(neg_returns) > 1 else 0.0

        # ── 资金因子 ──
        if flow_data:
            factors['main_net_buy'] = flow_data.get('main_net_buy')
            factors['retail_net_buy'] = flow_data.get('retail_net_buy')
            factors['northbound_5d'] = flow_data.get('northbound_change_5d')

        # ── 筹码因子 ──
        if len(turns) >= 21 and turns[-1] > 0:
            mean_turn = np.mean(turns[-21:])
            std_turn = np.std(turns[-21:])
            if std_turn > 0:
                factors['turnover_zscore'] = round(float((turns[-1] - mean_turn) / std_turn), 2)

        if len(volumes) >= 21:
            avg_vol_5 = np.mean(volumes[-5:])
            avg_vol_20 = np.mean(volumes[-20:])
            factors['vol_ratio_trend'] = round(float(avg_vol_5 / avg_vol_20), 2) if avg_vol_20 > 0 else 1.0

        if len(highs) >= 6 and len(lows) >= 6:
            amps = [(highs[i] - lows[i]) / closes[i] * 100 for i in range(-5, 0)]
            factors['amplitude_5d'] = round(float(np.mean(amps)), 2)

        # ── 估值因子（需外部注入）──
        factors['pe_percentile'] = None  # 需要 tushare 历史PE计算分位数
        factors['pb_percentile'] = None

        # ── 质量因子（需外部注入）──
        factors['roe_stability'] = None
        factors['cf_profit_ratio'] = None

        return {k: v for k, v in factors.items() if v is not None}


# ═══════════════════════════════════════
# IC 计算引擎
# ═══════════════════════════════════════

@dataclass
class ICRecord:
    """单日 IC 记录"""
    date: str
    factor_id: str
    rank_ic: float            # Spearman Rank IC
    icir_20d: Optional[float] = None  # 滚动20日 ICIR
    status: str = 'active'    # active / deprecated


class ICEvaluator:
    """因子 IC/ICIR 评估器"""

    def __init__(self):
        self.calc = FactorCalculator()
        self.history: List[ICRecord] = []
        self._load()

    def _load(self):
        if IC_PATH.exists():
            try:
                data = json.loads(IC_PATH.read_text())
                self.history = [ICRecord(**r) for r in data.get('records', [])]
            except Exception:
                self.history = []

    def _save(self):
        IC_PATH.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'updated': datetime.now().isoformat(),
            'records': [
                {'date': r.date, 'factor_id': r.factor_id,
                 'rank_ic': r.rank_ic, 'icir_20d': r.icir_20d, 'status': r.status}
                for r in self.history[-IC_HISTORY_MAX * len(FACTOR_REGISTRY):]
            ]
        }
        IC_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def compute_daily_ic(self, date_str: str = None) -> Dict[str, float]:
        """
        计算今日各因子 Rank IC。

        从 daily_pool.json 获取推荐池候选股 → 拉历史日线 → 计算因子 → 计算 IC。
        返回 {factor_id: rank_ic, ...}
        """
        if date_str is None:
            date_str = datetime.now().strftime('%Y%m%d')

        # 加载推荐池评分
        if not POOL_PATH.exists():
            print('[IC] 推荐池文件不存在，跳过')
            return {}

        pool = json.loads(POOL_PATH.read_text())
        candidates = pool.get('candidates', [])
        if not candidates:
            print('[IC] 推荐池无候选，跳过')
            return {}

        # 收集因子面板 → 需要实跑推荐引擎或直接拉日线
        # 简化方案：直接用候选的 factor_scores 做五因子 IC
        # 新增因子暂时从历史日线计算（如果可用）
        ic_results = {}
        today = date_str

        # ── Part 1: 五因子 IC（从 daily_pool 已有数据）──
        legacy_ics = self._compute_legacy_ic(candidates)
        ic_results.update(legacy_ics)

        # ── Part 2: 新因子 IC（拉日线计算）──
        try:
            from data_pipeline import get_historical_k_with_ma
            codes = [c['code'] for c in candidates if c.get('total_score', 0) > 0]
            if codes:
                bs_data = get_historical_k_with_ma(codes[:50], days=65)
                new_ics = self._compute_new_factor_ic(codes[:50], bs_data, candidates)
                ic_results.update(new_ics)
        except Exception as e:
            print(f'[IC] 新因子计算失败: {e}')

        # 保存
        for fid, ic_val in ic_results.items():
            self.history.append(ICRecord(
                date=today,
                factor_id=fid,
                rank_ic=round(float(ic_val), 4),
            ))

        # 计算滚动 ICIR
        self._update_icir()

        self._save()
        print(f'[IC] {today}: {len(ic_results)} 因子 IC 已更新')
        return ic_results

    def _compute_legacy_ic(self, candidates: List[Dict]) -> Dict[str, float]:
        """计算五因子 IC。用 total_score 作为次日收益的代理（简化）。"""
        ics = {}
        n = len(candidates)
        if n < 10:
            return ics

        score_fields = ['event_score', 'fund_score', 'sentiment_score', 'technical_score', 'research_score']
        field_to_fid = {
            'event_score': 'event_score',
            'fund_score': 'fund_score',
            'sentiment_score': 'sentiment_score',
            'technical_score': 'technical_score',
            'research_score': 'research_score',
        }

        # 用 total_score 作为排序目标（次日实际收益的代理）
        scores = np.array([c.get('total_score', 0) for c in candidates], dtype=float)

        for field in score_fields:
            factor_vals = np.array([c.get('factor_scores', {}).get(field, 50) for c in candidates], dtype=float)
            if np.std(factor_vals) < 0.1:
                continue
            # Spearman Rank IC
            ic = self._spearman_ic(factor_vals, scores)
            ics[field_to_fid[field]] = ic

        return ics

    def _compute_new_factor_ic(self, codes: List[str], bs_data: Dict,
                                candidates: List[Dict]) -> Dict[str, float]:
        """计算新增因子的 IC"""
        ics = {}
        # 构建 code → total_score 映射
        score_map = {str(c['code']): c.get('total_score', 0) for c in candidates}

        for fid in FACTOR_REGISTRY:
            if fid in ics:  # 已计算的跳过
                continue
            factor_vals = []
            target_vals = []
            for code in codes:
                bars = bs_data.get(code, [])
                if not bars:
                    continue
                factors = self.calc.compute_panel(code, bars)
                val = factors.get(fid)
                target = score_map.get(code, 0)
                if val is not None and target > 0:
                    factor_vals.append(val)
                    target_vals.append(target)

            if len(factor_vals) >= 10:
                ic = self._spearman_ic(np.array(factor_vals), np.array(target_vals))
                ics[fid] = ic

        return ics

    @staticmethod
    def _spearman_ic(x: np.ndarray, y: np.ndarray) -> float:
        """Spearman Rank IC"""
        from scipy.stats import spearmanr
        try:
            corr, _ = spearmanr(x, y)
            return float(corr) if not np.isnan(corr) else 0.0
        except Exception:
            return 0.0

    def _update_icir(self):
        """更新每个因子的滚动20日 ICIR"""
        # 按因子分组
        by_factor: Dict[str, List[ICRecord]] = defaultdict(list)
        for r in self.history:
            by_factor[r.factor_id].append(r)

        for fid, records in by_factor.items():
            recent = [r.rank_ic for r in records[-20:]]
            if len(recent) >= 5:
                mean_ic = np.mean(recent)
                std_ic = np.std(recent) if np.std(recent) > 0 else 0.01
                for r in records[-1:]:
                    r.icir_20d = round(float(mean_ic / std_ic), 4)

    def get_factor_report(self) -> List[Dict]:
        """获取因子状态报告"""
        by_factor: Dict[str, List[float]] = defaultdict(list)
        by_factor_latest: Dict[str, float] = {}
        for r in self.history:
            by_factor[r.factor_id].append(r.rank_ic)
            by_factor_latest[r.factor_id] = r.rank_ic

        report = []
        all_factors = {**FACTOR_REGISTRY, **LEGACY_FACTORS}
        for fid, meta in all_factors.items():
            ics = by_factor.get(fid, [])
            if not ics:
                report.append({
                    'factor_id': fid, 'label': meta['label'], 'class': meta['class'],
                    'n_days': 0, 'mean_ic': 0, 'std_ic': 0, 'icir_20d': 0,
                    'latest_ic': 0, 'status': 'no_data', 'min_icir': meta['min_icir'],
                })
                continue

            mean_ic = np.mean(ics[-60:]) if len(ics) >= 5 else 0
            std_ic = np.std(ics[-60:]) if len(ics) >= 5 else 0
            icir = mean_ic / std_ic if std_ic > 0 else 0

            # 状态判定
            if abs(icir) >= meta['min_icir']:
                status = 'active'
            elif abs(icir) >= meta['min_icir'] * 0.5:
                status = 'watch'
            else:
                status = 'deprecated'

            report.append({
                'factor_id': fid, 'label': meta['label'], 'class': meta['class'],
                'n_days': len(ics), 'mean_ic': round(float(mean_ic), 4),
                'std_ic': round(float(std_ic), 4), 'icir_20d': round(float(icir), 4),
                'latest_ic': round(float(by_factor_latest.get(fid, 0)), 4),
                'status': status, 'min_icir': meta['min_icir'],
            })

        return sorted(report, key=lambda x: abs(x['icir_20d']), reverse=True)

    def purge_deprecated(self) -> List[str]:
        """月度淘汰：标记连续低效的因子"""
        report = self.get_factor_report()
        purged = []
        for r in report:
            if r['status'] == 'deprecated' and r['n_days'] >= 20:
                purged.append(r['factor_id'])
                # 标记历史记录
                for rec in self.history:
                    if rec.factor_id == r['factor_id']:
                        rec.status = 'deprecated'

        self._save()
        if purged:
            print(f'[IC] 月度淘汰: {purged}')
        return purged


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--report', action='store_true', help='输出因子报告')
    ap.add_argument('--purge', action='store_true', help='月度淘汰低效因子')
    ap.add_argument('--json', action='store_true', help='JSON输出')
    args = ap.parse_args()

    evaluator = ICEvaluator()

    if args.purge:
        purged = evaluator.purge_deprecated()
        if args.json:
            print(json.dumps({'purged': purged}, ensure_ascii=False))
        else:
            print(f'已淘汰: {purged or "无"}')

    elif args.report:
        report = evaluator.get_factor_report()
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            _print_report(report)

    else:
        # 默认：计算今日IC
        ics = evaluator.compute_daily_ic()
        if args.json:
            print(json.dumps(ics, ensure_ascii=False))
        else:
            active = sum(1 for v in ics.values() if abs(v) >= 0.02)
            print(f'因子IC: {len(ics)} 计算, {active} 有效 (|IC|≥0.02)')
            for fid, ic in sorted(ics.items(), key=lambda x: abs(x[1]), reverse=True):
                marker = '✅' if abs(ic) >= 0.05 else ('⚠️' if abs(ic) >= 0.02 else '❌')
                print(f'  {marker} {fid}: {ic:+.4f}')


def _print_report(report: List[Dict]):
    from report_formatter import Report
    r = Report(title='因子有效性评估', icon='📊', color='blue')
    r.header_meta(更新=datetime.now().strftime('%Y-%m-%d %H:%M'), 已计算=f'{len(report)}因子')

    r.section('高效因子 (|ICIR|≥0.03)')
    for item in [x for x in report if abs(x['icir_20d']) >= 0.03]:
        r.kv(f"{item['label']}", f"ICIR={item['icir_20d']:+.4f} IC={item['latest_ic']:+.4f} N={item['n_days']}d", '✅')

    r.section('观察因子 (0.01≤|ICIR|<0.03)')
    for item in [x for x in report if 0.01 <= abs(x['icir_20d']) < 0.03]:
        r.kv(f"{item['label']}", f"ICIR={item['icir_20d']:+.4f} IC={item['latest_ic']:+.4f}", '⚠️')

    r.section('待淘汰 (|ICIR|<0.01)')
    for item in [x for x in report if abs(x['icir_20d']) < 0.01 and x['n_days'] > 0]:
        r.kv(f"{item['label']}", f"ICIR={item['icir_20d']:+.4f}", '❌')

    r.footer(f'factor_evaluator.py · {datetime.now().strftime("%Y-%m-%d")}')
    print(r.markdown())


# ═══════════════════════════════════════
# 滚动窗口特征 (P2-2)
# ═══════════════════════════════════════

class RollingFeatureComputer:
    """
    从历史因子序列计算滚动窗口统计特征。

    产出:
      - 滚动均值 (5d/10d/20d)
      - 滚动标准差
      - Z-score (当前值偏离历史均值多少个标准差)
      - 分位数 (当前值在历史中的位置)
      - 趋势 (斜率/加速度)
    """

    def __init__(self, windows: List[int] = None):
        self.windows = windows or [5, 10, 20]
        self.max_window = max(self.windows)

    def compute(self, factor_series: List[float]) -> Dict[str, float]:
        """
        对单因子历史序列计算滚动特征。

        Args:
            factor_series: 因子值序列 [val_t-N, ..., val_t]

        Returns:
            {
              'val': 最新值,
              'mean_5d': 5日均值, 'std_5d': 5日标准差,
              'mean_10d': ..., 'std_10d': ...,
              'mean_20d': ..., 'std_20d': ...,
              'zscore_20d': (val - mean_20d) / std_20d,
              'percentile_20d': 当前值在20日中的分位数,
              'trend_10d': 10日线性斜率,
              'acceleration': 5日趋势 - 10日趋势,
            }
        """
        if not factor_series:
            return {}

        result = {'val': factor_series[-1]}
        n = len(factor_series)

        for w in self.windows:
            if n < w:
                continue
            window = factor_series[-w:]
            result[f'mean_{w}d'] = round(float(np.mean(window)), 4)
            result[f'std_{w}d'] = round(float(np.std(window)), 4)

        # Z-score (20日)
        if n >= 20 and result.get('std_20d', 0) > 0:
            result['zscore_20d'] = round(
                (result['val'] - result['mean_20d']) / result['std_20d'], 3)

        # 分位数 (20日)
        if n >= 20:
            window = factor_series[-20:]
            result['percentile_20d'] = round(
                sum(1 for v in window if v <= result['val']) / 20 * 100, 1)

        # 趋势 (线性回归斜率)
        if n >= 10:
            x = np.arange(10)
            y = np.array(factor_series[-10:])
            slope = np.polyfit(x, y, 1)[0]
            result['trend_10d'] = round(float(slope), 6)

        # 加速度
        if n >= 10:
            x = np.arange(5)
            y5 = np.array(factor_series[-5:])
            y10 = np.array(factor_series[-10:-5])
            slope5 = float(np.polyfit(x, y5, 1)[0]) if len(y5) >= 2 else 0
            slope10 = float(np.polyfit(x, y10, 1)[0]) if len(y10) >= 2 else 0
            result['acceleration'] = round(slope5 - slope10, 6)

        return result

    def compute_panel(self, factor_history: Dict[str, List[float]]) -> Dict[str, Dict[str, float]]:
        """
        对多因子历史数据批量计算滚动特征。

        Args:
            factor_history: {factor_id: [val_1, val_2, ..., val_N]}

        Returns:
            {factor_id: {val, mean_5d, std_5d, zscore_20d, ...}}
        """
        panel = {}
        for fid, series in factor_history.items():
            feat = self.compute(series)
            if feat:
                panel[fid] = feat
        return panel


if __name__ == '__main__':
    main()
