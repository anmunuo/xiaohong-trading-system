#!/usr/bin/env python3
"""
target_pool.py — 目标池管理模块 v1.0
====================================
盘中实时决策链的终端：从推荐池中选出当日最优 3 只可操作标的。

功能:
  select_target_pool(daily_pool)  → 初始选池 (09:30)
  update_target_pool(new_stock)   → 盘中动态更新 (高分替换低分)
  load_target_pool()              → 读取当前目标池
  get_target_pool_summary()       → 狙击手消费接口

数据流:
  侦察兵发现 → 三级认证门通过 → daily_pool
                                    │
  09:30 ────────────────────────────┤
        select_target_pool() ← 综合排序: 议会偏多×0.35 + 五因子×0.35 + 基本面×0.15 + 流动性×0.15
                                    │
  盘中 ─────────────────────────────┤
        update_target_pool() ← 新标的 > 池内最低分 → 替换
                                    │
  狙击手 ← get_target_pool_summary() ← 量比 + 分时K线 + 技术信号
"""

import json, os, sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
TARGET_POOL_PATH = DATA_DIR / "target_pool.json"

# ═══════════════════════════════════════════
# 核心数据结构
# ═══════════════════════════════════════════

# target_pool.json schema:
# {
#   "date": "20260606",
#   "selected_at": "09:30",
#   "updated_at": "11:00",
#   "capacity": 3,
#   "stocks": [
#     {
#       "code": "300750",
#       "name": "宁德时代",
#       "sector": "新能源",
#       "score": 78.5,
#       "parliament": {"bias": "偏多", "confidence": 0.72, "bull_signals": 3, "bear_signals": 1},
#       "factor_scores": {"event": 65, "fund": 82, "sentiment": 70, "technical": 75, "research": 60},
#       "fundamental": {"pe": 28.5, "pb": 4.2, "roe": 18.3, "debt_ratio": 55.2},
#       "entry_ready": false,
#       "entry_signal": null,
#       "added_at": "09:30",
#       "source": "recommender"
#     }
#   ],
#   "history": [...]    ← 当日被替换出池的记录
# }


def load_target_pool() -> Dict:
    """读取当前目标池"""
    if not TARGET_POOL_PATH.exists():
        return _empty_pool()
    try:
        with open(TARGET_POOL_PATH) as f:
            return json.load(f)
    except Exception:
        return _empty_pool()


def save_target_pool(pool: Dict):
    """持久化目标池"""
    TARGET_POOL_PATH.parent.mkdir(parents=True, exist_ok=True)
    pool["updated_at"] = datetime.now().strftime("%H:%M")
    with open(TARGET_POOL_PATH, "w") as f:
        json.dump(pool, f, ensure_ascii=False, indent=2)


def _empty_pool() -> Dict:
    return {
        "date": datetime.now().strftime("%Y%m%d"),
        "selected_at": None,
        "updated_at": None,
        "capacity": 3,
        "stocks": [],
        "history": [],
    }


# ═══════════════════════════════════════════
# 选池逻辑
# ═══════════════════════════════════════════

def select_target_pool(daily_pool_path: str = None, force: bool = False) -> Dict:
    """
    从 daily_pool.json 中选出 Top 3 当日可操作标的。

    评分权重:
      · 议会偏多置信度 × 0.35
      · 五因子综合评分   × 0.35
      · 基本面健康度     × 0.15  (PE>0+ROE+负债率)
      · 流动性          × 0.15  (涨跌幅+量比)

    只在 09:30 后首次调用时选池，之后调用返回已有池 (除非 force=True)。
    """
    pool = load_target_pool()

    # 同一天已选池且非强制 → 返回已有池
    today = datetime.now().strftime("%Y%m%d")
    if pool["date"] == today and pool["stocks"] and not force:
        return pool

    # 加载 daily_pool
    if daily_pool_path is None:
        daily_pool_path = str(DATA_DIR / "daily_pool.json")
    dp_path = Path(daily_pool_path)
    if not dp_path.exists():
        pool["selected_at"] = datetime.now().strftime("%H:%M")
        save_target_pool(pool)
        return pool

    try:
        with open(dp_path) as f:
            dp = json.load(f)
    except Exception:
        save_target_pool(pool)
        return pool

    recs = dp.get("recommendations", [])
    if not recs:
        save_target_pool(pool)
        return pool

    # 逐只评分
    scored = []
    for r in recs:
        s = _score_for_target(r)
        if s["score"] > 0:
            scored.append(s)

    # 按综合分降序 → 取前 3
    scored.sort(key=lambda x: x["score"], reverse=True)
    selected = scored[:3]

    pool["date"] = today
    pool["selected_at"] = datetime.now().strftime("%H:%M")
    pool["stocks"] = selected

    save_target_pool(pool)
    return pool


def _score_for_target(rec: Dict) -> Dict:
    """单只标的综合评分 → 目标池候选"""
    try:
        code = str(rec.get("code", ""))
        name = str(rec.get("name", ""))
        sector = rec.get("sector", "综合")

        # 1. 议会评分 (35%)
        parliament = rec.get("parliament", rec.get("researcher_analysis", {}).get("cross_analysis", {}))
        if not parliament or not parliament.get("bias"):
            parliament_score = 40  # 无议会数据 → 中等偏低
        else:
            confidence = parliament.get("confidence", 0.5)
            if parliament["bias"] == "偏多":
                parliament_score = min(100, 60 + confidence * 40)
            elif "偏多" in str(parliament["bias"]):
                parliament_score = min(90, 50 + confidence * 40)
            elif parliament["bias"] == "中性":
                parliament_score = 50
            else:
                parliament_score = max(10, 30 - confidence * 20)

        # 2. 五因子评分 (35%)
        factor_scores = rec.get("factor_scores", {})
        total_score = rec.get("total_score", 50)
        factor_score = min(100, max(0, total_score))

        # 3. 基本面 (15%)
        fin = rec.get("fundamental", rec.get("researcher_analysis", {}).get("fundamental", {}))
        pe = fin.get("pe", rec.get("pe", 0))
        pb = fin.get("pb", rec.get("pb", 0))
        roe = fin.get("roe", 0)
        debt = fin.get("debt_ratio", fin.get("debt_to_assets", 50))

        fund_score = 50
        if pe > 0 and pe < 50:
            fund_score += 15
        elif pe > 0 and pe < 100:
            fund_score += 8
        if pb > 0 and pb < 5:
            fund_score += 10
        if roe > 10:
            fund_score += 15
        elif roe > 5:
            fund_score += 8
        if debt < 60:
            fund_score += 10
        fund_score = min(100, fund_score)

        # 4. 流动性 (15%)
        change_pct = rec.get("change_pct", 0)
        vol_ratio = rec.get("vol_ratio", rec.get("volume_ratio", 1.0))

        liq_score = 50
        if 1 < change_pct < 8:
            liq_score += 20
        elif 0 < change_pct <= 1:
            liq_score += 10
        if vol_ratio > 1.5:
            liq_score += 15
        elif vol_ratio > 1.0:
            liq_score += 8
        if change_pct < -3:
            liq_score -= 15
        liq_score = min(100, max(10, liq_score))

        # 综合
        composite = round(
            parliament_score * 0.35 +
            factor_score * 0.35 +
            fund_score * 0.15 +
            liq_score * 0.15, 1
        )

        return {
            "code": code,
            "name": name,
            "sector": sector,
            "score": composite,
            "parliament": {
                "bias": parliament.get("bias", "未知"),
                "confidence": parliament.get("confidence", 0),
                "bull_signals": parliament.get("bull_signals", 0),
                "bear_signals": parliament.get("bear_signals", 0),
            },
            "factor_scores": factor_scores,
            "fundamental": {
                "pe": pe, "pb": pb, "roe": roe, "debt_ratio": debt,
            },
            "entry_ready": False,
            "entry_signal": None,
            "added_at": datetime.now().strftime("%H:%M"),
            "source": rec.get("source", "recommender"),
        }
    except Exception as e:
        return {"code": rec.get("code", "?"), "name": rec.get("name", "?"),
                "score": 0, "error": str(e)[:80]}


def update_target_pool(new_stock: Dict) -> Dict:
    """
    🆕 盘中动态更新：新标的如果评分高于池内最低分 → 替换。

    new_stock 必须包含:
      {code, name, score, parliament, factor_scores, fundamental}
    """
    pool = load_target_pool()
    today = datetime.now().strftime("%Y%m%d")

    if pool["date"] != today:
        pool = _empty_pool()

    stock_code = new_stock.get("code", "")
    stock_score = new_stock.get("score", 0)

    if not stock_code or stock_score <= 0:
        return pool

    stocks = pool.get("stocks", [])

    # 已在池中？更新评分
    for s in stocks:
        if s["code"] == stock_code:
            if stock_score > s["score"]:
                s.update(new_stock)
                s["updated_at"] = datetime.now().strftime("%H:%M")
                save_target_pool(pool)
            return pool

    # 池未满 → 直接加入
    if len(stocks) < pool["capacity"]:
        new_stock["added_at"] = datetime.now().strftime("%H:%M")
        stocks.append(new_stock)
        save_target_pool(pool)
        return pool

    # 池已满 → 与最低分比较
    min_idx = min(range(len(stocks)), key=lambda i: stocks[i]["score"])
    if stock_score > stocks[min_idx]["score"]:
        replaced = stocks[min_idx]
        pool.setdefault("history", []).append({
            "code": replaced["code"], "name": replaced["name"],
            "score": replaced["score"],
            "replaced_at": datetime.now().strftime("%H:%M"),
            "replaced_by": stock_code,
        })
        new_stock["added_at"] = datetime.now().strftime("%H:%M")
        stocks[min_idx] = new_stock
        save_target_pool(pool)

    return pool


def get_target_pool_summary() -> Dict:
    """
    狙击手消费接口。
    返回当前目标池 + 每只标的的 entry_signal 状态。
    """
    pool = load_target_pool()

    for s in pool.get("stocks", []):
        if "entry_signal" not in s:
            s["entry_signal"] = None
        if "entry_ready" not in s:
            s["entry_ready"] = False

    return pool


def mark_entry_signal(code: str, signal: Dict):
    """狙击手调用：标记某只标的的开仓信号"""
    pool = load_target_pool()
    for s in pool.get("stocks", []):
        if s["code"] == code:
            s["entry_signal"] = signal
            s["entry_ready"] = signal.get("ready", False)
            s["entry_updated_at"] = datetime.now().strftime("%H:%M:%S")
            break
    save_target_pool(pool)


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="目标池管理")
    parser.add_argument("--select", action="store_true", help="从 daily_pool 选池")
    parser.add_argument("--show", action="store_true", help="显示当前目标池")
    parser.add_argument("--force", action="store_true", help="强制重新选池")
    args = parser.parse_args()

    if args.select:
        pool = select_target_pool(force=args.force)
        print(f"🎯 目标池 ({pool['date']} {pool['selected_at']})")
        for i, s in enumerate(pool["stocks"], 1):
            p = s.get("parliament", {})
            print(f"  {i}. {s['code']} {s['name']:8s}  "
                  f"评分:{s['score']:.1f}  "
                  f"议会:{p.get('bias','?')}({p.get('confidence',0):.0%})  "
                  f"来源:{s.get('source','?')}")
        print(f"  --- 共 {len(pool['stocks'])} 只 ---")

    elif args.show:
        pool = load_target_pool()
        if not pool["stocks"]:
            print("🎯 目标池为空")
        else:
            print(f"🎯 目标池 ({pool['date']} 选于{pool.get('selected_at','?')}  "
                  f"更新于{pool.get('updated_at','?')})")
            for i, s in enumerate(pool["stocks"], 1):
                p = s.get("parliament", {})
                f = s.get("fundamental", {})
                es = s.get("entry_signal", {})
                es_str = f"  🟢{es.get('signal','')}" if s.get("entry_ready") else "  ⏳待机"
                print(f"  {i}. {s['code']} {s['name']:8s}  "
                      f"评分:{s['score']:.1f}  "
                      f"议会:{p.get('bias','?')}({p.get('confidence',0):.0%})  "
                      f"PE:{f.get('pe',0):.1f}  ROE:{f.get('roe',0):.1f}%{es_str}")

    else:
        parser.print_help()
