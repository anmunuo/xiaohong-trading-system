#!/usr/bin/env python3
"""
文工团复盘 v3.0
===============
日终决策复盘：战果 → 持仓体检 → 交易记录 → 信号复盘 → 选股复盘 → 纪律清单。

v3.0 升级:
  · 选股复盘 — 今日涨幅 6%+ 股票 vs 推荐池/瞭望塔/侦察兵，自我优化
  · 当日盈亏 — 对比昨日净值，计算今日变化
  · 信号闭环 — 侦察兵/竞价信号正确率反馈
  · 纪律清单 — 7 项逐条检查
  · 错误归类 — 亏损按原因标签分类

用法:
  python3 review.py
"""

__version__ = "3.1.0"

import sys, json, os, re
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from data_pipeline._core import _em_api_get
from data_pipeline import get_market_money_flow, get_stock_realtime
from report_formatter import Report

# ── 可进化参数常量（evolution_engine v2.0 可自动调整）──
GAINER_MIN_PCT: float = 6.0   # path: review_gainer_min_pct
GAINER_TOP_N: int = 50        # path: review_gainer_top_n

HOLDINGS_PATH = BASE_DIR / "data" / "holdings.json"
POOL_PATH = SCRIPT_DIR / "data" / "daily_pool.json"
REPORTS_DIR = BASE_DIR / "reports" / "daily"


# ═══════════════════════════════════════════
# 1. 今日涨幅榜
# ═══════════════════════════════════════════

def get_top_gainers(min_pct: float = None, top_n: int = None) -> list:
    """获取今日涨幅 ≥ min_pct 的股票

    主通道: 东方财富 push2 (po=0降序) → tushare daily 回退（盘后 push2 关闭时）
    """
    if min_pct is None:
        min_pct = GAINER_MIN_PCT
    if top_n is None:
        top_n = GAINER_TOP_N

    # ── 主通道: 东方财富 push2 ──
    params = {
        'pn': 1, 'pz': top_n, 'po': 0, 'np': 1,  # po=0=降序，取涨幅从高到低
        'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
        'fltt': 2, 'invt': 2, 'fid': 'f3',
        'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23',
        'fields': 'f12,f14,f2,f3,f20,f62',
    }
    data = _em_api_get('https://push2.eastmoney.com/api/qt/clist/get', params)
    if data and data.get('data') and data['data'].get('diff'):
        items = data['data']['diff']
        result = [
            {
                'code': str(i.get('f12', '')),
                'name': str(i.get('f14', '')),
                'price': float(i.get('f2', 0)),
                'change_pct': float(i.get('f3', 0)),
                'amount': float(i.get('f20', 0)),
            }
            for i in items
            if float(i.get('f3', 0)) >= min_pct
        ]
        if result:
            return result

    # ── 回退通道: tushare daily（盘后 push2 关闭时可用）──
    try:
        import tushare as ts
        from dotenv import load_dotenv
        load_dotenv()
        token = os.environ.get('TUSHARE_TOKEN', '')
        if token:
            pro = ts.pro_api(token)
            today = datetime.now().strftime('%Y%m%d')
            df = pro.daily(trade_date=today,
                           fields='ts_code,open,high,low,close,pre_close,vol,amount')
            if df is not None and not df.empty:
                # 批量获取名称
                codes = [str(c)[:6] for c in df['ts_code'].unique()]
                names = {}
                try:
                    df_names = pro.stock_basic(ts_code=','.join(codes[:200]),
                        fields='ts_code,name')
                    if df_names is not None and not df_names.empty:
                        for _, nr in df_names.iterrows():
                            names[nr['ts_code'][:6]] = nr['name']
                except Exception:
                    pass

                result = []
                for _, row in df.iterrows():
                    pre = float(row['pre_close'] or 0)
                    close = float(row['close'] or 0)
                    if pre <= 0:
                        continue
                    chg = round((close - pre) / pre * 100, 2)
                    if chg >= min_pct:
                        code = str(row['ts_code'])[:6]
                        result.append({
                            'code': code,
                            'name': names.get(code, ''),
                            'price': close,
                            'change_pct': chg,
                            'amount': float(row['amount'] or 0),
                        })
                result.sort(key=lambda x: x['change_pct'], reverse=True)
                return result[:top_n]
    except Exception:
        pass

    return []


# ═══════════════════════════════════════════
# 2. 选股复盘：涨幅榜 vs 各系统
# ═══════════════════════════════════════════

def load_pool_stocks() -> dict:
    """加载推荐池股票 {code: info}"""
    pool = {}
    if POOL_PATH.exists():
        try:
            with open(POOL_PATH) as f:
                data = json.load(f)
            for r in data.get('recommendations', []):
                pool[str(r['code'])] = {
                    'name': r['name'],
                    'sector': r.get('sector', ''),
                    'risk_level': r.get('risk_level', ''),
                }
        except Exception:
            pass
    return pool


def load_morning_picks(date_str: str) -> set:
    """从瞭望塔晨报保存文件中提取推荐代码"""
    picks = set()
    report_path = REPORTS_DIR / f"瞭望塔晨报-{date_str}.md"
    if not report_path.exists():
        # 尝试 v8.0 命名
        for p in REPORTS_DIR.glob(f"瞭望塔晨报*{date_str}*.md"):
            report_path = p
            break
    if report_path.exists():
        text = report_path.read_text(encoding='utf-8')
        # 提取 6 位数字代码
        codes = re.findall(r'\b(6\d{5}|0\d{5}|3\d{5})\b', text)
        picks = set(codes)
    return picks


def load_scout_picks(date_str: str) -> set:
    """从侦察兵输出中提取推荐代码"""
    picks = set()
    # 尝试多个可能的文件名
    patterns = [
        f"侦察兵*{date_str}*.md",
        f"scout*{date_str}*.md",
    ]
    for pat in patterns:
        for p in REPORTS_DIR.glob(pat):
            text = p.read_text(encoding='utf-8')
            codes = re.findall(r'\b(6\d{5}|0\d{5}|3\d{5})\b', text)
            picks.update(codes)
            break
    return picks


def analyze_stock_selection(gainers: list, pool: dict,
                            morning_picks: set, scout_picks: set) -> dict:
    """
    选股复盘：涨幅 6%+ 的股票中有多少被各系统选中。

    返回命中率和优化建议。
    """
    result = {
        'total_gainers': len(gainers),
        'pool_hits': [],
        'morning_hits': [],
        'scout_hits': [],
        'missed': [],
    }

    pool_codes = set(pool.keys())

    for g in gainers:
        code = g['code']
        name = g['name']
        hit_pool = code in pool_codes
        hit_morning = code in morning_picks
        hit_scout = code in scout_picks

        if hit_pool:
            result['pool_hits'].append(g)
        if hit_morning:
            result['morning_hits'].append(g)
        if hit_scout:
            result['scout_hits'].append(g)

        # 全部错过
        if not hit_pool and not hit_morning and not hit_scout:
            result['missed'].append(g)

    # 命中率
    n = max(len(gainers), 1)
    result['pool_rate'] = round(len(result['pool_hits']) / n * 100, 1)
    result['morning_rate'] = round(len(result['morning_hits']) / n * 100, 1)
    result['scout_rate'] = round(len(result['scout_hits']) / n * 100, 1)
    result['missed_rate'] = round(len(result['missed']) / n * 100, 1)

    return result


def generate_optimization(selection: dict, pool: dict) -> list:
    """v3.1: 产出具体可执行的参数优化建议"""
    tips = []
    missed = selection['missed']
    pool_total = len(pool)

    # 1. 按涨跌、市值、板块分析错过的股票
    if missed:
        # 市值分布
        mc_vals = [m.get('market_cap', 0) for m in missed if m.get('market_cap', 0) > 0]
        if mc_vals:
            small_miss = sum(1 for m in mc_vals if m < 50)
            mid_miss = sum(1 for m in mc_vals if 50 <= m <= 200)
            tips.append(
                f"市值分布: {small_miss}只<50亿, {mid_miss}只50-200亿, "
                f"{len(mc_vals)-small_miss-mid_miss}只>200亿"
            )
            if small_miss >= 10:
                tips.append(
                    f"⚡ ACTION: 市值下限偏高({small_miss}只<50亿被排除)。"
                    "建议 stock_recommender._apply_filters: mkt_cap < 40.0 → < 30.0"
                )

        # 板块分布  
        sectors = {}
        for m in missed:
            s = m.get('sector', '?')
            sectors[s] = sectors.get(s, 0) + 1
        if sectors:
            top3 = sorted(sectors.items(), key=lambda x: x[1], reverse=True)[:3]
            tips.append(f"板块集中: " + ", ".join(f"{s}({n}只)" for s, n in top3))

    # 2. 捕获率诊断
    if selection['pool_rate'] < 10 and pool_total > 0:
        tips.append(
            f"🔴 推荐池捕获率 {selection['pool_rate']:.0f}% ({len(selection['pool_hits'])}/{len(missed)})。"
            "建议: 检查候选源是否过度依赖公告事件(单一source=announcement)，"
            "增加资金流候选权重或放宽首板纳入逻辑"
        )
    elif selection['pool_rate'] < 30:
        tips.append(
            f"⚠️ 推荐池捕获率 {selection['pool_rate']:.0f}%。"
            "关注后续交易日是否持续<10%——若连续3天建议进化引擎介入调参"
        )

    # 3. 侦察兵诊断
    if selection['scout_rate'] < 10 and selection['pool_rate'] > 20:
        tips.append(
            "侦察兵捕获率远低于推荐池。"
            "建议: scout.py adaptive_flow_threshold 降低门槛 5000→3000"
        )

    # 4. 池质量
    if pool_total > 0:
        pool_mc = [p.get('market_cap', 0) for p in pool.values() if p.get('market_cap', 0) > 0]
        if pool_mc:
            avg_mc = sum(pool_mc) / len(pool_mc)
            tips.append(f"当前推荐池平均市值: {avg_mc:.0f}亿")

    return tips


# ═══════════════════════════════════════════
# 3. 数据加载
# ═══════════════════════════════════════════

def load_holdings() -> dict:
    if HOLDINGS_PATH.exists():
        return json.loads(HOLDINGS_PATH.read_text(encoding='utf-8'))
    return {}


def get_yesterday_nv(date_str: str) -> float:
    """从昨日弹药库报告中提取净值"""
    yesterday = (datetime.strptime(date_str, '%Y-%m-%d') - timedelta(days=1)).strftime('%Y-%m-%d')
    path = REPORTS_DIR / f"弹药库风控-{yesterday}.md"
    if path.exists():
        text = path.read_text(encoding='utf-8')
        m = re.search(r'净值.*?¥([\d,]+)', text)
        if m:
            return float(m.group(1).replace(',', ''))
    return 0


# ═══════════════════════════════════════════
# 4. 错误归类
# ═══════════════════════════════════════════

def categorize_losses(holdings: list) -> list:
    """分析持仓亏损的可能原因"""
    categories = []
    for h in holdings:
        pnl_pct = h.get('pnlPct', 0)
        if pnl_pct >= 0:
            continue
        code = h['code']
        name = h.get('name', code)
        cost = h.get('costPrice', 0)
        last = h.get('lastPrice', 0)

        reasons = []
        if last and cost:
            if pnl_pct < -5:
                reasons.append('止损犹豫')
            elif pnl_pct < -3:
                reasons.append('未及时止盈转亏')
            if (cost - last) / cost > 0.03:
                reasons.append('追高买入')
        if not reasons:
            reasons.append('市场回调')

        categories.append({
            'code': code, 'name': name,
            'pnl_pct': pnl_pct,
            'reasons': reasons,
            'loss': h.get('unrealizedPnL', 0),
        })
    return categories


# ═══════════════════════════════════════════
# 5. 报告生成
# ═══════════════════════════════════════════

def generate_review() -> Report:
    data = load_holdings()
    account = data.get("accountInfo", {})
    holdings = data.get("holdings", [])
    closed = data.get("closedPositions", [])

    net_value = account.get('currentNetValue', 0)
    initial = account.get('initialCapital', 1)
    total_pnl = net_value - initial
    total_pnl_pct = (total_pnl / initial * 100)

    date_str = datetime.now().strftime('%Y-%m-%d')
    time_str = datetime.now().strftime('%H:%M')
    color = "green" if total_pnl >= 0 else "red"

    # 当日盈亏
    yesterday_nv = get_yesterday_nv(date_str)
    daily_pnl = net_value - yesterday_nv if yesterday_nv else 0
    daily_pnl_pct = (daily_pnl / yesterday_nv * 100) if yesterday_nv else 0

    # 大盘对比
    mf = get_market_money_flow()
    sh_change = mf.get('sh_change', 0)

    r = Report(title="文工团 · 每日复盘", icon="🏥", color=color)
    r.header_meta(
        日期=date_str,
        净值=f"¥{net_value:,.0f}",
        总盈亏=f"{total_pnl_pct:+.2f}%",
        今日=f"{daily_pnl_pct:+.2f}%" if yesterday_nv else "—",
    )

    # ═══ 一 · 今日战果 ═══
    r.section("今日战果")
    if yesterday_nv:
        day_emoji = "🟢" if daily_pnl >= 0 else "🔴"
        vs_market = daily_pnl_pct - sh_change
        vs_emoji = "🏆 跑赢" if vs_market > 0 else ("⚖️ 持平" if abs(vs_market) < 0.1 else "📉 跑输")
        r.text(
            f"{day_emoji} 当日盈亏: ¥{daily_pnl:+,.0f} ({daily_pnl_pct:+.2f}%)  |  "
            f"上证 {sh_change:+.2f}%  |  {vs_emoji} {abs(vs_market):.2f}%"
        )
    r.text(f"净值: ¥{net_value:,.0f}  |  累计盈亏: ¥{total_pnl:+,.0f} ({total_pnl_pct:+.2f}%)")

    # ═══ 二 · 持仓体检 ═══
    if holdings:
        r.divider()
        r.section(f"持仓体检（{len(holdings)}只）")
        codes = [h['code'] for h in holdings]
        quotes = get_stock_realtime(codes) if codes else {}
        pool = load_pool_stocks()
        pool_codes = set(pool.keys())

        for h in holdings:
            code = h['code']
            name = h['name']
            pnl_pct = h.get('pnlPct', 0)
            unrealized = h.get('unrealizedPnL', 0)
            last_price = h.get('lastPrice', 0)
            cost = h.get('costPrice', 0)

            emoji = "🟢" if pnl_pct >= 0 else "🔴"
            pool_mark = " ⭐池内" if code in pool_codes else " ⚡外"

            # 止损距离
            stop_dist_str = ""
            for trade in h.get('trades', []):
                sl = trade.get('stopLoss', 0)
                if sl and last_price:
                    dist = (last_price - sl) / sl * 100
                    stop_dist_str = f" | 距止损 {dist:+.1f}%"
                    break

            main_val = f"{emoji} 浮亏 ¥{unrealized:+,.0f} ({pnl_pct:+.1f}%){pool_mark}"
            sub = f"¥{last_price:.2f} × {h['shares']}股 | 成本¥{cost:.3f}{stop_dist_str}"
            r.kv(f"{name} {code}", main_val, sub)
    else:
        r.text("当前空仓")

    # ═══ 三 · 今日交易 ═══
    r.divider()
    r.section("今日交易")
    week_closed = closed[-5:] if closed else []
    if week_closed:
        realized = sum(t.get('profit', 0) for t in week_closed)
        r.text(f"近 5 笔平仓合计: ¥{realized:+,.0f}")
        for t in week_closed:
            p_emoji = "🟢" if t.get('profit', 0) >= 0 else "🔴"
            r.text(f"  {p_emoji} {t.get('name','?')} {t.get('code','?')}  "
                   f"¥{t.get('profit',0):+,.0f} ({t.get('profitPct',0):+.1f}%)  "
                   f"持{t.get('holdingDays',0)}天")
    else:
        r.text("今日无交易")

    # ═══ 四 · 选股复盘 ⭐ 核心新增 ═══
    r.divider()
    r.section("选股复盘")

    gainers = get_top_gainers(6.0, 50)
    if gainers:
        pool = load_pool_stocks()
        morning_picks = load_morning_picks(date_str)
        scout_picks = load_scout_picks(date_str)

        selection = analyze_stock_selection(gainers, pool, morning_picks, scout_picks)

        r.text(f"📊 今日涨幅 ≥6%: **{selection['total_gainers']}只**")
        r.text(
            f"🎯 推荐池命中: **{len(selection['pool_hits'])}只 ({selection['pool_rate']}%)**  |  "
            f"🌅 瞭望塔命中: **{len(selection['morning_hits'])}只 ({selection['morning_rate']}%)**  |  "
            f"🔍 侦察兵命中: **{len(selection['scout_hits'])}只 ({selection['scout_rate']}%)**"
        )
        r.text(f"❌ 全部错过: **{len(selection['missed'])}只 ({selection['missed_rate']}%)**")

        # 命中明细
        if selection['pool_hits']:
            names = " · ".join(f"{g['name']}({g['change_pct']:+.1f}%)"
                             for g in selection['pool_hits'][:8])
            r.text(f"  ⭐ 池内命中: {names}")

        if selection['missed'][:5]:
            names = " · ".join(f"{g['name']}({g['change_pct']:+.1f}%)"
                             for g in selection['missed'][:5])
            r.text(f"  ❌ 错过: {names}")

        # 优化建议
        tips = generate_optimization(selection, pool)
        if tips:
            r.divider()
            r.section("优化建议")
            for t in tips:
                r.text(f"• {t}")

            # 写入 weights 供系统学习
            reflection = {
                'date': date_str,
                'pool_rate': selection['pool_rate'],
                'morning_rate': selection['morning_rate'],
                'scout_rate': selection['scout_rate'],
                'missed_count': len(selection['missed']),
                'tips': tips,
            }
            refl_path = SCRIPT_DIR / 'data' / 'reflection_log.json'
            existing = []
            if refl_path.exists():
                existing = json.loads(refl_path.read_text())
            existing.append(reflection)
            refl_path.parent.mkdir(parents=True, exist_ok=True)
            refl_path.write_text(json.dumps(existing[-30:], ensure_ascii=False, indent=2))
    else:
        r.text("📊 今日无涨幅 ≥6% 数据（非交易日或数据未就绪）")

    # ═══ 五 · 纪律清单 ═══
    r.divider()
    r.section("纪律清单")

    checks = []
    # 1. 仓位上限
    checks.append(("持仓 ≤9只", len(holdings) <= 9))
    # 2. 单票集中度
    max_pos = max(
        (h.get('marketValue', 0) / net_value * 100 if net_value else 0)
        for h in holdings
    ) if holdings else 0
    checks.append(("单票 ≤33.3%", max_pos <= 33.3))
    # 3. 止损纪律
    triggered = any(
        h.get('lastPrice', 0) <= t.get('stopLoss', float('inf'))
        for h in holdings for t in h.get('trades', [])
        if h.get('lastPrice') and t.get('stopLoss')
    )
    checks.append(("止损纪律", not triggered))
    # 4. 可用资金
    available = account.get('availableCash', 0)
    checks.append(("预留现金 ≥5%", available / net_value >= 0.05 if net_value else True))
    # 5. 追高检查
    chasing = any(
        h.get('pnlPct', 0) < -3 and h.get('costPrice', 0) > h.get('lastPrice', 0) * 1.05
        for h in holdings
    )
    checks.append(("无追高买入", not chasing))
    # 6. 频率
    checks.append(("今日交易 ≤3笔", len(week_closed) <= 3))
    # 7. 计划执行
    checks.append(("按计划执行", True))  # 需人工确认

    for label, ok in checks:
        mark = "✅" if ok else "❌"
        r.text(f"{mark} {label}")
        if not ok:
            r.alert(f"{label} 违规", "warning")

    # ═══ 六 · 错误归类 ═══
    losses = categorize_losses(holdings)
    if losses:
        r.divider()
        r.section("亏损分析")
        for l in losses:
            tags = " · ".join(l['reasons'])
            r.text(f"🔴 {l['name']} {l['code']}  "
                   f"浮亏 {l['pnl_pct']:+.1f}% (¥{l['loss']:+,.0f})  —  {tags}")

    r.footer(f"v3.1 · data_pipeline · {time_str}")

    # 🆕 v3.1: 回测曲线嵌入
    try:
        from backtest_chart import generate_all_charts, generate_markdown_embed
        charts = generate_all_charts()
        if charts:
            r.section("📈 策略回测")
            embed = generate_markdown_embed(charts)
            for line in embed.split('\n'):
                if line.startswith('MEDIA:'):
                    r.text(line)  # MEDIA: 路径由飞书渲染为图片
                elif line.strip() and not line.startswith('#'):
                    r.text(line)
    except Exception:
        pass  # 图表生成失败不影响复盘报告

    return r


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    report = generate_review()
    print(report.markdown())

    date_str = datetime.now().strftime('%Y-%m-%d')
    md_path = REPORTS_DIR / f"文工团复盘-{date_str}.md"
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(report.markdown(), encoding='utf-8')
    print(f"\n📁 已保存: {md_path}")


if __name__ == "__main__":
    main()
