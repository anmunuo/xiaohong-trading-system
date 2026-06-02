#!/usr/bin/env python3
"""
data_hub.py — 数据研究员中枢 v2.0
=================================
职责:
  1. 数据分发 — 为各模块生成定制数据包
  2. 缺口发现 — 检测哪些数据没有被任何模块使用
  3. 新源扫描 — 主动发现值得接入的数据源
  4. 质量监控 — 数据新鲜度/完整性/冲突检测

用法:
  python3 data_hub.py --distribute     # 数据分发 → data_packages/*.json
  python3 data_hub.py --discover       # 新数据源发现 → discovery_report.json
  python3 data_hub.py --health         # 数据健康检查
"""

import json, os, sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_DIR = SCRIPT_DIR.parent
DATA_DIR = SCRIPT_DIR / "data"
KB_DIR = PROFILE_DIR / "data" / "kb"
PKG_DIR = DATA_DIR / "data_packages"
DISCOVERY_PATH = DATA_DIR / "discovery_report.json"
HEALTH_PATH = DATA_DIR / "data_health.json"

# ═══════════════════════════════════════════
# 数据资产注册表 — 所有系统数据的权威清单
# ═══════════════════════════════════════════

DATA_REGISTRY = {
    # (数据名, 来源, 消费者, 更新频率, 关键字段)
    "global_indices": {
        "source": "data_pipeline.get_index_data → mega_collector → mega_latest.external_futures",
        "consumers": ["market_snapshot", "瞭望塔晨报", "决策官", "推荐引擎(sentiment)"],
        "frequency": "每小时采集",
        "status": "active",
        "fields": ["us.dow/sp500/nasdaq", "asia.nikkei/hangseng/shanghai", "europe.ftse/dax"],
    },
    "north_flow": {
        "source": "data_pipeline.get_north_flow → mega_collector → mega_latest.north_flow",
        "consumers": ["market_snapshot", "瞭望塔晨报", "推荐引擎(fund)"],
        "frequency": "每小时采集",
        "status": "active",
        "fields": ["net_flow", "沪股通", "深股通"],
    },
    "sector_flow": {
        "source": "data_pipeline.get_sector_flow_rank → market_snapshot + scout",
        "consumers": ["market_snapshot", "scout", "推荐引擎(sentiment)"],
        "frequency": "盘中实时 + 盘前快照",
        "status": "active",
        "fields": ["name", "change_pct", "net_flow"],
    },
    "market_money": {
        "source": "data_pipeline.get_market_money_flow → ammo_risk + market_snapshot",
        "consumers": ["market_snapshot", "ammo_risk"],
        "frequency": "盘后采集",
        "status": "active",
        "fields": ["main_net", "retail_net"],
    },
    "stock_realtime": {
        "source": "data_pipeline.get_stock_realtime (Sina 批量)",
        "consumers": ["推荐引擎", "弹药库", "狙击手", "股票跟踪器", "竞价学习器"],
        "frequency": "实时拉取",
        "status": "active",
        "fields": ["close", "change_pct", "volume", "amount"],
    },
    "fundamentals": {
        "source": "tushare daily_basic (PE/PB/total_mv/circ_mv)",
        "consumers": ["推荐引擎(fund)", "弹药库"],
        "frequency": "每日盘前采集",
        "status": "active",
        "fields": ["pe_ttm", "pb", "total_mv"],
    },
    "announcements": {
        "source": "mega_collector (akshare 公告)",
        "consumers": ["推荐引擎(event)", "研究员议会", "kb_insights"],
        "frequency": "每小时采集",
        "status": "active",
        "fields": ["title", "code", "type"],
    },
    "dragon_tiger": {
        "source": "mega_collector (akshare 龙虎榜)",
        "consumers": ["推荐引擎(event)", "研究员议会"],
        "frequency": "盘后采集",
        "status": "active",
        "fields": ["code", "net_amount", "buy_amount", "sell_amount"],
    },
    "broker_views": {
        "source": "mega_collector (akshare 研报)",
        "consumers": ["推荐引擎(research)", "研究员议会"],
        "frequency": "每小时采集",
        "status": "active",
        "fields": ["code", "rating", "target_price"],
    },
    "hot_events": {
        "source": "mega_collector (东方财富热搜)",
        "consumers": ["推荐引擎(sentiment)"],
        "frequency": "每小时采集",
        "status": "weak",  # 经常为空
        "fields": ["code", "hot_rank"],
    },
    "auction_data": {
        "source": "auction_collector (东方财富竞价)",
        "consumers": ["竞价学习器", "侦察兵"],
        "frequency": "09:15 采集",
        "status": "active",
        "fields": ["open", "bid_vol", "ask_vol", "pre_close"],
    },

    # ── 未使用/待开发数据源 ──
    "limit_up_pool": {
        "source": "akshare.stock_zt_pool_em",
        "consumers": ["推荐引擎(候选源·首板)"],
        "frequency": "每日盘前",
        "status": "partial",  # 仅首板用
        "note": "涨停池完整数据(封板时间/炸板次数/连板数)未被充分挖掘",
    },
    "industry_news": {
        "source": "mega_collector (行业新闻)",
        "consumers": ["kb_insights", "推荐引擎(event) 🆕"],
        "frequency": "每小时采集",
        "status": "active",
        "fields": ["title", "sector", "sentiment"],
    },
    "policy_macro": {
        "source": "mega_collector (宏观政策 85条)",
        "consumers": ["kb_insights", "推荐引擎(event) 🆕"],
        "frequency": "每小时采集",
        "status": "active",
        "fields": ["title", "country", "impact"],
    },
    "margin_trading": {
        "source": "akshare.stock_margin_sse → market_snapshot 🆕",
        "consumers": ["market_snapshot", "瞭望塔", "决策官"],
        "frequency": "盘前采集",
        "status": "active",
        "note": "融资余额/买入额/融券余额 — 杠杆情绪指标",
    },
    "index_valuation": {
        "source": "tushare.index_dailybasic → index_valuation.py 🆕",
        "consumers": ["market_snapshot", "弹药库(仓位中枢)", "瞭望塔", "决策官"],
        "frequency": "盘前采集",
        "status": "active",
        "note": "四大指数PE分位数 — 决定系统级仓位参数",
    },
    "short_selling": {
        "source": "未接入",
        "consumers": [],
        "frequency": "—",
        "status": "missing",
        "note": "融券余量 — 做空情绪指标，对高估值股预警价值高",
    },
    "institutional_holdings": {
        "source": "未接入",
        "consumers": [],
        "frequency": "—",
        "status": "missing",
        "note": "机构持仓变动(季报) — tushare.fund_portfolio 可用，中期方向信号",
    },
    "index_valuation": {
        "source": "未接入",
        "consumers": [],
        "frequency": "—",
        "status": "missing",
        "note": "指数PE/PB分位数 — 判断市场整体估值水位，决定仓位中枢",
    },
    "volatility_index": {
        "source": "未接入",
        "consumers": [],
        "frequency": "—",
        "status": "missing",
        "note": "VIX/波指 — 市场恐慌指标，a股可用 50ETF 波指替代",
    },
}


def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ═══════════════════════════════════════════
# 1. 数据分发
# ═══════════════════════════════════════════

def distribute():
    """为各消费模块生成定制数据包"""
    PKG_DIR.mkdir(parents=True, exist_ok=True)
    packages = {}

    # ── 包1: market_context (瞭望塔/决策官) ──
    packages["market_context"] = _build_market_context()
    # ── 包2: sector_signals (推荐引擎/侦察兵) ──
    packages["sector_signals"] = _build_sector_signals()
    # ── 包3: macro_pulse (议会/进化引擎) ──
    packages["macro_pulse"] = _build_macro_pulse()

    for name, data in packages.items():
        path = PKG_DIR / f"{name}.json"
        with open(path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    return packages


def _build_market_context() -> dict:
    """构建市场上下文数据包"""
    ctx = {"generated_at": now(), "indices": {}, "north_flow": {}, "sector_flow": [], "alerts": []}
    try:
        snap = DATA_DIR / "market_snapshot.json"
        if snap.exists():
            with open(snap) as f:
                s = json.load(f)
            ctx["indices"] = s.get("global_indices", {})
            ctx["north_flow"] = s.get("north_flow", {})
            ctx["sector_flow"] = s.get("sector_flow_top5", [])
    except Exception as e:
        ctx["alerts"].append(str(e))
    return ctx


def _build_sector_signals() -> dict:
    """构建板块信号数据包"""
    sig = {"generated_at": now(), "hot_sectors": [], "cold_sectors": [], "fund_flow_summary": ""}
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from data_pipeline import get_sector_flow_rank
        sectors = get_sector_flow_rank('3') or []
        for s in sectors[:10]:
            net = s.get("net_flow", 0)
            entry = {"name": s.get("name", ""), "change_pct": s.get("change_pct", 0), "net_flow": net}
            if net > 5e7:
                sig["hot_sectors"].append(entry)
            elif net < -5e7:
                sig["cold_sectors"].append(entry)
            else:
                sig["hot_sectors"].append(entry)  # 暂不分冷热，全放 hot
        sig["fund_flow_summary"] = f"TOP3资金流入: {', '.join(s['name'] for s in sig['hot_sectors'][:3])}"
    except Exception:
        pass
    return sig


def _build_macro_pulse() -> dict:
    """构建宏观脉动数据包"""
    pulse = {"generated_at": now(), "market_bias": "neutral", "risk_signals": [], "opportunity_signals": []}
    try:
        mega = KB_DIR / "mega_latest.json"
        if mega.exists():
            with open(mega) as f:
                kb = json.load(f)
            modules = kb.get("modules", {})

            # 宏观政策密度 → 事件驱动判断
            policy = modules.get("policy_macro", {}).get("data", [])
            pulse["policy_density"] = len(policy) if isinstance(policy, list) else 0

            # 公告情绪
            ann = modules.get("announcements", {}).get("data", [])
            buyback = sum(1 for a in ann if isinstance(a, dict) and '回购' in str(a.get('title', '')))
            jianchi = sum(1 for a in ann if isinstance(a, dict) and '减持' in str(a.get('title', '')))
            pulse["buyback_count"] = buyback
            pulse["reduce_count"] = jianchi
            if buyback > jianchi * 3:
                pulse["opportunity_signals"].append("回购潮(买入信号): 回购/减持比 >3:1")
            if jianchi > buyback * 0.3:
                pulse["risk_signals"].append(f"减持增多: 减持{buyback}条/回购{jianchi}条")

            # 外部期货方向
            ext = modules.get("external_futures", {}).get("data", {})
            us = ext.get("us", {})
            up_count = sum(1 for v in us.values() if isinstance(v, list) and len(v) > 1 and v[1] > 0)
            if up_count >= 3:
                pulse["market_bias"] = "bullish"
            elif up_count <= 1:
                pulse["market_bias"] = "bearish"
    except Exception:
        pass
    return pulse


# ═══════════════════════════════════════════
# 2. 缺口发现
# ═══════════════════════════════════════════

def discover_gaps() -> dict:
    """发现数据缺口和未充分利用的数据源"""
    report = {
        "generated_at": now(),
        "missing_sources": [],
        "underutilized_sources": [],
        "weak_sources": [],
        "recommendations": [],
    }

    for name, info in DATA_REGISTRY.items():
        status = info.get("status", "unknown")
        consumers = info.get("consumers", [])

        if status == "missing":
            report["missing_sources"].append({
                "name": name,
                "note": info.get("note", ""),
                "potential_impact": _estimate_impact(name),
            })
        elif status == "underutilized":
            report["underutilized_sources"].append({
                "name": name,
                "current_consumers": consumers,
                "note": info.get("note", ""),
            })
        elif status == "weak":
            report["weak_sources"].append({
                "name": name,
                "current_consumers": consumers,
                "note": "数据经常为空或质量不稳定",
            })

    # 生成建议
    report["recommendations"] = _generate_recommendations(report)
    DISCOVERY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(DISCOVERY_PATH, 'w') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    return report


def _estimate_impact(name: str) -> str:
    impacts = {
        "margin_trading": "高 — 杠杆资金情绪直接反映市场风险偏好，可用于仓位中枢调整",
        "short_selling": "中高 — 做空信号对高估值/创业板标的预警价值高",
        "institutional_holdings": "中 — 季频数据，中期方向信号，辅助板块配置",
        "index_valuation": "高 — 指数PE分位数决定整体仓位中枢，是系统级参数",
        "volatility_index": "高 — 恐慌指标可触发行情冷却机制，保护持仓",
    }
    return impacts.get(name, "待评估")


def _generate_recommendations(report: dict) -> list:
    recs = []
    for m in report.get("missing_sources", []):
        recs.append(f"[P1] 接入 {m['name']}: {m['note'][:80]}")
    for u in report.get("underutilized_sources", []):
        recs.append(f"[P2] 激活 {u['name']}: 当前仅 {u['current_consumers']} 使用，应注入推荐引擎/瞭望塔")
    for w in report.get("weak_sources", []):
        recs.append(f"[P0] 修复 {w['name']}: 数据质量不稳定，影响 {w['current_consumers']}")
    return recs


# ═══════════════════════════════════════════
# 3. 数据健康检查
# ═══════════════════════════════════════════

def health_check() -> dict:
    """检查所有数据源的新鲜度和可用性"""
    health = {
        "checked_at": now(),
        "sources": {},
        "overall_status": "healthy",
        "issues": [],
    }

    checks = {
        "mega_latest": _check_mega_latest,
        "daily_pool": _check_daily_pool,
        "market_snapshot": _check_market_snapshot,
        "tracked_pool": _check_tracked_pool,
        "kb_insights": _check_kb_insights,
    }

    for name, check_fn in checks.items():
        try:
            result = check_fn()
            health["sources"][name] = result
            if not result.get("ok", True):
                health["issues"].append(f"{name}: {result.get('error', 'unknown')}")
        except Exception as e:
            health["sources"][name] = {"ok": False, "error": str(e)}
            health["issues"].append(f"{name}: {e}")

    if health["issues"]:
        health["overall_status"] = "degraded"

    HEALTH_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(HEALTH_PATH, 'w') as f:
        json.dump(health, f, ensure_ascii=False, indent=2, default=str)
    return health


def _check_mega_latest() -> dict:
    path = KB_DIR / "mega_latest.json"
    if not path.exists():
        return {"ok": False, "error": "文件不存在"}
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age_h = (datetime.now() - mtime).total_seconds() / 3600
    with open(path) as f:
        kb = json.load(f)
    modules = kb.get("modules", {})
    module_count = len(modules)
    empty_modules = [k for k, v in modules.items() if not v.get("data")]
    return {"ok": age_h < 3, "age_hours": round(age_h, 1), "module_count": module_count,
            "empty_modules": empty_modules, "error": f"数据过期({age_h:.1f}h)" if age_h >= 3 else ""}


def _check_daily_pool() -> dict:
    path = DATA_DIR / "daily_pool.json"
    if not path.exists():
        return {"ok": False, "error": "文件不存在"}
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age_h = (datetime.now() - mtime).total_seconds() / 3600
    with open(path) as f:
        pool = json.load(f)
    count = len(pool.get("recommendations", []))
    return {"ok": age_h < 24 and count > 0, "age_hours": round(age_h, 1),
            "stock_count": count, "error": "推荐池为空" if count == 0 else ""}


def _check_market_snapshot() -> dict:
    path = DATA_DIR / "market_snapshot.json"
    if not path.exists():
        return {"ok": False, "error": "文件不存在"}
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age_h = (datetime.now() - mtime).total_seconds() / 3600
    return {"ok": age_h < 24, "age_hours": round(age_h, 1)}


def _check_tracked_pool() -> dict:
    path = DATA_DIR / "tracked_pool.json"
    if not path.exists():
        return {"ok": True, "error": "尚无跟踪数据（正常）"}
    with open(path) as f:
        tp = json.load(f)
    active = sum(1 for s in tp.get("stocks", []) if s.get("status") == "active")
    return {"ok": True, "active_count": active}


def _check_kb_insights() -> dict:
    path = KB_DIR / "kb_insights.json"
    if not path.exists():
        return {"ok": False, "error": "文件不存在"}
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age_h = (datetime.now() - mtime).total_seconds() / 3600
    with open(path) as f:
        insights = json.load(f)
    count = len(insights) if isinstance(insights, list) else len(insights.get("insights", []))
    return {"ok": age_h < 6, "age_hours": round(age_h, 1), "entry_count": count}


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description="数据研究员中枢 v2.0")
    p.add_argument("--distribute", action="store_true", help="数据分发")
    p.add_argument("--discover", action="store_true", help="缺口发现")
    p.add_argument("--health", action="store_true", help="健康检查")
    args = p.parse_args()

    if args.health:
        h = health_check()
        print(f"\n📊 数据健康: {h['overall_status']}")
        for name, s in h["sources"].items():
            icon = "✅" if s.get("ok") else "❌"
            extra = f" ({s.get('error','')})" if not s.get("ok") else ""
            print(f"  {icon} {name}: age={s.get('age_hours','?')}h{extra}")
        if h["issues"]:
            print(f"\n⚠️ 问题: {len(h['issues'])}个")
            for i in h["issues"]:
                print(f"  - {i}")

    if args.discover:
        r = discover_gaps()
        print(f"\n🔍 数据缺口发现:")
        print(f"  缺失源: {len(r['missing_sources'])}")
        for m in r['missing_sources']:
            print(f"    - {m['name']}: {m['potential_impact']}")
        print(f"  未充分利用: {len(r['underutilized_sources'])}")
        for u in r['underutilized_sources']:
            print(f"    - {u['name']}: {u['note'][:80]}")
        print(f"\n📋 建议 ({len(r['recommendations'])}条):")
        for i, rec in enumerate(r['recommendations'], 1):
            print(f"  {i}. {rec}")

    if args.distribute:
        pkgs = distribute()
        print(f"\n📦 数据分发完成 ({len(pkgs)}个包):")
        for name in pkgs:
            path = PKG_DIR / f"{name}.json"
            print(f"  → {name}.json ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
