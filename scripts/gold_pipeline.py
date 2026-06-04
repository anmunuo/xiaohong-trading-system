#!/usr/bin/env python3
"""
gold_pipeline.py — Gold 特征层 ETL 引擎
==========================================
从 Silver 层读取清洗数据 → 计算因子面板 → 构建 ML 数据集 → 归档 daily_pool。

原则:
  - Gold 主要读 Silver，启动期补充读 Bronze 历史
  - 所有因子计算逻辑可复现（纯数学，无随机性）
  - 因子面板版本化管理 (v3)
  - ML 数据集带标签 (y = 次日涨跌方向)

用法:
  python3 gold_pipeline.py --date 2026-06-04          # 单日 ETL
  python3 gold_pipeline.py --backfill 30               # 回填近30天
  python3 gold_pipeline.py --build-ml                  # 仅重建 ML 数据集
  python3 gold_pipeline.py --verify                    # 验证可复现性
"""

import sys, os, json, gzip, math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
SILVER_ROOT = BASE_DIR / 'data' / 'silver'
BRONZE_ROOT = BASE_DIR / 'data' / 'bronze'
GOLD_ROOT = BASE_DIR / 'data' / 'gold'
POOL_PATH = SCRIPT_DIR / 'data' / 'daily_pool.json'

# 因子面板 schema 版本
FEATURE_SET_VERSION = 'v3'
MIN_LOOKBACK_DAYS = 60  # 因子计算最少需要的历史天数
ML_MIN_SAMPLES = 100     # ML 数据集最少样本数


# ═══════════════════════════════════════
# 因子注册表 (v3)
# ═══════════════════════════════════════

FACTOR_SPEC = {
    # ── 动量类 (4) ──
    'mom_5d':          {'label': '5日动量(%)',           'class': 'momentum'},
    'mom_20d':         {'label': '20日动量(%)',          'class': 'momentum'},
    'mom_60d':         {'label': '60日动量(%)',          'class': 'momentum'},
    'alpha_idx':       {'label': '20日超额收益(%)',       'class': 'momentum'},

    # ── 波动类 (3) ──
    'atr_14':          {'label': 'ATR波动率(14日,%)',     'class': 'volatility'},
    'vol_20d':         {'label': '20日波动率(%)',         'class': 'volatility'},
    'downside_vol':    {'label': '下行波动率(%)',         'class': 'volatility'},

    # ── 资金类 (3) ──
    'net_flow':        {'label': '主力净流入(万)',        'class': 'flow'},
    'turnover':        {'label': '换手率(%)',             'class': 'flow'},
    'volume_ratio':    {'label': '量比',                  'class': 'flow'},

    # ── 筹码类 (3) ──
    'turnover_zscore': {'label': '换手率Z-score',        'class': 'position'},
    'vol_ratio_trend': {'label': '量比趋势(5/20)',       'class': 'position'},
    'amplitude_5d':    {'label': '5日平均振幅(%)',       'class': 'position'},

    # ── 估值类 (3) ──
    'pe_ttm':          {'label': 'PE_TTM',               'class': 'valuation'},
    'pb':              {'label': 'PB',                   'class': 'valuation'},
    'total_mv_log':    {'label': 'log10(总市值)',         'class': 'valuation'},

    # ── 质量标记 (3) ──
    'is_suspended':    {'label': '停牌',                  'class': 'quality'},
    'is_st':           {'label': 'ST标记',                'class': 'quality'},
    'n_quality_flags': {'label': '质量标记数',            'class': 'quality'},

    # ── 滚动特征 (6) ──
    'close_zscore':    {'label': '收盘价Z-score(20日)',   'class': 'rolling'},
    'volume_zscore':   {'label': '成交量Z-score(20日)',   'class': 'rolling'},
    'pe_percentile':   {'label': 'PE 20日分位数',         'class': 'rolling'},
    'pb_percentile':   {'label': 'PB 20日分位数',         'class': 'rolling'},
    'ma5_deviation':   {'label': 'MA5偏离(%)',           'class': 'rolling'},
    'ma20_deviation':  {'label': 'MA20偏离(%)',          'class': 'rolling'},
}
FEATURE_NAMES = list(FACTOR_SPEC.keys())


# ═══════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════

def _load_silver_daily(date: str) -> Optional[Dict[str, dict]]:
    """加载 Silver 层某日的 stock_daily，返回 {code: row_dict}。"""
    d = datetime.strptime(date, '%Y-%m-%d')
    path = SILVER_ROOT / 'stock_daily' / d.strftime('%Y') / d.strftime('%m') / d.strftime('%d') / 'all.json.gz'
    if not path.exists():
        return None
    rows = json.loads(gzip.decompress(path.read_bytes()))
    return {r['code']: r for r in rows}


def _load_bronze_kline(date: str) -> Optional[Dict[str, dict]]:
    """加载 Bronze 层某日的 daily_kline (Sina)，返回 {code: row_dict}。"""
    d = datetime.strptime(date, '%Y-%m-%d')
    for src in ['sina', 'baostock']:
        path = BRONZE_ROOT / 'daily_kline' / d.strftime('%Y') / d.strftime('%m') / d.strftime('%d') / f'{src}.json.gz'
        if path.exists():
            data = json.loads(gzip.decompress(path.read_bytes()))
            if isinstance(data, dict):
                # v8.7+ 格式: {code: row_dict}，键即股票代码
                return data
            elif isinstance(data, list):
                # 旧格式: [{code, ...}, ...]
                return {r.get('code', r.get('symbol', '')): r for r in data if isinstance(r, dict)}
    return None


def _get_historical_bars(code: str, ref_date: str, max_days: int = 80) -> List[dict]:
    """
    获取某只股票在 ref_date 之前的历史日线数据。
    优先 Silver → 回退 Bronze。
    返回按日期升序的日线列表 [{'date','open','high','low','close','volume','amount','turn'}, ...]。
    """
    ref_dt = datetime.strptime(ref_date, '%Y-%m-%d')
    bars = []
    for i in range(1, max_days + 1):
        dt = ref_dt - timedelta(days=i)
        date_str = dt.strftime('%Y-%m-%d')

        # 优先 Silver
        silver_data = _load_silver_daily(date_str)
        if silver_data and code in silver_data:
            row = silver_data[code]
            bars.append({
                'date': row.get('date', date_str),
                'open': row.get('open', 0),
                'high': row.get('high', 0),
                'low': row.get('low', 0),
                'close': row.get('close', 0),
                'volume': row.get('volume', 0),
                'amount': row.get('amount', 0),
                'turn': row.get('turnover', 0),
            })
            continue

        # 回退 Bronze
        bronze_data = _load_bronze_kline(date_str)
        if bronze_data and code in bronze_data:
            row = bronze_data[code]
            bars.append({
                'date': date_str,
                'open': float(row.get('open', 0)),
                'high': float(row.get('high', 0)),
                'low': float(row.get('low', 0)),
                'close': float(row.get('close', 0)),
                'volume': float(row.get('volume', 0)),
                'amount': float(row.get('amount', 0)),
                'turn': float(row.get('turn', 0) if row.get('turn') else 0),
            })

    bars.reverse()  # 从旧到新
    return bars


# ═══════════════════════════════════════
# 因子计算引擎
# ═══════════════════════════════════════

class FactorBuilder:
    """从 Silver + 历史日线构建因子面板。"""

    def __init__(self, index_returns: List[float] = None):
        self.index_returns = index_returns or []  # 沪深300日收益序列(与bars对齐)

    def compute_factors(self, code: str, silver_row: dict, bars: List[dict]) -> Dict[str, float]:
        """
        对单只股票计算全部因子。

        Args:
            code: 股票代码
            silver_row: Silver 层当日数据 (含资金/估值/状态标记)
            bars: 历史日线 (从旧到新，不含当日——当日用silver_row)
        """
        factors = {}

        # 合并当日和历史
        all_closes = [b['close'] for b in bars] + [silver_row.get('close', 0)]
        all_highs = [b['high'] for b in bars] + [silver_row.get('high', 0)]
        all_lows = [b['low'] for b in bars] + [silver_row.get('low', 0)]
        all_volumes = [b.get('volume', 0) for b in bars] + [silver_row.get('volume', 0)]
        all_turns = [b.get('turn', 0) for b in bars] + [silver_row.get('turnover', 0)]

        # 过滤掉 0 值
        closes = np.array([c for c in all_closes if c > 0], dtype=float)
        highs = np.array(all_highs[-len(closes):], dtype=float)
        lows = np.array(all_lows[-len(closes):], dtype=float)
        volumes = np.array(all_volumes[-len(closes):], dtype=float)
        turns = np.array(all_turns[-len(closes):], dtype=float)

        n = len(closes)
        if n < 1:
            return factors  # 数据不足

        # ── 动量因子 ──
        factors['mom_5d'] = self._pct(closes, -1, -min(6, n)) if n >= 6 else None
        factors['mom_20d'] = self._pct(closes, -1, -min(21, n)) if n >= 21 else None
        factors['mom_60d'] = self._pct(closes, -1, -min(61, n)) if n >= 61 else None

        # alpha: 20日超额收益
        if n >= 21 and len(self.index_returns) >= 20:
            stock_ret = closes[-1] / closes[-21] - 1
            idx_ret = np.prod(1 + np.array(self.index_returns[-20:])) - 1
            factors['alpha_idx'] = round(float((stock_ret - idx_ret) * 100), 2)
        else:
            factors['alpha_idx'] = None

        # ── 波动因子 ──
        factors['atr_14'] = self._atr(highs, lows, closes, 14) if n >= 15 else None
        if n >= 21:
            rets = np.diff(closes[-21:]) / closes[-21:-1]
            factors['vol_20d'] = round(float(np.std(rets) * 100), 2)
            neg = rets[rets < 0]
            factors['downside_vol'] = round(float(np.std(neg) * 100), 2) if len(neg) > 1 else 0.0
        else:
            factors['vol_20d'] = None
            factors['downside_vol'] = None

        # ── 资金因子 (直接取自 Silver) ──
        factors['net_flow'] = silver_row.get('net_flow', 0) or 0
        factors['turnover'] = silver_row.get('turnover', 0) or 0
        factors['volume_ratio'] = silver_row.get('volume_ratio', 0) or 0

        # ── 筹码因子 ──
        factors['turnover_zscore'] = self._zscore(turns, 20) if n >= 21 else None
        factors['vol_ratio_trend'] = self._ratio_mean(volumes, 5, 20) if n >= 21 else None
        factors['amplitude_5d'] = self._mean_amp(highs, lows, closes, 5) if n >= 6 else None

        # ── 估值因子 (直接取自 Silver) ──
        pe = silver_row.get('pe_ttm', 0) or 0
        pb = silver_row.get('pb', 0) or 0
        mv = silver_row.get('total_mv', 0) or 0
        factors['pe_ttm'] = pe if pe > 0 else None
        factors['pb'] = pb if pb > 0 else None
        factors['total_mv_log'] = round(math.log10(mv), 4) if mv > 0 else None

        # ── 质量标记 (直接取自 Silver) ──
        factors['is_suspended'] = 1.0 if silver_row.get('is_suspended', False) else 0.0
        factors['is_st'] = 1.0 if silver_row.get('is_st', False) else 0.0
        factors['n_quality_flags'] = float(len(silver_row.get('quality_flags', []) or []))

        # ── 滚动特征 ──
        if n >= 21:
            factors['close_zscore'] = self._zscore(closes, 20)
            factors['volume_zscore'] = self._zscore(volumes, 20)
            if pe > 0:
                recent_pes = [pe] * min(n, 10)  # 简化：Silver只有当日PE
                factors['pe_percentile'] = 0.5   # 占位，等Silver积累更多历史
            else:
                factors['pe_percentile'] = None
            if pb > 0:
                factors['pb_percentile'] = 0.5   # 占位
            else:
                factors['pb_percentile'] = None
        else:
            factors['close_zscore'] = None
            factors['volume_zscore'] = None
            factors['pe_percentile'] = None
            factors['pb_percentile'] = None

        # MA 偏离
        if n >= 5:
            ma5 = np.mean(closes[-5:])
            factors['ma5_deviation'] = round(float((closes[-1] / ma5 - 1) * 100), 2)
        else:
            factors['ma5_deviation'] = None
        if n >= 20:
            ma20 = np.mean(closes[-20:])
            factors['ma20_deviation'] = round(float((closes[-1] / ma20 - 1) * 100), 2)
        else:
            factors['ma20_deviation'] = None

        return factors

    def _pct(self, arr, idx1, idx2):
        if abs(idx2) >= len(arr) or arr[idx2] <= 0 or arr[idx1] <= 0:
            return None
        return round(float((arr[idx1] / arr[idx2] - 1) * 100), 2)

    def _atr(self, highs, lows, closes, period):
        trs = []
        for i in range(max(1, len(closes) - period), len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i-1])
            lc = abs(lows[i] - closes[i-1])
            trs.append(max(hl, hc, lc))
        atr = np.mean(trs) if trs else 0
        return round(float(atr / closes[-1] * 100), 2) if closes[-1] > 0 else None

    def _zscore(self, arr, window):
        if len(arr) < window:
            return None
        segment = arr[-window:]
        mean = np.mean(segment)
        std = np.std(segment)
        return round(float((arr[-1] - mean) / std), 2) if std > 0 else 0.0

    def _ratio_mean(self, arr, win1, win2):
        if len(arr) < win2:
            return None
        m1 = np.mean(arr[-win1:])
        m2 = np.mean(arr[-win2:])
        return round(float(m1 / m2), 2) if m2 > 0 else 1.0

    def _mean_amp(self, highs, lows, closes, window):
        if len(closes) < window:
            return None
        amps = []
        for i in range(-window, 0):
            if closes[i] > 0:
                amps.append((highs[i] - lows[i]) / closes[i] * 100)
        return round(float(np.mean(amps)), 2) if amps else None


# ═══════════════════════════════════════
# ML 数据集构建
# ═══════════════════════════════════════

class MLDatasetBuilder:
    """从因子面板构建 ML 训练/评估数据集。"""

    def build(self, factor_panels: Dict[str, Dict[str, Dict[str, float]]],
              silver: Dict[str, dict],
              next_silver: Optional[Dict[str, dict]] = None) -> Optional[dict]:
        """
        Args:
            factor_panels: {date: {code: {factor: value}}}
            silver: 当日 Silver 数据
            next_silver: 次日 Silver 数据 (用于标签)

        Returns:
            {'X_train': ndarray, 'y_train': ndarray, 'X_eval': ndarray, 'y_eval': ndarray,
             'train_codes': list, 'eval_codes': list, 'feature_names': list}
        """
        X, y, codes = [], [], []
        feature_names = FEATURE_NAMES.copy()

        # 找到最近有因子面板的日期
        dates = sorted(factor_panels.keys())
        if not dates:
            return None

        # 按日期构建样本：对每个有次日 Silver 数据的日期，用其因子面板作为 X，次日涨跌作为 y
        for i, date in enumerate(dates):
            panel = factor_panels[date]
            # 找次日数据做标签
            dt = datetime.strptime(date, '%Y-%m-%d')
            next_date = (dt + timedelta(days=1)).strftime('%Y-%m-%d')

            # 尝试加载次日因子面板
            next_panel = factor_panels.get(next_date, {})
            if not next_panel:
                # 从 Silver 加载次日数据
                next_silver_day = _load_silver_daily(next_date)
                if not next_silver_day:
                    continue
            else:
                next_silver_day = None

            for code, factors in panel.items():
                # 构建特征向量
                feat = []
                valid = True
                for fn in feature_names:
                    v = factors.get(fn)
                    if v is None:
                        v = 0.0  # NaN 填 0
                    if not isinstance(v, (int, float)):
                        v = 0.0
                    if math.isnan(v) or math.isinf(v):
                        v = 0.0
                    feat.append(v)

                # 标签：次日涨跌 (1=涨, 0=跌)
                if next_silver_day and code in next_silver_day:
                    chg = next_silver_day[code].get('change_pct', 0) or 0
                elif next_panel and code in next_panel:
                    chg = next_panel[code].get('mom_5d', 0) or 0
                else:
                    continue

                label = 1 if chg > 0 else 0
                X.append(feat)
                y.append(label)
                codes.append(f"{date}:{code}")

        if len(X) < ML_MIN_SAMPLES:
            return None

        X = np.array(X, dtype=np.float32)
        y = np.array(y, dtype=np.int32)

        # 按时间切分训练/评估集 (80/20)
        split = int(len(X) * 0.8)
        if split < 2:
            split = max(1, len(X) - 1)

        return {
            'X_train': X[:split],
            'y_train': y[:split],
            'X_eval': X[split:],
            'y_eval': y[split:],
            'train_codes': codes[:split],
            'eval_codes': codes[split:],
            'feature_names': feature_names,
            'n_features': len(feature_names),
            'n_samples': len(X),
            'class_balance': round(float(np.mean(y)), 3),
        }


# ═══════════════════════════════════════
# Gold ETL 主引擎
# ═══════════════════════════════════════

@dataclass
class GoldManifest:
    date: str
    version: str = FEATURE_SET_VERSION
    n_stocks: int = 0
    n_factors: int = len(FEATURE_NAMES)
    n_valid_factors: int = 0
    coverage_pct: float = 0.0          # 因子覆盖率
    ml_dataset_built: bool = False
    ml_n_samples: int = 0
    pool_archived: bool = False
    data_sources: List[str] = field(default_factory=list)  # ['silver', 'bronze']
    warnings: List[str] = field(default_factory=list)
    generated_at: str = ""


class GoldPipeline:
    """Gold 层 ETL 主引擎。"""

    def __init__(self):
        self.factor_builder = FactorBuilder()
        self.ml_builder = MLDatasetBuilder()

    def run(self, date: str) -> Tuple[Optional[Dict[str, Dict[str, float]]], GoldManifest]:
        """
        执行单日 Gold ETL。

        Returns:
            (factor_panel: {code: {factor: value}}, manifest)
        """
        manifest = GoldManifest(date=date, generated_at=datetime.now().isoformat())
        data_sources = []

        # Step 1: 加载当日 Silver
        silver = _load_silver_daily(date)
        if not silver:
            manifest.warnings.append(f'Silver data not found for {date}')
            return None, manifest

        data_sources.append('silver')
        codes = list(silver.keys())
        manifest.n_stocks = len(codes)

        # Step 2: 计算因子面板
        factor_panel = {}
        valid_factors = set()
        n_computed = 0

        for code in codes:
            row = silver[code]
            # 获取历史日线 (从 Bronze 补充)
            bars = _get_historical_bars(code, date, MIN_LOOKBACK_DAYS)
            if bars:
                data_sources.append('bronze_kline')

            # 即使无历史日线，也用当日 Silver 数据构建基础因子
            if not bars:
                bars = [{  # 用当日数据构造最小 bars
                    'date': date,
                    'open': row.get('open', 0),
                    'high': row.get('high', 0),
                    'low': row.get('low', 0),
                    'close': row.get('close', 0),
                    'volume': row.get('volume', 0),
                    'amount': row.get('amount', 0),
                    'turn': row.get('turnover', 0),
                }]

            factors = self.factor_builder.compute_factors(code, row, bars)
            if factors:
                factor_panel[code] = factors
                n_computed += 1
                for k, v in factors.items():
                    if v is not None:
                        valid_factors.add(k)

        manifest.n_valid_factors = len(valid_factors)
        manifest.coverage_pct = round(n_computed / max(manifest.n_stocks, 1) * 100, 1)
        manifest.data_sources = list(set(data_sources))

        if n_computed == 0:
            manifest.warnings.append(f'No factor panel computed for {date}')
        else:
            # Step 3: 写入因子面板
            self._save_factor_panel(date, factor_panel, manifest)

            # Step 4: 构建 ML 数据集 (如果有足够的跨日数据)
            ml_result = self._build_and_save_ml(date, factor_panel, silver)
            if ml_result:
                manifest.ml_dataset_built = True
                manifest.ml_n_samples = ml_result.get('n_samples', 0)

        # Step 5: 归档 daily_pool (总是尝试)
        manifest.pool_archived = self._archive_daily_pool(date)

        return factor_panel, manifest

    def _save_factor_panel(self, date: str, panel: Dict, manifest: GoldManifest):
        """写入因子面板到 Parquet。若无 pandas 则写 JSON。"""
        d = datetime.strptime(date, '%Y-%m-%d')
        dir_path = GOLD_ROOT / 'factor_panel' / d.strftime('%Y') / d.strftime('%m') / d.strftime('%d')
        dir_path.mkdir(parents=True, exist_ok=True)

        # 尝试 Parquet
        try:
            import pandas as pd
            rows = []
            for code, factors in panel.items():
                row = {'code': code, 'date': date, **factors}
                rows.append(row)
            df = pd.DataFrame(rows)
            df.to_parquet(dir_path / f'{FEATURE_SET_VERSION}.parquet', index=False)
            print(f'[Gold] Factor panel: {len(rows)} stocks → {dir_path}/{FEATURE_SET_VERSION}.parquet')
            return
        except ImportError:
            pass

        # Fallback: gzip JSON
        output = []
        for code, factors in panel.items():
            output.append({'code': code, 'date': date, 'factors': factors})
        path = dir_path / f'{FEATURE_SET_VERSION}.json.gz'
        path.write_bytes(gzip.compress(json.dumps(output, ensure_ascii=False).encode()))
        print(f'[Gold] Factor panel: {len(output)} stocks → {path} (JSON fallback)')

    def _build_and_save_ml(self, date: str, today_panel: Dict, silver: Dict) -> Optional[dict]:
        """构建 ML 数据集。需要多日因子面板才能做训练集。"""
        # 加载近 90 天的因子面板
        all_panels = {}
        dt = datetime.strptime(date, '%Y-%m-%d')

        for i in range(90):
            d = (dt - timedelta(days=i)).strftime('%Y-%m-%d')
            # 优先从磁盘加载已保存的面板
            panel = self._load_factor_panel_from_disk(d)
            if panel:
                all_panels[d] = panel

        # 加入今日面板
        all_panels[date] = today_panel

        if len(all_panels) < 2:
            return None

        # 构建数据集
        result = self.ml_builder.build(all_panels, silver)
        if not result:
            return None

        # 保存
        dir_path = GOLD_ROOT / 'ml_datasets'
        dir_path.mkdir(parents=True, exist_ok=True)
        safe_date = date.replace('-', '')
        train_path = dir_path / f'train_{safe_date}_{FEATURE_SET_VERSION}.npz'
        eval_path = dir_path / f'eval_{safe_date}_{FEATURE_SET_VERSION}.npz'

        np.savez_compressed(train_path,
            X=result['X_train'], y=result['y_train'],
            codes=np.array(result['train_codes'], dtype='S'))
        np.savez_compressed(eval_path,
            X=result['X_eval'], y=result['y_eval'],
            codes=np.array(result['eval_codes'], dtype='S'))

        # 保存元数据
        meta = {
            'version': FEATURE_SET_VERSION,
            'date': date,
            'n_samples': result['n_samples'],
            'n_features': result['n_features'],
            'feature_names': result['feature_names'],
            'class_balance': result['class_balance'],
            'train_samples': len(result['train_codes']),
            'eval_samples': len(result['eval_codes']),
            'generated_at': datetime.now().isoformat(),
        }
        meta_path = dir_path / f'meta_{safe_date}_{FEATURE_SET_VERSION}.json'
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

        print(f'[Gold] ML dataset: {result["n_samples"]} samples ({meta["train_samples"]} train / {meta["eval_samples"]} eval)')
        return result

    def _load_factor_panel_from_disk(self, date: str) -> Optional[Dict[str, Dict[str, float]]]:
        """从磁盘加载已保存的因子面板。"""
        d = datetime.strptime(date, '%Y-%m-%d')
        base = GOLD_ROOT / 'factor_panel' / d.strftime('%Y') / d.strftime('%m') / d.strftime('%d')

        # 优先 Parquet
        pq_path = base / f'{FEATURE_SET_VERSION}.parquet'
        if pq_path.exists():
            try:
                import pandas as pd
                df = pd.read_parquet(pq_path)
                panel = {}
                for _, row in df.iterrows():
                    code = row['code']
                    factors = {}
                    for fn in FEATURE_NAMES:
                        if fn in row:
                            v = row[fn]
                            factors[fn] = v if not (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else None
                    panel[code] = factors
                return panel
            except Exception:
                pass

        # Fallback JSON
        json_path = base / f'{FEATURE_SET_VERSION}.json.gz'
        if json_path.exists():
            rows = json.loads(gzip.decompress(json_path.read_bytes()))
            panel = {}
            for item in rows:
                code = item['code']
                factors = item.get('factors', {})
                panel[code] = factors
            return panel

        return None

    def _archive_daily_pool(self, date: str) -> bool:
        """归档 daily_pool.json 到 Gold 层。"""
        if not POOL_PATH.exists():
            return False

        d = datetime.strptime(date, '%Y-%m-%d')
        dir_path = GOLD_ROOT / 'daily_pool' / d.strftime('%Y') / d.strftime('%m')
        dir_path.mkdir(parents=True, exist_ok=True)

        dest = dir_path / f'{d.strftime("%d")}.json'
        try:
            pool_data = json.loads(POOL_PATH.read_text())
            dest.write_text(json.dumps(pool_data, ensure_ascii=False, indent=2))
            print(f'[Gold] Daily pool archived: {dest}')
            return True
        except Exception as e:
            print(f'[Gold] Failed to archive daily_pool: {e}')
            return False

    def _save_manifest(self, date: str, manifest: GoldManifest):
        """保存 Gold manifest。"""
        d = datetime.strptime(date, '%Y-%m-%d')
        dir_path = GOLD_ROOT / '_meta'
        dir_path.mkdir(parents=True, exist_ok=True)
        path = dir_path / f'gold_manifest_{date}.json'
        path.write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2))

    def backfill(self, days: int = 30):
        """回填最近 N 天。"""
        today = datetime.now()
        for i in range(days):
            date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            panel, manifest = self.run(date)
            if manifest.n_stocks == 0:
                print(f'[Gold] {date}: 跳过 (无 Silver 数据)')
            if manifest.warnings:
                for w in manifest.warnings:
                    print(f'  ⚠️ {w}')

    def verify_reproducibility(self, date: str) -> bool:
        """验证可复现性：跑两次比对哈希。"""
        import hashlib

        panel1, _ = self.run(date)
        if not panel1:
            print(f'[Verify] 无法运行 {date}')
            return False

        panel2, _ = self.run(date)

        # 比较因子值
        codes1 = set(panel1.keys())
        codes2 = set(panel2.keys())
        if codes1 != codes2:
            print(f'[Verify] 代码集不一致: {len(codes1)} vs {len(codes2)}')
            return False

        diffs = 0
        for code in codes1:
            f1 = panel1[code]
            f2 = panel2[code]
            for k in f1:
                v1 = f1.get(k)
                v2 = f2.get(k)
                if v1 != v2:
                    if v1 is None and v2 is None:
                        continue
                    if isinstance(v1, float) and isinstance(v2, float):
                        if abs(v1 - v2) > 0.001:
                            diffs += 1
                    else:
                        diffs += 1

        if diffs > 0:
            print(f'[Verify] ❌ 不可复现: {diffs} 处差异')
            return False
        print(f'[Verify] ✅ 可复现: {len(codes1)} 只股票完全一致')
        return True


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description='Gold 特征层 ETL')
    ap.add_argument('--date', type=str, help='执行单日 ETL (YYYY-MM-DD)')
    ap.add_argument('--backfill', type=int, default=0, help='回填最近 N 天')
    ap.add_argument('--build-ml', action='store_true', help='仅重建 ML 数据集')
    ap.add_argument('--verify', action='store_true', help='验证可复现性')
    ap.add_argument('--date-range', type=str, help='日期范围 START:END')
    args = ap.parse_args()

    pipeline = GoldPipeline()

    if args.verify:
        date = args.date or datetime.now().strftime('%Y-%m-%d')
        ok = pipeline.verify_reproducibility(date)
        sys.exit(0 if ok else 1)

    if args.date_range:
        start_str, end_str = args.date_range.split(':')
        start = datetime.strptime(start_str, '%Y-%m-%d')
        end = datetime.strptime(end_str, '%Y-%m-%d')
        d = start
        while d <= end:
            date = d.strftime('%Y-%m-%d')
            panel, manifest = pipeline.run(date)
            if manifest.n_stocks > 0:
                pipeline._save_manifest(date, manifest)
            else:
                print(f'[Gold] {date}: 跳过 (无 Silver)')
            d += timedelta(days=1)
        return

    if args.backfill:
        pipeline.backfill(args.backfill)
        return

    date = args.date or datetime.now().strftime('%Y-%m-%d')
    panel, manifest = pipeline.run(date)
    if manifest.n_stocks > 0:
        pipeline._save_manifest(date, manifest)
    else:
        print(f'[Gold] {date}: 无数据，跳过')
        sys.exit(0)

    # 输出摘要
    print(f'\n📊 Gold ETL · {date}')
    print(f'  股票: {manifest.n_stocks} 只')
    print(f'  因子: {manifest.n_valid_factors}/{manifest.n_factors} 类有效')
    print(f'  覆盖率: {manifest.coverage_pct}%')
    print(f'  ML: {"✅" if manifest.ml_dataset_built else "❌ 数据不足"}')
    print(f'  Pool: {"✅" if manifest.pool_archived else "❌"}')
    if manifest.warnings:
        for w in manifest.warnings:
            print(f'  ⚠️ {w}')


if __name__ == '__main__':
    main()
