#!/usr/bin/env python3
"""
silver_verifier.py — Silver 层质量验证
=======================================
验证清洗后数据的完整性、一致性、质量标记分布。

用法:
  python3 silver_verifier.py --date 2026-06-03
  python3 silver_verifier.py --report
"""

import json, gzip, sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

SCRIPT_DIR = Path(__file__).resolve().parent
SILVER_ROOT = SCRIPT_DIR.parent / 'data' / 'silver'


def verify_date(date: str) -> Dict:
    """验证指定日期的 Silver 数据"""
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    file_path = (SILVER_ROOT / 'stock_daily' / str(date_obj.year) /
                 f'{date_obj.month:02d}' / f'{date_obj.day:02d}' /
                 'all.json.gz')

    result = {
        'date': date,
        'checked_at': datetime.now().isoformat(),
        'exists': False,
        'n_rows': 0,
        'n_suspended': 0,
        'n_outliers': 0,
        'quality_flags': {},
        'field_completeness': {},
        'issues': [],
        'overall': 'missing',
    }

    if not file_path.exists():
        result['issues'].append('Silver 文件不存在')
        return result

    result['exists'] = True

    try:
        data = json.loads(gzip.decompress(file_path.read_bytes()))
        result['n_rows'] = len(data)

        if len(data) == 0:
            result['overall'] = 'degraded'
            result['issues'].append('数据为空')
            return result

        # 字段完整性
        required_fields = ['code', 'name', 'close', 'change_pct', 'volume']
        for field in required_fields:
            valid = sum(1 for r in data if r.get(field))
            pct = round(valid / len(data) * 100, 1)
            result['field_completeness'][field] = f'{pct}%'

        # 质量标记统计
        flag_counts = {}
        n_suspended = 0
        for r in data:
            if r.get('is_suspended'):
                n_suspended += 1
            for f in r.get('quality_flags', []):
                flag_counts[f] = flag_counts.get(f, 0) + 1

        result['n_suspended'] = n_suspended
        result['n_outliers'] = sum(flag_counts.values())
        result['quality_flags'] = flag_counts

        # 判定
        if result['field_completeness'].get('close', '0%') == '0%':
            result['overall'] = 'down'
            result['issues'].append('收盘价全空')
        elif n_suspended / max(len(data), 1) > 0.5:
            result['overall'] = 'degraded'
            result['issues'].append(f'停牌率过高: {n_suspended}/{len(data)}')
        else:
            result['overall'] = 'ok'

    except Exception as e:
        result['overall'] = 'down'
        result['issues'].append(f'读取失败: {e}')

    return result


def format_report(results: Dict) -> str:
    lines = []
    icon = {'ok': '✅', 'degraded': '⚠️', 'missing': '🔴', 'down': '🚨'}
    s = icon.get(results['overall'], '❓')

    lines.append(f'# {s} Silver 层质量验证')
    lines.append(f'> {results["date"]} · {results["checked_at"][:19]}')
    lines.append(f'> 综合: **{results["overall"]}** | 行数: {results.get("n_rows", 0)}')
    lines.append('')

    if results.get('field_completeness'):
        lines.append('### 字段完整性')
        for f, pct in results['field_completeness'].items():
            lines.append(f'- {f}: {pct}')

    if results.get('quality_flags'):
        lines.append('\n### 质量标记')
        for flag, count in results['quality_flags'].items():
            lines.append(f'- {flag}: {count} 只')

    if results.get('issues'):
        lines.append('\n### 问题')
        for issue in results['issues']:
            lines.append(f'- ⚠️ {issue}')

    return '\n'.join(lines)


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', type=str, help='验证日期')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args()

    date = args.date or datetime.now().strftime('%Y-%m-%d')
    results = verify_date(date)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print(format_report(results))

    if results['overall'] in ('degraded', 'down', 'missing'):
        sys.exit(1)
