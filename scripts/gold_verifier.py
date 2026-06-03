#!/usr/bin/env python3
"""
gold_verifier.py — Gold 层完整性验证器
==========================================
验证因子面板、ML 数据集、daily_pool 归档的完整性和可复现性。

用法:
  python3 gold_verifier.py --date 2026-06-04     # 验证指定日期
  python3 gold_verifier.py --all                  # 验证所有日期
  python3 gold_verifier.py --json                 # JSON 输出模式
"""

import sys, os, json, gzip, math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
GOLD_ROOT = BASE_DIR / 'data' / 'gold'
SILVER_ROOT = BASE_DIR / 'data' / 'silver'
POOL_PATH = SCRIPT_DIR / 'data' / 'daily_pool.json'

FEATURE_SET_VERSION = 'v3'
EXPECTED_FACTORS = [
    'mom_5d', 'mom_20d', 'mom_60d', 'alpha_idx',
    'atr_14', 'vol_20d', 'downside_vol',
    'net_flow', 'turnover', 'volume_ratio',
    'turnover_zscore', 'vol_ratio_trend', 'amplitude_5d',
    'pe_ttm', 'pb', 'total_mv_log',
    'is_suspended', 'is_st', 'n_quality_flags',
    'close_zscore', 'volume_zscore', 'pe_percentile', 'pb_percentile',
    'ma5_deviation', 'ma20_deviation',
]


@dataclass
class GoldVerifyResult:
    date: str
    status: str = "ok"           # ok / degraded / missing
    factor_panel_exists: bool = False
    factor_panel_stocks: int = 0
    factor_panel_factors: int = 0
    factor_coverage_pct: float = 0.0
    ml_train_exists: bool = False
    ml_eval_exists: bool = False
    ml_n_samples: int = 0
    pool_archived: bool = False
    pool_stocks: int = 0
    manifest_exists: bool = False
    issues: List[str] = field(default_factory=list)
    silver_comparison_ok: bool = False


def _load_panel(date: str) -> Optional[Dict]:
    """加载因子面板。"""
    d = datetime.strptime(date, '%Y-%m-%d')
    base = GOLD_ROOT / 'factor_panel' / d.strftime('%Y') / d.strftime('%m') / d.strftime('%d')

    # Parquet
    pq = base / f'{FEATURE_SET_VERSION}.parquet'
    if pq.exists():
        try:
            import pandas as pd
            df = pd.read_parquet(pq)
            panel = {}
            for _, row in df.iterrows():
                code = row['code']
                factors = {k: row.get(k) for k in EXPECTED_FACTORS if k in row}
                panel[code] = factors
            return panel
        except Exception:
            pass

    # JSON
    jz = base / f'{FEATURE_SET_VERSION}.json.gz'
    if jz.exists():
        rows = json.loads(gzip.decompress(jz.read_bytes()))
        panel = {}
        for item in rows:
            code = item['code']
            panel[code] = item.get('factors', {})
        return panel
    return None


def verify_date(date: str) -> GoldVerifyResult:
    """验证指定日期的 Gold 层数据。"""
    r = GoldVerifyResult(date=date)

    # 1. 因子面板
    panel = _load_panel(date)
    if panel:
        r.factor_panel_exists = True
        r.factor_panel_stocks = len(panel)

        # 统计因子覆盖率
        total_factors = 0
        found_factors = set()
        for code, factors in panel.items():
            for k, v in factors.items():
                if v is not None and not (isinstance(v, float) and math.isnan(v)):
                    found_factors.add(k)
                    total_factors += 1

        r.factor_panel_factors = len(found_factors)
        avg_factors = total_factors / max(len(panel), 1)
        r.factor_coverage_pct = round(avg_factors / len(EXPECTED_FACTORS) * 100, 1) if EXPECTED_FACTORS else 0

        # 检查缺失的因子
        missing = set(EXPECTED_FACTORS) - found_factors
        if missing:
            r.issues.append(f'缺失因子: {",".join(sorted(missing))}')
        if r.factor_coverage_pct < 50:
            r.status = 'degraded'
            r.issues.append(f'因子覆盖率过低: {r.factor_coverage_pct}%')

        # 与 Silver 对比
        silver = _load_silver_daily(date)
        if silver:
            silver_codes = set(silver.keys())
            gold_codes = set(panel.keys())
            overlap = silver_codes & gold_codes
            mismatch = silver_codes - gold_codes
            r.silver_comparison_ok = len(mismatch) == 0
            if mismatch:
                r.issues.append(f'Silver 有但 Gold 缺失: {len(mismatch)}只 ({",".join(list(mismatch)[:5])}...)')
    else:
        r.status = 'missing'
        r.issues.append('因子面板不存在')

    # 2. ML 数据集
    safe_date = date.replace('-', '')
    train_path = GOLD_ROOT / 'ml_datasets' / f'train_{safe_date}_{FEATURE_SET_VERSION}.npz'
    eval_path = GOLD_ROOT / 'ml_datasets' / f'eval_{safe_date}_{FEATURE_SET_VERSION}.npz'

    if train_path.exists():
        r.ml_train_exists = True
        try:
            data = np.load(train_path)
            r.ml_n_samples = len(data['y'])
        except Exception as e:
            r.issues.append(f'ML train 读取失败: {e}')
    if eval_path.exists():
        r.ml_eval_exists = True

    # 3. daily_pool 归档
    d = datetime.strptime(date, '%Y-%m-%d')
    pool_path = GOLD_ROOT / 'daily_pool' / d.strftime('%Y') / d.strftime('%m') / f'{d.strftime("%d")}.json'
    if pool_path.exists():
        r.pool_archived = True
        try:
            pool = json.loads(pool_path.read_text())
            r.pool_stocks = len(pool.get('stocks', pool if isinstance(pool, list) else []))
        except Exception as e:
            r.issues.append(f'Pool JSON 读取失败: {e}')
    else:
        # 也检查源文件是否存在
        if POOL_PATH.exists():
            r.issues.append('daily_pool.json 存在但未归档到 Gold')

    # 4. Manifest
    manifest_path = GOLD_ROOT / '_meta' / f'gold_manifest_{date}.json'
    r.manifest_exists = manifest_path.exists()

    # 综合判定
    if r.status == 'missing':
        pass  # 保持 missing
    elif r.issues:
        r.status = 'degraded'

    return r


def verify_all() -> List[GoldVerifyResult]:
    """验证所有有数据的日期。"""
    results = []
    panel_root = GOLD_ROOT / 'factor_panel'
    if not panel_root.exists():
        return results

    for year_dir in sorted(panel_root.iterdir()):
        if not year_dir.is_dir():
            continue
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir():
                continue
            for day_dir in sorted(month_dir.iterdir()):
                if not day_dir.is_dir():
                    continue
                date = f'{year_dir.name}-{month_dir.name}-{day_dir.name}'
                results.append(verify_date(date))
    return results


def _load_silver_daily(date: str) -> Optional[Dict]:
    """加载 Silver stock_daily。"""
    d = datetime.strptime(date, '%Y-%m-%d')
    path = SILVER_ROOT / 'stock_daily' / d.strftime('%Y') / d.strftime('%m') / d.strftime('%d') / 'all.json.gz'
    if not path.exists():
        return None
    rows = json.loads(gzip.decompress(path.read_bytes()))
    return {r['code']: r for r in rows}


def main():
    import argparse
    ap = argparse.ArgumentParser(description='Gold 层验证器')
    ap.add_argument('--date', type=str, help='验证指定日期')
    ap.add_argument('--all', action='store_true', help='验证所有日期')
    ap.add_argument('--json', action='store_true', help='JSON 输出')
    args = ap.parse_args()

    if args.all:
        results = verify_all()
    elif args.date:
        results = [verify_date(args.date)]
    else:
        today = datetime.now().strftime('%Y-%m-%d')
        results = [verify_date(today)]

    if args.json:
        output = []
        for r in results:
            output.append(asdict(r))
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return

    # 文本输出
    for r in results:
        icon = {'ok': '✅', 'degraded': '⚠️', 'missing': '❌'}.get(r.status, '❓')
        print(f'{icon} Gold {r.date} [{r.status}]')
        if r.factor_panel_exists:
            print(f'   因子面板: {r.factor_panel_stocks}只 × {r.factor_panel_factors}因子 (覆盖{r.factor_coverage_pct}%)')
        else:
            print(f'   因子面板: ❌ 不存在')
        print(f'   ML训练集: {"✅" if r.ml_train_exists else "❌"} | 评估集: {"✅" if r.ml_eval_exists else "❌"} | 样本: {r.ml_n_samples}')
        print(f'   Pool归档: {"✅" if r.pool_archived else "❌"} | Manifest: {"✅" if r.manifest_exists else "❌"}')
        print(f'   Silver对齐: {"✅" if r.silver_comparison_ok else "⚠️"}')
        if r.issues:
            for issue in r.issues:
                print(f'   ⚡ {issue}')

    # 退出码
    has_error = any(r.status == 'missing' for r in results)
    sys.exit(1 if has_error else 0)


if __name__ == '__main__':
    main()
