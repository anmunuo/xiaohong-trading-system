#!/usr/bin/env python3
"""
researchers.py — 研究员议会 v2.0
================================
6 位研究员：数据 / 基本面 / 技术面 / 多方 / 空方 / 资金面
核心升级：自主学习者 —— 假设提出→证据积累→验证→信念更新

v2.0 新增:
  · Hypothesis 假设机制 + Bayesian 信念追踪
  · ResearcherState 跨日持久化
  · 资金面研究员（市场各类资金 + 量价关系）
  · 自动验证旧假设、生成新假设

用法:
  python3 researchers.py --study          # 自主研学模式
  python3 researchers.py --parliament     # 议会模式
  python3 researchers.py --report         # 查看最近研究报告
  python3 researchers.py --verify         # 验证过往假设
"""

import json, os, sys, re, time
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
STATE_PATH = RESEARCH_DIR / "researcher_state.json"

__version__ = "2.2.0"

# ═══════════════════════════════════════════
# v2.0 数据模型
# ═══════════════════════════════════════════

@dataclass
class Hypothesis:
    """研究员假设 —— 可跨日追踪、验证"""
    id: str                          # 唯一标识
    statement: str                   # 假设陈述
    category: str                    # 分类: market/stock/sector/data/risk
    confidence: float = 0.5          # 当前置信度 0-1 (Bayesian 后验)
    alpha: int = 1                   # 支持证据计数
    beta: int = 1                    # 反对证据计数
    evidence_for: List[str] = field(default_factory=list)
    evidence_against: List[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    verified_at: str = ""
    status: str = "active"           # active/confirmed/rejected/archived
    related_symbols: List[str] = field(default_factory=list)
    source: str = ""                 # 哪个研究员提出的

    def update_belief(self, positive: bool, evidence: str = ""):
        """Bayesian 更新: 支持→α+1, 反对→β+1"""
        if positive:
            self.alpha += 1
            self.evidence_for.append(evidence[:200])
        else:
            self.beta += 1
            self.evidence_against.append(evidence[:200])
        self.confidence = round(self.alpha / (self.alpha + self.beta), 4)
        self.updated_at = datetime.now().strftime('%Y-%m-%d %H:%M')
        # 自动判定状态
        if self.confidence >= 0.8:
            self.status = "confirmed"
        elif self.confidence <= 0.2:
            self.status = "rejected"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Hypothesis":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


class ResearcherState:
    """研究员跨日状态管理器"""

    def __init__(self):
        self.hypotheses: Dict[str, Hypothesis] = {}  # id → hypothesis
        self.verified_today: List[str] = []           # 今天验证过的假设id
        self.agenda: List[str] = []                   # 当前研究议程
        self.gaps: List[str] = []                     # 数据缺口
        self.stats: Dict = {"total_hypotheses": 0, "confirmed": 0, "rejected": 0,
                            "total_verifications": 0, "accuracy": 0.0}

    def load(self):
        """从磁盘加载状态"""
        if STATE_PATH.exists():
            data = json.loads(STATE_PATH.read_text())
            for hid, hd in data.get("hypotheses", {}).items():
                self.hypotheses[hid] = Hypothesis.from_dict(hd)
            self.agenda = data.get("agenda", [])
            self.gaps = data.get("gaps", [])
            self.stats = data.get("stats", self.stats)
            self.verified_today = []

    def save(self):
        """持久化到磁盘"""
        RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "version": __version__,
            "updated_at": datetime.now().isoformat(),
            "hypotheses": {hid: h.to_dict() for hid, h in self.hypotheses.items()},
            "agenda": self.agenda[-20:],
            "gaps": self.gaps[-20:],
            "stats": self.stats,
        }
        STATE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    def add_hypothesis(self, h: Hypothesis):
        if not h.created_at:
            h.created_at = datetime.now().strftime('%Y-%m-%d %H:%M')
        self.hypotheses[h.id] = h
        self.stats["total_hypotheses"] = len(self.hypotheses)

    def verify_hypothesis(self, hid: str, positive: bool, evidence: str = ""):
        """验证假设并更新信念"""
        if hid in self.hypotheses:
            old_status = self.hypotheses[hid].status
            self.hypotheses[hid].update_belief(positive, evidence)
            self.hypotheses[hid].verified_at = datetime.now().strftime('%Y-%m-%d %H:%M')
            self.verified_today.append(hid)
            # 更新统计
            self.stats["total_verifications"] += 1
            new_status = self.hypotheses[hid].status
            if old_status != "confirmed" and new_status == "confirmed":
                self.stats["confirmed"] += 1
            if old_status != "rejected" and new_status == "rejected":
                self.stats["rejected"] += 1

    def get_active_hypotheses(self) -> List[Hypothesis]:
        return [h for h in self.hypotheses.values() if h.status == "active"]

    def get_recent_verified(self, days: int = 3) -> List[Hypothesis]:
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        return [h for h in self.hypotheses.values()
                if h.verified_at >= cutoff]

    def add_gap(self, gap: str):
        if gap not in self.gaps:
            self.gaps.append(gap)

    def add_agenda(self, item: str):
        if item not in self.agenda:
            self.agenda.append(item)


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
    perspective: str
    key_findings: List[str]
    data_evidence: List[str]
    confidence: float
    recommendations: List[str]
    red_flags: List[str] = field(default_factory=list)
    raw_context: Dict = field(default_factory=dict)
    new_hypotheses: List[Hypothesis] = field(default_factory=list)  # 🆕
    verified_hypotheses: List[dict] = field(default_factory=list)   # 🆕


RESEARCHERS = {
    "data": {
        "name": "数据研究员",
        "emoji": "📊",
        "persona": """你是安幕诺家族的数据研究员。你主动发现数据缺口、追踪数据质量趋势、挖掘隐藏的数据洞察。

核心能力：识别数据缺口→提出获取方案→挖掘隐藏信息→排除干扰噪声。

学习方法：每天对比数据新鲜度变化趋势，当你发现某个数据源连续3天延迟，你应提出假设"该数据源可靠性下降"并追踪验证。""",
        "debate_weight": 1.0,
    },
    "fundamental": {
        "name": "基本面研究员",
        "emoji": "🏢",
        "persona": """你是安幕诺家族的基本面研究员。你从公告/财报/研报中提炼超越统计数字的洞察。

核心能力：公告深层解读→财报质量评估→行业轮动判断→情绪拐点识别。

学习方法：当你说"增持信号压倒减持"时，不止步于计数。你要提出假设"回购潮通常领先指数反弹2-4周"，然后在后续交易日验证这个时间窗口。""",
        "debate_weight": 1.2,
    },
    "technical": {
        "name": "技术面研究员",
        "emoji": "📈",
        "persona": """你是安幕诺家族的技术面研究员。你判断趋势阶段、识别反转信号、寻找最佳入场点。

核心能力：形态识别→量价关系→关键位→危险信号→操作建议。

学习方法：当你说"MA20附近整理"时，要预测"突破方向"。每次预测后追踪验证，更新你对当前市场技术特征的信念。""",
        "debate_weight": 1.0,
    },
    "bull": {
        "name": "多方研究员",
        "emoji": "🐂",
        "persona": """你是安幕诺家族的多方研究员。你是天生的乐观派，但你用数据和逻辑支撑你的乐观。

核心能力：挖掘被忽视的积极因素→寻找业绩超预期线索→识别估值洼地→跟踪产业向上拐点。

学习方法：你的每一次"看多"预测都会被追踪。如果看多标的随后上涨，你的信念增强；如果下跌，你要反思为什么遗漏了风险因素。""",
        "debate_weight": 1.0,
    },
    "bear": {
        "name": "空方研究员",
        "emoji": "🐻",
        "persona": """你是安幕诺家族的空方研究员。你无情揭示风险，但不仅仅是为了唱空——你的目标是帮助系统避免踩雷。

核心能力：财务风险识别→估值泡沫判断→利空事件预判→行业逆风预警。

学习方法：你的风险预警被验证时，你的红旗建议权重提升；被证伪时（标的在风险评级"高"的情况下反而大涨），你要重新评估自己的风险判断框架。""",
        "debate_weight": 1.0,
    },
    "flow": {
        "name": "资金面研究员",
        "emoji": "💰",
        "persona": """你是安幕诺家族的资金面研究员。你专注于全市场资金流向、主力行为、量价关系和宏观流动性的研究。

核心能力：
- 跟踪北向资金/主力资金/游资/融资融券/ETF申赎等多维资金动向
- 分析资金流入板块的逻辑和持续性
- 识别主力建仓/出货的量价特征
- 判断市场整体流动性水位和风险偏好
- 评估量价关系是否健康（放量上涨/缩量下跌/放量滞涨等）

分析框架：
1. 宏观流动性 — 社融/M2/利率/汇率对股市资金面的传导
2. 北向资金 — 外资的行业偏好、流入/流出的拐点信号
3. 主力资金 — 超大单/大单净流入板块和个股
4. 融资融券 — 杠杆资金情绪（融资余额趋势）
5. 量价关系 — 放量突破 vs 缩量阴跌 vs 放量滞涨的判断
6. 资金风格 — 当前是机构主导还是游资主导
7. ETF资金 — 行业ETF的份额变化反映的机构配置方向

学习方法：你的核心研究课题是"资金流向是否能预测股价方向"。每天验证你对资金流入板块的走势预测，追踪资金-价格领先滞后关系的时间窗口。""",
        "debate_weight": 1.1,
    },
}


# ═══════════════════════════════════════════
# 研究员基类
# ═══════════════════════════════════════════

class Researcher:
    """研究员基类 v2.0 — 带假设追踪和跨日记忆"""

    _hyp_counter = 0  # 🆕 防止同秒ID冲突

    def __init__(self, role_id: str, state: ResearcherState):
        cfg = RESEARCHERS[role_id]
        self.role_id = role_id
        self.name = cfg["name"]
        self.emoji = cfg["emoji"]
        self.persona = cfg["persona"]
        self.debate_weight = cfg["debate_weight"]
        self.state = state  # 🆕 共享状态

    def analyze(self, context: Dict) -> ResearchReport:
        raise NotImplementedError

    def verify_past_hypotheses(self, context: Dict) -> List[dict]:
        """验证该研究员过往的活跃假设，返回验证结果"""
        results = []
        my_hypotheses = [h for h in self.state.get_active_hypotheses()
                         if h.source == self.role_id]
        for h in my_hypotheses:
            # 子类覆盖此方法提供具体验证逻辑
            result = self._verify_one(h, context)
            if result:
                results.append(result)
                self.state.verify_hypothesis(h.id, result["positive"], result["evidence"])
        return results

    def _verify_one(self, h: Hypothesis, context: Dict) -> Optional[dict]:
        """子类覆盖：验证单个假设。返回 {positive: bool, evidence: str} 或 None"""
        return None

    def _make_hypothesis(self, statement: str, category: str,
                         confidence: float = 0.5, symbols: list = None) -> Hypothesis:
        """创建新假设"""
        import time
        Researcher._hyp_counter += 1
        hid = f"{self.role_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{Researcher._hyp_counter:03d}"
        return Hypothesis(
            id=hid, statement=statement, category=category,
            confidence=confidence, source=self.role_id,
            related_symbols=symbols or [],
            created_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
        )

    def get_system_prompt(self) -> str:
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
# 6位研究员实现
# ═══════════════════════════════════════════

class DataResearcher(Researcher):

    def __init__(self, state: ResearcherState):
        super().__init__("data", state)

    def analyze(self, context: Dict) -> ResearchReport:
        findings, evidence, flags, recs = [], [], [], []
        sources = context.get("data_sources", {})
        kb_files = context.get("kb_files", {})

        # 数据源状态
        ok_count = 0
        for src_name, status in sources.items():
            if status.get("ok"):
                ok_count += 1
            else:
                findings.append(f"{src_name}: 数据源异常 — {status.get('error', '未知')}")
                flags.append(f"{src_name} 数据源异常需修复")
        if ok_count == len(sources):
            findings.append(f"全部 {len(sources)} 个数据源正常")

        # 🆕 v2.2: 数据内容验证 — 不只检查连通性，还要验证数据合理性
        content_issues = self._validate_data_content(context)
        flags.extend(content_issues.get("flags", []))
        findings.extend(content_issues.get("findings", []))
        recs.extend(content_issues.get("recs", []))

        # KB时效 + 趋势追踪
        stale_count = 0
        for fname, age_h in kb_files.items():
            if age_h < 2:
                evidence.append(f"{fname} 更新及时 ({age_h:.1f}h)")
            elif age_h < 6:
                findings.append(f"{fname} 数据略旧 ({age_h:.1f}h)")
                stale_count += 1
            else:
                flags.append(f"{fname} 严重过期 ({age_h:.1f}h)")
                stale_count += 1

        # 🆕 追踪数据退化趋势
        if stale_count >= 2:
            h = self._make_hypothesis(
                f"多个数据源({stale_count}个)时效性下降，可能是上游API变更",
                "data", 0.55
            )
            self.state.add_hypothesis(h)
            findings.append(f"⚠️ {stale_count}个数据源时效下降，已创建追踪假设")

        # 数据缺口
        gaps = context.get("data_gaps", [])
        for g in gaps:
            self.state.add_gap(g)
            recs.append(f"数据缺口: {g} — 建议接入")

        # 未用数据源
        available = context.get("available_sources", [])
        used = context.get("used_sources", [])
        unused = [s for s in available if s not in used]
        if unused:
            recs.append(f"建议接入未使用数据源: {', '.join(unused[:5])}")
        else:
            recs.append("当前数据源覆盖完整")

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "数据质量巡检"),
            perspective=f"数据源 {len(sources)}个 / KB文件 {len(kb_files)}个",
            key_findings=findings, data_evidence=evidence,
            confidence=0.9 if not flags else 0.7,
            recommendations=recs, red_flags=flags,
        )

    def _validate_data_content(self, context: Dict) -> Dict:
        """v2.2: 验证数据内容合理性，不只是连通性"""
        flags, findings, recs = [], [], []

        north = context.get("north_flow", {})
        if north:
            nf_val = north.get("net_flow", 0)
            nf_source = north.get("data_source", "")
            # 交叉验证：直接用 tushare 拉原始数据比对字段
            try:
                import tushare as ts
                pro = ts.pro_api()
                for i in range(5):
                    dt = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
                    df = pro.moneyflow_hsgt(trade_date=dt)
                    if not df.empty:
                        row = df.iloc[-1]
                        north_raw = float(row.get('north_money', 0)) / 1e4
                        south_raw = float(row.get('south_money', 0)) / 1e4
                        diff_north = abs(nf_val - north_raw)
                        diff_south = abs(nf_val - south_raw)
                        if diff_south < diff_north and nf_val < 20:
                            flags.append(
                                f"北向数据疑似字段混淆: 当前{nf_val:.1f}亿更接近南向({south_raw:.1f}亿)"
                                f"而非北向({north_raw:.1f}亿) → 检查get_north_flow()字段")
                            recs.append("紧急: 验证get_north_flow()是否用ggt_ss/ggt_sz(南向)而非north_money")
                        break
            except Exception:
                pass

            if abs(nf_val) < 10 and nf_val != 0:
                findings.append(f"北向{nf_val:.1f}亿偏低，与万亿成交额不匹配，可能数据失真")

        return {"flags": flags, "findings": findings, "recs": recs}

    def _verify_one(self, h: Hypothesis, context: Dict) -> Optional[dict]:
        # 验证数据退化假设：重新检查当前数据源状态
        if "数据源" in h.statement and "时效" in h.statement:
            kb = context.get("kb_files", {})
            stale_now = sum(1 for v in kb.values() if v >= 6)
            return {"positive": stale_now == 0, "evidence": f"当前过期数据源: {stale_now}个"}
        return None


class FundamentalResearcher(Researcher):

    def __init__(self, state: ResearcherState):
        super().__init__("fundamental", state)

    def analyze(self, context: Dict) -> ResearchReport:
        findings, evidence, flags, recs = [], [], [], []
        new_hyps = []
        announcements = context.get("announcements", [])

        buyback = sum(1 for a in announcements if any(
            kw in str(a) for kw in ["回购", "增持", "注销"]))
        sell = sum(1 for a in announcements if any(
            kw in str(a) for kw in ["减持", "质押", "冻结"]))
        mna = sum(1 for a in announcements if any(
            kw in str(a) for kw in ["要约收购", "并购", "重组"]))

        if buyback > sell:
            ratio = buyback / max(sell, 1)
            findings.append(f"增持/回购({buyback}条) vs 减持({sell}条), 比={ratio:.1f}:1")
            evidence.append(f"内部人行为偏多: 回购增持{buyback} vs 减持{sell}")
            # 🆕 生成假设：回购潮领先指数反弹
            if ratio > 5:
                h = self._make_hypothesis(
                    f"回购/减持比 {ratio:.1f}:1 处于极高水平，4周内上证指数上涨概率>60%",
                    "market", 0.55
                )
                new_hyps.append(h)
                self.state.add_hypothesis(h)
        elif sell > buyback:
            flags.append(f"减持信号({sell}条)多于回购({buyback}条)，需警惕")

        if mna > 0:
            findings.append(f"M&A活跃({mna}条)，资本运作密集期")

        # 板块情绪
        sectors = context.get("sector_sentiment", {})
        hot = [s for s, v in sectors.items() if v.get("score", 0) > 70]
        cold = [s for s, v in sectors.items() if v.get("score", 0) < 30]
        if hot:
            findings.append(f"板块热度: {', '.join(hot[:3])}")
        if cold:
            recs.append(f"关注超跌板块: {', '.join(cold[:3])}")

        # 研报
        broker = context.get("broker_views", [])
        buy_cnt = sum(1 for b in broker if "买入" in str(b)) if broker else 0
        if broker:
            evidence.append(f"券商覆盖{len(broker)}只，买入{buy_cnt}只")

        # 财报分析
        pool_stocks = context.get("pool_stocks", [])
        if pool_stocks:
            try:
                from data_pipeline import get_financial_summary
                fin_scores = []
                for s in pool_stocks[:8]:
                    code = s.get('code', '')
                    fs = get_financial_summary(code)
                    if fs.get('data_source') != 'no_data':
                        fin_scores.append((s.get('name', code), fs['score']))
                        if fs['score'] >= 80:
                            findings.append(f"{s.get('name','')}: 财务优秀(评分{fs['score']})")
                        elif fs['score'] < 40:
                            flags.append(f"{s.get('name','')}: 财务堪忧(评分{fs['score']})")
                if fin_scores:
                    avg = sum(s[1] for s in fin_scores) / len(fin_scores)
                    evidence.append(f"池内财务均分: {avg:.0f}/100")
            except Exception:
                pass

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "基本面分析"),
            perspective=f"公告{len(announcements)}条 / 板块{len(sectors)}个",
            key_findings=findings or ["基本面信号中性"],
            data_evidence=evidence,
            confidence=0.75 if not flags else 0.6,
            recommendations=recs or ["维持现有持仓基本面评估"],
            red_flags=flags, new_hypotheses=new_hyps,
        )

    def _verify_one(self, h: Hypothesis, context: Dict) -> Optional[dict]:
        if "回购" in h.statement and "上证" in h.statement:
            idx = context.get("index_data", {})
            sh = idx.get("asia", {}).get("shanghai", [0, 0])
            change = sh[1] if len(sh) > 1 else 0
            age_days = (datetime.now() - datetime.strptime(h.created_at[:10], '%Y-%m-%d')).days
            return {"positive": change > 0, "evidence": f"创建{age_days}天后上证{change:+.2f}%"}
        return None


class TechnicalResearcher(Researcher):

    def __init__(self, state: ResearcherState):
        super().__init__("technical", state)

    def analyze(self, context: Dict) -> ResearchReport:
        findings, evidence, flags, recs = [], [], [], []
        new_hyps = []
        pool = context.get("pool_stocks", [])

        for s in pool:
            code = s.get("code", "")
            name = s.get("name", "")
            dev = float(s.get("ma20_dev", 0))
            tech = float(s.get("technical", 50))

            if tech >= 65:
                findings.append(f"{name}: 技术面强势(评分{tech})")
            if -2 <= dev <= 2:
                recs.append(f"{name}: MA20附近整理，等突破确认")
                # 🆕 生成方向预测假设
                h = self._make_hypothesis(
                    f"{name}({code}) MA20附近盘整，预计5日内选择向上突破",
                    "stock", 0.5, [code]
                )
                new_hyps.append(h)
                self.state.add_hypothesis(h)
            elif dev > 8:
                flags.append(f"{name}: 偏离MA20 +{dev:.0f}%，追高风险")
            elif dev < -8:
                findings.append(f"{name}: 超跌{dev:.0f}%，关注止跌")

        if pool:
            avg_tech = sum(float(s.get("technical", 50)) for s in pool) / len(pool)
            tag = "偏强" if avg_tech > 60 else ("偏弱" if avg_tech < 40 else "中性")
            findings.insert(0, f"池整体技术面{tag}(均分{avg_tech:.0f})")

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "技术面扫描"),
            perspective=f"池内{len(pool)}只标的形态评估",
            key_findings=findings or ["无显著技术信号"],
            data_evidence=evidence,
            confidence=0.7,
            recommendations=recs or ["观望为主，等待明确信号"],
            red_flags=flags, new_hypotheses=new_hyps,
        )

    def _verify_one(self, h: Hypothesis, context: Dict) -> Optional[dict]:
        if "突破" in h.statement and h.related_symbols:
            code = h.related_symbols[0]
            pool = context.get("pool_stocks", [])
            for s in pool:
                if s.get("code") == code:
                    dev = float(s.get("ma20_dev", 0))
                    return {"positive": dev > 0, "evidence": f"{code} MA20偏离{dev:+.1f}%"}
        return None


class BullResearcher(Researcher):

    def __init__(self, state: ResearcherState):
        super().__init__("bull", state)

    def analyze(self, context: Dict) -> ResearchReport:
        findings, evidence, recs = [], [], []
        new_hyps = []
        pool = context.get("pool_stocks", [])
        insights = context.get("kb_insights", [])

        for s in pool:
            name = s.get("name", "")
            code = s.get("code", "")
            sentiment = float(s.get("sentiment", 50))
            event = float(s.get("event", 50))

            if sentiment >= 70:
                findings.append(f"{name}: 情绪面积极({sentiment})")
            if event >= 65:
                findings.append(f"{name}: 事件催化密集({event})")
                h = self._make_hypothesis(
                    f"{name}({code}) 事件催化密集，5日内上涨概率>60%",
                    "stock", 0.55, [code]
                )
                new_hyps.append(h)
                self.state.add_hypothesis(h)

            for ins in insights:
                text = str(ins)
                if code in text and any(kw in text for kw in
                    ["回购", "增持", "利好", "突破", "中标", "订单", "增长", "注销", "激励"]):
                    evidence.append(f"{name}: KB洞察确认正面信号")

        if not findings:
            findings.append("当前池内标的无明显看多信号")

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "多方研判"),
            perspective=f"池内{len(pool)}只标的看多因素",
            key_findings=findings, data_evidence=evidence,
            confidence=0.7 if evidence else 0.5,
            recommendations=recs or ["观望——多方信号不足"],
            new_hypotheses=new_hyps,
        )

    def _verify_one(self, h: Hypothesis, context: Dict) -> Optional[dict]:
        if h.related_symbols:
            code = h.related_symbols[0]
            pool = context.get("pool_stocks", [])
            for s in pool:
                if s.get("code") == code:
                    chg = float(s.get("change_pct", 0))
                    return {"positive": chg > 0, "evidence": f"{code} 涨跌{chg:+.1f}%"}
        return None


class BearResearcher(Researcher):

    def __init__(self, state: ResearcherState):
        super().__init__("bear", state)

    def analyze(self, context: Dict) -> ResearchReport:
        findings, evidence, flags = [], [], []
        pool = context.get("pool_stocks", [])
        insights = context.get("kb_insights", [])

        for s in pool:
            name = s.get("name", "")
            code = s.get("code", "")
            risk = s.get("risk_level", "中")
            mkt_cap = float(s.get("market_cap", 0))

            if risk == "高":
                findings.append(f"{name}: 风险评级「高」")
            if 0 < mkt_cap < 80:
                flags.append(f"{name}: 小市值({mkt_cap:.0f}亿)，流动性风险")
                # 🆕 生成风险追踪假设
                h = self._make_hypothesis(
                    f"{name}({code}) 小市值({mkt_cap:.0f}亿)流动性风险将导致日内波动>5%",
                    "risk", 0.5, [code]
                )
                self.state.add_hypothesis(h)

            for ins in insights:
                text = str(ins)
                if code in text and any(kw in text for kw in
                    ["减持", "终止", "亏损", "诉讼", "处罚", "退市", "警示", "冻结"]):
                    flags.append(f"{name}: KB洞察发现风险信号")

        if not findings and not flags:
            findings.append("当前池内标的无明显看空信号")

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "空方研判"),
            perspective=f"池内{len(pool)}只标的风险因素",
            key_findings=findings, data_evidence=evidence,
            confidence=0.7,
            recommendations=["高风偏标的控制仓位 ≤ 11.1%，严格执行止损"],
            red_flags=flags,
        )

    def _verify_one(self, h: Hypothesis, context: Dict) -> Optional[dict]:
        if "波动" in h.statement and h.related_symbols:
            code = h.related_symbols[0]
            pool = context.get("pool_stocks", [])
            for s in pool:
                if s.get("code") == code:
                    chg = abs(float(s.get("change_pct", 0)))
                    return {"positive": chg > 5,
                            "evidence": f"{code} 波动{chg:.1f}%"}
        return None


class CapitalFlowResearcher(Researcher):
    """🆕 资金面研究员 — 全市场资金流向 + 量价关系分析"""

    def __init__(self, state: ResearcherState):
        super().__init__("flow", state)

    def analyze(self, context: Dict) -> ResearchReport:
        findings, evidence, flags, recs = [], [], [], []
        new_hyps = []

        # 1. 北向资金 — 先验证数据质量再使用
        north = context.get("north_flow", {})
        nf_val = north.get("net_flow", 0)
        nf_source = north.get("data_source", "unknown")
        nf_quality = north.get("_quality", "")

        # 🆕 v2.2: 前置数据验证 — 不盲目信任输入
        if nf_val != 0:
            # 验证1: 北向<10亿对万亿成交额来说异常偏小
            if abs(nf_val) < 10:
                flags.append(
                    f"🚨 北向{nf_val:.1f}亿严重偏低(正常日30-100亿)，疑似数据源字段错误"
                    f"（可能把南向ggt_ss/ggt_sz当北向）→ 已标记红旗"
                )
                recs.append("暂停基于北向数据的决策，先修复get_north_flow()字段映射")
                # 不生成基于失真数据的假设
            else:
                direction = "净流入" if nf_val > 0 else "净流出"
                findings.append(f"北向资金: {nf_val:.1f}亿{direction} (来源:{nf_source})")
                if nf_val > 30:
                    recs.append("北向大幅流入，关注外资偏好板块")
                    h = self._make_hypothesis(
                        f"北向单日流入{nf_val:.0f}亿，次日上证上涨概率>60%",
                        "market", 0.55
                    )
                    new_hyps.append(h)
                    self.state.add_hypothesis(h)
                elif nf_val < -30:
                    flags.append(f"北向大幅流出{nf_val:.0f}亿，外资撤离信号")
        else:
            evidence.append(f"北向实时数据不可用，使用{str(nf_quality) or 'T-1'}数据")

        # 2. 全市场资金流向
        mf = context.get("market_flow", {})
        main_net = mf.get("main_net", 0)
        retail_net = mf.get("retail_net", 0)
        if main_net != 0:
            findings.append(f"主力资金: {main_net/1e8:.0f}亿{'流入'if main_net>0 else '流出'}")
            # 主力 vs 散户背离是重要信号
            if main_net > 0 and retail_net < 0:
                findings.append("⚠️ 主力流入但散户流出——聪明钱在接盘")
            elif main_net < 0 and retail_net > 0:
                flags.append("主力出货散户接盘——危险信号")

        # 3. 板块资金流入Top3
        top_stocks = context.get("top_flow_stocks", [])
        if top_stocks:
            sector_flow = {}
            for s in top_stocks[:20]:
                sec = s.get("sector", "综合")
                nf = float(s.get("net_flow", 0))
                sector_flow[sec] = sector_flow.get(sec, 0) + nf
            if sector_flow:
                top3 = sorted(sector_flow.items(), key=lambda x: x[1], reverse=True)[:3]
                findings.append(f"板块资金TOP3: " + ", ".join(
                    f"{s}({v/1e4:.0f}万)" for s, v in top3))
                # 🆕 生成板块资金持续性假设
                top_sec = top3[0][0]
                h = self._make_hypothesis(
                    f"资金流入最多的板块{top_sec}将在3日内持续获得资金青睐",
                    "sector", 0.5
                )
                new_hyps.append(h)
                self.state.add_hypothesis(h)

        # 4. 融资融券情绪
        margin = context.get("margin_data", {})
        if margin:
            bal = margin.get("margin_balance", 0)
            findings.append(f"融资余额: {bal/1e8:.0f}亿")

        # 5. 量价关系诊断
        pool = context.get("pool_stocks", [])
        abnormal_vol = []
        for s in pool:
            code = s.get("code", "")
            name = s.get("name", "")
            chg = float(s.get("change_pct", 0))
            vol_ratio = float(s.get("volume_ratio", 1.0))
            if vol_ratio > 2.5:
                if chg > 5:
                    findings.append(f"{name}: 放量上涨(chg{chg:+.1f}% vol{vol_ratio:.1f}x)——强势突破")
                elif chg < -3:
                    flags.append(f"{name}: 放量下跌——出货信号")
                else:
                    abnormal_vol.append(name)

        if abnormal_vol:
            recs.append(f"关注异常放量标的: {', '.join(abnormal_vol)}")

        # 6. 杠杆资金风险偏好
        ins = context.get("kb_insights", [])
        margin_bull = sum(1 for i in ins if "融资买入" in str(i) or "杠杆" in str(i))
        if margin_bull > 5:
            findings.append(f"杠杆资金活跃({margin_bull}条相关事件)")

        return ResearchReport(
            author=self.name, author_emoji=self.emoji,
            timestamp=datetime.now().isoformat(),
            topic=context.get("topic", "资金面分析"),
            perspective=f"北向{nf_val:.0f}亿 / 主力{main_net/1e8:.0f}亿 / 量价{len(pool)}只",
            key_findings=findings or ["资金面信号中性，无明显异常"],
            data_evidence=evidence,
            confidence=0.7 if findings else 0.5,
            recommendations=recs or ["维持现有资金面评估"],
            red_flags=flags, new_hypotheses=new_hyps,
        )

    def _verify_one(self, h: Hypothesis, context: Dict) -> Optional[dict]:
        if "板块" in h.statement and "资金" in h.statement:
            top = context.get("top_flow_stocks", [])
            if top:
                sec_flows = {}
                for s in top[:20]:
                    sec_flows[s.get("sector","")] = sec_flows.get(s.get("sector",""), 0) + float(s.get("net_flow",0))
                top_sec = max(sec_flows, key=sec_flows.get) if sec_flows else ""
                target_sec = h.statement.split("板块")[1].split("将")[0].strip()
                return {"positive": target_sec in top_sec,
                        "evidence": f"当前资金TOP板块: {top_sec}"}
        if "北向" in h.statement and "上证" in h.statement:
            idx = context.get("index_data", {})
            sh = idx.get("asia", {}).get("shanghai", [0, 0])
            chg = sh[1] if len(sh) > 1 else 0
            return {"positive": chg > 0, "evidence": f"上证{chg:+.2f}%"}
        return None


# ═══════════════════════════════════════════
# 研究员工厂
# ═══════════════════════════════════════════

def get_all_researchers(state: ResearcherState) -> List[Researcher]:
    return [
        DataResearcher(state),
        FundamentalResearcher(state),
        TechnicalResearcher(state),
        BullResearcher(state),
        BearResearcher(state),
        CapitalFlowResearcher(state),  # 🆕
    ]


# ═══════════════════════════════════════════
# 议会 (保持不变，增加资金面研究员)
# ═══════════════════════════════════════════

class Parliament:
    """研究员议会 — 3轮辩论 → 小红终审"""

    def __init__(self):
        self.state = ResearcherState()
        self.state.load()
        self.researchers = get_all_researchers(self.state)

    def load_context(self) -> Dict:
        """加载当日研究上下文"""
        ctx = {
            "data_sources": {}, "kb_files": {}, "announcements": [],
            "sector_sentiment": {}, "broker_views": [], "pool_stocks": [],
            "kb_insights": [], "data_gaps": [], "available_sources": [],
            "used_sources": [], "data_conflicts": [],
            "north_flow": {}, "market_flow": {}, "top_flow_stocks": [],
            "margin_data": {}, "index_data": {},
        }

        try:
            # KB数据
            mega_path = KB_DIR / "mega_latest.json"
            if mega_path.exists():
                mega = json.loads(mega_path.read_text())
                modules = mega.get("modules", {})
                ctx["announcements"] = modules.get("announcements", {}).get("data", [])
                ctx["kb_insights"] = []
                ins_path = DATA_DIR / "kb" / "kb_insights.json"
                if ins_path.exists():
                    ins_data = json.loads(ins_path.read_text())
                    ctx["kb_insights"] = ins_data.get("insights", [])

            # 数据源状态
            for f in KB_DIR.glob("*.json"):
                age = (datetime.now().timestamp() - f.stat().st_mtime) / 3600
                ctx["kb_files"][f.name] = round(age, 1)

            # 推荐池
            pool_path = SCRIPT_DIR / "data" / "daily_pool.json"
            if pool_path.exists():
                pool = json.loads(pool_path.read_text())
                ctx["pool_stocks"] = pool.get("recommendations", [])

            # 数据源状态
            from data_pipeline import check_data_health, get_north_flow, get_market_money_flow, get_top_flow_stocks, get_index_data
            health = check_data_health()
            ctx["data_sources"]["push2"] = {"ok": health.get("status") == "ok",
                                              "error": health.get("detail", "")}
            ctx["north_flow"] = get_north_flow()
            ctx["market_flow"] = get_market_money_flow()
            ctx["top_flow_stocks"] = get_top_flow_stocks(20)
            ctx["index_data"] = get_index_data()

        except Exception:
            pass

        return ctx

    def debate(self, topic: str) -> Dict:
        """3轮辩论 → 小红终审"""
        context = self.load_context()
        context["topic"] = topic
        reports = []

        # 第1轮: 独立研判
        for r in self.researchers:
            try:
                report = r.analyze(context)
                reports.append(report)
            except Exception:
                pass

        # 第2轮: 交叉质疑
        bull_findings = []
        bear_flags = []
        for rp in reports:
            if rp.author_emoji == "🐂":
                bull_findings = rp.key_findings
            if rp.author_emoji == "🐻":
                bear_flags = rp.red_flags

        cross_findings = []
        if bull_findings and bear_flags:
            overlap = set(bull_findings) & set(str(f) for f in bear_flags)
            if overlap:
                cross_findings.append(f"⚠️ 多空分歧: {list(overlap)[:3]}")
            else:
                cross_findings.append("多空双方无直接冲突——市场方向不明")

        # 第3轮: 小红终审
        total_bull = sum(1 for r in reports if len(r.key_findings) > 0 and r.author_emoji in ["🐂","📈"])
        total_bear = sum(1 for r in reports if len(r.red_flags) > 0 and r.author_emoji in ["🐻","📊"])

        verdict = {
            "topic": topic,
            "timestamp": datetime.now().isoformat(),
            "bull_signals": total_bull,
            "bear_signals": total_bear,
            "bias": "偏多" if total_bull > total_bear else ("偏空" if total_bear > total_bull else "中性"),
            "confidence": round(0.5 + abs(total_bull - total_bear) * 0.1, 2),
            "red_flags": [f for r in reports for f in r.red_flags],
            "recommendations": [rec for r in reports for rec in r.recommendations],
            "hypotheses_created": sum(len(r.new_hypotheses) for r in reports),
        }

        # 持久化日志
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        logs = []
        if LOG_PATH.exists():
            logs = json.loads(LOG_PATH.read_text())
        logs.append(verdict)
        LOG_PATH.write_text(json.dumps(logs[-100:], ensure_ascii=False, indent=2))

        return {**verdict, "reports": reports}


# ═══════════════════════════════════════════
# 🆕 v2.1 个股级研究员分析 — 渗透到全链路
# ═══════════════════════════════════════════

def build_stock_context(code: str, name: str = "") -> Dict:
    """
    为单只股票构建研究员分析所需的完整上下文。
    拉取：实时行情、财务、K线+MA、资金流向、KB洞察
    """
    ctx = {
        "topic": f"个股深度分析: {name or code}",
        "pool_stocks": [],
        "kb_insights": [],
        "north_flow": {},
        "market_flow": {},
        "top_flow_stocks": [],
        "margin_data": {},
        "index_data": {},
        "announcements": [],
        "sector_sentiment": {},
        "broker_views": [],
        "data_sources": {},
        "kb_files": {},
        "_errors": [],
    }

    try:
        from data_pipeline import (
            get_stock_realtime, get_financial_summary,
            get_historical_k_with_ma, get_top_flow_stocks,
            get_north_flow, get_market_money_flow, get_index_data
        )

        # 数据源追踪 — 每步拉取都标记状态
        _ds = ctx["data_sources"]

        # 1. 实时行情
        try:
            rt = get_stock_realtime([code])
            if code in rt:
                stock = rt[code]
                name = name or stock.get("name", "")
                stock_info = {
                    "code": code,
                    "name": name,
                    "close": stock.get("close", 0),
                    "change_pct": stock.get("change_pct", 0),
                    "open": stock.get("open", 0),
                    "high": stock.get("high", 0),
                    "low": stock.get("low", 0),
                    "volume": stock.get("volume", 0),
                    "amount": stock.get("amount", 0),
                }
                ctx["pool_stocks"] = [stock_info]
                _ds["realtime"] = {"ok": True, "source": rt[code].get("data_source", "sina")}
        except Exception as e:
            ctx["_errors"].append(f"行情: {e}")
            ctx["pool_stocks"] = [{"code": code, "name": name}]
            _ds["realtime"] = {"ok": False, "error": str(e)[:80]}

        # 2. 财务数据
        try:
            fin = get_financial_summary(code)
            if fin and fin.get("data_source") != "no_data":
                ctx["pool_stocks"][0]["financial_score"] = fin.get("score", 50)
                ctx["pool_stocks"][0]["financial_highlights"] = fin.get("highlights", [])
                ctx["pool_stocks"][0]["financial_risks"] = fin.get("risks", [])
                ctx["pool_stocks"][0]["roe"] = fin.get("roe")
                ctx["pool_stocks"][0]["debt_ratio"] = fin.get("debt_ratio")
                ctx["pool_stocks"][0]["profit_growth"] = fin.get("profit_growth")
                _ds["financial"] = {"ok": True, "score": fin.get("score")}
            else:
                _ds["financial"] = {"ok": False, "error": "无数据"}
        except Exception as e:
            ctx["_errors"].append(f"财务: {e}")
            _ds["financial"] = {"ok": False, "error": str(e)[:80]}

        # 3. K线+MA (用于技术面分析)
        #    get_historical_k_with_ma 返回: {code: [{date,close,volume,ma5,ma10,peTTM,pbMRQ,turn},...]}
        try:
            kline = get_historical_k_with_ma([code], days=60)
            bars = kline.get(code, [])
            if isinstance(bars, list) and bars:
                closes = [b.get('close', 0) for b in bars]
                ctx["pool_stocks"][0]["close_history"] = closes
                last = bars[-1]
                ctx["pool_stocks"][0]["ma5"] = last.get("ma5")
                ctx["pool_stocks"][0]["ma10"] = last.get("ma10")
                # MA20 自算
                if len(closes) >= 20:
                    ma20_val = sum(closes[-20:]) / 20
                    ctx["pool_stocks"][0]["ma20"] = round(ma20_val, 2)
                    ctx["pool_stocks"][0]["ma20_dev"] = round(
                        (closes[-1] - ma20_val) / ma20_val * 100, 1) if ma20_val else 0
                ctx["pool_stocks"][0]["pe_ttm"] = last.get("peTTM")
                ctx["pool_stocks"][0]["pb_mrq"] = last.get("pbMRQ")
                ctx["pool_stocks"][0]["turnover"] = last.get("turn")
                _ds["kline"] = {"ok": True, "bars": len(bars), "source": "baostock"}
            else:
                _ds["kline"] = {"ok": False, "error": "无K线数据"}
        except Exception as e:
            ctx["_errors"].append(f"K线: {e}")
            _ds["kline"] = {"ok": False, "error": str(e)[:80]}

        # 4. 资金流向 (从TOP股票中筛出此code)
        try:
            top20 = get_top_flow_stocks(20)
            ctx["top_flow_stocks"] = top20
            for s in top20:
                if str(s.get("code", "")) == str(code):
                    ctx["pool_stocks"][0]["net_flow"] = s.get("net_flow", 0)
                    ctx["pool_stocks"][0]["volume_ratio"] = s.get("volume_ratio", 1.0)
                    ctx["pool_stocks"][0]["main_net"] = s.get("main_net", 0)
                    _ds["fund_flow"] = {"ok": True, "source": "push2"}
                    break
            else:
                _ds["fund_flow"] = {"ok": True, "note": "不在TOP20"}
        except Exception as e:
            ctx["_errors"].append(f"资金流向: {e}")
            _ds["fund_flow"] = {"ok": False, "error": str(e)[:80]}

        # 5. 宏观资金面
        try:
            ctx["north_flow"] = get_north_flow()
            ctx["market_flow"] = get_market_money_flow()
            ctx["index_data"] = get_index_data()
            _ds["macro"] = {"ok": True, "source": "tushare+akshare"}
        except Exception:
            _ds["macro"] = {"ok": False, "error": "宏观数据拉取失败"}

        # 6. KB洞察 (与code相关)
        try:
            kb_path = SCRIPT_DIR / "data" / "kb" / "kb_insights.json"
            if kb_path.exists():
                ins = json.loads(kb_path.read_text())
                all_ins = ins.get("insights", [])
                ctx["kb_insights"] = [
                    i for i in all_ins
                    if str(code) in str(i) or (name and name in str(i))
                ][:10]
        except Exception:
            pass

        # 7. KB数据源时效
        try:
            for f in KB_DIR.glob("*.json"):
                age = (datetime.now().timestamp() - f.stat().st_mtime) / 3600
                ctx["kb_files"][f.name] = round(age, 1)
        except Exception:
            pass

    except Exception as e:
        ctx["_errors"].append(f"上下文构建: {e}")

    return ctx


def analyze_stock(code: str, name: str = "") -> Dict:
    """
    🆕 v2.1 个股研究员全维度分析。

    拉取个股数据 → 6位研究员逐一分析 → 交叉汇总。
    返回可直接嵌入 daily_pool recommendation 的 researcher_analysis 字段。
    """
    state = ResearcherState()
    state.load()
    researchers = get_all_researchers(state)

    context = build_stock_context(code, name)

    reports = {}
    flags_aggregated = []
    bull_signals = 0
    bear_signals = 0

    for r in researchers:
        try:
            report = r.analyze(context)
            reports[r.role_id] = {
                "author": r.name,
                "emoji": r.emoji,
                "perspective": report.perspective,
                "key_findings": report.key_findings[:5] if report.key_findings else [],
                "data_evidence": report.data_evidence[:3] if report.data_evidence else [],
                "confidence": report.confidence,
                "recommendations": report.recommendations[:3] if report.recommendations else [],
                "red_flags": report.red_flags[:5] if report.red_flags else [],
            }
            # 统计多空
            if r.role_id in ("bull", "technical"):
                if report.confidence >= 0.6 and report.key_findings:
                    bull_signals += 1
            if r.role_id in ("bear",):
                if report.red_flags and len(report.red_flags) > 0:
                    bear_signals += 1
            flags_aggregated.extend(report.red_flags[:3] if report.red_flags else [])
        except Exception as e:
            reports[r.role_id] = {
                "author": r.name, "emoji": r.emoji,
                "perspective": f"分析异常: {e}",
                "confidence": 0.0,
                "red_flags": [f"{r.name}分析失败: {str(e)[:100]}"]
            }

    # 交叉分析
    bias = "偏多" if bull_signals > bear_signals else (
        "偏空" if bear_signals > bull_signals else "中性"
    )

    return {
        "timestamp": datetime.now().isoformat(),
        "version": "v2.1",
        "reports": reports,
        "cross_analysis": {
            "bias": bias,
            "bull_votes": bull_signals,
            "bear_votes": bear_signals,
            "aggregated_flags": list(dict.fromkeys(flags_aggregated))[:8],
            "consensus_findings": _extract_consensus(reports),
            "data_errors": context.get("_errors", []),
        }
    }


def _extract_consensus(reports: Dict) -> List[str]:
    """提取至少2位研究员共同关注的发现"""
    from collections import Counter
    keywords_counter = Counter()
    keyword_map = {}

    sector_kw = ["突破", "反弹", "放量", "缩量", "均线", "支撑", "压力",
                 "资金流入", "资金流出", "主力", "北向", "融资",
                 "低估", "高估", "回购", "增持", "减持", "反转",
                 "风险", "超买", "超卖", "背离", "盘整", "上涨", "下跌"]

    for rid, rpt in reports.items():
        for f in rpt.get("key_findings", []):
            for kw in sector_kw:
                if kw in str(f):
                    keywords_counter[kw] += 1
                    if kw not in keyword_map:
                        keyword_map[kw] = []
                    keyword_map[kw].append(f[:80])

    consensus = []
    for kw, cnt in keywords_counter.most_common(5):
        if cnt >= 2:
            consensus.append(f"[{cnt}位研究员] {kw}: {keyword_map[kw][0]}")

    return consensus[:5]


def query_stock(code: str, name: str = "") -> str:
    """
    🆕 用户查询个股 → 返回格式化分析报告供飞书展示。
    CLI: python3 researchers.py --query 600519
    """
    analysis = analyze_stock(code, name)
    cross = analysis["cross_analysis"]
    reports = analysis["reports"]

    stock_name = name or code

    lines = [
        f"# 🔬 研究员深度分析: {stock_name}({code})",
        f"> 分析时间: {analysis['timestamp'][:19]}  |  bias: {cross['bias']}  "
        f"(多{cross['bull_votes']} 空{cross['bear_votes']})",
        "",
    ]

    if cross["consensus_findings"]:
        lines.append("## 🤝 研究员共识")
        for c in cross["consensus_findings"]:
            lines.append(f"- {c}")
        lines.append("")

    order = ["fundamental", "technical", "flow", "bull", "bear", "data"]
    for rid in order:
        if rid not in reports:
            continue
        r = reports[rid]
        lines.append(f"### {r['emoji']} {r['author']}")
        lines.append(f"**视角**: {r['perspective']}")
        lines.append(f"_置信度: {r['confidence']:.0%}_")
        if r['key_findings']:
            for f in r['key_findings'][:3]:
                lines.append(f"- {f}")
        if r['red_flags']:
            lines.append(f"🚩 " + " · ".join(r['red_flags'][:3]))
        lines.append("")

    if cross["aggregated_flags"]:
        lines.append("## ⚠️ 红旗汇总")
        for f in cross["aggregated_flags"][:5]:
            lines.append(f"- 🚩 {f}")
        lines.append("")

    if cross.get("data_errors"):
        lines.append("## ⚙️ 数据获取异常")
        for e in cross["data_errors"]:
            lines.append(f"- ⚡ {e}")
        lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════

def run_study_session():
    """v2.0 自主研学：分析→验证旧假设→生成新假设→保存报告"""
    print(f"📚 研究员自主研学 v{__version__} · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    parliament = Parliament()
    context = parliament.load_context()
    state = parliament.state

    # 显示状态概览
    active_h = state.get_active_hypotheses()
    print(f"\n🧠 研究员状态: {len(state.hypotheses)}个假设 "
          f"(活跃{len(active_h)}, 确认{state.stats['confirmed']}, "
          f"驳回{state.stats['rejected']})")
    if state.agenda:
        print(f"📋 研究议程: {state.agenda[-3:]}")

    all_reports = []
    total_new_hyps = 0

    for r in parliament.researchers:
        print(f"\n{r.emoji} {r.name}")
        try:
            # 1. 验证过往假设
            verified = r.verify_past_hypotheses(context)
            if verified:
                for v in verified:
                    icon = "✅" if v["positive"] else "❌"
                    print(f"  验证假设: {icon} {v['evidence'][:80]}")

            # 2. 当日分析
            ctx = {**context, "topic": f"{r.name}自主研学"}
            report = r.analyze(ctx)
            all_reports.append(report)

            print(f"  视角: {report.perspective}")
            print(f"  置信度: {report.confidence:.0%}")
            if report.key_findings:
                print(f"  发现: {report.key_findings[0][:80]}")
            if report.new_hypotheses:
                total_new_hyps += len(report.new_hypotheses)
                print(f"  🆕 新假设: {len(report.new_hypotheses)}个")
            if report.red_flags:
                print(f"  🚩 {len(report.red_flags)}个红旗")
        except Exception as e:
            print(f"  ❌ 异常: {e}")

    # 保存状态
    state.save()
    print(f"\n💾 状态已保存: {len(state.hypotheses)}个假设, "
          f"今日验证{len(state.verified_today)}个, 新增{total_new_hyps}个")

    # 保存报告
    date_str = datetime.now().strftime('%Y-%m-%d')
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    lines = [f"# 📚 研究员自主研学报告 v{__version__}",
             f"> {date_str}  |  状态: {len(state.hypotheses)}假设 "
             f"(确认{state.stats['confirmed']}/驳回{state.stats['rejected']})",
             ""]

    # 假设追踪面板
    if active_h:
        lines.append("## 🧠 活跃假设")
        for h in active_h[:5]:
            lines.append(f"- [{h.source}] {h.statement} "
                        f"(置信度:{h.confidence:.0%} α:{h.alpha} β:{h.beta})")
        lines.append("")

    for r in parliament.researchers:
        lines.append(f"## {r.emoji} {r.name}")
        try:
            ctx = {**context, "topic": f"{r.name}自主研学"}
            report = r.analyze(ctx)
            if report.key_findings:
                lines.append("**核心发现**:")
                for f in report.key_findings[:3]:
                    lines.append(f"- {f}")
            if report.data_evidence:
                lines.append("**数据证据**:")
                for e in report.data_evidence[:3]:
                    lines.append(f"- {e}")
            if report.red_flags:
                lines.append("🚩 **红旗**:")
                for rf in report.red_flags[:3]:
                    lines.append(f"- {rf}")
            if report.new_hypotheses:
                lines.append("🆕 **新假设**:")
                for h in report.new_hypotheses[:3]:
                    lines.append(f"- {h.statement} (置信度:{h.confidence:.0%})")
            lines.append(f"_置信度: {report.confidence:.0%}_\n")
        except Exception as e:
            lines.append(f"_异常: {e}_\n")

    report_path = REPORTS_DIR / f"研学报告-{date_str}.md"
    report_path.write_text('\n'.join(lines))
    print(f"📁 报告: {report_path}")

    return all_reports


def run_quick_parliament(code: str, name: str = "") -> Dict:
    """
    🆕 v2.3 快速单票议会 — 盘中侦察兵调用。

    2 轮快速研判 (独立研判 → 小红终审)，适合盘中实时决策。
    与完整议会不同：砍掉交叉辩论轮、不生成独立报告文件。

    返回:
      {
        bias: "偏多" | "偏空" | "中性",
        confidence: 0.0-1.0,
        bull_signals: int,
        bear_signals: int,
        red_flags: [str],
        passed: bool,          # confidence ≥ 0.5 且 bias != "偏空"
        duration_s: float      # 耗时 (秒)
      }
    """
    t0 = time.time()
    state = ResearcherState()
    state.load()
    researchers = get_all_researchers(state)

    # 只取核心研究员：多方/空方/技术面/基本面 (跳过数据和板块研究员)
    core_roles = {"bull", "bear", "technical", "fundamental"}
    core_researchers = [r for r in researchers if r.role_id in core_roles]

    context = build_stock_context(code, name)

    # ── Round 1: 独立研判 ──
    reports = {}
    bull_signals, bear_signals = 0, 0
    all_flags = []

    for r in core_researchers:
        try:
            report = r.analyze(context)
            reports[r.role_id] = {
                "author": r.name, "emoji": r.emoji,
                "perspective": report.perspective,
                "confidence": report.confidence,
                "red_flags": report.red_flags[:3] if report.red_flags else [],
            }
            if r.role_id in ("bull", "technical"):
                if report.confidence >= 0.5 and report.key_findings:
                    bull_signals += 1
            if r.role_id in ("bear",):
                if report.red_flags and len(report.red_flags) >= 2:
                    bear_signals += 1
            all_flags.extend(report.red_flags[:3] if report.red_flags else [])
        except Exception as e:
            reports[r.role_id] = {
                "author": r.name, "emoji": r.emoji,
                "perspective": f"分析异常: {e}",
                "confidence": 0.0,
                "red_flags": [f"分析失败: {str(e)[:80]}"]
            }

    # ── Round 2: 小红终审 ──
    total_votes = len(core_researchers)
    effective_votes = max(1, total_votes - sum(1 for rp in reports.values() if rp["confidence"] == 0))
    bias_ratio = bull_signals / max(1, effective_votes)

    if bias_ratio >= 0.67:
        bias = "偏多"
        confidence = min(0.9, 0.5 + bias_ratio * 0.3)
    elif bias_ratio >= 0.5:
        bias = "中性偏多"
        confidence = 0.4 + bias_ratio * 0.2
    elif bull_signals >= bear_signals:
        bias = "中性"
        confidence = 0.3
    else:
        bias = "偏空"
        bear_ratio = bear_signals / max(1, effective_votes)
        confidence = min(0.7, 0.3 + bear_ratio * 0.3)

    unique_flags = list(dict.fromkeys(all_flags))[:5]
    duration_s = round(time.time() - t0, 1)

    # 通过条件: 非偏空 且 置信度≥0.5
    passed = bias != "偏空" and confidence >= 0.5

    return {
        "code": code,
        "name": name,
        "bias": bias,
        "confidence": round(confidence, 2),
        "bull_signals": bull_signals,
        "bear_signals": bear_signals,
        "red_flags": unique_flags,
        "passed": passed,
        "duration_s": duration_s,
        "timestamp": datetime.now().isoformat(),
    }


def run_winner_study(gainers: List[Dict], all_pool_codes: set = None) -> str:
    """
    🆕 v3.0 涨幅榜学习 — 批量预拉取 + 全量分析。

    改进:
      · 不再限5只 — 全量分析，TOP 5 深度 + 其余快速
      · 批量拉取 — 一次 get_stock_realtime + get_historical_k_with_ma 覆盖全部
      · 真实数据 — 每位研究员基于实际数据而非空壳模板
      · 覆盖计算 — 推荐池覆盖率 / 侦察兵发现率 / 遗漏特征

    返回: Markdown 格式研究报告
    """
    if not gainers:
        return "无涨幅 ≥6% 数据"

    date_str = datetime.now().strftime('%Y-%m-%d')
    state = ResearcherState()
    state.load()

    all_codes = [str(g.get('code', '')) for g in gainers if str(g.get('code', ''))]
    if not all_codes:
        return "涨幅数据无有效股票代码"

    # ── 导入数据管线 ──
    from data_pipeline import (
        get_stock_realtime, get_historical_k_with_ma,
        get_north_flow, get_market_money_flow, get_index_data
    )

    # ── 批量预拉取 ──
    print(f"[winner_study] 批量拉取 {len(all_codes)} 只股票数据...")

    # 1. 批量实时行情
    try:
        all_quotes = get_stock_realtime(all_codes)
    except Exception as e:
        all_quotes = {}
        print(f"[winner_study] 行情批量拉取失败: {e}")

    # 2. 批量历史K线 (processpool, ~5s for 50 stocks)
    try:
        all_kline = get_historical_k_with_ma(all_codes, days=60)
    except Exception as e:
        all_kline = {}
        print(f"[winner_study] K线批量拉取失败: {e}")

    # 3. 宏观数据 (共用)
    try:
        north = get_north_flow()
        market = get_market_money_flow()
        idx = get_index_data()
    except Exception:
        north, market, idx = {}, {}, {}

    # 3.5 财务数据 (批量，逐个尝试)
    financials = {}
    try:
        from data_pipeline import get_financial_summary
        for code in all_codes:
            try:
                fin = get_financial_summary(code)
                if fin and fin.get('data_source') != 'no_data':
                    financials[code] = fin
            except Exception:
                pass
    except Exception:
        pass

    # 4. 推荐池代码 (用于计算覆盖率)
    pool_codes = all_pool_codes or set()
    if not pool_codes:
        try:
            with open(SCRIPT_DIR / "data" / "daily_pool.json") as f:
                dp = json.load(f)
            pool_codes = {str(r['code']) for r in dp.get('recommendations', [])}
        except Exception:
            pool_codes = set()

    # ── 为每只涨幅股构建快速上下文 ──
    quick_contexts = []
    for g in gainers:
        code = str(g.get('code', ''))
        name = str(g.get('name', ''))
        chg = g.get('change_pct', 0)

        q = all_quotes.get(code, {})
        # 补名称
        if not name and q.get('name'):
            name = q['name']

        kl_bars = all_kline.get(code, [])
        closes = [b.get('close', 0) for b in kl_bars] if isinstance(kl_bars, list) else []

        quick_contexts.append({
            'code': code, 'name': name, 'change_pct': chg,
            'close': q.get('close', 0),
            'volume': q.get('volume', 0),
            'amount': q.get('amount', 0),
            'turnover': q.get('turnover', 0),
            'close_history': closes,
            'bars_count': len(closes),
            'ma5': kl_bars[-1].get('ma5') if kl_bars else None,
            'ma10': kl_bars[-1].get('ma10') if kl_bars else None,
            'pe_ttm': kl_bars[-1].get('peTTM') if kl_bars else None,
            'pb_mrq': kl_bars[-1].get('pbMRQ') if kl_bars else None,
            'in_pool': code in pool_codes,
            'data_error': not bool(q.get('close')),
            # 财务数据
            'roe': financials.get(code, {}).get('roe'),
            'debt_ratio': financials.get(code, {}).get('debt_ratio'),
            'profit_growth': financials.get(code, {}).get('profit_growth'),
            'fin_score': financials.get(code, {}).get('score'),
        })

    # ── 统计覆盖情况 ──
    in_pool_count = sum(1 for c in quick_contexts if c['in_pool'])
    has_data_count = sum(1 for c in quick_contexts if not c['data_error'])

    # ── 生成报告 ──
    lines = [
        f"# 🏆 涨幅榜深度学习报告",
        f"> {date_str}  |  涨幅 ≥6%: {len(gainers)}只  |  有行情数据: {has_data_count}只  |  池内覆盖: {in_pool_count}只",
        "",
        "---",
        "",
    ]

    # ═══ 宏观环境 ═══
    lines.append("## 🌍 今日市场环境")
    lines.append("")
    if idx:
        sh = idx.get('上证指数', idx.get('sh_index', {}))
        if isinstance(sh, dict):
            lines.append(f"- 上证: {sh.get('close','?')}  {sh.get('change_pct',0):+.2f}%")
    if north:
        lines.append(f"- 北向: {north.get('net_flow',0):+.1f}亿 (来源:{north.get('data_source','?')})")
    if market:
        lines.append(f"- 主力: {market.get('main_net',0):+.0f}亿")
    lines.append("")

    # ═══ 涨幅榜概览 ═══
    lines.append("## 📋 涨幅榜概览")
    lines.append("")
    lines.append("| # | 代码 | 名称 | 涨幅 | 现价 | PE(TTM) | 池内 |")
    lines.append("|:--|:--|:--|:--|:--|:--|:--:|")
    for i, c in enumerate(quick_contexts, 1):
        pe_str = f"{c['pe_ttm']:.1f}" if c['pe_ttm'] else "—"
        pool_mark = "⭐" if c['in_pool'] else ""
        lines.append(
            f"| {i} | {c['code']} | {c['name'][:8]} | {c['change_pct']:+.1f}% | "
            f"{c['close']:.2f} | {pe_str} | {pool_mark} |"
        )
    lines.append("")

    # ═══ 覆盖率分析 ═══
    lines.append("## 📊 系统覆盖率")
    lines.append("")
    pool_rate = in_pool_count / len(gainers) * 100 if gainers else 0
    lines.append(f"- 推荐池覆盖: **{in_pool_count}/{len(gainers)}** ({pool_rate:.0f}%)")
    lines.append(f"- 数据可分析: **{has_data_count}/{len(gainers)}** 只")
    not_covered = [c for c in quick_contexts if not c['in_pool']]
    if not_covered:
        # 分析遗漏特征
        missing_codes = [c['code'] for c in not_covered[:10]]
        lines.append(f"- 遗漏标的 (前10): {', '.join(missing_codes)}")
        # 检查是否是北交所/新股
        bj_count = sum(1 for c in not_covered if c['code'].startswith('920'))
        if bj_count:
            lines.append(f"- 其中北交所(920): {bj_count}只 — 北交所标的不在沪深推荐池覆盖范围")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ═══ TOP 5 深度分析 ═══
    lines.append("## 🔬 TOP 5 深度分析")
    lines.append("")

    researchers_list = get_all_researchers(state)

    for rank, c in enumerate(quick_contexts[:5], 1):
        code, name, chg = c['code'], c['name'], c['change_pct']
        lines.append(f"### #{rank} {code} {name}  (+{chg:.1f}%)")
        lines.append("")

        if c['data_error']:
            lines.append(f"> ⚠️ 无法获取该股票实时数据，跳过深度分析")
            lines.append("")
            continue

        # 为每只构建完整 context（复用预拉取数据）
        ctx = {
            "topic": f"涨幅榜深度分析: {name or code}",
            "pool_stocks": [{
                "code": code, "name": name,
                "close": c['close'], "change_pct": chg,
                "volume": c['volume'], "amount": c['amount'],
                "close_history": c['close_history'],
                "ma5": c['ma5'], "ma10": c['ma10'],
                "pe_ttm": c['pe_ttm'], "pb_mrq": c['pb_mrq'],
                "turnover": c['turnover'],
                "roe": c.get('roe'), "debt_ratio": c.get('debt_ratio'),
                "profit_growth": c.get('profit_growth'),
                "financial_score": c.get('fin_score'),
            }],
            "north_flow": north, "market_flow": market, "index_data": idx,
            "kb_insights": [], "kb_files": {},
            "data_sources": {
                "realtime": {"ok": c['close'] > 0, "source": "sina:batch"},
                "kline": {"ok": c['bars_count'] > 0, "bars": c['bars_count']},
                "macro": {"ok": bool(north)},
                "financial": {"ok": c.get('roe') is not None, "score": c.get('fin_score')},
            },
            "_errors": [],
        }

        for r in researchers_list:
            try:
                report = r.analyze(ctx)
                lesson = _extract_domain_lesson_v3(r.role_id, report, c)
                if lesson:
                    lines.append(f"**{r.emoji} {r.name}**")
                    lines.append(f"")
                    lines.append(f"{lesson}")
                    lines.append(f"")
            except Exception as e:
                lines.append(f"**{r.emoji} {r.name}**: 分析异常 ({str(e)[:60]})")
                lines.append(f"")

        lines.append("")

    # ═══ 其余涨幅股快速分析 ═══
    if len(quick_contexts) > 5:
        lines.append("---")
        lines.append("")
        lines.append(f"## ⚡ 其余 {len(quick_contexts)-5} 只快速扫描")
        lines.append("")
        lines.append("| 代码 | 名称 | 涨幅 | 现价 | MA20偏离 | 池内 |")
        lines.append("|:--|:--|:--|:--|:--|:--:|")
        for c in quick_contexts[5:]:
            # 计算MA20偏离
            ma20_dev = "—"
            if c['close_history'] and len(c['close_history']) >= 20:
                ma20 = sum(c['close_history'][-20:]) / 20
                if ma20 > 0:
                    ma20_dev = f"{(c['close'] - ma20) / ma20 * 100:+.1f}%"
            pool_mark = "⭐" if c['in_pool'] else ""
            lines.append(
                f"| {c['code']} | {c['name'][:8]} | {c['change_pct']:+.1f}% | "
                f"{c['close']:.2f} | {ma20_dev} | {pool_mark} |"
            )
        lines.append("")

    # ═══ 跨标的共性与系统学习 ═══
    lines.append("---")
    lines.append("")
    lines.append("## 🧠 跨标的共性与系统学习")
    lines.append("")

    # 行业集中度
    sectors = {}
    for c in quick_contexts:
        sec = c.get('sector', '未知')
        sectors[sec] = sectors.get(sec, 0) + 1
    top_sectors = sorted(sectors.items(), key=lambda x: x[1], reverse=True)[:3]
    sector_str = ", ".join(f"{s}({n}只)" for s, n in top_sectors if n >= 2)
    if sector_str:
        lines.append(f"- 📊 行业集中: {sector_str}")
    else:
        lines.append(f"- 📊 行业分布: 分散（无明显集中）")

    avg_chg = sum(g.get('change_pct', 0) for g in gainers) / len(gainers) if gainers else 0
    lines.append(f"- 📈 平均涨幅: {avg_chg:.1f}% — {'强趋势日' if avg_chg > 8 else '温和上涨日'}")

    # 有数据的股票的技术特征
    with_data = [c for c in quick_contexts if not c['data_error'] and c['close_history'] and len(c['close_history']) >= 20]
    if with_data:
        above_ma20 = sum(1 for c in with_data if c['close'] > sum(c['close_history'][-20:])/20)
        lines.append(f"- 📐 技术面: {above_ma20}/{len(with_data)} 只站在MA20上方")
        
        pe_vals = [c['pe_ttm'] for c in with_data if c['pe_ttm'] and c['pe_ttm'] > 0]
        if pe_vals:
            lines.append(f"- 💰 估值: PE中位数 {sorted(pe_vals)[len(pe_vals)//2]:.1f} (有PE数据{len(pe_vals)}只)")

    # 覆盖反思
    lines.append(f"- 💡 系统反思: {in_pool_count}/{len(gainers)} 在推荐池 → 覆盖率 {pool_rate:.0f}%")
    if pool_rate < 30:
        lines.append(f"  - 🔴 覆盖率严重不足，需检查候选源和筛选条件")
    elif pool_rate < 60:
        lines.append(f"  - 🟡 覆盖率偏低，关注遗漏标的的共同特征")
    else:
        lines.append(f"  - 🟢 覆盖率良好")

    not_covered_codes = [c['code'] for c in quick_contexts if not c['in_pool'] and not c['data_error']]
    if not_covered_codes and pool_rate < 60:
        lines.append(f"  - 遗漏标的: {', '.join(not_covered_codes[:8])}")
        lines.append(f"  - 🔧 行动: 分析遗漏标的行业/市值/形态特征，调整筛选参数")

    lines.append("")
    lines.append("---")
    lines.append(f"*研究员涨幅榜学习 v3.0 · {datetime.now().strftime('%Y-%m-%d %H:%M')}*")

    report = "\n".join(lines)

    # 保存
    report_path = REPORTS_DIR / f"涨幅榜学习-{date_str}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)

    return report


def _extract_domain_lesson_v3(role_id: str, report, ctx: Dict) -> str:
    """🆕 v3.0: 从研究员报告中提取真实的领域洞察，不再输出占位文本"""
    name = ctx.get('name', '')
    code = ctx.get('code', '')
    chg = ctx.get('change_pct', 0)
    # ctx 是 quick_context 字典，字段直接读取
    ma5 = ctx.get('ma5')
    ma10 = ctx.get('ma10')
    close = ctx.get('close', 0)
    roe = ctx.get('roe')
    debt = ctx.get('debt_ratio')
    growth = ctx.get('profit_growth')
    in_pool = ctx.get('in_pool', False)

    if role_id == "data":
        parts = []
        if report.key_findings:
            real = [f for f in report.key_findings if "0 个数据源" not in f and "数据源正常" not in f]
            if real:
                parts.append(f"> 数据发现: {'; '.join(real[:3])}")
        if report.data_evidence:
            parts.append(f"> 证据: {'; '.join(report.data_evidence[:2])}")
        if not parts:
            parts.append(f"> 行情: {name or code} 现价¥{close:.2f} 涨{chg:+.1f}%")
        return "\n".join(parts)

    elif role_id == "fundamental":
        parts = []
        metrics = []
        if roe is not None: metrics.append(f"ROE {roe:.1f}%")
        if debt is not None: metrics.append(f"负债率 {debt:.1f}%")
        if growth is not None: metrics.append(f"利润增速 {growth:+.1f}%")
        if metrics:
            parts.append(f"> 财务指标: {', '.join(metrics)}")
        if report.key_findings:
            real = [f for f in report.key_findings if "中性" not in f and "无明显" not in f]
            if real:
                parts.append(f"> 基本面发现: {'; '.join(real[:3])}")
        if report.red_flags:
            parts.append(f"> ⚠️ 风险: {'; '.join(report.red_flags[:2])}")
        if not parts:
            parts.append(f"> 基本面: {name or code} — 暂无显著催化剂识别")
        return "\n".join(parts)

    elif role_id == "technical":
        parts = []
        if ma5 and ma10:
            pos = "多头排列" if ma5 > ma10 else "空头排列"
            parts.append(f"> 均线: MA5={ma5:.2f} MA10={ma10:.2f} ({pos})")
        if close and ctx.get('close_history') and len(ctx['close_history']) >= 20:
            ma20 = sum(ctx['close_history'][-20:]) / 20
            if ma20 > 0:
                dev = (close - ma20) / ma20 * 100
                parts.append(f"> MA20偏离: {dev:+.1f}%")
        if report.key_findings:
            real = [f for f in report.key_findings if "无显著" not in f and "中性" not in f]
            if real:
                parts.append(f"> 技术发现: {'; '.join(real[:3])}")
        parts.append(f"> 💡 涨幅复盘: 今日 +{chg:.1f}%，回溯近5日K线 — 突破/回踩信号？MA偏离？成交量配合？")
        return "\n".join(parts)

    elif role_id == "bull":
        parts = []
        if report.key_findings:
            real = [f for f in report.key_findings if "无明显看多" not in f]
            if real:
                parts.append(f"> 看多信号: {'; '.join(real[:3])}")
        if in_pool:
            parts.append(f"> ✅ 该股在推荐池中 — 系统已识别")
        else:
            parts.append(f"> ⚠️ 该股不在推荐池 — 检查是否漏掉做多信号")
        parts.append(f"> 💡 反思: 涨幅 +{chg:.1f}% — 系统是否有任何前置看多信号？如果有为什么没触发？如果没有应该有什么？")
        return "\n".join(parts)

    elif role_id == "bear":
        parts = []
        if report.red_flags:
            parts.append(f"> 空方曾担忧: {'; '.join(report.red_flags[:3])}")
            parts.append(f"> 💡 教训: 这些空方信号今天被市场证伪（涨幅 +{chg:.1f}%），相关权重是否需要下调？")
        else:
            parts.append(f"> 空方未发现显著红旗 — {name or code} 的涨幅没有明显隐患")
        return "\n".join(parts)

    elif role_id == "capital_flow":
        parts = []
        if report.key_findings:
            real = [f for f in report.key_findings if "中性" not in f]
            if real:
                parts.append(f"> 资金特征: {'; '.join(real[:3])}")
        if report.data_evidence:
            parts.append(f"> 数据: {'; '.join(report.data_evidence[:2])}")
        if not parts:
            parts.append(f"> 资金面: {name or code} — 盘后资金流数据需T+1获取")
        return "\n".join(parts)

    else:
        findings = report.key_findings[0][:200] if report.key_findings else report.perspective[:200]
        return f"> {findings}"


def _extract_common_patterns(gainers: List[Dict], researchers) -> List[str]:
    """从多只涨幅股中提取跨标的共性"""
    patterns = []
    n = len(gainers)

    if n < 2:
        patterns.append("样本不足，无法提取共性")
        return patterns

    # 统计行业分布
    sectors = {}
    for g in gainers:
        sec = g.get('sector', '未知')
        sectors[sec] = sectors.get(sec, 0) + 1

    top_sectors = sorted(sectors.items(), key=lambda x: x[1], reverse=True)[:3]
    sector_str = ", ".join(f"{s}({c}只)" for s, c in top_sectors if c >= 2)
    if sector_str:
        patterns.append(f"📊 行业集中: {sector_str} — 关注是否有板块级催化剂")

    # 涨幅分布
    avg_chg = sum(g.get('change_pct', 0) for g in gainers) / n
    patterns.append(f"📈 平均涨幅: {avg_chg:.1f}% — {'强趋势日' if avg_chg > 8 else '温和上涨日'}")

    # 系统覆盖反思
    patterns.append(f"💡 系统反思: 对今日 {n} 只涨幅≥6%个股做回溯检查——"
                   f"推荐池覆盖了几只？侦察兵发现了几只？漏掉的个股有什么共同特征？")
    patterns.append(f"🔧 行动建议: 如系统覆盖率<30%，需调整筛选参数或扩展候选源")

    return patterns


def _fetch_gainers_for_study() -> List[Dict]:
    """自动获取今日涨幅榜（复用 review.py 的 get_top_gainers）"""
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from review import get_top_gainers
        return get_top_gainers(6.0, 50)
    except ImportError:
        pass
    except Exception as e:
        print(f"  [涨幅榜] review.py 导入失败: {e}")

    # Fallback: 东方财富 push2 直拉
    try:
        import urllib.request
        url = ('https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=0&np=1'
               '&fltt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23'
               '&fields=f12,f14,f2,f3,f20&ut=bd1d9ddb04089700cf9c27f6f7426281')
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://data.eastmoney.com/'
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        items = data.get('data', {}).get('diff', [])
        return [
            {
                'code': str(i.get('f12', '')),
                'name': str(i.get('f14', '')),
                'price': float(i.get('f2', 0)),
                'change_pct': float(i.get('f3', 0)),
            }
            for i in items if float(i.get('f3', 0)) >= 6.0
        ]
    except Exception as e:
        print(f"  [涨幅榜] push2 直拉失败: {e}")

    return []


def run_parliament():
    """议会模式"""
    parliament = Parliament()
    topic = f"每日推荐池标的研判 — {datetime.now().strftime('%Y-%m-%d')}"
    verdict = parliament.debate(topic)

    # 保存议会报告
    date_str = datetime.now().strftime('%Y-%m-%d')
    lines = [
        f"# 🏛️ 研究员议会报告",
        f"> {verdict['timestamp'][:19]}",
        "",
        "## 独立研判", ""
    ]

    for r in verdict.get("reports", []):
        lines.append(f"### {r.author_emoji} {r.author}")
        lines.append(f"**视角**: {r.perspective}")
        lines.append(f"_置信度: {r.confidence:.0%}_")
        if r.key_findings:
            for f in r.key_findings[:2]:
                lines.append(f"- {f}")
        if r.red_flags:
            lines.append(f"🚩 红旗: " + ", ".join(r.red_flags[:3]))
        lines.append("")

    lines += [
        "## 小红终审", "",
        f"**市场判断**: {verdict['bias']}  (置信度 {verdict['confidence']:.0%})",
        f"**多方信号**: {verdict['bull_signals']}  |  **空方信号**: {verdict['bear_signals']}",
    ]
    if verdict['red_flags']:
        lines.append(f"**关键红旗**: " + ", ".join(verdict['red_flags'][:3]))
    lines.append("")
    for rec in verdict.get('recommendations', [])[:5]:
        lines.append(f"- 🌹 {rec}")

    report_path = REPORTS_DIR / f"议会报告-{date_str}.md"
    report_path.write_text('\n'.join(lines))
    print(f"📁 议会报告: {report_path}")

    return verdict


def run_verify_only():
    """仅验证过往假设，不生成新报告"""
    parliament = Parliament()
    context = parliament.load_context()
    total = 0
    for r in parliament.researchers:
        verified = r.verify_past_hypotheses(context)
        if verified:
            for v in verified:
                icon = "✅" if v["positive"] else "❌"
                print(f"{r.emoji} {icon} {v['evidence'][:100]}")
                total += 1
    parliament.state.save()
    print(f"\n已验证 {total} 个假设，状态已保存")


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description=f'研究员议会 v{__version__}')
    ap.add_argument('--study', action='store_true', help='自主研学模式')
    ap.add_argument('--parliament', action='store_true', help='议会模式')
    ap.add_argument('--verify', action='store_true', help='仅验证过往假设')
    ap.add_argument('--report', action='store_true', help='查看最近研究报告')
    ap.add_argument('--reset', action='store_true', help='重置研究员状态')
    ap.add_argument('--query', type=str, help='查询单只股票深度分析 (code, 例如 600519)')
    ap.add_argument('--name', type=str, default='', help='--query时指定股票名称')
    ap.add_argument('--winners', nargs='?', const='auto',
                    help='🆕 涨幅榜学习模式 (默认: auto 自动拉取)')
    args = ap.parse_args()

    if args.query:
        print(query_stock(args.query, args.name))
        return

    if args.reset:
        if STATE_PATH.exists():
            STATE_PATH.unlink()
        print("🔄 研究员状态已重置")
        return

    if args.verify:
        run_verify_only()
    elif args.winners:
        # 🆕 涨幅榜学习模式
        gainers_path = args.winners if args.winners != "auto" else None
        if gainers_path and Path(gainers_path).exists():
            import json
            gainers = json.loads(Path(gainers_path).read_text())
        else:
            # 自动从 review 获取今日涨幅榜
            gainers = _fetch_gainers_for_study()
        if gainers:
            report = run_winner_study(gainers)
            print(report)
        else:
            print("无涨幅 ≥6% 数据或非交易日")
    elif args.parliament:
        run_parliament()
    elif args.report:
        reports = sorted(REPORTS_DIR.glob("研学报告-*.md"), reverse=True)
        if reports:
            print(reports[0].read_text()[:2000])
        else:
            print("暂无研究报告")
    else:
        run_study_session()


if __name__ == "__main__":
    main()
