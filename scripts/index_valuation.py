#!/usr/bin/env python3
"""
index_valuation.py — 指数估值中枢 v1.0
=====================================
获取主要指数当前PE及历史分位数，输出估值信号。

用法: python3 index_valuation.py

数据源: tushare index_dailybasic (月度PE)
覆盖: 上证50(000016) / 沪深300(000300) / 中证500(000905) / 创业板(399006)
"""

import json, os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
VALUATION_PATH = DATA_DIR / "index_valuation.json"

# 指数定义
INDICES = {
    "000016.SH": "上证50",
    "000300.SH": "沪深300",
    "000905.SH": "中证500",
    "399006.SZ": "创业板指",
}

# 历史分位数阈值（基于A股长期特征）
PERCENTILE_THRESHOLDS = {
    "cheap": 25,      # <25% = 低估
    "fair": 50,       # 25-50% = 合理偏低
    "neutral": 75,    # 50-75% = 合理偏高
    "expensive": 100, # >75% = 偏贵
}


def _get_tushare_token() -> str:
    token = os.environ.get('TUSHARE_TOKEN', '')
    if not token:
        env_path = SCRIPT_DIR.parent / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    if line.startswith('TUSHARE_TOKEN='):
                        token = line.split('=', 1)[1].strip()
    return token


def fetch_valuation() -> dict:
    """获取指数估值数据"""
    token = _get_tushare_token()
    if not token:
        return {"error": "TUSHARE_TOKEN 未配置", "indices": {}}

    import tushare as ts
    pro = ts.pro_api(token)
    result = {"generated_at": datetime.now().isoformat(), "indices": {}, "summary": {}}

    for ts_code, name in INDICES.items():
        try:
            # 当前 PE
            today_df = pro.index_dailybasic(trade_date=datetime.now().strftime('%Y%m%d'),
                                            fields='ts_code,pe_ttm')
            # 如果当天无数据，用昨天
            if today_df is None or today_df.empty:
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y%m%d')
                today_df = pro.index_dailybasic(trade_date=yesterday, fields='ts_code,pe_ttm')

            current_pe = None
            if today_df is not None and not today_df.empty:
                row = today_df[today_df['ts_code'] == ts_code]
                if not row.empty:
                    current_pe = float(row.iloc[0]['pe_ttm'])

            if current_pe is None or current_pe <= 0:
                continue

            # 3年月度PE历史
            start_date = (datetime.now() - timedelta(days=1095)).strftime('%Y%m%d')
            end_date = datetime.now().strftime('%Y%m%d')
            hist_df = pro.index_dailybasic(ts_code=ts_code, start_date=start_date,
                                           end_date=end_date, fields='trade_date,pe_ttm')

            pe_values = []
            if hist_df is not None and not hist_df.empty:
                pe_values = sorted([float(v) for v in hist_df['pe_ttm'].dropna() if v > 0])

            # 计算分位数
            percentile = 50
            if pe_values and current_pe > 0:
                below = sum(1 for v in pe_values if v <= current_pe)
                percentile = round(below / len(pe_values) * 100, 1)

            # 估值信号
            if percentile < PERCENTILE_THRESHOLDS["cheap"]:
                signal = "🟢 低估"
            elif percentile < PERCENTILE_THRESHOLDS["fair"]:
                signal = "🟡 合理偏低"
            elif percentile < PERCENTILE_THRESHOLDS["neutral"]:
                signal = "🟠 合理偏高"
            else:
                signal = "🔴 偏贵"

            result["indices"][ts_code] = {
                "name": name,
                "pe_ttm": round(current_pe, 1),
                "percentile": percentile,
                "signal": signal,
                "history_points": len(pe_values),
            }
        except Exception as e:
            result["indices"][ts_code] = {"name": name, "error": str(e)[:100]}

    # 综合判断
    signals = [v.get("signal", "") for v in result["indices"].values() if "signal" in v]
    greens = sum(1 for s in signals if "低估" in s)
    reds = sum(1 for s in signals if "偏贵" in s)
    pe_vals = [v.get("pe_ttm", 0) for v in result["indices"].values() if v.get("pe_ttm")]
    avg_pe = round(sum(pe_vals) / len(pe_vals), 1) if pe_vals else 0
    avg_pct = round(sum(v.get("percentile", 50) for v in result["indices"].values()
                        if "percentile" in v) / max(len(signals), 1), 1)

    if greens >= 3:
        position_signal = "可重仓（整体低估）"
    elif greens >= 2:
        position_signal = "中等仓位（部分低估）"
    elif reds >= 3:
        position_signal = "轻仓/防御（整体偏贵）"
    elif reds >= 2:
        position_signal = "中等偏低仓位（偏贵信号增多）"
    else:
        position_signal = "中性仓位"

    result["summary"] = {
        "avg_pe_ttm": avg_pe,
        "avg_percentile": avg_pct,
        "undervalued_count": greens,
        "overvalued_count": reds,
        "position_signal": position_signal,
    }

    # 持久化
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(VALUATION_PATH, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    return result


def print_valuation(result: dict):
    """美化输出"""
    print(f"\n{'='*55}")
    print(f"  📈 指数估值中枢  {result.get('generated_at','')[:19]}")
    print(f"  {'='*55}")
    for code, v in result.get("indices", {}).items():
        if "error" in v:
            print(f"  {code:12s} {v['name']:6s} ❌ {v['error']}")
        else:
            print(f"  {code:12s} {v['name']:6s} PE={v['pe_ttm']:5.1f}  分位={v['percentile']:5.1f}%  {v['signal']}")
    s = result.get("summary", {})
    print(f"  {'='*55}")
    print(f"  综合: PE={s.get('avg_pe_ttm',0)}  分位={s.get('avg_percentile',0)}%")
    print(f"  低估: {s.get('undervalued_count',0)}个  偏贵: {s.get('overvalued_count',0)}个")
    print(f"  仓位建议: {s.get('position_signal','?')}")
    print()


if __name__ == "__main__":
    result = fetch_valuation()
    print_valuation(result)
