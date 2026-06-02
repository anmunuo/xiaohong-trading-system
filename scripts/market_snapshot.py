#!/usr/bin/env python3
"""
market_snapshot.py — 市场统一快照 v1.0
======================================
盘前 08:28 生成，聚合 data_pipeline + mega_latest 的关键数据，
为瞭望塔晨报、决策官等 LLM cron 提供统一市场上下文。

输出: data/market_snapshot.json
用法: python3 market_snapshot.py
"""

import json, os, sys
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
KB_ROOT = Path(os.environ.get('XIAOHONG_KB_ROOT', str(SCRIPT_DIR.parent / 'data' / 'kb')))
SNAPSHOT_PATH = DATA_DIR / "market_snapshot.json"

def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def collect():
    """采集全市场关键数据，合并为统一快照"""
    snapshot = {
        "generated_at": now(),
        "generated_by": "market_snapshot.py v1.0",
        "global_indices": {},
        "north_flow": {},
        "market_money": {},
        "index_valuation": {},
        "margin_trading": {},
        "sector_flow_top5": [],
        "external_futures": {},
        "narrative": "",
        "alerts": [],
    }

    # ── 1. 全球指数 (从 mega_latest external_futures) ──
    try:
        mega = KB_ROOT / "mega_latest.json"
        if mega.exists():
            with open(mega) as f:
                kb = json.load(f)
            modules = kb.get("modules", {})
            ext = modules.get("external_futures", {}).get("data", {})
            snapshot["global_indices"] = {
                "us": ext.get("us", {}),
                "europe": ext.get("europe", {}),
                "asia": ext.get("asia_pacific", {}) or ext.get("asia", {}),
            }
            # 北向资金
            nf = modules.get("north_flow", {}).get("data", {})
            snapshot["north_flow"] = nf.get("summary", {})
    except Exception as e:
        snapshot["alerts"].append(f"mega_latest 读取失败: {e}")

    # ── 2. 数据管道实时补充 (板块流/市场资金流/估值) ──
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from data_pipeline import get_sector_flow_rank, get_market_money_flow
        sectors = get_sector_flow_rank('3') or []
        for s in sectors[:5]:
            snapshot["sector_flow_top5"].append({
                "name": s.get("name", ""),
                "change_pct": s.get("change_pct", 0),
                "net_flow": s.get("net_flow", 0),
            })
        mm = get_market_money_flow() or {}
        snapshot["market_money"] = {
            "main_net": mm.get("main_net", 0),
            "retail_net": mm.get("retail_net", 0),
        }
        # 指数估值
        try:
            from index_valuation import fetch_valuation
            val = fetch_valuation()
            snapshot["index_valuation"] = val.get("summary", {})
            snapshot["index_valuation"]["details"] = val.get("indices", {})
        except Exception:
            pass
        # 融资融券情绪
        try:
            import akshare as ak
            from datetime import timedelta
            start_d = (datetime.now() - timedelta(days=5)).strftime('%Y%m%d')
            end_d = datetime.now().strftime('%Y%m%d')
            margin_df = ak.stock_margin_sse(start_date=start_d, end_date=end_d)
            if margin_df is not None and not margin_df.empty:
                latest = margin_df.iloc[-1]
                bal = float(latest['融资余额']) / 1e8
                buy = float(latest['融资买入额']) / 1e8
                short_mv = float(latest['融券余量金额']) / 1e8
                prev_bal = float(margin_df.iloc[0]['融资余额']) / 1e8 if len(margin_df) > 1 else bal
                ratio = round(buy / bal * 100, 1) if bal > 0 else 0
                trend_5d = round((bal - prev_bal) / prev_bal * 100, 2)
                signal = "🟢 杠杆加仓" if trend_5d > 2 else ("🟡 平稳" if trend_5d > 0 else "🔴 去杠杆")
                snapshot["margin_trading"] = {
                    "balance": round(bal, 0),
                    "buy_amount": round(buy, 0),
                    "short_balance": round(short_mv, 0),
                    "buy_ratio": ratio,
                    "trend_5d_pct": trend_5d,
                    "signal": signal,
                }
        except Exception:
            pass
    except Exception as e:
        snapshot["alerts"].append(f"data_pipeline 补充失败: {e}")

    # ── 3. 数据分发 ──
    try:
        from data_hub import distribute
        distribute()
    except Exception as e:
        snapshot["alerts"].append(f"数据分发失败: {e}")

    # ── 4. 生成叙事摘要 ──
    snapshot["narrative"] = _build_narrative(snapshot)

    # ── 4. 持久化 ──
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SNAPSHOT_PATH, 'w') as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2, default=str)

    # ── 5. 终端输出 ──
    print_snapshot(snapshot)
    return snapshot


def _build_narrative(snap: dict) -> str:
    """从数据构建自然语言摘要"""
    parts = []

    gi = snap.get("global_indices", {})
    asia = gi.get("asia", {})
    us = gi.get("us", {})

    # 亚太
    asia_up = []
    for k, v in asia.items():
        if isinstance(v, list) and len(v) > 1:
            if v[1] > 0:
                asia_up.append(f"{k}+{v[1]:.1f}%")
            elif v[1] < 0:
                asia_up.append(f"{k}{v[1]:.1f}%")
    if asia_up:
        parts.append("亚太: " + " | ".join(asia_up))

    # 美股
    us_up = []
    for k, v in us.items():
        if isinstance(v, list) and len(v) > 1:
            if v[1] > 0:
                us_up.append(f"{k}+{v[1]:.2f}%")
    if us_up:
        parts.append("美股: " + " | ".join(us_up))

    # 北向
    nf = snap.get("north_flow", {})
    nf_net = nf.get("net_flow", 0) or 0
    if nf_net > 0:
        parts.append(f"北向净流入{nf_net:.1f}亿")
    elif nf_net < 0:
        parts.append(f"北向净流出{abs(nf_net):.1f}亿")

    # 板块
    sectors = snap.get("sector_flow_top5", [])
    if sectors:
        top3 = [s["name"] for s in sectors[:3]]
        parts.append(f"资金热: {'/'.join(top3)}")

    # 估值
    val = snap.get("index_valuation", {})
    if val:
        pos = val.get("position_signal", "")
        pct = val.get("avg_percentile", 0)
        if pos:
            parts.append(f"估值: {pos}(分位{pct}%)")

    # 融资
    margin = snap.get("margin_trading", {})
    if margin:
        parts.append(f"融资: {margin.get('signal','?')} ({margin.get('trend_5d_pct',0):+.1f}%)")

    return " | ".join(parts) if parts else "数据采集窗口静默"


def print_snapshot(snap: dict):
    """美化输出"""
    print(f"\n{'='*55}")
    print(f"  📊 市场统一快照  {snap['generated_at']}")
    print(f"  {'='*55}")
    print(f"  {snap['narrative']}")
    print(f"  {'='*55}")

    gi = snap.get("global_indices", {})
    for region, indices in gi.items():
        if indices:
            line = " | ".join(
                f"{k}: {v[0]:,.0f} ({v[1]:+.2f}%)"
                for k, v in indices.items()
                if isinstance(v, list) and len(v) > 1
            )
            if line:
                print(f"  {region.upper():8s}: {line}")

    nf = snap.get("north_flow", {})
    if nf:
        status = nf.get("status", "")
        print(f"  北向    : {status}")

    sectors = snap.get("sector_flow_top5", [])
    if sectors:
        names = " → ".join(s["name"] for s in sectors)
        print(f"  板块TOP5: {names}")

    val = snap.get("index_valuation", {})
    if val:
        print(f"  指数估值: PE={val.get('avg_pe_ttm','?')} 分位={val.get('avg_percentile','?')}% → {val.get('position_signal','?')}")

    margin = snap.get("margin_trading", {})
    if margin:
        print(f"  融资融券: 余额{margin.get('balance','?')}亿 {margin.get('signal','?')}")

    alerts = snap.get("alerts", [])
    if alerts:
        for a in alerts:
            print(f"  ⚠️ {a}")
    print()


if __name__ == "__main__":
    collect()
