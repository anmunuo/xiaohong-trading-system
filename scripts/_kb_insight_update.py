#!/usr/bin/env python3
"""Append structured insights to kb_insights.json"""
import json
from datetime import datetime
from pathlib import Path

KB_DIR = Path("/home/pc/.hermes/profiles/xiaohong/data/kb")
INSIGHTS_FILE = KB_DIR / "kb_insights.json"

now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

new_block = {
    "timestamp": now_str,
    "insights": [
        {
            "type": "risk_alert",
            "title": "重大重组单日井喷: 韩建河山/华峰化学/信达证券/上海莱士/海汽集团5家同日披露重组进展",
            "body": "144条公告中重大重组类至少占25+条. 韩建河山(603616)拟收购辽宁兴福新材料(10+条配套公告含评估报告+券商核查), 华峰化学(002064)筹划重组(8条含合规说明), 信达证券(601059)中金换股吸收合并自查, 上海莱士(002252)控股股东被动增持至30%+免于要约收购. 5家同日井喷构成并购重组政策窗口期信号 -- 建议本周推荐引擎将重组标的纳入候选源名单, 首板/重组进展股优先关注.",
            "confidence": "high",
            "sources": ["announcements"]
        },
        {
            "type": "sentiment_shift",
            "title": "日本Q1 GDP超预期(年化+1.8% vs 预期+1.3%)但日经-3.85% -- 宏观利好被全球risk-off完全淹没",
            "body": "日本Q1实际GDP季率终值+0.5%(预期+0.3%), 年化+1.8%(预期+1.3%)全面超预期, 经常帐39078亿日元远超预期的31367亿. 但日经225收跌3.85%, 说明纳指-4.18%驱动的全球risk-off情绪完全压倒区域性宏观利好. 此模式对A股有传导含义: 利好不涨是熊市特征 -- 上证今日-1.7%已确认. 叠加德国工业订单月率-3.8%(预期-2.0%)大幅不及预期, 外需+外盘双杀格局形成.",
            "confidence": "high",
            "sources": ["policy_macro", "external_futures"]
        },
        {
            "type": "sector_anomaly",
            "title": "格林美固态电池+中天科技数据中心+新宙邦电解液 -- 新能源/新材料/数据中心三链催化剂同日共振",
            "body": "格林美(002340)签署共建固态电池正极材料联合实验室协议(产业化关键技术联合攻关), 中天科技(600522)中标互联网企业数据中心用耗材项目(早盘获2份研报覆盖+热搜, 日终新增合同公告=三重共振), 新宙邦(300037)签订电解液合作协议. 三条产业链同日出现签约/中标/合作公告, 非偶然 -- 建议明日晨报将固态电池->正极材料->电解液和数据中心耗材列为独立关注方向.",
            "confidence": "medium",
            "sources": ["announcements", "industry_news"]
        },
        {
            "type": "fund_signal",
            "title": "中航沈飞/龙佰集团/金洲管道高管增持+回购 -- 日终虽上证-1.7%, 但产业资本逆势加仓密度不减",
            "body": "中航沈飞(600760)董事长+董事+高管同步增持, 龙佰集团(002601)控股股东+董事+高管+核心骨干增持计划, 金洲管道(002443)回购达4%. 日终144条公告中增持/回购类仍超50%(与10:05的56%持平) -- 这是连续第5个采集窗口回购占比>50%, 创下年内最长回购密集期. 与上证-1.7%形成结构性背离: 产业资本认为当前估值已低估, 但市场仍在risk-off尾声杀跌.",
            "confidence": "high",
            "sources": ["announcements", "external_futures"]
        }
    ]
}

# Load existing
if INSIGHTS_FILE.exists():
    with open(INSIGHTS_FILE, 'r') as f:
        existing = json.load(f)
else:
    existing = []

# Prepend and keep last 50
existing.insert(0, new_block)
trimmed = existing[:50]

with open(INSIGHTS_FILE, 'w') as f:
    json.dump(trimmed, f, ensure_ascii=False, indent=2)

print(f"OK: kb_insights.json updated, {len(trimmed)} entries (max 50)")
for i, ins in enumerate(new_block["insights"]):
    print(f"  [{i+1}] {ins['type']}: {ins['title'][:70]}")
