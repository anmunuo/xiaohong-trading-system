#!/usr/bin/env python3
"""
auto_heal.py — 系统自愈引擎 v1.0
================================
读取 system_health_check 结果 → 逐项自动修复 → 重新检查 → 报告

用法:
  python3 auto_heal.py              # 全自愈
  python3 auto_heal.py --dry-run    # 仅诊断，不执行修复

Cron: 建议 08:10 运行（开盘前 15 分钟留余量）
"""

import json, os, sys, time, subprocess
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
HEALTH_LOG = WORKSPACE / "data" / "auto_heal_log.json"

__version__ = "1.0.0"


# ═══════════════════════════════════════════
# 修复策略表
# ═══════════════════════════════════════════

FIX_STRATEGIES = {
    # ── 数据新鲜度 ──
    'mega_latest_stale': {
        'desc': 'mega_latest 过期',
        'action': 'run_mega_collector',
        'priority': 0,
    },
    'mega_latest_missing': {
        'desc': 'mega_latest 缺失',
        'action': 'run_mega_collector',
        'priority': 0,
    },
    'daily_pool_stale': {
        'desc': 'daily_pool 过期',
        'action': 'run_recommender',
        'priority': 0,
    },
    'daily_pool_missing': {
        'desc': 'daily_pool 缺失',
        'action': 'run_recommender',
        'priority': 0,
    },
    'kb_insights_stale': {
        'desc': 'kb_insights 过期',
        'action': 'run_kb_digest',
        'priority': 1,
    },
    'market_snapshot_missing': {
        'desc': 'market_snapshot 缺失',
        'action': 'run_market_snapshot',
        'priority': 1,
    },

    # ── 持仓估值 ──
    'valuation_no_price': {
        'desc': '持仓无最新价',
        'action': 'run_ammo_update',
        'priority': 0,
    },

    # ── 弹药库 ──
    'ammo_r_value_missing': {
        'desc': 'R值未设置',
        'action': 'run_ammo_update',
        'priority': 0,
    },
    'ammo_drawdown_missing': {
        'desc': '回撤未计算',
        'action': 'run_ammo_update',
        'priority': 0,
    },

    # ── 议会链路 ──
    'parliament_log_missing': {
        'desc': '议会日志缺失',
        'action': 'run_parliament',
        'priority': 1,
    },

    # ── 研究员质量 ──
    'research_report_empty': {
        'desc': '研学报告空壳',
        'action': 'run_researcher_study',
        'priority': 1,
    },
    'research_report_missing': {
        'desc': '研学报告未生成',
        'action': 'run_researcher_study',
        'priority': 1,
    },

    # ── 侦察兵 ──
    'scout_degraded': {
        'desc': '侦察兵数据降级',
        'action': 'notify_scout_degraded',
        'priority': 2,
    },

    # ── 数据管线 ──
    'push2_degraded': {
        'desc': '东方财富 push2 降级',
        'action': 'switch_push2_fallback',
        'priority': 1,
    },
}


def run_mega_collector() -> bool:
    """运行知识库采集器"""
    try:
        result = subprocess.run(
            ['python3', str(SCRIPT_DIR / 'mega_collector.py'), '--quick'],
            capture_output=True, text=True, timeout=120,
            cwd=str(SCRIPT_DIR)
        )
        return result.returncode == 0
    except Exception:
        return False


def run_recommender() -> bool:
    """运行推荐引擎"""
    try:
        result = subprocess.run(
            ['python3', str(SCRIPT_DIR / 'stock_recommender.py'), '--top', '9'],
            capture_output=True, text=True, timeout=120,
            cwd=str(SCRIPT_DIR)
        )
        return result.returncode == 0
    except Exception:
        return False


def run_ammo_update() -> bool:
    """更新持仓估值"""
    try:
        result = subprocess.run(
            ['python3', str(SCRIPT_DIR / 'ammo_risk.py'), '--update'],
            capture_output=True, text=True, timeout=30,
            cwd=str(SCRIPT_DIR)
        )
        return result.returncode == 0
    except Exception:
        return False


def run_parliament() -> bool:
    """运行研究员议会"""
    try:
        result = subprocess.run(
            ['python3', str(SCRIPT_DIR / 'researchers.py'), '--parliament',
             '--topic', '盘前系统自愈诊断'],
            capture_output=True, text=True, timeout=60,
            cwd=str(SCRIPT_DIR)
        )
        return result.returncode == 0
    except Exception:
        return False


def run_researcher_study() -> bool:
    """运行研究员自主研学"""
    try:
        result = subprocess.run(
            ['python3', str(SCRIPT_DIR / 'researchers.py'), '--study'],
            capture_output=True, text=True, timeout=60,
            cwd=str(SCRIPT_DIR)
        )
        return result.returncode == 0
    except Exception:
        return False


def run_kb_digest() -> bool:
    """运行知识库 LLM 消化"""
    try:
        result = subprocess.run(
            ['python3', str(SCRIPT_DIR / 'data_pipeline.py')],
            capture_output=True, text=True, timeout=30,
            cwd=str(SCRIPT_DIR)
        )
        return result.returncode == 0
    except Exception:
        return False


def run_market_snapshot() -> bool:
    """生成市场快照"""
    try:
        result = subprocess.run(
            ['python3', str(SCRIPT_DIR / 'market_snapshot.py')],
            capture_output=True, text=True, timeout=60,
            cwd=str(SCRIPT_DIR)
        )
        return result.returncode == 0
    except Exception:
        return False


# ═══════════════════════════════════════════
# 诊断 + 修复引擎
# ═══════════════════════════════════════════

def diagnose_issues(health: dict) -> list:
    """从健康检查结果提取需要修复的问题"""
    issues = []
    checks = health.get('checks', {})

    # 数据新鲜度
    freshness = checks.get('1_data_freshness', {})
    for name in ['mega_latest', 'daily_pool', 'kb_insights', 'market_snapshot']:
        info = freshness.get(name, {})
        status = info.get('status', 'ok')
        key = f'{name}_{status}'
        if key in FIX_STRATEGIES:
            issues.append(FIX_STRATEGIES[key])

    # 估值同步
    val = checks.get('2_valuation_sync', {})
    if val.get('issues'):
        for iss in val['issues']:
            if '无最新价' in str(iss) or 'lastPrice' in str(iss):
                issues.append(FIX_STRATEGIES['valuation_no_price'])
                break

    # 弹药库
    ammo = checks.get('4_ammo_risk', {})
    if ammo.get('issues'):
        for iss in ammo['issues']:
            if 'R 值' in str(iss):
                issues.append(FIX_STRATEGIES['ammo_r_value_missing'])
            if '回撤' in str(iss):
                issues.append(FIX_STRATEGIES['ammo_drawdown_missing'])

    # 议会
    parliament = checks.get('3_parliament_flow', {})
    if not parliament.get('parliament_in_pool'):
        issues.append(FIX_STRATEGIES['parliament_log_missing'])

    # 研究员
    research = checks.get('7_researcher_quality', {})
    for iss in research.get('issues', []):
        if '空壳' in str(iss):
            issues.append(FIX_STRATEGIES['research_report_empty'])
        if '未生成' in str(iss):
            issues.append(FIX_STRATEGIES['research_report_missing'])

    # 数据管线降级
    pipeline = checks.get('5_data_pipeline', {})
    providers = pipeline.get('providers', {})
    if 'degraded' in str(providers.get('push2_list', '')):
        issues.append(FIX_STRATEGIES['push2_degraded'])

    # 侦察兵降级
    scout = checks.get('6_scout_sniper', {})
    scout_info = scout.get('scout', {})
    if scout_info.get('status') == 'degraded':
        issues.append(FIX_STRATEGIES['scout_degraded'])

    return issues


def apply_fix(strategy: dict, dry_run: bool) -> dict:
    """执行一条修复策略"""
    action = strategy['action']
    desc = strategy['desc']

    action_map = {
        'run_mega_collector': run_mega_collector,
        'run_recommender': run_recommender,
        'run_ammo_update': run_ammo_update,
        'run_parliament': run_parliament,
        'run_researcher_study': run_researcher_study,
        'run_kb_digest': run_kb_digest,
        'run_market_snapshot': run_market_snapshot,
    }

    result = {
        'strategy': action,
        'desc': desc,
        'dry_run': dry_run,
        'success': None,
    }

    if dry_run:
        result['success'] = 'skipped'
        return result

    fn = action_map.get(action)
    if fn:
        try:
            ok = fn()
            result['success'] = ok
        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
    else:
        result['success'] = 'unknown_action'

    return result


def run_auto_heal(dry_run: bool = False, max_rounds: int = 3) -> dict:
    """执行自愈循环"""
    log_entries = []

    for round_num in range(1, max_rounds + 1):
        # 1. 健康检查
        try:
            result = subprocess.run(
                ['python3', str(SCRIPT_DIR / 'system_health_check.py'), '--json'],
                capture_output=True, text=True, timeout=60,
                cwd=str(SCRIPT_DIR)
            )
            health = json.loads(result.stdout) if result.returncode in (0, 1) else {
                'overall': 'down', 'checks': {}, 'issue_count': 1}
        except Exception as e:
            health = {'overall': 'down', 'checks': {}, 'issue_count': 1,
                      'error': str(e)}

        issues = diagnose_issues(health)
        round_entry = {
            'round': round_num,
            'overall_before': health.get('overall', 'unknown'),
            'issue_count_before': health.get('issue_count', len(issues)),
            'issues_found': len(issues),
            'fixes': [],
        }

        if not issues:
            round_entry['message'] = '系统健康，无需修复'
            log_entries.append(round_entry)
            break

        # 2. 按优先级排序并去重
        seen = set()
        unique_fixes = []
        for s in sorted(issues, key=lambda x: x['priority']):
            if s['action'] not in seen:
                seen.add(s['action'])
                unique_fixes.append(s)

        # 3. 执行修复
        for fix in unique_fixes:
            fr = apply_fix(fix, dry_run)
            round_entry['fixes'].append(fr)

        log_entries.append(round_entry)

        # 4. 短暂等待让修复生效
        time.sleep(2)

    # 最终检查
    try:
        final = subprocess.run(
            ['python3', str(SCRIPT_DIR / 'system_health_check.py'), '--json'],
            capture_output=True, text=True, timeout=60,
            cwd=str(SCRIPT_DIR)
        )
        final_health = json.loads(final.stdout) if final.returncode in (0, 1) else {
            'overall': 'unknown'}
    except Exception:
        final_health = {'overall': 'unknown'}

    return {
        'version': __version__,
        'timestamp': datetime.now().isoformat(),
        'dry_run': dry_run,
        'rounds': len(log_entries),
        'log': log_entries,
        'final_status': final_health.get('overall', 'unknown'),
        'final_issues': final_health.get('issue_count', 0),
    }


def format_report(result: dict) -> str:
    """格式化自愈报告"""
    lines = [
        f"# 🩺 系统自愈报告  v{__version__}",
        f"> {result['timestamp'][:19]}",
        f"> 模式: {'🔍 诊断' if result['dry_run'] else '🔧 自愈'}  |  "
        f"轮次: {result['rounds']}  |  终态: **{result['final_status']}**",
        "",
        "---",
        "",
    ]

    for entry in result['log']:
        r = entry['round']
        icon = '✅' if entry['issue_count_before'] == 0 else '🔧'
        lines.append(f"### {icon} Round {r}")
        lines.append(f"修复前: {entry['overall_before']} ({entry['issue_count_before']} 项问题)")
        if entry.get('message'):
            lines.append(f"> {entry['message']}")
            lines.append("")
            continue

        for fix in entry['fixes']:
            s = fix['success']
            if s is True:
                status = '✅ 已修复'
            elif s == 'skipped':
                status = '⏭️ 跳过'
            elif s is False:
                status = f'❌ 失败'
            else:
                status = f'⚠️ {s}'
            lines.append(f"- {status}: {fix['desc']} ({fix['strategy']})")
        lines.append("")

    lines.append("---")
    lines.append(f"*auto_heal v{__version__} · {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='系统自愈引擎')
    parser.add_argument('--dry-run', action='store_true', help='仅诊断')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()

    result = run_auto_heal(dry_run=args.dry_run)

    # 持久化日志
    HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)
    log = []
    if HEALTH_LOG.exists():
        try:
            log = json.loads(HEALTH_LOG.read_text())
        except Exception:
            pass
    log.append(result)
    if len(log) > 30:
        log = log[-30:]
    HEALTH_LOG.write_text(json.dumps(log, ensure_ascii=False, indent=2))

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_report(result))
