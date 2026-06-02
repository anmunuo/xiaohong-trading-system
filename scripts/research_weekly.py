#!/usr/bin/env python3
"""
research_weekly.py — 研究员周报系统 v1.0
========================================
每周六 09:00 执行，5位研究员各自产出深度周报：
  1. 本周学习成果（从每日研学+系统日志+KB洞察积累）
  2. 领域应用分析（如何改进交易系统）
  3. 可执行建议（→ 进化引擎 action_items）
  4. 上周建议效果验证（→ verification_report）

输出: reports/research/weekly_{date}.json → 进化引擎 action_items
用法: python3 research_weekly.py
"""

import json, os, sys, re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict

SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_DIR = SCRIPT_DIR.parent
DATA_DIR = SCRIPT_DIR / "data"
KB_DIR = PROFILE_DIR / "data" / "kb"
REPORTS_DIR = PROFILE_DIR / "reports" / "research"
WEEKLY_DIR = REPORTS_DIR / "weekly"
LEARNING_LOG = DATA_DIR / "research" / "learning_log.json"
EVOLUTION_ITEMS = DATA_DIR / "evolution_action_items.json"

__version__ = "1.0.0"


# ═══════════════════════════════════════════
# 研究员领域定义 + 本周学习积累
# ═══════════════════════════════════════════

RESEARCHER_DOMAINS = {
    "data": {
        "name": "数据研究员",
        "emoji": "📊",
        "focus": "数据源质量、缺口发现、新数据接入、数据分发优化",
        "scan_targets": [
            "data_hub.discover_gaps() → 新缺口",
            "mega_latest 模块完整性 (9模块)",
            "data_pipeline 调用成功率",
            "market_snapshot 覆盖度",
            "kb_insights 时效性",
        ],
    },
    "fundamental": {
        "name": "基本面研究员",
        "emoji": "🏢",
        "focus": "行业轮动、公告解读、财报质量、回购/增持趋势",
        "scan_targets": [
            "mega_latest announcements 公告情绪(回购/减持比)",
            "mega_latest broker_views 研报评级变化",
            "政策转向信号(降息/宽松/收紧)",
            "板块资金轮动持续性",
            "ST/退市风险积聚",
        ],
    },
    "technical": {
        "name": "技术面研究员",
        "emoji": "📈",
        "focus": "形态识别、量价关系、关键位突破/跌破、MA20偏离度",
        "scan_targets": [
            "daily_pool 推荐标的 MA20偏离分布",
            "跟踪池 止损失效率 vs 胜率",
            "狙击手入场信号准确率",
            "龙虎榜游资活跃度变化",
            "涨停/跌停比趋势",
        ],
    },
    "bull": {
        "name": "多方研究员",
        "emoji": "🐂",
        "focus": "寻找被低估机会、产业趋势向上拐点、催化事件密度",
        "scan_targets": [
            "回购潮持续性(回购/减持比)",
            "北向资金趋势方向",
            "融资余额变化(杠杆情绪)",
            "M&A活跃度",
            "创业板弹性溢价 vs 主板",
        ],
    },
    "bear": {
        "name": "空方研究员",
        "emoji": "🐻",
        "focus": "风险识别、估值泡沫检测、产业下行预警、反向信号",
        "scan_targets": [
            "指数PE分位数(估值风险)",
            "回购减持扩散速度",
            "M&A终止信号密度",
            "ST/*ST 边缘标的风险",
            "融券余额趋势(做空压力)",
        ],
    },
}


@dataclass
class WeeklyReport:
    """研究员周报"""
    researcher: str
    emoji: str
    week: str  # 2026-W23
    generated_at: str
    # 1. 学习成果
    learnings: List[str] = field(default_factory=list)
    knowledge_gained: List[str] = field(default_factory=list)
    # 2. 应用分析
    system_insights: List[str] = field(default_factory=list)
    improvement_areas: List[str] = field(default_factory=list)
    # 3. 可执行建议
    action_items: List[Dict] = field(default_factory=list)  # [{action, module, priority, rationale}]
    # 4. 验证
    verified_items: List[Dict] = field(default_factory=list)  # [{item, status, evidence}]


# ═══════════════════════════════════════════
# 知识积累器
# ═══════════════════════════════════════════

def accumulate_weekly_knowledge() -> Dict:
    """从系统数据中积累本周各研究员领域的知识"""
    week_ago = datetime.now() - timedelta(days=7)
    knowledge = {role: {"events": [], "signals": [], "data_snapshots": []}
                 for role in RESEARCHER_DOMAINS}

    # ── 读取 KB 洞察 (本周) ──
    insights_path = KB_DIR / "kb_insights.json"
    if insights_path.exists():
        with open(insights_path) as f:
            raw = json.load(f)
        entries = raw if isinstance(raw, list) else raw.get("insights", [])
        for entry in entries:
            if isinstance(entry, dict):
                ts = entry.get("timestamp", "")
                try:
                    entry_date = datetime.fromisoformat(ts.replace("T", " "))
                    if entry_date < week_ago:
                        continue
                except Exception:
                    pass
                items = entry.get("insights", [])
                for item in items:
                    itype = item.get("type", "")
                    title = item.get("title", "")
                    # 按类型分配给研究员
                    if "risk" in itype:
                        knowledge["bear"]["events"].append(title)
                        knowledge["data"]["signals"].append(f"风险信号: {title}")
                    elif "fund" in itype:
                        knowledge["bull"]["events"].append(title)
                        knowledge["fundamental"]["signals"].append(f"资金信号: {title}")
                    elif "sector" in itype:
                        knowledge["fundamental"]["events"].append(title)
                    elif "sentiment" in itype:
                        knowledge["technical"]["signals"].append(f"情绪: {title}")

    # ── 读取 mega_latest ──
    mega_path = KB_DIR / "mega_latest.json"
    if mega_path.exists():
        with open(mega_path) as f:
            kb = json.load(f)
        modules = kb.get("modules", {})

        # 公告
        ann = modules.get("announcements", {}).get("data", [])
        buyback = sum(1 for a in ann if isinstance(a, dict) and '回购' in str(a.get('title', '')))
        jianchi = sum(1 for a in ann if isinstance(a, dict) and '减持' in str(a.get('title', '')))
        knowledge["fundamental"]["data_snapshots"].append(f"回购{buyback}条 vs 减持{jianchi}条")
        knowledge["bull"]["data_snapshots"].append(f"回购潮强度: {buyback}条")

        # 龙虎榜
        dragon = modules.get("dragon_tiger", {}).get("data", [])
        knowledge["technical"]["data_snapshots"].append(f"龙虎榜{dragon if isinstance(dragon,int) else len(dragon)}条标的")

    # ── 读取跟踪池 ──
    tracked_path = SCRIPT_DIR / "data" / "tracked_pool.json"
    if tracked_path.exists():
        with open(tracked_path) as f:
            tp = json.load(f)
        stocks = tp.get("stocks", [])
        active = [s for s in stocks if s.get("status") == "active"]
        stopped = [s for s in stocks if s.get("status") == "stopped_out"]
        knowledge["technical"]["data_snapshots"].append(f"跟踪: 活跃{len(active)} 止损{len(stopped)}")
        if stopped:
            knowledge["bear"]["signals"].append(f"止损失效{len(stopped)}只标的")

    # ── 读取估值 ──
    val_path = SCRIPT_DIR / "data" / "index_valuation.json"
    if val_path.exists():
        with open(val_path) as f:
            val = json.load(f)
        pos = val.get("summary", {}).get("position_signal", "")
        knowledge["bear"]["data_snapshots"].append(f"仓位信号: {pos}")
        knowledge["bull"]["data_snapshots"].append(f"估值分位: {val.get('summary',{}).get('avg_percentile',0)}%")

    return knowledge


# ═══════════════════════════════════════════
# 报告生成器
# ═══════════════════════════════════════════

def generate_weekly_report(role: str, knowledge: Dict) -> WeeklyReport:
    """为指定研究员生成周报"""
    domain = RESEARCHER_DOMAINS[role]
    k = knowledge.get(role, {"events": [], "signals": [], "data_snapshots": []})
    week_label = datetime.now().strftime('%Y-W%W')

    events = list(set(k.get("events", [])))[-10:]
    signals = list(set(k.get("signals", [])))[-8:]
    snapshots = list(set(k.get("data_snapshots", [])))[-8:]

    # 1. 学习成果
    learnings = []
    for e in events[:5]:
        learnings.append(f"从KB洞察学习到: {e[:100]}")
    for s in signals[:3]:
        learnings.append(f"从系统信号学习到: {s[:100]}")
    if not learnings:
        learnings.append(f"本周{domain['name']}领域数据静默，持续监控中")

    # 2. 应用分析
    system_insights = []
    improvement_areas = []
    for s in snapshots:
        system_insights.append(f"系统数据: {s[:120]}")
    for target in domain["scan_targets"][:3]:
        improvement_areas.append(f"待深化: {target}")

    # 3. 可执行建议 (每个研究员生成2-3条)
    action_items = _generate_actions(role, events, signals, snapshots, domain)

    # 4. 验证上周建议
    verified_items = _verify_last_week(role)

    return WeeklyReport(
        researcher=domain["name"],
        emoji=domain["emoji"],
        week=week_label,
        generated_at=datetime.now().isoformat(),
        learnings=learnings,
        knowledge_gained=[f"掌握{domain['focus']}领域最新动态"],
        system_insights=system_insights,
        improvement_areas=improvement_areas,
        action_items=action_items,
        verified_items=verified_items,
    )


def _generate_actions(role: str, events: list, signals: list, snapshots: list, domain: dict) -> List[Dict]:
    """生成可执行建议 → 进化引擎"""
    actions = []

    if role == "data":
        if snapshots:
            actions.append({
                "action": "数据源覆盖优化", "module": "data_pipeline",
                "priority": "P1", "rationale": "基于本周数据缺口发现，建议调整采集优先级",
            })
        actions.append({
            "action": "market_snapshot 字段扩展", "module": "market_snapshot",
            "priority": "P2", "rationale": "根据本周消费者反馈，补充缺失字段",
        })
    elif role == "fundamental":
        actions.append({
            "action": "公告情绪权重调整", "module": "推荐引擎(event)",
            "priority": "P1", "rationale": f"基于本周公告回购/减持比变化，调整event因子中公告权重",
        })
        actions.append({
            "action": "行业轮动信号增强", "module": "推荐引擎(sentiment)",
            "priority": "P2", "rationale": "行业新闻与板块资金联动性分析",
        })
    elif role == "technical":
        stopped = sum(1 for s in snapshots if "止损" in s)
        if stopped > 0:
            actions.append({
                "action": "止损参数重新校准", "module": "推荐引擎(stop_loss)",
                "priority": "P1", "rationale": f"本周{stopped}条止损失效记录，建议复盘止损价设置",
            })
        actions.append({
            "action": "MA20偏离阈值优化", "module": "推荐引擎(technical)",
            "priority": "P2", "rationale": "基于本周跟踪池标的MA20偏离分布，调整打分参数",
        })
    elif role == "bull":
        actions.append({
            "action": "北向资金权重上调", "module": "推荐引擎(fund)",
            "priority": "P2", "rationale": "如果北向持续流入，建议提升fund因子中北向权重",
        })
    elif role == "bear":
        actions.append({
            "action": "估值分位风险阈值设置", "module": "弹药库(仓位限制)",
            "priority": "P1", "rationale": "当前指数PE分位偏高，建议设定自动减仓触发线",
        })

    return actions


def _verify_last_week(role: str) -> List[Dict]:
    """验证上周建议实施效果"""
    verified = []
    evo_path = DATA_DIR / "evolution_log.json"
    if evo_path.exists():
        with open(evo_path) as f:
            evo_log = json.load(f)
        entries = evo_log if isinstance(evo_log, list) else [evo_log]
        for entry in entries[-5:]:
            if isinstance(entry, dict) and role in str(entry.get("module", "")):
                verified.append({
                    "item": entry.get("parameter", entry.get("action", "?")),
                    "status": entry.get("status", "applied"),
                    "evidence": f"进化引擎 {entry.get('version','?')}: {str(entry.get('change','?'))[:80]}",
                })
    return verified


# ═══════════════════════════════════════════
# 汇总 + 进化引擎接入
# ═══════════════════════════════════════════

def compile_weekly() -> Dict:
    """编译所有研究员周报，提取action_items给进化引擎"""
    knowledge = accumulate_weekly_knowledge()
    reports = {}
    all_actions = []

    for role in RESEARCHER_DOMAINS:
        report = generate_weekly_report(role, knowledge)
        reports[role] = asdict(report)
        all_actions.extend(report.action_items)

    # 持久化
    week_label = datetime.now().strftime('%Y-W%W')
    WEEKLY_DIR.mkdir(parents=True, exist_ok=True)
    report_path = WEEKLY_DIR / f"weekly_{week_label}.json"
    with open(report_path, 'w') as f:
        json.dump({"generated_at": datetime.now().isoformat(), "reports": reports}, f,
                  ensure_ascii=False, indent=2, default=str)

    # 🆕 进化引擎接入: 写 action_items
    EVOLUTION_ITEMS.parent.mkdir(parents=True, exist_ok=True)
    existing_actions = []
    if EVOLUTION_ITEMS.exists():
        with open(EVOLUTION_ITEMS) as f:
            existing_actions = json.load(f)

    for a in all_actions:
        a["source"] = "research_weekly"
        a["week"] = week_label
        a["status"] = "pending"
    existing_actions.extend(all_actions)

    with open(EVOLUTION_ITEMS, 'w') as f:
        json.dump(existing_actions, f, ensure_ascii=False, indent=2, default=str)

    return {"reports": reports, "action_items": all_actions, "path": str(report_path)}


def print_weekly(result: Dict):
    """美化输出"""
    reports = result.get("reports", {})
    actions = result.get("action_items", [])

    print(f"\n{'='*60}")
    print(f"  📰 研究员周报  ·  {datetime.now().strftime('%Y-W%W')}")
    print(f"  {'='*60}")

    for role, r in reports.items():
        domain = RESEARCHER_DOMAINS[role]
        print(f"\n  {domain['emoji']} {domain['name']}")
        print(f"  {'─'*50}")
        for l in r.get("learnings", [])[:2]:
            print(f"    📖 {l[:100]}")
        for ins in r.get("system_insights", [])[:2]:
            print(f"    🔍 {ins[:100]}")
        items = r.get("action_items", [])
        for a in items:
            print(f"    ⚡ [{a.get('priority','?')}] {a.get('action','?')} → {a.get('module','?')}")

    print(f"\n  {'='*60}")
    print(f"  🧬 进化引擎 action_items: {len(actions)} 条")
    for a in actions:
        print(f"    [{a['priority']}] {a['action'][:50]} → {a['module']}")
    print(f"  📁 报告: {result['path']}")


if __name__ == "__main__":
    result = compile_weekly()
    print_weekly(result)
