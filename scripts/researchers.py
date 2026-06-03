#!/usr/bin/env python3
"""
researchers.py — 研究员议会 v1.0
================================
5 位研究员：数据 / 基本面 / 技术面 / 多方 / 空方
两种模式：每日自主研学 + 决策时议会（3轮辩论 → 小红终审）

用法:
  python3 researchers.py --study          # 自主研学模式
  python3 researchers.py --parliament     # 议会模式（需传入议题）
  python3 researchers.py --report         # 查看最近研究报告
"""

import json, os, sys, re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
KB_DIR = DATA_DIR / "kb"
RESEARCH_DIR = DATA_DIR / "research"
REPORTS_DIR = SCRIPT_DIR.parent / "reports" / "research"
LOG_PATH = RESEARCH_DIR / "parliament_log.json"

__version__ = "1.0.0"

# ═══════════════════════════════════════════
# 研究员定义
# ═══════════════════════════════════════════

@dataclass
class ResearchReport:
    """研究员分析报告"""
    author: str
    author_emoji: str
    timestamp: str
    topic: str
    perspective: str           # 视角简述
    key_findings: List[str]    # 核心发现
    data_evidence: List[str]   # 数据证据
    confidence: float          # 置信度 0-1
    recommendations: List[str] # 建议
    red_flags: List[str] = field(default_factory=list)  # 红旗警告
    raw_context: Dict = field(default_factory=dict)


RESEARCHERS = {
    "data": {
        "name": "数据研究员",
        "emoji": "📊",
        "persona": """你是安幕诺家族的数据研究员。你的使命是确保交易系统始终基于即时、准确、有效的数据运行。

核心能力：
- 识别哪些数据对系统能力提升有价值
- 研究数据应该从哪里获得、如何接入
- 能识别有效数据 vs 干扰噪声
- 主动挖掘目标标的的隐藏信息
- 维护数据质量，排除过期/异常/重复数据

分析框架：
1. 数据完整性 — 关键数据源是否齐全、及时
2. 数据准确性 — 是否存在异常值、数据冲突
3. 隐藏信息 — 从原始数据中能挖掘出什么非显而易见的洞察
4. 新数据源 — 是否有值得接入的新数据源
5. 干扰排除 — 哪些数据是噪声应忽略""",
        "debate_weight": 1.0,
    },
    "fundamental": {
        "name": "基本面研究员",
        "emoji": "🏢",
        "persona": """你是安幕诺家族的基本面研究员。你专注于财报、公告、研报、行业趋势和情绪热度分析。

核心能力：
- 从知识库吸收的资讯中提炼对板块和个股的影响
- 评估企业护城河、盈利质量、成长性
- 跟踪行业轮动和资金流向
- 识别情绪过热/过冷的拐点信号

分析框架：
1. 公告解读 — 增持/回购/减持/合同/处罚等事件的真实影响
2. 财报质量 — ROE/毛利率/现金流/负债率的趋势和同业对比
3. 行业轮动 — 当前市场风格偏好哪个板块，为什么
4. 情绪热度 — 市场关注度是否过热或过冷
5. 催化剂 — 近期有哪些可能改变基本面的催化剂""",
        "debate_weight": 1.2,
    },
    "technical": {
        "name": "技术面研究员",
        "emoji": "📈",
        "persona": """你是安幕诺家族的技术面研究员。你专攻K线形态、量价关系和技术指标。

核心能力：
- 识别多阶段形态（底部盘整/突破/主升/冲高回踩）
- 判断量价关系是否健康
- 确定关键支撑阻力位
- 评估技术风险信号

分析框架：
1. 形态阶段 — 当前处于什么阶段，方向判断
2. 量价关系 — 放量突破还是缩量下跌，筹码是否锁定
3. 关键位 — MA20/前高/前低/黄金分割位
4. 危险信号 — 顶背离/放量滞涨/连续缩量阴跌
5. 操作建议 — 基于技术面的具体买卖点""",
        "debate_weight": 1.0,
    },
    "bull": {
        "name": "多方研究员",
        "emoji": "🐂",
        "persona": """你是安幕诺家族的多方研究员。你的职责是为每一只标的寻找最有力的看多论据。

核心能力：
- 挖掘被市场忽视的积极因素
- 寻找业绩超预期、订单爆发的蛛丝马迹
- 识别估值洼地和价值重估机会
- 跟踪产业趋势向上拐点

分析框架：
1. 增长逻辑 — 业绩增长的确定性在哪里
2. 估值空间 — 当前估值是否被低估，目标估值是多少
3. 催化事件 — 近期有什么可能推动股价上涨的事件
4. 行业顺风 — 行业政策/周期/趋势利好
5. 资金信号 — 主力/北向/机构是否在买入""",
        "debate_weight": 1.0,
    },
    "bear": {
        "name": "空方研究员",
        "emoji": "🐻",
        "persona": """你是安幕诺家族的空方研究员。你的职责是不留情面地揭示每一只标的的风险和看空逻辑。

核心能力：
- 挖掘被市场忽视的风险因素
- 识别财务造假、管理层问题的信号
- 预判行业下行和政策收紧的风险
- 找出估值泡沫和炒作过度的证据

分析框架：
1. 风险隐患 — 业绩下滑/商誉减值/质押爆仓/债务违约
2. 估值风险 — 当前估值是否已经泡沫化
3. 利空事件 — 减持/解禁/诉讼/监管/退市风险
4. 行业逆风 — 行业衰退/政策收紧/竞争加剧/替代风险
5. 资金风险 — 主力出货/流动性枯竭/筹码分散""",
        "debate_weight": 1.0,
    },
}


# ═══════════════════════════════════════════
# 研究员基类
# ═══════════════════════════════════════════

class Researcher:
    """研究员基类"""

    def __init__(self, role_id: str):
        cfg = RESEARCHERS[role_id]
        self.role_id = role_id
        self.name = cfg["name"]
        self.emoji = cfg["emoji"]
        self.persona = cfg["persona"]
        self.debate_weight = cfg["debate_weight"]

    def analyze(self, context: Dict) -> ResearchReport:
        """基于上下文生成分析报告（结构化数据分析，不调LLM）"""
        raise NotImplementedError

    def get_system_prompt(self) -> str:
        """获取 LLM 系统提示词"""
        return f"""你是安幕诺家族的{self.emoji} {self.name}。

{self.persona}

输出格式（严格遵守JSON）：
{{
  "perspective": "一句话视角",
  "key_findings": ["发现1", "发现2", "发现3"],
  "data_evidence": ["证据1", "证据2"],
  "confidence": 0.0-1.0,
  "recommendations": ["建议1", "建议2"],
  "red_flags": ["红旗1"] 
}}"""


# ═══════════════════════════════════════════
# 结构化分析（不调LLM的轻量模式）
# ═══════════════════════════════════════════

class DataResearcher(Researcher):
    """数据研究员 — 结构化数据质量分析"""

    def __init__(self):
        super().__init__("data")

    def analyze(self, context: Dict) -> ResearchReport:
        findings = []
        evidence = []
        flags = []

        # 检查数据源完整性
        sources = context.get("data_sources", {})
        for src_name, status in sources.items():
            if status.get("ok"):
                findings.append(f"{src_name}: 数据源正常")
            else:
                findings.append(f"{src_name}: 数据源异常 — {status.get('error', '未知')}")
                flags.append(f"{src_name} 数据源异常需修复")

        # 检查KB数据时效
        kb_files = context.get("kb_files", {})
        for fname, age_h in kb_files.items():
            if age_h < 2:
                evidence.append(f"{fname} 更新及时 ({age_h:.1f}h)")
            elif age_h < 6:
                findings.append(f"{fname} 数据略旧 ({age_h:.1f}h)")
            else:
                flags.append(f"{fname} 严重过期 ({age_h:.1f}h)")

        # 检查数据冲突
        conflicts = context.get("data_conflicts", [])
        for conf in conflicts:
            flags.append(f"数据冲突: {conf}")

        # 新数据源建议
        available = context.get("available_sources", [])
        used = context.get("used_sources", [])
        unused = [s for s in available if s not in used]
        if unused:
            recommendations = [f"建议接入未使用数据源: {', '.join(unused)}"]
        else:
            recommendations = ["当前数据源覆盖完整，无需新增"]

        conf = 0.9 if not flags else 0.7

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "数据质量巡检"),
            perspective=f"数据源 {len(sources)}个 / KB文件 {len(kb_files)}个",
            key_findings=findings,
            data_evidence=evidence,
            confidence=conf,
            recommendations=recommendations,
            red_flags=flags,
        )


class FundamentalResearcher(Researcher):
    """基本面研究员 — KB事件解析"""

    def __init__(self):
        super().__init__("fundamental")

    def analyze(self, context: Dict) -> ResearchReport:
        findings = []
        evidence = []
        flags = []
        recs = []

        # 公告分析
        announcements = context.get("announcements", [])
        buyback = sum(1 for a in announcements if any(
            kw in str(a) for kw in ["回购", "增持", "注销"]
        ))
        sell = sum(1 for a in announcements if any(
            kw in str(a) for kw in ["减持", "质押", "冻结"]
        ))
        mna = sum(1 for a in announcements if any(
            kw in str(a) for kw in ["要约收购", "并购", "重组"]
        ))

        if buyback > sell:
            findings.append(f"增持/回购信号({buyback}条)压倒减持({sell}条)，上市公司积极信号")
            evidence.append(f"内部人行为偏多: 回购增持{buyback} vs 减持{sell}")
        elif sell > buyback:
            flags.append(f"减持信号({sell}条)多于回购({buyback}条)，需警惕")

        if mna > 0:
            findings.append(f"M&A活动活跃({mna}条)，资本运作密集期")

        # 板块情绪
        sectors = context.get("sector_sentiment", {})
        hot_sectors = [s for s, v in sectors.items() if v.get("score", 0) > 70]
        cold_sectors = [s for s, v in sectors.items() if v.get("score", 0) < 30]
        if hot_sectors:
            findings.append(f"板块热度高: {', '.join(hot_sectors[:3])}")
        if cold_sectors:
            recs.append(f"关注超跌板块反弹机会: {', '.join(cold_sectors[:3])}")

        # 研报信号
        broker = context.get("broker_views", [])
        if broker:
            findings.append(f"券商覆盖 {len(broker)} 只标的")
            buy_cnt = sum(1 for b in broker if "买入" in str(b))
            if buy_cnt > len(broker) * 0.7:
                evidence.append(f"券商买入评级占比 {buy_cnt}/{len(broker)}")
            elif buy_cnt < len(broker) * 0.3:
                flags.append("券商买入评级偏低，市场情绪谨慎")

        # ── 财报分析 (v8.3) ──
        pool_stocks = context.get("pool_stocks", [])
        if pool_stocks:
            try:
                from data_pipeline import get_financial_summary
                fin_scores = []
                for s in pool_stocks[:8]:
                    code = s.get('code', '')
                    name = s.get('name', code)
                    fs = get_financial_summary(code)
                    if fs.get('data_source') != 'no_data':
                        fin_scores.append((name, code, fs['score'], fs))
                        if fs['score'] >= 80:
                            findings.append(f"{name}: 财务面优秀 (评分{fs['score']})")
                        elif fs['score'] < 40:
                            flags.append(f"{name}: 财务面堪忧 (评分{fs['score']})")
                if fin_scores:
                    avg = sum(s[2] for s in fin_scores) / len(fin_scores)
                    evidence.append(f"池内标的财务均分: {avg:.0f}/100 ({len(fin_scores)}只)")
            except Exception:
                pass

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "基本面分析"),
            perspective=f"公告{len(announcements)}条 / 板块{len(sectors)}个",
            key_findings=findings or ["基本面信号中性，无显著异常"],
            data_evidence=evidence,
            confidence=0.75 if not flags else 0.6,
            recommendations=recs or ["维持现有持仓基本面评估"],
            red_flags=flags,
        )


class TechnicalResearcher(Researcher):
    """技术面研究员 — 池内标的形态扫描"""

    def __init__(self):
        super().__init__("technical")

    def analyze(self, context: Dict) -> ResearchReport:
        findings = []
        evidence = []
        flags = []
        recs = []

        pool = context.get("pool_stocks", [])
        for s in pool:
            code = s.get("code", "")
            name = s.get("name", "")
            dev = float(s.get("ma20_dev", 0))
            tech = float(s.get("technical", 50))

            if tech >= 65:
                findings.append(f"{name}({code}): 技术面强势 (评分{tech})")
                evidence.append(f"{name} MA20偏离{dev:+.1f}%")

            # MA20位置判断
            if -2 <= dev <= 2:
                recs.append(f"{name}: MA20附近整理，可等突破确认")
            elif dev > 8:
                flags.append(f"{name}: 偏离MA20 +{dev:.0f}%，追高风险大")
            elif dev < -8:
                findings.append(f"{name}: 超跌 {dev:.0f}%，关注止跌信号")

        # 池整体判断
        if pool:
            avg_tech = sum(float(s.get("technical", 50)) for s in pool) / len(pool)
            if avg_tech > 60:
                findings.insert(0, f"池整体技术面偏强 (均分{avg_tech:.0f})")
            else:
                findings.insert(0, f"池整体技术面中性 (均分{avg_tech:.0f})")

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "技术面扫描"),
            perspective=f"池内{len(pool)}只标的形态评估",
            key_findings=findings or ["池内标的无显著技术信号"],
            data_evidence=evidence,
            confidence=0.7,
            recommendations=recs or ["观望为主，等待明确技术信号"],
            red_flags=flags,
        )


class BullResearcher(Researcher):
    """多方研究员 — 寻找看多因素"""

    def __init__(self):
        super().__init__("bull")

    def analyze(self, context: Dict) -> ResearchReport:
        findings = []
        evidence = []
        recs = []

        pool = context.get("pool_stocks", [])
        insights = context.get("kb_insights", [])

        # 扫描利好信号
        for s in pool:
            name = s.get("name", "")
            code = s.get("code", "")
            sentiment = float(s.get("sentiment", 50))
            event = float(s.get("event", 50))

            if sentiment >= 70:
                findings.append(f"{name}: 情绪面积极 (评分{sentiment})")
                evidence.append(f"{name} 市场关注度和正面讨论高")

            if event >= 65:
                findings.append(f"{name}: 事件催化密集 (评分{event})")
                recs.append(f"{name}: 事件驱动型，关注后续公告进展")

            # 从insights中找看多信号
            for ins in insights:
                text = str(ins)
                if code in text:
                    positive_kw = ["回购", "增持", "利好", "突破", "中标", "订单", "增长", "注销", "激励"]
                    if any(kw in text for kw in positive_kw):
                        evidence.append(f"{name}: KB洞察确认正面信号")

        if not findings:
            findings.append("当前池内标的无明显看多信号，建议等待更好的入场时机")

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "多方研判"),
            perspective=f"池内{len(pool)}只标的看多因素",
            key_findings=findings,
            data_evidence=evidence,
            confidence=0.7 if evidence else 0.5,
            recommendations=recs or ["观望——多方信号不足"],
            red_flags=[],
        )


class BearResearcher(Researcher):
    """空方研究员 — 寻找看空因素"""

    def __init__(self):
        super().__init__("bear")

    def analyze(self, context: Dict) -> ResearchReport:
        findings = []
        evidence = []
        flags = []

        pool = context.get("pool_stocks", [])
        insights = context.get("kb_insights", [])

        for s in pool:
            name = s.get("name", "")
            code = s.get("code", "")
            risk = s.get("risk_level", "中")
            mkt_cap = float(s.get("market_cap", 0))

            if risk == "高":
                findings.append(f"{name}: 风险评级为「高」")
                evidence.append(f"{name} 风险等级高，需控制仓位")

            if 0 < mkt_cap < 80:
                flags.append(f"{name}: 小市值({mkt_cap:.0f}亿)，流动性风险")

            # 从insights找看空信号
            for ins in insights:
                text = str(ins)
                if code in text:
                    negative_kw = ["减持", "终止", "亏损", "诉讼", "处罚", "退市", "警示", "冻结", "下跌"]
                    if any(kw in text for kw in negative_kw):
                        flags.append(f"{name}: KB洞察发现风险信号")
                        evidence.append(f"{name}: 洞察中出现利空关键词")

        if not findings and not flags:
            findings.append("当前池内标的无明显看空信号")

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "空方研判"),
            perspective=f"池内{len(pool)}只标的风险因素",
            key_findings=findings,
            data_evidence=evidence,
            confidence=0.7,
            recommendations=["严格要求止损，高风偏标的控制仓位 ≤ 11.1%"],
            red_flags=flags,
        )


# ═══════════════════════════════════════════
# 研究员工厂
# ═══════════════════════════════════════════

def get_all_researchers() -> List[Researcher]:
    return [
        DataResearcher(),
        FundamentalResearcher(),
        TechnicalResearcher(),
        BullResearcher(),
        BearResearcher(),
    ]


def get_researcher(role_id: str) -> Optional[Researcher]:
    mapping = {
        "data": DataResearcher,
        "fundamental": FundamentalResearcher,
        "technical": TechnicalResearcher,
        "bull": BullResearcher,
        "bear": BearResearcher,
    }
    cls = mapping.get(role_id)
    return cls() if cls else None


# ═══════════════════════════════════════════
# 议会调度器
# ═══════════════════════════════════════════

class Parliament:
    """研究员议会 — 3轮辩论协议"""

    def __init__(self):
        self.researchers = get_all_researchers()
        self.rounds = []

    def load_context(self) -> Dict:
        """加载当前系统上下文"""
        ctx = {
            "topic": "系统全景分析",
            "timestamp": datetime.now().isoformat(),
        }

        # 加载推荐池
        pool_path = DATA_DIR / "daily_pool.json"
        if pool_path.exists():
            try:
                pool = json.loads(pool_path.read_text())
                ctx["pool_stocks"] = pool.get("recommendations", [])
                ctx["excluded"] = pool.get("excluded", {})
            except Exception:
                ctx["pool_stocks"] = []

        # 加载KB洞察
        kb_path = SCRIPT_DIR.parent / "data" / "kb" / "kb_insights.json"
        if kb_path.exists():
            try:
                ctx["kb_insights"] = json.loads(kb_path.read_text())
            except Exception:
                ctx["kb_insights"] = []

        # 加载KB最新采集
        mega_path = SCRIPT_DIR.parent / "data" / "kb" / "mega_latest.json"
        kb_files = {}
        if mega_path.exists():
            kb_files["mega_latest"] = (
                datetime.now().timestamp() - mega_path.stat().st_mtime
            ) / 3600
        ctx["kb_files"] = kb_files

        # 加载持仓
        holdings_path = SCRIPT_DIR.parent / "data" / "holdings.json"
        if holdings_path.exists():
            try:
                ctx["holdings"] = json.loads(holdings_path.read_text())
            except Exception:
                ctx["holdings"] = {}

        # 公告/板块
        if mega_path.exists():
            try:
                mega = json.loads(mega_path.read_text())
                modules = mega.get("modules", {})
                ctx["announcements"] = modules.get("announcements", {}).get("data", [])
                ctx["broker_views"] = modules.get("broker_views", {}).get("data", [])
            except Exception:
                pass

        return ctx

    def round_one(self, context: Dict) -> Dict[str, ResearchReport]:
        """Round 1: 独立研判 — 各研究员独立分析"""
        reports = {}
        pool = context.get("pool_stocks", [])

        for r in self.researchers:
            ctx = {**context, "topic": f"{r.name}独立研判"}
            try:
                report = r.analyze(ctx)
                reports[r.role_id] = report
            except Exception as e:
                reports[r.role_id] = ResearchReport(
                    author=r.name, author_emoji=r.emoji,
                    timestamp=datetime.now().isoformat(),
                    topic=ctx["topic"],
                    perspective="分析异常",
                    key_findings=[f"分析出错: {str(e)[:100]}"],
                    data_evidence=[],
                    confidence=0.0,
                    recommendations=["需人工复核"],
                )

        self.rounds.append({"name": "独立研判", "reports": reports})
        return reports

    def round_two(self, round1_reports: Dict[str, ResearchReport]) -> Dict:
        """Round 2: 交叉辩论 — 多空互驳 + 基本面技术面交叉验证"""
        debate = {
            "bull_vs_bear": self._debate_pair(
                round1_reports.get("bull"),
                round1_reports.get("bear"),
                "多空辩论"
            ),
            "fundamental_vs_technical": self._debate_pair(
                round1_reports.get("fundamental"),
                round1_reports.get("technical"),
                "基本面×技术面交叉验证"
            ),
            "data_verdict": self._data_verdict(round1_reports),
        }

        self.rounds.append({"name": "交叉辩论", "debate": debate})
        return debate

    def _debate_pair(self, report_a, report_b, title: str) -> Dict:
        """两方辩论：比较观点，找共识和分歧"""
        if not report_a or not report_b:
            return {"title": title, "status": "缺失一方报告", "consensus": [], "divergence": []}

        a_findings = set(report_a.key_findings) if report_a.key_findings else set()
        b_findings = set(report_b.key_findings) if report_b.key_findings else set()

        # 简单共识/分歧检测（关键词重叠）
        consensus = []
        divergence = []

        a_keywords = set()
        b_keywords = set()
        for f in a_findings:
            a_keywords.update(re.findall(r'[\u4e00-\u9fff]{2,}', f))
        for f in b_findings:
            b_keywords.update(re.findall(r'[\u4e00-\u9fff]{2,}', f))

        shared = a_keywords & b_keywords
        if shared:
            consensus.append(f"共同关注点: {'/'.join(list(shared)[:5])}")

        a_unique = a_keywords - b_keywords
        b_unique = b_keywords - a_keywords
        if a_unique:
            divergence.append(f"{report_a.author_emoji}独有关注: {'/'.join(list(a_unique)[:3])}")
        if b_unique:
            divergence.append(f"{report_b.author_emoji}独有关注: {'/'.join(list(b_unique)[:3])}")

        return {
            "title": title,
            "a_perspective": f"{report_a.author_emoji}: {report_a.perspective}",
            "b_perspective": f"{report_b.author_emoji}: {report_b.perspective}",
            "consensus": consensus or ["无明显共识"],
            "divergence": divergence or ["无明显分歧"],
        }

    def _data_verdict(self, reports: Dict[str, ResearchReport]) -> Dict:
        """数据研究员做裁判：用数据验证各方论据"""
        data_rpt = reports.get("data")
        if not data_rpt:
            return {"verdict": "数据研究员未参与，无法裁判"}

        all_flags = []
        for rid, rpt in reports.items():
            if rid != "data" and rpt.red_flags:
                all_flags.extend(rpt.red_flags)

        return {
            "verdict": f"数据研报置信度 {data_rpt.confidence:.0%}",
            "data_quality_flags": data_rpt.red_flags,
            "cross_validated_flags": list(set(all_flags))[:5],
        }

    def round_three(self, round1: Dict, round2: Dict) -> Dict:
        """Round 3: 小红终审 — 综合所有报告形成统一结论"""
        decision = {
            "timestamp": datetime.now().isoformat(),
            "verdict": self._synthesize(round1, round2),
            "researcher_credits": self._score_researchers(round1),
        }
        self.rounds.append({"name": "小红终审", "decision": decision})
        return decision

    def _synthesize(self, round1: Dict, round2: Dict) -> Dict:
        """综合研判"""
        confidences = [r.confidence for r in round1.values() if r.confidence > 0]
        avg_conf = sum(confidences) / len(confidences) if confidences else 0.5

        # 汇总红旗
        all_flags = []
        for r in round1.values():
            all_flags.extend(r.red_flags)
        unique_flags = list(set(all_flags))

        # 汇总建议
        all_recs = []
        for r in round1.values():
            all_recs.extend(r.recommendations)

        # 多空对比
        bull_rpt = round1.get("bull")
        bear_rpt = round1.get("bear")
        bull_signals = len(bull_rpt.key_findings) if bull_rpt else 0
        bear_signals = len(bear_rpt.red_flags) if bear_rpt else 0

        if bull_signals > bear_signals + 2:
            bias = "偏多"
        elif bear_signals > bull_signals + 2:
            bias = "偏空"
        else:
            bias = "中性"

        return {
            "overall_confidence": round(avg_conf, 2),
            "bias": bias,
            "bull_strength": bull_signals,
            "bear_strength": bear_signals,
            "critical_flags": unique_flags[:5],
            "consolidated_recommendations": list(dict.fromkeys(all_recs))[:5],  # 去重
        }

    def _score_researchers(self, round1: Dict) -> Dict:
        """根据报告质量给研究员打分"""
        scores = {}
        for rid, rpt in round1.items():
            # 评分维度：置信度 + 发现数量 + 证据数量
            evidence_bonus = min(len(rpt.data_evidence) * 0.05, 0.2)
            finding_bonus = min(len(rpt.key_findings) * 0.03, 0.1)
            score = min(rpt.confidence + evidence_bonus + finding_bonus, 1.0)
            scores[rid] = round(score, 2)
        return scores

    def execute(self, topic: str = None) -> Dict:
        """执行完整议会流程"""
        print(f"\n🏛️ 研究员议会 · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"   议题: {topic or '系统全景分析'}\n")

        # Round 1
        print("━" * 50)
        print("📋 Round 1: 独立研判")
        context = self.load_context()
        if topic:
            context["topic"] = topic
        r1 = self.round_one(context)
        for rid, rpt in r1.items():
            print(f"  {rpt.author_emoji} {rpt.author}: {rpt.perspective} "
                  f"(置信度 {rpt.confidence:.0%})")

        # Round 2
        print("\n━" * 50)
        print("⚔️ Round 2: 交叉辩论")
        r2 = self.round_two(r1)
        for debate_id, debate in r2.items():
            print(f"  [{debate.get('title', debate_id)}]")
            for cons in debate.get("consensus", []):
                print(f"    🤝 {cons}")
            for div in debate.get("divergence", []):
                print(f"    ⚡ {div}")

        # Round 3
        print("\n━" * 50)
        print("🌹 Round 3: 小红终审")
        r3 = self.round_three(r1, r2)
        verdict = r3["verdict"]
        print(f"   市场判断: {verdict['bias']}  (置信度 {verdict['overall_confidence']:.0%})")
        print(f"   多方信号: {verdict['bull_strength']}  |  空方信号: {verdict['bear_strength']}")
        if verdict["critical_flags"]:
            print(f"   🚩 关键红旗: {verdict['critical_flags'][0]}")

        # 保存
        self._save()
        return {"round1": r1, "round2": r2, "round3": r3}

    def _save(self):
        """保存议会记录"""
        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)

        # 保存结构化日志
        record = {
            "timestamp": datetime.now().isoformat(),
            "rounds": []
        }

        for r in self.rounds:
            rd = {"name": r["name"]}
            if "reports" in r:
                rd["reports"] = {
                    rid: {
                        "perspective": rpt.perspective,
                        "key_findings": rpt.key_findings,
                        "confidence": rpt.confidence,
                        "recommendations": rpt.recommendations,
                        "red_flags": rpt.red_flags,
                    }
                    for rid, rpt in r["reports"].items()
                }
            elif "debate" in r:
                rd["debate"] = r["debate"]
            elif "decision" in r:
                rd["decision"] = r["decision"]
            record["rounds"].append(rd)

        log = []
        if LOG_PATH.exists():
            try:
                log = json.loads(LOG_PATH.read_text())
            except Exception:
                pass
        log.append(record)
        if len(log) > 90:
            log = log[-90:]
        LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2))

        # 保存可读报告
        date_str = datetime.now().strftime('%Y-%m-%d')
        report_md = self._format_markdown(record)
        (REPORTS_DIR / f"议会报告-{date_str}.md").write_text(report_md)

    def _format_markdown(self, record: Dict) -> str:
        """生成议会报告 Markdown"""
        lines = [
            f"# 🏛️ 研究员议会报告",
            f"> {record['timestamp'][:19]}",
            "",
        ]
        for rd in record["rounds"]:
            lines.append(f"## {rd['name']}")
            lines.append("")
            if "reports" in rd:
                # Round 1: 独立研判
                for rid, rpt in rd["reports"].items():
                    if not isinstance(rpt, dict):
                        continue
                    cfg = RESEARCHERS.get(rid, {})
                    lines.append(f"### {cfg.get('emoji','')} {cfg.get('name', rid)}")
                    lines.append(f"**视角**: {rpt.get('perspective','')}")
                    for f in rpt.get('key_findings', []):
                        lines.append(f"- {f}")
                    conf = rpt.get('confidence', 0)
                    lines.append(f"_置信度: {conf:.0%}_")
                    flags = rpt.get('red_flags', [])
                    if flags:
                        lines.append(f"🚩 红旗: {', '.join(flags[:3])}")
                    lines.append("")
            elif "debate" in rd:
                # Round 2: 交叉辩论
                for debate_id, debate in rd["debate"].items():
                    if isinstance(debate, dict):
                        lines.append(f"### {debate.get('title', debate_id)}")
                        for cons in debate.get('consensus', []):
                            lines.append(f"- 🤝 {cons}")
                        for div in debate.get('divergence', []):
                            lines.append(f"- ⚡ {div}")
                        lines.append("")
            elif "decision" in rd:
                # Round 3: 小红终审
                d = rd["decision"]
                v = d.get("verdict", {})
                lines.append(f"**市场判断**: {v.get('bias','?')}  (置信度 {v.get('overall_confidence',0):.0%})")
                lines.append(f"**多方信号**: {v.get('bull_strength',0)}  |  **空方信号**: {v.get('bear_strength',0)}")
                if v.get('critical_flags'):
                    lines.append(f"**关键红旗**: {v['critical_flags'][0]}")
                lines.append("")
                for rec in v.get('consolidated_recommendations', []):
                    lines.append(f"- 🌹 {rec}")
                lines.append("")
        return '\n'.join(lines)


# ═══════════════════════════════════════════
# 自主研学模式
# ═══════════════════════════════════════════

def run_study_session():
    """每日自主研学 — 系统空闲时段各研究员独立深度学习"""
    print(f"📚 研究员自主研学 · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    parliament = Parliament()
    context = parliament.load_context()

    for r in parliament.researchers:
        print(f"\n{r.emoji} {r.name} 研学报导...")
        try:
            ctx = {**context, "topic": f"{r.name}自主研学"}
            report = r.analyze(ctx)
            print(f"  视角: {report.perspective}")
            print(f"  置信度: {report.confidence:.0%}")
            if report.key_findings:
                print(f"  发现: {report.key_findings[0][:60]}...")
            if report.red_flags:
                print(f"  🚩 {len(report.red_flags)} 个红旗")
        except Exception as e:
            print(f"  ❌ 研学异常: {e}")

    # 保存研学报告（v2.0: 写入实质内容）
    date_str = datetime.now().strftime('%Y-%m-%d')
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [f"# 📚 研究员自主研学报告", f"> {date_str}", ""]
    
    reports_written = 0
    for r in parliament.researchers:
        lines.append(f"## {r.emoji} {r.name}")
        try:
            # 重新 analyze 获取报告（之前的 report 变量作用域受限）
            ctx = {**context, "topic": f"{r.name}自主研学"}
            report = r.analyze(ctx)
            if report.key_findings:
                lines.append("**核心发现**:")
                for f in report.key_findings[:3]:
                    lines.append(f"- {f}")
                reports_written += 1
            if report.data_evidence:
                lines.append("**数据证据**:")
                for e in report.data_evidence[:3]:
                    lines.append(f"- {e}")
            if report.red_flags:
                lines.append("🚩 **红旗**:")
                for rf in report.red_flags[:3]:
                    lines.append(f"- {rf}")
            lines.append(f"_置信度: {report.confidence:.0%}_")
        except Exception as e:
            lines.append(f"_研学异常: {e}_")
        lines.append("")

    (REPORTS_DIR / f"研学报告-{date_str}.md").write_text('\n'.join(lines))
    
    print(f"\n✅ 研学完成 → {REPORTS_DIR / f'研学报告-{date_str}.md'}")
    print(f"   实质报告: {reports_written}/{len(parliament.researchers)} 位研究员")


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description='研究员议会 v1.0')
    p.add_argument('--study', action='store_true', help='自主研学模式')
    p.add_argument('--parliament', action='store_true', help='完整议会模式')
    p.add_argument('--topic', type=str, help='议会议题')
    p.add_argument('--report', action='store_true', help='查看最近报告')
    args = p.parse_args()

    if args.report:
        if LOG_PATH.exists():
            log = json.loads(LOG_PATH.read_text())
            print(f"📜 议会记录: {len(log)} 条")
            if log:
                last = log[-1]
                print(f"   最近: {last['timestamp'][:19]}")
                for rd in last.get("rounds", []):
                    print(f"   └ {rd['name']}")
            else:
                print("   无记录")
        else:
            print("📭 无议会记录")
    elif args.study:
        run_study_session()
    elif args.parliament:
        parliament = Parliament()
        parliament.execute(topic=args.topic)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
