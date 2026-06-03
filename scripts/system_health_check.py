#!/usr/bin/env python3
"""
system_health_check.py — 交易系统健康扫描 v1.0
=============================================
7 维自动诊断：数据源 → 估值 → 推荐池 → 持仓 → 进程 → 研究员 → 告警

用法:
  python3 system_health_check.py              # 全扫描 → 终端输出
  python3 system_health_check.py --json        # JSON 输出
  python3 system_health_check.py --push        # 推送飞书

Cron: 建议 08:15 / 15:30 / 22:00 各一次
"""

import json, os, sys, time, gzip
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent  # ~/.hermes/profiles/xiaohong/
DATA_DIR = WORKSPACE / "data"
KB_DIR = DATA_DIR / "kb"
REPORTS_DIR = WORKSPACE / "reports"

__version__ = "1.0.0"


def check_data_freshness() -> dict:
    """维度1: 数据源新鲜度"""
    items = {
        'mega_latest':       (KB_DIR / 'mega_latest.json', 6),
        'daily_pool':        (SCRIPT_DIR / 'data' / 'daily_pool.json', 24),
        'kb_insights':       (KB_DIR / 'kb_insights.json', 3),
        'holdings':          (DATA_DIR / 'holdings.json', 24),
        'market_snapshot':   (DATA_DIR / 'market_snapshot.json', 8),
    }

    results = {}
    for name, (path, max_age_h) in items.items():
        if path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            status = 'ok' if age_h < max_age_h else 'stale'
            results[name] = {'age_h': round(age_h, 1), 'status': status}
        else:
            results[name] = {'age_h': None, 'status': 'missing'}
    return results


def check_valuation_sync() -> dict:
    """维度2: 持仓估值同步"""
    holdings_path = DATA_DIR / 'holdings.json'
    if not holdings_path.exists():
        return {'status': 'missing', 'issues': ['holdings.json 不存在']}

    try:
        with open(holdings_path) as f:
            data = json.load(f)
    except Exception as e:
        return {'status': 'error', 'issues': [str(e)]}

    issues = []
    positions = data.get('positions', data.get('holdings', []))
    if not positions:
        return {'status': 'empty', 'issues': ['无持仓记录']}

    no_price = []
    for p in positions:
        code = p.get('code', p.get('symbol', '?'))
        lp = p.get('lastPrice')
        pnl = p.get('pnlPct')
        if lp is None or lp == 0:
            no_price.append(code)
        if pnl is None and lp not in (None, 0):
            issues.append(f'{code} 无盈亏数据')

    if no_price:
        issues.append(f'{len(no_price)} 只持仓无最新价: {",".join(no_price)}')

    return {
        'status': 'ok' if not issues else 'degraded',
        'position_count': len(positions),
        'no_price_count': len(no_price),
        'issues': issues,
    }


def check_parliament_flow() -> dict:
    """维度3: 研究员议会 → 下游链路"""
    issues = []

    # 3a: daily_pool 含 parliament 字段？
    pool_path = SCRIPT_DIR / 'data' / 'daily_pool.json'
    parliament_ok = False
    if pool_path.exists():
        try:
            with open(pool_path) as f:
                pool = json.load(f)
            p = pool.get('parliament', {})
            if p and p.get('bias'):
                parliament_ok = True
            else:
                issues.append('daily_pool.json 无议会结论（parliament.bias 缺失）')
        except Exception as e:
            issues.append(f'读取 daily_pool.json 失败: {e}')
    else:
        issues.append('daily_pool.json 不存在')

    # 3b: parliament_log 存在？
    log_path = DATA_DIR / 'research' / 'parliament_log.json'
    if log_path.exists():
        try:
            with open(log_path) as f:
                log = json.load(f)
        except Exception:
            log = {}
        issues.append('parliament_log.json 存在但无实质内容' if not log else '')
    else:
        issues.append('parliament_log.json 不存在')

    return {
        'status': 'ok' if parliament_ok else 'degraded',
        'parliament_in_pool': parliament_ok,
        'issues': [i for i in issues if i],
    }


def check_ammo_risk() -> dict:
    """维度4: 弹药库风控状态"""
    hp = DATA_DIR / 'holdings.json'
    if not hp.exists():
        return {'status': 'missing', 'issues': ['holdings.json 不存在']}

    try:
        with open(hp) as f:
            data = json.load(f)
    except Exception as e:
        return {'status': 'error', 'issues': [str(e)]}

    issues = []

    # 检查 R 值
    rv = data.get('currentRValue') or data.get('riskManagement', {}).get('currentRValue')
    if rv is None or rv == 0:
        issues.append('R 值未设置（ammo_risk.py --update 未运行？）')

    # 检查回撤
    drawdown = data.get('currentDrawdown') or data.get('riskManagement', {}).get('currentDrawdown')
    if drawdown is None:
        issues.append('回撤数据未计算')

    # 检查净值
    nv = data.get('currentNetValue') or data.get('accountInfo', {}).get('currentNetValue')
    if nv is None or nv == 0:
        issues.append('净值未更新')

    return {
        'status': 'ok' if not issues else 'degraded',
        'issues': issues,
        'r_value': rv,
        'drawdown': drawdown,
    }


def check_data_pipeline() -> dict:
    """维度5: 数据管线连通性"""
    results = {}
    tests = {
        'push2_list':      ('东方财富 push2 列表API', 'f62 资金流字段'),
        'sina_realtime':   ('新浪实时行情', '价格/涨跌幅'),
        'baostock_klines': ('BaoStock 历史K线', 'MA20/PE'),
        'tushare_basic':   ('tushare 基本面', 'PE/PB/ROE'),
    }

    # 测试 push2 资金流（po=0降序取净流入Top）
    try:
        import urllib.request
        url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5&po=0&np=1&fltt=2&fid=f62&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f3,f62&ut=bd1d9ddb04089700cf9c27f6f7426281'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        items = data.get('data', {}).get('diff', [])
        f62_ok = sum(1 for i in items if float(i.get('f62', 0) or 0) != 0)
        results['push2_list'] = 'ok' if f62_ok > 0 else 'degraded (f62=0)'
    except Exception as e:
        results['push2_list'] = f'down: {e}'

    # 测试 push2 涨幅榜（po=0降序，验证能取到涨停股）
    try:
        url = 'https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=5&po=0&np=1&fltt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f12,f3&ut=bd1d9ddb04089700cf9c27f6f7426281'
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://data.eastmoney.com/'})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        items = data.get('data', {}).get('diff', [])
        top_chg = max(float(i.get('f3', 0) or 0) for i in items) if items else 0
        results['push2_gainers'] = 'ok' if top_chg >= 5 else f'degraded (top_chg={top_chg}%)'
    except Exception as e:
        results['push2_gainers'] = f'down: {e}'

    # 测试 Sina
    try:
        import urllib.request
        req = urllib.request.Request('http://hq.sinajs.cn/list=sh000001',
                                     headers={'Referer': 'https://finance.sina.com.cn'})
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read().decode('gbk')
        results['sina_realtime'] = 'ok' if '上证指数' in raw else 'degraded'
    except Exception as e:
        results['sina_realtime'] = f'down: {e}'

    # 测试 tushare
    try:
        sys.path.insert(0, str(SCRIPT_DIR))
        from dotenv import load_dotenv
        load_dotenv()
        import tushare as ts
        pro = ts.pro_api(os.environ.get('TUSHARE_TOKEN', ''))
        df = pro.daily_basic(ts_code='000001.SZ', trade_date=(datetime.now()-timedelta(days=1)).strftime('%Y%m%d'),
                             fields='ts_code,trade_date')
        results['tushare_basic'] = 'ok' if df is not None and not df.empty else 'degraded (无数据)'
    except Exception as e:
        results['tushare_basic'] = f'down: {e}'

    # 测试 BaoStock
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code == '0':
            rs = bs.query_history_k_data_plus('sh.000001', 'date,close',
                start_date=(datetime.now()-timedelta(days=5)).strftime('%Y-%m-%d'),
                end_date=datetime.now().strftime('%Y-%m-%d'), frequency='d', adjustflag='2')
            results['baostock_klines'] = 'ok' if rs.error_code == '0' and rs.data else 'degraded'
            bs.logout()
        else:
            results['baostock_klines'] = 'down: login failed'
    except Exception as e:
        results['baostock_klines'] = f'down: {e}'

    total_ok = sum(1 for v in results.values() if v == 'ok')
    return {
        'status': 'ok' if total_ok >= 3 else ('degraded' if total_ok >= 1 else 'down'),
        'providers': results,
    }


def check_scout_sniper() -> dict:
    """维度6: 侦察兵/狙击手状态"""
    results = {}

    # 侦察兵最近一次输出
    scout_dir = SCRIPT_DIR.parent / 'cron' / 'output' / 'a6b4e31d3919'
    if scout_dir.exists():
        files = sorted(scout_dir.glob('*.md'), key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            latest = files[0]
            age_h = (time.time() - latest.stat().st_mtime) / 3600
            # 读最后输出看数据源状态
            content = latest.read_text()[:1000]
            has_degraded = '数据源降级' in content
            results['scout'] = {
                'last_run_h': round(age_h, 1),
                'status': 'degraded' if has_degraded else 'ok',
            }
        else:
            results['scout'] = {'last_run_h': None, 'status': 'no_output'}
    else:
        results['scout'] = {'last_run_h': None, 'status': 'no_dir'}

    return results


def check_researcher_reports() -> dict:
    """维度7: 研究员报告质量 + 旧数据源检测"""
    research_dir = REPORTS_DIR / 'research'
    issues = []

    # 🆕 检测废弃 openclaw workspace 旧数据
    stale_holdings = Path('/home/pc/.openclaw/workspace/anmunuo-family/xiaohong/holdings.json')
    if stale_holdings.exists():
        issues.append('废弃 openclaw workspace 仍有旧 holdings.json（需删除避免混淆）')
    stale_backup = Path('/home/pc/.openclaw/workspace.backup.20260419_233239/anmunuo-family/xiaohong/holdings.json')
    if stale_backup.exists():
        issues.append('备份 workspace 仍有旧 holdings.json（需删除）')

    study_path = research_dir / f'研学报告-{datetime.now().strftime("%Y-%m-%d")}.md'
    if study_path.exists():
        content = study_path.read_text()
        if '_自主学习完成_' in content and '发现:' not in content:
            issues.append('研学报告为空壳（仅"自主学习完成"，无实质发现）')
    else:
        issues.append('今日研学报告未生成')

    parliament_path = research_dir / f'议会报告-{datetime.now().strftime("%Y-%m-%d")}.md'
    if parliament_path.exists():
        content = parliament_path.read_text()
        if '小红终审' not in content:
            issues.append('议会报告未完成（缺少小红终审）')
    else:
        issues.append('今日议会报告未生成')

    return {
        'status': 'ok' if not issues else 'degraded',
        'issues': issues,
    }


def check_factor_quality() -> dict:
    """维度8: 因子有效性"""
    ic_path = SCRIPT_DIR / 'data' / 'factor_ic.json'
    if not ic_path.exists():
        return {'status': 'degraded', 'issues': ['factor_ic.json 未生成（需运行 factor_evaluator.py）']}

    try:
        data = json.loads(ic_path.read_text())
        records = data.get('records', [])
        if not records:
            return {'status': 'degraded', 'issues': ['factor_ic.json 无记录']}

        # 统计有效因子数
        from collections import defaultdict
        by_factor = defaultdict(list)
        for r in records[-500:]:  # 最近500条
            by_factor[r['factor_id']].append(r.get('rank_ic', 0))

        active = 0
        deprecated = 0
        for fid, ics in by_factor.items():
            if len(ics) < 5:
                continue
            mean_ic = sum(ics) / len(ics)
            std_ic = (sum((x - mean_ic)**2 for x in ics) / len(ics)) ** 0.5
            icir = mean_ic / std_ic if std_ic > 0 else 0
            if abs(icir) >= 0.02:
                active += 1
            else:
                deprecated += 1

        issues = []
        if deprecated > active:
            issues.append(f'低效因子过多: {active} 有效 vs {deprecated} 待淘汰')
        if active < 3:
            issues.append('有效因子不足3个，评分体系可能退化为噪声')

        return {
            'status': 'degraded' if issues else 'ok',
            'active_factors': active,
            'deprecated_factors': deprecated,
            'issues': issues,
        }
    except Exception as e:
        return {'status': 'degraded', 'issues': [f'读取 factor_ic.json 失败: {e}']}


def check_portfolio_risk() -> dict:
    """维度9: 组合风险健康度"""
    pr_path = SCRIPT_DIR / 'data' / 'portfolio_risk.json'
    if not pr_path.exists():
        return {'status': 'ok', 'issues': [], 'note': 'portfolio_risk.json 未生成（无可检查项）'}

    try:
        data = json.loads(pr_path.read_text())
        issues = []
        criticals = data.get('criticals', [])
        warnings = data.get('warnings', [])

        if criticals:
            issues.extend(criticals)
        if warnings:
            issues.extend(warnings)

        var = data.get('var')
        if var and abs(var.get('var_pct', 0)) > 3:
            issues.append(f'VaR超标: {abs(var["var_pct"]):.1f}% > 3%')

        return {
            'status': 'critical' if criticals else ('degraded' if issues else 'ok'),
            'criticals': len(criticals),
            'warnings': len(warnings),
            'issues': issues,
        }
    except Exception as e:
        return {'status': 'degraded', 'issues': [f'读取 portfolio_risk.json 失败: {e}']}


def check_silver_quality() -> dict:
    """维度10: Silver 层数据质量"""
    date = datetime.now().strftime('%Y-%m-%d')
    silver_path = (SCRIPT_DIR.parent / 'data' / 'silver' / 'stock_daily' /
                   datetime.now().strftime('%Y') / f'{datetime.now().month:02d}' /
                   f'{datetime.now().day:02d}' / 'all.json.gz')
    if not silver_path.exists():
        return {'status': 'degraded', 'issues': [f'Silver {date} 未生成']}

    try:
        data = json.loads(gzip.decompress(silver_path.read_bytes()))
        n = len(data)
        if n < 100:
            return {'status': 'degraded', 'issues': [f'Silver 行数过少: {n}']}
        suspended = sum(1 for r in data if r.get('is_suspended'))
        outliers = sum(1 for r in data if r.get('quality_flags'))
        return {
            'status': 'ok' if outliers < n * 0.05 else 'degraded',
            'n_rows': n,
            'n_suspended': suspended,
            'n_outliers': outliers,
            'issues': [f'{outliers}只异常标记'] if outliers > n * 0.05 else [],
        }
    except Exception as e:
        return {'status': 'down', 'issues': [f'Silver 读取失败: {e}']}


def check_gold_quality() -> dict:
    """维度11: Gold 特征层数据质量"""
    gold_root = SCRIPT_DIR.parent / 'data' / 'gold'
    if not gold_root.exists():
        return {'status': 'degraded', 'issues': ['Gold 数据目录不存在']}

    issues = []
    date = datetime.now().strftime('%Y-%m-%d')
    d = datetime.now()

    # 1. 因子面板存在？
    fp_dir = gold_root / 'factor_panel' / d.strftime('%Y') / f'{d.month:02d}' / f'{d.day:02d}'
    panel_exists = (fp_dir / 'v3.parquet').exists() or (fp_dir / 'v3.json.gz').exists()
    n_factors = 0
    if panel_exists:
        try:
            panel = None
            pq = fp_dir / 'v3.parquet'
            if pq.exists():
                import pandas as pd
                df = pd.read_parquet(pq)
                n_factors = len(df.columns) - 2  # 减 code, date
            else:
                jz = fp_dir / 'v3.json.gz'
                data = json.loads(gzip.decompress(jz.read_bytes()))
                if data:
                    n_factors = len(data[0].get('factors', {}))
        except Exception as e:
            issues.append(f'因子面板读取失败: {e}')
    else:
        issues.append(f'Gold 因子面板 {date} 不存在')

    # 2. ML 数据集存在？
    safe_date = date.replace('-', '')
    ml_train = gold_root / 'ml_datasets' / f'train_{safe_date}_v3.npz'
    ml_eval = gold_root / 'ml_datasets' / f'eval_{safe_date}_v3.npz'
    ml_ok = ml_train.exists() and ml_eval.exists()
    if not ml_ok:
        issues.append('ML 数据集未生成 (数据量不足或首次运行)')

    # 3. daily_pool 归档
    pool_path = gold_root / 'daily_pool' / d.strftime('%Y') / f'{d.month:02d}' / f'{d.day:02d}.json'
    pool_ok = pool_path.exists()

    # 综合判定
    if panel_exists and not issues:
        status = 'ok'
    elif panel_exists:
        status = 'degraded'
    else:
        status = 'missing'

    return {
        'status': status,
        'panel_exists': panel_exists,
        'n_factors': n_factors,
        'ml_ok': ml_ok,
        'pool_ok': pool_ok,
        'issues': issues,
    }


def run_full_check() -> dict:
    """执行全维扫描"""
    checks = {
        '1_data_freshness':    check_data_freshness(),
        '2_valuation_sync':    check_valuation_sync(),
        '3_parliament_flow':   check_parliament_flow(),
        '4_ammo_risk':         check_ammo_risk(),
        '5_data_pipeline':     check_data_pipeline(),
        '6_scout_sniper':      check_scout_sniper(),
        '7_researcher_quality': check_researcher_reports(),
        '8_factor_quality':    check_factor_quality(),
        '9_portfolio_risk':    check_portfolio_risk(),
        '10_silver_quality':   check_silver_quality(),
        '11_gold_quality':     check_gold_quality(),
    }

    # 汇总
    statuses = [v.get('status', 'unknown') for v in checks.values()]
    overall = 'critical' if 'down' in statuses else ('degraded' if 'degraded' in statuses else 'ok')

    return {
        'version': __version__,
        'checked_at': datetime.now().isoformat(),
        'overall': overall,
        'checks': checks,
        'issue_count': sum(len(v.get('issues', [])) for v in checks.values()),
    }


def format_report(result: dict) -> str:
    """格式化健康报告"""
    lines = []
    status_icon = {'ok': '✅', 'degraded': '⚠️', 'down': '🔴', 'critical': '🚨'}
    icon = status_icon.get(result['overall'], '❓')

    lines.append(f"# {icon} 交易系统健康扫描  v{__version__}")
    lines.append(f"> {result['checked_at'][:19]}")
    lines.append(f"> 综合状态: **{result['overall']}**  |  问题: {result['issue_count']} 项")
    lines.append("")
    lines.append("---")
    lines.append("")

    labels = {
        '1_data_freshness': '📦 数据新鲜度',
        '2_valuation_sync': '💰 持仓估值',
        '3_parliament_flow': '🏛️ 议会链路',
        '4_ammo_risk': '🛡️ 弹药库风控',
        '5_data_pipeline': '🔌 数据管线',
        '6_scout_sniper': '🔍 侦察兵',
        '7_researcher_quality': '🧠 研究员质量',
        '8_factor_quality': '📊 因子有效性',
        '9_portfolio_risk': '🛡️ 组合风险',
        '10_silver_quality': '🥈 Silver质量',
        '11_gold_quality':   '🏆 Gold质量',
    }

    for key, label in labels.items():
        check = result['checks'].get(key, {})
        status = check.get('status', 'unknown')
        s_icon = status_icon.get(status, '❓')
        lines.append(f"### {s_icon} {label}")
        lines.append("")

        if key == '5_data_pipeline':
            providers = check.get('providers', {})
            for name, state in providers.items():
                p_icon = '✅' if state == 'ok' else ('⚠️' if 'degraded' in str(state) else '🔴')
                lines.append(f"- {p_icon} {name}: {state}")
        elif key == '1_data_freshness':
            for name, info in check.items():
                if isinstance(info, dict):
                    age = info.get('age_h')
                    status = info.get('status', '?')
                    icon2 = '✅' if status == 'ok' else '⚠️'
                    age_str = f'{age:.1f}h' if age is not None else '缺失'
                    lines.append(f"- {icon2} {name}: {age_str}")
        else:
            for issue in check.get('issues', []):
                lines.append(f"- ⚠️ {issue}")
            other = {k: v for k, v in check.items() if k not in ('status', 'issues')}
            if other:
                for k, v in other.items():
                    if v is not None:
                        lines.append(f"- {k}: {v}")

        lines.append("")

    lines.append("---")
    lines.append(f"*system_health_check v{__version__} · {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    return "\n".join(lines)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--push', action='store_true')
    args = parser.parse_args()

    result = run_full_check()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(format_report(result))

    if args.push:
        try:
            from feishu_push import push_text
            report = format_report(result)
            push_text(report)
        except Exception as e:
            print(f"推送失败: {e}")

    # 仅 down/critical 时非零退出，degraded 是"需要注意"不是"故障"
    if result['overall'] in ('down', 'critical'):
        sys.exit(1)
    sys.exit(0)
