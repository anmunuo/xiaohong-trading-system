#!/usr/bin/env python3
"""
bronze_verifier.py — Bronze 层完整性验证
=========================================
每日验证 Bronze 数据是否完整、可读、无损坏。

用法:
  python3 bronze_verifier.py --date 2026-06-03
  python3 bronze_verifier.py --today
"""

import json, gzip, sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
BRONZE_ROOT = SCRIPT_DIR.parent / 'data' / 'bronze'
META_DIR = BRONZE_ROOT / '_meta'

EXPECTED_SOURCES = {
    'daily_kline':  {'min_sources': 1, 'min_items': 100, 'label': '日K线'},
    'fund_flow':    {'min_sources': 1, 'min_items': 10,  'label': '资金流向'},
    'market_index': {'min_sources': 1, 'min_items': 3,   'label': '全球指数'},
    'events':       {'min_sources': 1, 'min_items': 10,  'label': '事件数据'},
    'intraday':     {'min_sources': 1, 'min_items': 5,   'label': '分时K线'},
}


def verify_date(date: str) -> Dict:
    """验证指定日期的 Bronze 数据完整性"""
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    dir_path = (BRONZE_ROOT / str(date_obj.year) /
                f'{date_obj.month:02d}' / f'{date_obj.day:02d}')

    results = {
        'date': date,
        'checked_at': datetime.now().isoformat(),
        'categories': {},
        'overall': 'ok',
        'issues': [],
    }

    if not dir_path.exists():
        # 遍历所有子目录查找
        found = list(BRONZE_ROOT.rglob(f'*{date_obj.day:02d}*'))
        if not found:
            results['overall'] = 'missing'
            results['issues'].append(f'{date}: 无 Bronze 数据')
            return results
        dir_path = found[0].parent if found else dir_path

    total_items = 0
    total_sources = 0

    for category, spec in EXPECTED_SOURCES.items():
        cat_path = (BRONZE_ROOT / category / str(date_obj.year) /
                    f'{date_obj.month:02d}' / f'{date_obj.day:02d}')

        cat_result = {'status': 'ok', 'sources': [], 'items': 0, 'issues': []}

        if cat_path.exists():
            gz_files = list(cat_path.glob('*.json.gz'))
            cat_result['sources'] = [f.stem.replace('.json', '') for f in gz_files]
            cat_result['items'] = 0

            for gz in gz_files:
                try:
                    data = json.loads(gzip.decompress(gz.read_bytes()))
                    if isinstance(data, list):
                        cat_result['items'] += len(data)
                    elif isinstance(data, dict):
                        cat_result['items'] += len(data)
                except Exception as e:
                    cat_result['issues'].append(f'{gz.name}: 损坏 ({e})')

            if not gz_files:
                cat_result['status'] = 'missing'
                cat_result['issues'].append('无数据文件')
            elif cat_result['items'] < spec['min_items']:
                cat_result['status'] = 'insufficient'
                cat_result['issues'].append(
                    f'条目不足: {cat_result["items"]} < {spec["min_items"]}')

        else:
            cat_result['status'] = 'missing'
            cat_result['issues'].append('目录不存在')

        total_items += cat_result['items']
        total_sources += len(cat_result.get('sources', []))

        if cat_result['status'] != 'ok':
            results['issues'].append(
                f'{spec["label"]}: {cat_result["status"]} ({"; ".join(cat_result["issues"])})'
            )

        results['categories'][category] = cat_result

    # 综合判定
    ok_cats = sum(1 for c in results['categories'].values() if c['status'] == 'ok')
    if ok_cats == 0:
        results['overall'] = 'down'
    elif ok_cats < len(EXPECTED_SOURCES):
        results['overall'] = 'degraded'

    results['total_items'] = total_items
    results['total_sources'] = total_sources
    results['completeness'] = round(ok_cats / len(EXPECTED_SOURCES) * 100, 1)

    return results


def format_report(results: Dict) -> str:
    """格式化验证报告"""
    lines = []
    icon = {'ok': '✅', 'degraded': '⚠️', 'missing': '🔴', 'down': '🚨'}
    status_icon = icon.get(results['overall'], '❓')

    lines.append(f'# {status_icon} Bronze 层完整性验证')
    lines.append(f'> {results["date"]}  ·  检查时间: {results["checked_at"][:19]}')
    lines.append(f'> 综合: **{results["overall"]}** ({results["completeness"]}%)')
    lines.append(f'> 数据源: {results.get("total_sources", 0)}个  ·  条目: {results.get("total_items", 0)}')
    lines.append('')

    for cat, info in results.get('categories', {}).items():
        label = EXPECTED_SOURCES.get(cat, {}).get('label', cat)
        s_icon = '✅' if info['status'] == 'ok' else '⚠️'
        lines.append(f'### {s_icon} {label}')
        lines.append(f'- 数据源: {info.get("sources", [])}')
        lines.append(f'- 条目数: {info.get("items", 0)}')
        if info.get('issues'):
            for issue in info['issues']:
                lines.append(f'- ⚠️ {issue}')
        lines.append('')

    if results.get('issues'):
        lines.append('---')
        lines.append('### 问题清单')
        for issue in results['issues']:
            lines.append(f'- {issue}')

    return '\n'.join(lines)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', type=str, help='验证日期 YYYY-MM-DD')
    ap.add_argument('--today', action='store_true', help='验证今天')
    ap.add_argument('--json', action='store_true', help='JSON输出')
    args = ap.parse_args()

    date = args.date or (datetime.now().strftime('%Y-%m-%d') if args.today else None)
    if not date:
        print('请指定 --date YYYY-MM-DD 或 --today')
        sys.exit(1)

    results = verify_date(date)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(format_report(results))

    if results['overall'] in ('degraded', 'down', 'missing'):
        sys.exit(1)
