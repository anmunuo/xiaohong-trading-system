#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 基本面知识库
================================
【定位】

不是一次性报告，而是持续积累的结构化知识库：
  · 每小时增量采集公告/新闻/研报/政策
  · 自动去重 → 按日期/板块/个股三级索引
  · 最新线索秒级检索 → 供瞭望塔/侦察兵/决策官调用

【目录结构】

  data/knowledge_base/
  ├── index.json              # 总索引（最新时间戳 + 各分区条目数）
  ├── leads/
  │   └── latest.json         # 最新高价值线索 Top 20
  ├── announcements/
  │   └── YYYY-MM-DD.json     # 每日公告事件
  ├── policy_news/
  │   └── YYYY-MM-DD.json     # 每日政策/宏观新闻
  ├── research/
  │   └── YYYY-MM-DD.json     # 每日研报摘要
  ├── sector_events/
  │   └── YYYY-MM-DD.json     # 按板块聚合的事件
  ├── stock_events/
  │   └── {code}.json         # 单只股票的历史事件链
  └── search_index.json       # 关键词→事件ID 倒排索引

【检索接口】

  python3 knowledge_base.py search --sector 半导体
  python3 knowledge_base.py search --stock 688525
  python3 knowledge_base.py search --keyword 合同签订
  python3 knowledge_base.py leads              # 最新线索
  python3 knowledge_base.py stats              # 库统计
  python3 knowledge_base.py collect            # 手动采集（cron 也调用此模式）

版本: 1.0.0
创建: 2026-05-27
"""

import os, sys, json, hashlib
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# 抑制噪音
os.environ['TQDM_DISABLE'] = '1'

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

KB_ROOT = SCRIPT_DIR.parent / 'data' / 'knowledge_base'

# 保留天数
RETENTION_DAYS = 7
# 每条记录唯一标识的字段组合
DEDUP_FIELDS = ['code', 'title', 'date', 'source']


# ═══════════════════════════════════════════
# 存储引擎
# ═══════════════════════════════════════════

def _ensure_dirs():
    """确保目录结构存在"""
    for sub in ['announcements', 'policy_news', 'research', 
                'sector_events', 'stock_events', 'leads']:
        (KB_ROOT / sub).mkdir(parents=True, exist_ok=True)


def _content_hash(record: dict) -> str:
    """生成记录唯一哈希（用于去重）"""
    key_parts = []
    for f in DEDUP_FIELDS:
        val = record.get(f, '')
        if isinstance(val, list):
            val = ','.join(sorted(val))
        key_parts.append(str(val)[:100])
    return hashlib.md5('|'.join(key_parts).encode()).hexdigest()[:12]


def _load_existing(date_str: str, category: str) -> tuple:
    """加载已有数据，返回 (records_list, hash_set)"""
    path = KB_ROOT / category / f'{date_str}.json'
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding='utf-8'))
            hashes = {_content_hash(r) for r in existing}
            return existing, hashes
        except Exception:
            return [], set()
    return [], set()


def _save_records(date_str: str, category: str, records: list):
    """保存记录到日期文件"""
    path = KB_ROOT / category / f'{date_str}.json'
    # 序列化处理：确保所有值可 JSON 化
    clean = []
    for r in records:
        item = {}
        for k, v in r.items():
            if isinstance(v, datetime):
                item[k] = v.isoformat()
            elif hasattr(v, 'item'):  # numpy types
                item[k] = v.item()
            else:
                try:
                    json.dumps({k: v})
                    item[k] = v
                except Exception:
                    item[k] = str(v)
        clean.append(item)
    path.write_text(json.dumps(clean, ensure_ascii=False, indent=2))


def _update_search_index(new_records: list):
    """更新倒排索引"""
    idx_path = KB_ROOT / 'search_index.json'
    index = {}
    if idx_path.exists():
        try:
            index = json.loads(idx_path.read_text(encoding='utf-8'))
        except Exception:
            pass
    
    for r in new_records:
        event_id = _content_hash(r)
        # 提取可搜索文本
        search_text = ' '.join([
            r.get('title', ''),
            r.get('name', ''),
            r.get('code', ''),
            r.get('event_type', ''),
            r.get('event_label', ''),
            r.get('source', ''),
            ' '.join(r.get('sector_tags', [])),
        ])
        
        # 分词（按常见分隔符）
        words = set()
        for token in search_text.replace(':', ' ').replace('：', ' ').split():
            token = token.strip()
            if len(token) >= 2:
                words.add(token)
                # 也存 bigram
                words.add(token[:4])
        
        for w in words:
            if w not in index:
                index[w] = []
            if event_id not in index[w]:
                index[w].append(event_id)
    
    # 清理过期索引（保留最近30天）
    # 暂不实现全量清理，增量更新即可
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))


def _update_stock_events(new_records: list):
    """更新单只股票的事件历史"""
    for r in new_records:
        code = r.get('code', '')
        if not code:
            continue
        path = KB_ROOT / 'stock_events' / f'{code}.json'
        existing = []
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding='utf-8'))
            except Exception:
                pass
        
        hashes = {_content_hash(e) for e in existing}
        r_hash = _content_hash(r)
        if r_hash not in hashes:
            existing.append({
                'date': r.get('date', ''),
                'title': r.get('title', ''),
                'event_type': r.get('event_type', ''),
                'event_label': r.get('event_label', ''),
                'source': r.get('source', ''),
                'hash': r_hash,
            })
            # 只保留最近 30 条
            existing = existing[-30:]
            path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))


def _update_leads(all_new: list):
    """更新最新线索 Top 20（按权重排序）"""
    path = KB_ROOT / 'leads' / 'latest.json'
    
    # 加载现有线索
    existing = []
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            pass
    
    # 合并 + 去重
    existing_hashes = {_content_hash(e) for e in existing}
    for r in all_new:
        if _content_hash(r) not in existing_hashes:
            existing.append(r)
    
    # 按权重 + 新鲜度排序
    def sort_key(r):
        weight = r.get('event_weight', 0)
        date_str = str(r.get('date', ''))
        # 今天的事件加成
        today = datetime.now().strftime('%Y%m%d')
        freshness = 1.5 if date_str == today else 1.0
        return weight * freshness
    
    existing.sort(key=sort_key, reverse=True)
    
    # Top 20，精简字段
    leads = []
    for r in existing[:20]:
        leads.append({
            'code': r.get('code', ''),
            'name': r.get('name', ''),
            'title': (r.get('title', '') or '')[:80],
            'event_label': r.get('event_label', ''),
            'sector_tags': r.get('sector_tags', []),
            'source': r.get('source', ''),
            'date': str(r.get('date', '')),
            'hash': _content_hash(r),
        })
    
    path.write_text(json.dumps(leads, ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════
# 采集主逻辑
# ═══════════════════════════════════════════

def collect_all(date_str: str = None) -> dict:
    """
    全量采集 → 去重 → 存储
    
    Returns:
        {
            new_announcements: int,
            new_policy: int,
            new_research: int,
            total_new: int,
            leads_updated: bool,
        }
    """
    if date_str is None:
        date_str = datetime.now().strftime('%Y%m%d')
    
    date_display = f"{date_str[:4]}-{date_str[1:4]}-{date_str[4:]}"
    _ensure_dirs()
    
    all_new = []
    stats = {
        'new_announcements': 0,
        'new_policy': 0,
        'new_research': 0,
        'total_new': 0,
        'leads_updated': False,
        'timestamp': datetime.now().isoformat(),
    }
    
    # === 1. 公司公告 ===
    try:
        from resource_pool import fetch_corporate_announcements, fetch_research_reports, fetch_policy_macro_news
        
        # 公告
        announcements = fetch_corporate_announcements(date_str)
        existing, hashes = _load_existing(date_display, 'announcements')
        existing_before = len(existing)
        for a in announcements:
            if _content_hash(a) not in hashes:
                existing.append(a)
                hashes.add(_content_hash(a))
                all_new.append(a)
        stats['new_announcements'] = len(existing) - existing_before
        if stats['new_announcements'] > 0:
            _save_records(date_display, 'announcements', existing)
        
        # 政策/宏观
        policy_news = fetch_policy_macro_news()
        existing_p, hashes_p = _load_existing(date_display, 'policy_news')
        existing_p_before = len(existing_p)
        for p in policy_news:
            if _content_hash(p) not in hashes_p:
                existing_p.append(p)
                hashes_p.add(_content_hash(p))
                all_new.append(p)
        stats['new_policy'] = len(existing_p) - existing_p_before
        if stats['new_policy'] > 0:
            _save_records(date_display, 'policy_news', existing_p)
        
        # 研报
        hot_codes = list(set(a.get('code', '') for a in announcements if a.get('code')))
        research = fetch_research_reports(hot_codes[:30] if hot_codes else [])
        existing_r, hashes_r = _load_existing(date_display, 'research')
        existing_r_before = len(existing_r)
        for r in research:
            if _content_hash(r) not in hashes_r:
                existing_r.append(r)
                hashes_r.add(_content_hash(r))
                all_new.append(r)
        stats['new_research'] = len(existing_r) - existing_r_before
        if stats['new_research'] > 0:
            _save_records(date_display, 'research', existing_r)
        
    except Exception as e:
        stats['error'] = str(e)
        return stats
    
    stats['total_new'] = len(all_new)
    
    # === 2. 更新检索基础设施 ===
    if all_new:
        _update_search_index(all_new)
        _update_stock_events(all_new)
        _update_leads(all_new)
        stats['leads_updated'] = True
    
    # === 3. 更新总索引 ===
    _update_master_index(stats)
    
    # === 4. 清理过期数据 ===
    _cleanup_old_files()
    
    return stats


def _update_master_index(stats: dict):
    """更新总索引文件"""
    idx_path = KB_ROOT / 'index.json'
    index = {
        'last_collection': stats['timestamp'],
        'total_events_today': stats['total_new'],
        'categories': {
            'announcements': stats['new_announcements'],
            'policy_news': stats['new_policy'],
            'research': stats['new_research'],
        },
    }
    idx_path.write_text(json.dumps(index, ensure_ascii=False, indent=2))


def _cleanup_old_files():
    """清理超过保留期的数据文件"""
    cutoff = datetime.now() - timedelta(days=RETENTION_DAYS)
    for category in ['announcements', 'policy_news', 'research']:
        cat_dir = KB_ROOT / category
        if not cat_dir.exists():
            continue
        for f in cat_dir.glob('*.json'):
            try:
                date_part = f.stem[:10]
                file_date = datetime.strptime(date_part, '%Y-%m-%d')
                if file_date < cutoff:
                    f.unlink()
            except Exception:
                pass


# ═══════════════════════════════════════════
# 检索接口
# ═══════════════════════════════════════════

def search_leads() -> list:
    """获取最新高价值线索"""
    path = KB_ROOT / 'leads' / 'latest.json'
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding='utf-8'))


def search_by_sector(sector: str, limit: int = 10) -> list:
    """按板块搜索事件"""
    results = []
    for category in ['announcements', 'policy_news']:
        cat_dir = KB_ROOT / category
        if not cat_dir.exists():
            continue
        for f in sorted(cat_dir.glob('*.json'), reverse=True):
            try:
                records = json.loads(f.read_text(encoding='utf-8'))
                for r in records:
                    if sector in r.get('sector_tags', []):
                        results.append(r)
                        if len(results) >= limit:
                            return results
            except Exception:
                pass
    return results


def search_by_stock(code: str, limit: int = 20) -> list:
    """按股票代码搜索事件历史"""
    path = KB_ROOT / 'stock_events' / f'{code}.json'
    if not path.exists():
        return []
    events = json.loads(path.read_text(encoding='utf-8'))
    return events[-limit:]


def search_by_keyword(keyword: str, limit: int = 10) -> list:
    """通过倒排索引按关键词搜索"""
    idx_path = KB_ROOT / 'search_index.json'
    if not idx_path.exists():
        return []
    
    index = json.loads(idx_path.read_text(encoding='utf-8'))
    event_ids = index.get(keyword, [])[:limit * 2]
    
    # 从各分区文件中找回完整记录
    results = []
    found_ids = set()
    for category in ['announcements', 'policy_news', 'research']:
        cat_dir = KB_ROOT / category
        if not cat_dir.exists():
            continue
        for f in sorted(cat_dir.glob('*.json'), reverse=True):
            try:
                records = json.loads(f.read_text(encoding='utf-8'))
                for r in records:
                    rid = _content_hash(r)
                    if rid in event_ids and rid not in found_ids:
                        results.append(r)
                        found_ids.add(rid)
                        if len(results) >= limit:
                            return results
            except Exception:
                pass
    return results


def get_stats() -> dict:
    """获取知识库统计信息"""
    idx_path = KB_ROOT / 'index.json'
    stats = {
        'total_files': 0,
        'total_events': 0,
        'latest_leads': 0,
        'stock_events_count': 0,
    }
    
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text(encoding='utf-8'))
            stats['last_collection'] = idx.get('last_collection', 'N/A')
        except Exception:
            stats['last_collection'] = 'N/A'
    
    for category in ['announcements', 'policy_news', 'research']:
        cat_dir = KB_ROOT / category
        if cat_dir.exists():
            for f in cat_dir.glob('*.json'):
                stats['total_files'] += 1
                try:
                    records = json.loads(f.read_text(encoding='utf-8'))
                    stats['total_events'] += len(records)
                except Exception:
                    pass
    
    leads_path = KB_ROOT / 'leads' / 'latest.json'
    if leads_path.exists():
        try:
            stats['latest_leads'] = len(json.loads(leads_path.read_text(encoding='utf-8')))
        except Exception:
            pass
    
    stock_dir = KB_ROOT / 'stock_events'
    if stock_dir.exists():
        stats['stock_events_count'] = len(list(stock_dir.glob('*.json')))
    
    return stats


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description='小红·基本面知识库')
    sub = parser.add_subparsers(dest='command')
    
    # collect
    sub.add_parser('collect', help='执行一次采集')
    
    # search
    p_search = sub.add_parser('search', help='搜索')
    p_search.add_argument('--sector', help='按板块搜索')
    p_search.add_argument('--stock', help='按股票代码搜索')
    p_search.add_argument('--keyword', help='按关键词搜索')
    p_search.add_argument('--limit', type=int, default=10, help='返回条数')
    
    # leads
    sub.add_parser('leads', help='查看最新线索')
    
    # stats
    sub.add_parser('stats', help='查看知识库统计')
    
    args = parser.parse_args()
    
    if args.command == 'collect':
        print("📡 开始采集...")
        stats = collect_all()
        print(f"✅ 采集完成")
        print(f"   新增公告: {stats['new_announcements']} 条")
        print(f"   新增政策: {stats['new_policy']} 条")
        print(f"   新增研报: {stats['new_research']} 条")
        print(f"   总计新增: {stats['total_new']} 条")
        if stats.get('leads_updated'):
            print(f"   线索已更新 ✓")
        if stats.get('error'):
            print(f"   ⚠️ 采集错误: {stats['error']}")
        # 输出 JSON 供 cron 消费
        print(json.dumps(stats, ensure_ascii=False))
        
    elif args.command == 'search':
        results = []
        if args.sector:
            results = search_by_sector(args.sector, args.limit)
            print(f"🔍 板块 [{args.sector}] 搜索结果 ({len(results)} 条):")
        elif args.stock:
            results = search_by_stock(args.stock, args.limit)
            print(f"🔍 个股 [{args.stock}] 事件历史 ({len(results)} 条):")
        elif args.keyword:
            results = search_by_keyword(args.keyword, args.limit)
            print(f"🔍 关键词 [{args.keyword}] 搜索结果 ({len(results)} 条):")
        
        for i, r in enumerate(results, 1):
            code = r.get('code', '')
            name = r.get('name', '')
            title = (r.get('title', '') or '')[:80]
            label = r.get('event_label', '')
            date = r.get('date', '')
            print(f"  {i}. [{label}] {name}({code}) {date} | {title}")
            
    elif args.command == 'leads':
        leads = search_leads()
        print(f"🔦 最新线索 Top {len(leads)}:")
        for i, l in enumerate(leads, 1):
            sectors = ', '.join(l.get('sector_tags', []))
            print(f"  {i}. [{l.get('event_label')}] {l.get('name')}({l.get('code')}) "
                  f"| {sectors} | {(l.get('title') or '')[:60]}")
            
    elif args.command == 'stats':
        s = get_stats()
        print("📊 知识库统计:")
        for k, v in s.items():
            print(f"  {k}: {v}")
    
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
