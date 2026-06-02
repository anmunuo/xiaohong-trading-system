#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 基本面事件智能池
======================================
【资源池定位】

不是简单的新闻聚合器，而是：
  1. 从多元数据源采集事件（公告/合同/合作/政策/研报）
  2. 结构化标注：事件类型、影响板块、关联个股、可信度
  3. 交叉验证：事件 ⇄ 资金 ⇄ 涨停 ⇄ 研报，四维互证
  4. 输出板块级+个股级多维度信号

数据源矩阵:
  ┌──────────────┬─────────────────────────┬─────────────┐
  │ 维度          │ 数据源                   │ 权重         │
  ├──────────────┼─────────────────────────┼─────────────┤
  │ 公司公告      │ stock_notice_report()    │ 25%         │
  │ 券商研报      │ stock_research_report_em │ 15%         │
  │ 政策/宏观     │ news_economic_baidu()     │ 10%         │
  │ 新闻舆情      │ stock_news_em() + RSS     │ 10%         │
  │ 资金流向      │ data_pipeline             │ 25%         │
  │ 涨停动量      │ stock_zt_pool_em()        │ 15%         │
  └──────────────┴─────────────────────────┴─────────────┘

版本: 1.0.0
创建: 2026-05-27
"""

import sys
import json
import subprocess
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from typing import Dict, List, Optional, Tuple
import re
import hashlib

# 抑制 akshare tqdm 进度条噪音
os.environ['TQDM_DISABLE'] = '1'
import logging
logging.getLogger('akshare').setLevel(logging.WARNING)

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from data_pipeline import (
    get_north_flow, get_market_money_flow, get_sector_flow_rank, get_top_flow_stocks
)

# ═══════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════

# 关键词映射：公告标题中出现这些词 → 对应事件类型
EVENT_KEYWORDS = {
    'contract_sign': {
        'keywords': ['中标', '合同', '签订', '签约', '订单', '供货', '框架协议',
                     '中标公告', '合同公告', '经营合同'],
        'weight': 1.5,   # 直接商业利益，权重最高
        'label': '📝 合同签订',
    },
    'cooperation': {
        'keywords': ['战略合作', '合作协议', '合作开发', '合资', '联合',
                     '达成合作', '业务合作', '深度合作'],
        'weight': 1.3,
        'label': '🤝 战略合作',
    },
    'project_investment': {
        'keywords': ['投资建设', '项目投资', '新项目', '产能', '扩产',
                     '产线', '基地建设', '产业园'],
        'weight': 1.2,
        'label': '🏗️ 项目投资',
    },
    'major_restructure': {
        'keywords': ['重大资产重组', '重组', '并购', '收购', '资产注入',
                     '借壳', '合并', '剥离', '分拆上市'],
        'weight': 1.4,
        'label': '🔄 重大重组',
    },
    'shareholder_bullish': {
        'keywords': ['增持', '回购', '股权激励', '员工持股', '分红',
                     '大股东增持', '实控人增持'],
        'weight': 1.1,
        'label': '💎 增持/回购',
    },
    'policy_related': {
        'keywords': ['政策', '补贴', '扶持', '国务院', '发改委', '工信部',
                     '证监会', '央行', '降准', '降息', '利率'],
        'weight': 1.0,
        'label': '📋 政策利好',
    },
}

# 行业关键词映射 (公告/新闻中出现→对应板块)
# ⚠️ 注意：单字/通用词必须加负向排除，避免误伤！
SECTOR_KEYWORD_MAP = {
    '人工智能': ['AI', '人工智能', '大模型', '深度学习', '算力', 'GPU', '神经网络'],
    '半导体': ['芯片', '半导体', '晶圆', '光刻', '封装测试', 'EDA工具', 'NAND', 'DRAM', '存储芯片'],
    '新能源': ['光伏', '锂电', '储能', '新能源', '太阳能', '风电', '氢能'],
    '电力': ['电力', '电网', '绿电', '电价', '发电', '输配电'],
    '医药': ['创新药', '生物医药', '医疗器械', '疫苗', '基因治疗', '细胞治疗'],
    '消费': ['白酒', '食品饮料', '零售连锁', '家电', '旅游'],
    '房地产': ['房地产', '地产开发', '楼盘', '物业'],
    '汽车': ['新能源车', '电动车', '自动驾驶', '汽车零部件', '智能驾驶'],
    '数字经济': ['数字人民币', '数据要素', '区块链', 'Web3', '信创'],
    '机器人': ['机器人', '人形机器人', '智能制造'],
    '军工': ['军工', '国防', '航天', '卫星互联网', '导弹'],
}

# 负向排除词：标题包含这些词时，强制排除该板块匹配
SECTOR_NEGATIVE_FILTERS = {
    '半导体': ['募集资金', '资金存储', '专户存储', '存储三方', '存储四方'],
    '数字经济': ['数字证书', '数字化'],
    '人工智能': ['人工智能生成', 'AI生成内容'],
}


# ═══════════════════════════════════════════
# 数据采集层
# ═══════════════════════════════════════════

def fetch_corporate_announcements(date_str: str = None) -> List[dict]:
    """
    采集公司公告，按事件类型分类
    
    Args:
        date_str: YYYYMMDD，默认今天
        
    Returns:
        [{
            code, name, title, type, event_type, sector_tags,
            weight, url, date
        }, ...]
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    
    events = []
    try:
        import akshare as ak
        
        # 采集近3天公告
        for day_offset in range(3):
            d = (datetime.now() - timedelta(days=day_offset)).strftime('%Y%m%d')
            try:
                df = ak.stock_notice_report(symbol='全部', date=d)
                if df is None or df.empty:
                    continue
                    
                for _, row in df.iterrows():
                    title = str(row.get('公告标题', ''))
                    if not title or len(title) < 8:
                        continue
                    
                    # 匹配事件类型
                    for event_type, config in EVENT_KEYWORDS.items():
                        matched_kw = [kw for kw in config['keywords'] if kw in title]
                        if matched_kw:
                            # 识别板块（含负向过滤）
                            sector_tags = []
                            for sector, keywords in SECTOR_KEYWORD_MAP.items():
                                if any(kw in title for kw in keywords):
                                    # 检查负向排除
                                    neg_words = SECTOR_NEGATIVE_FILTERS.get(sector, [])
                                    if any(nw in title for nw in neg_words):
                                        continue  # 命中负向词，跳过该板块
                                    sector_tags.append(sector)
                            
                            events.append({
                                'code': str(row.get('代码', '')),
                                'name': str(row.get('名称', '')),
                                'title': title,
                                'type': str(row.get('公告类型', '')),
                                'event_type': event_type,
                                'event_label': config['label'],
                                'event_weight': config['weight'],
                                'sector_tags': sector_tags,
                                'url': str(row.get('网址', '')),
                                'date': d,
                                'source': 'announcement',
                            })
                            break  # 一个公告只匹配第一类事件
                            
            except Exception:
                continue
                
    except Exception as e:
        pass
    
    # 去重 (同一code+title)
    seen = set()
    unique = []
    for e in events:
        key = f"{e['code']}_{e['title'][:40]}"
        if key not in seen:
            seen.add(key)
            unique.append(e)
    
    return unique


def fetch_research_reports(hot_stocks: List[str] = None) -> List[dict]:
    """
    采集券商研报（评级+盈利预测）
    
    Args:
        hot_stocks: 热门股票代码列表
        
    Returns:
        [{
            code, name, report_name, rating, org, industry,
            profit_2026, pe_2026, date
        }, ...]
    """
    reports = []
    
    if hot_stocks is None:
        hot_stocks = []
    
    # 扩展：加入资金流入TOP股票
    try:
        top_flow = get_top_flow_stocks(15)
        for s in top_flow:
            hot_stocks.append(s.get('code', ''))
    except Exception:
        pass
    
    # 去重
    hot_stocks = list(set(hot_stocks))[:30]
    
    for code in hot_stocks:
        try:
            import akshare as ak
            df = ak.stock_research_report_em(symbol=code)
            if df is None or df.empty:
                continue
            
            # 取最近2篇研报
            recent = df.head(2)
            for _, row in recent.iterrows():
                rating = str(row.get('东财评级', ''))
                reports.append({
                    'code': code,
                    'name': str(row.get('股票简称', '')),
                    'report_name': str(row.get('报告名称', '')),
                    'rating': rating,
                    'org': str(row.get('机构', '')),
                    'industry': str(row.get('行业', '')),
                    'profit_2026': float(row.get('2026-盈利预测-收益', 0) or 0),
                    'pe_2026': float(row.get('2026-盈利预测-市盈率', 0) or 0),
                    'date': str(row.get('日期', '')),
                    'source': 'research_report',
                })
        except Exception:
            continue
    
    return reports


def fetch_policy_macro_news() -> List[dict]:
    """采集政策/宏观新闻"""
    events = []
    
    # 1. 经济数据日历
    try:
        import akshare as ak
        today = datetime.now().strftime('%Y%m%d')
        df = ak.news_economic_baidu(date=today)
        if df is not None and not df.empty:
            for _, row in df.iterrows():
                if str(row.get('重要性', '2')) == '1':
                    events.append({
                        'title': str(row.get('事件', '')),
                        'country': str(row.get('地区', '')),
                        'actual': str(row.get('公布', '')),
                        'expected': str(row.get('预期', '')),
                        'importance': '高',
                        'event_type': 'policy_related',
                        'event_label': '📋 宏观数据',
                        'event_weight': 0.8,
                        'sector_tags': [],
                        'source': 'economic_calendar',
                        'date': today,
                    })
    except Exception:
        pass
    
    # 2. RSS新闻
    try:
        proc = subprocess.run(
            ['data', 'fetch', 'news', '--category', 'headlines'],
            capture_output=True, text=True, timeout=20
        )
        data = json.loads(proc.stdout)
        for p in data.get('providers_attempted', []):
            if isinstance(p.get('data'), list):
                for item in p['data'][:10]:
                    title = item.get('title', '')
                    if title and len(title) > 10:
                        # 检查是否政策相关
                        policy_kw = EVENT_KEYWORDS['policy_related']['keywords']
                        if any(kw in title for kw in policy_kw + ['政策', '监管', '央行', '降息', '降准']):
                            sector_tags = []
                            for sector, kws in SECTOR_KEYWORD_MAP.items():
                                if any(kw in title for kw in kws):
                                    sector_tags.append(sector)
                            
                            events.append({
                                'title': title,
                                'event_type': 'policy_related',
                                'event_label': '📋 政策/监管',
                                'event_weight': 1.0,
                                'sector_tags': sector_tags,
                                'source': 'rss',
                                'date': datetime.now().strftime('%Y%m%d'),
                            })
                break
    except Exception:
        pass
    
    # 3. 东方财富新闻
    try:
        import akshare as ak
        df = ak.stock_news_em()
        if df is not None and not df.empty:
            for _, row in df.head(15).iterrows():
                title = str(row.get('新闻标题', ''))
                if not title:
                    continue
                
                # 识别板块
                sector_tags = []
                for sector, kws in SECTOR_KEYWORD_MAP.items():
                    if any(kw in title for kw in kws):
                        sector_tags.append(sector)
                
                if sector_tags or any(kw in title for kw in ['政策', '重磅', '突发', '大利好']):
                    events.append({
                        'title': title,
                        'event_type': 'policy_related',
                        'event_label': '📋 市场新闻',
                        'event_weight': 0.7,
                        'sector_tags': sector_tags,
                        'source': 'em_news',
                        'url': str(row.get('新闻链接', '')),
                        'date': datetime.now().strftime('%Y%m%d'),
                    })
    except Exception:
        pass
    
    return events


# ═══════════════════════════════════════════
# 交叉验证引擎
# ═══════════════════════════════════════════

def cross_validate_sectors(
    events: List[dict],
    zt_df=None,
    fund_flow_sectors: List[dict] = None,
    research_reports: List[dict] = None
) -> List[dict]:
    """
    四维交叉验证 → 板块综合评分
    
    验证维度:
      1. 事件密度: 板块关联事件的加权数量和新鲜度
      2. 资金流向: 板块资金净流入
      3. 涨停动量: 板块涨停家数和连板高度
      4. 研报共识: 板块内个股被买入评级的数量和比例
    
    Returns:
        [{
            sector, events_count, event_types, event_details,
            fund_flow, zt_count, zt_leader,
            research_buy, research_count,
            cross_score, confidence,
            key_stocks: [{code, name, event_count, fund_confirmed, rating}],
            event_drivers: [str]  # 事件驱动逻辑
        }, ...]
    """
    if fund_flow_sectors is None:
        fund_flow_sectors = []
    if research_reports is None:
        research_reports = []
    
    # 1. 按板块聚合事件
    sector_events = defaultdict(list)
    for e in events:
        has_tag = False
        for tag in e.get('sector_tags', []):
            sector_events[tag].append(e)
            has_tag = True
        
        # ★ 补充：公告有 code 但无 sector_tag 时，从涨停池推断行业
        if not has_tag and e.get('code') and zt_df is not None and not zt_df.empty:
            code = e['code']
            zt_match = zt_df[zt_df['代码'].astype(str) == str(code)]
            if not zt_match.empty:
                industry = str(zt_match.iloc[0].get('所属行业', ''))
                if industry:
                    # 映射涨停池行业到板块关键词
                    # 直接使用涨停池的行业名作为板块标签
                    e.setdefault('sector_tags', []).append(industry)
                    sector_events[industry].append(e)
    
    # 2. 涨停池按行业聚合
    sector_zt = defaultdict(lambda: {'count': 0, 'lianban_max': 0, 'stocks': []})
    if zt_df is not None and not zt_df.empty:
        for _, row in zt_df.iterrows():
            ind = str(row.get('所属行业', ''))
            if not ind:
                continue
            sector_zt[ind]['count'] += 1
            sector_zt[ind]['lianban_max'] = max(
                sector_zt[ind]['lianban_max'],
                int(row.get('连板数', 0))
            )
            sector_zt[ind]['stocks'].append({
                'code': str(row.get('代码', '')),
                'name': str(row.get('名称', '')),
                'lianban': int(row.get('连板数', 0)),
            })
    
    # 3. 研报按行业聚合
    sector_research = defaultdict(lambda: {'buy': 0, 'total': 0, 'reports': []})
    for r in research_reports:
        ind = r.get('industry', '')
        if not ind:
            continue
        sector_research[ind]['total'] += 1
        if r.get('rating') in ['买入', '增持']:
            sector_research[ind]['buy'] += 1
        sector_research[ind]['reports'].append(r)
    
    # 4. 资金流向索引
    fund_idx = {s.get('name', ''): s.get('flow', 0) for s in fund_flow_sectors}
    
    # 5. 综合评分
    results = []
    all_sectors = set(list(sector_events.keys()) + 
                      list(sector_zt.keys()) + 
                      list(sector_research.keys()))
    
    for sector in all_sectors:
        evts = sector_events.get(sector, [])
        zt = sector_zt.get(sector, {'count': 0, 'lianban_max': 0})
        research = sector_research.get(sector, {'buy': 0, 'total': 0})
        flow = fund_idx.get(sector, 0)
        
        # 子维度打分 (0-100)
        
        # a) 事件密度分 (0-25)
        event_score = 0
        if evts:
            total_weight = sum(e.get('event_weight', 0.5) for e in evts)
            # 新鲜度加成（今天的事件权重更高）
            today = datetime.now().strftime('%Y%m%d')
            fresh_bonus = sum(0.3 for e in evts if e.get('date') == today)
            event_score = min(25, total_weight * 5 + fresh_bonus * 3)
        
        # b) 涨停动量分 (0-20)
        zt_score = min(20, zt['count'] * 4 + zt['lianban_max'] * 3)
        
        # c) 资金验证分 (0-25)
        flow_score = 0
        if flow > 0:
            flow_score = min(25, 10 + flow / 2)  # 每2亿加1分
        elif flow < 0:
            flow_score = max(0, 10 + flow / 4) 
        
        # d) 研报共识分 (0-15)
        research_score = 0
        if research['total'] > 0:
            buy_ratio = research['buy'] / research['total']
            research_score = min(15, research['total'] * 3 + buy_ratio * 10)
        
        # e) 事件类型多样性加分 (0-15)
        unique_types = len(set(e.get('event_type', '') for e in evts))
        diversity_score = min(15, unique_types * 5)
        
        total = event_score + zt_score + flow_score + research_score + diversity_score
        
        # 置信度：至少2个维度有信号
        dimensions_with_signal = sum([
            1 if event_score > 5 else 0,
            1 if zt_score > 3 else 0,
            1 if flow_score > 5 else 0,
            1 if research_score > 3 else 0,
        ])
        confidence = '高' if dimensions_with_signal >= 3 else ('中' if dimensions_with_signal >= 2 else '低')
        
        # 生成事件驱动逻辑
        event_drivers = _generate_event_logic(sector, evts, zt, flow, research)
        
        # 提取关键个股
        key_stocks = _extract_key_stocks(evts, zt, sector)
        
        results.append({
            'sector': sector,
            'events_count': len(evts),
            'event_types': list(set(e.get('event_label', '') for e in evts)),
            'event_details': evts[:5],  # 前5条事件
            'fund_flow': flow,
            'zt_count': zt['count'],
            'zt_lianban_max': zt['lianban_max'],
            'research_buy': research['buy'],
            'research_total': research['total'],
            'event_score': round(event_score, 1),
            'zt_score': round(zt_score, 1),
            'flow_score': round(flow_score, 1),
            'research_score': round(research_score, 1),
            'diversity_score': round(diversity_score, 1),
            'cross_score': round(total, 1),
            'confidence': confidence,
            'key_stocks': key_stocks,
            'event_drivers': event_drivers,
        })
    
    # 排序
    results.sort(key=lambda x: (x['confidence'] != '高', -x['cross_score']))
    
    return results


def _generate_event_logic(sector, events, zt, flow, research) -> List[str]:
    """生成板块的事件驱动逻辑描述"""
    drivers = []
    
    if events:
        types = Counter(e.get('event_label', '') for e in events)
        top_types = types.most_common(2)
        for t, count in top_types:
            drivers.append(f"{t}×{count}")
    
    if zt['count'] > 0:
        drivers.append(f"涨停{zt['count']}只(最高{zt['lianban_max']}板)")
    
    if flow > 0:
        drivers.append(f"资金流入{flow:.0f}万")
    elif flow < 0:
        drivers.append(f"资金流出{abs(flow):.0f}万")
    
    if research['buy'] > 0:
        drivers.append(f"{research['buy']}家买入评级")
    
    return drivers


def _extract_key_stocks(events, zt, sector) -> List[dict]:
    """从事件和涨停池中提取板块关键个股"""
    stocks = {}
    
    # 从公告事件中提取个股
    for e in events:
        if e.get('code') and e.get('name'):
            code = e['code']
            if code not in stocks:
                stocks[code] = {
                    'code': code,
                    'name': e['name'],
                    'event_count': 0,
                    'event_types': [],
                    'fund_confirmed': False,
                    'lianban': 0,
                }
            stocks[code]['event_count'] += 1
            stocks[code]['event_types'].append(e.get('event_label', ''))
    
    # 从涨停池补充
    for s in zt.get('stocks', []):
        code = s['code']
        if code not in stocks:
            stocks[code] = {
                'code': code,
                'name': s['name'],
                'event_count': 0,
                'event_types': [],
                'fund_confirmed': False,
                'lianban': s['lianban'],
            }
        else:
            stocks[code]['lianban'] = max(stocks[code]['lianban'], s['lianban'])
    
    # 去重事件类型
    for s in stocks.values():
        s['event_types'] = list(set(s['event_types']))
    
    # 按 event_count + lianban 排序
    key = sorted(stocks.values(), 
                key=lambda x: (x['event_count'] * 10 + x['lianban'] * 5), 
                reverse=True)
    
    return key[:5]


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def build_resource_pool(
    date_str: str = None,
    zt_df=None, dt_df=None
) -> dict:
    """
    构建完整的资源池
    
    Returns:
        {
            announcements: [...],     # 公司公告事件
            research_reports: [...],  # 券商研报
            policy_news: [...],       # 政策/宏观新闻
            sector_analysis: [...],   # 板块交叉验证结果
            summary: str,             # 摘要
        }
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    
    # === 数据采集 ===
    announcements = fetch_corporate_announcements(date_str)
    policy_news = fetch_policy_macro_news()
    
    # 从公告中提取热门股票代码用于研报查询
    hot_codes = list(set(e['code'] for e in announcements if e.get('code')))
    research_reports = fetch_research_reports(hot_codes)
    
    # 资金流向
    fund_flow_sectors = get_sector_flow_rank('3')
    
    # === 交叉验证 ===
    all_events = announcements + policy_news
    sector_analysis = cross_validate_sectors(
        all_events, zt_df, fund_flow_sectors, research_reports
    )
    
    # === 摘要 ===
    total_announcements = len(announcements)
    total_policy = len(policy_news)
    high_conf_sectors = [s for s in sector_analysis if s['confidence'] == '高']
    
    summary = (
        f"资源池采集完成：公告 {total_announcements} 条 | 政策新闻 {total_policy} 条 | "
        f"板块分析 {len(sector_analysis)} 个 | 高置信板块 {len(high_conf_sectors)} 个"
    )
    
    return {
        'timestamp': datetime.now().isoformat(),
        'date': date_str,
        'announcements': announcements,
        'research_reports': research_reports,
        'policy_news': policy_news,
        'sector_analysis': sector_analysis,
        'summary': summary,
    }


# ═══════════════════════════════════════════
# 命令行
# ═══════════════════════════════════════════

if __name__ == '__main__':
    import sys
    
    print("=" * 60)
    print("🔬 基本面事件智能池 v1.0")
    print("=" * 60)
    
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    
    # 获取涨停数据（如果有）
    zt_df = None
    try:
        import akshare as ak
        zt_df = ak.stock_zt_pool_em(date=date_str or datetime.now().strftime('%Y%m%d'))
    except Exception:
        pass
    
    pool = build_resource_pool(date_str, zt_df)
    
    print(f"\n{pool['summary']}\n")
    
    # 输出前5个板块分析
    for s in pool['sector_analysis'][:5]:
        print(f"### {s['sector']} | 评分:{s['cross_score']} | 置信度:{s['confidence']}")
        print(f"    事件: {s['events_count']}条 | 涨停:{s['zt_count']}只 | "
              f"资金:{s['fund_flow']:.0f}万 | 研报买入:{s['research_buy']}")
        print(f"    驱动: {' · '.join(s['event_drivers'][:3])}")
        print(f"    关键股: {', '.join(st['name'] for st in s['key_stocks'][:3])}")
        print()
    
    # 保存
    output_dir = SCRIPT_DIR.parent / 'data' / 'resource_pool'
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"pool_{datetime.now().strftime('%Y%m%d')}.json"
    
    # 简化输出（去掉非序列化的）
    save_data = {
        'timestamp': pool['timestamp'],
        'date': pool['date'],
        'summary': pool['summary'],
        'sector_analysis': [
            {k: v for k, v in s.items() if k != 'event_details'} 
            for s in pool['sector_analysis']
        ],
        'announcements_count': len(pool['announcements']),
        'research_count': len(pool['research_reports']),
        'policy_count': len(pool['policy_news']),
    }
    output_path.write_text(json.dumps(save_data, ensure_ascii=False, indent=2, default=str))
    print(f"✅ 已保存: {output_path}")
