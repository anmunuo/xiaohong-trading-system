#!/usr/bin/env python3
"""
portfolio_risk.py — 组合层面风控引擎
=====================================
三层风控：相关性矩阵 → VaR/CVaR → 压力测试

用法:
  python3 portfolio_risk.py --daily     # 日频组合风控
  python3 portfolio_risk.py --weekly    # 周频压力测试
  python3 portfolio_risk.py --report    # 输出风控报告
"""

import sys, os, json, math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

HOLDINGS_PATH = BASE_DIR / 'data' / 'holdings.json'
POOL_PATH = SCRIPT_DIR / 'data' / 'daily_pool.json'
RISK_REPORT_PATH = SCRIPT_DIR / 'data' / 'portfolio_risk.json'

# ── 沪深300 代码 ──
HS300_INDEX_CODE = '000300'


# ═══════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════

@dataclass
class CorrPairResult:
    code_a: str
    name_a: str
    code_b: str
    name_b: str
    correlation: float
    severity: str  # 'critical' | 'warning' | 'ok'


@dataclass
class VaRResult:
    var_95: float
    cvar_95: float
    var_pct: float         # VaR占净值百分比
    cvar_pct: float
    confidence_95: float
    max_drawdown_hist: float  # 历史最大回撤


@dataclass
class StressScenario:
    name: str
    desc: str
    index_shock: float      # 沪深300冲击
    sector_shock: float     # 行业冲击
    liquidity_mult: float   # 流动性乘数
    estimated_loss: float = 0.0
    estimated_loss_pct: float = 0.0


@dataclass
class PortfolioRiskReport:
    date: str
    net_value: float
    n_positions: int
    correlations: List[CorrPairResult] = field(default_factory=list)
    var: Optional[VaRResult] = None
    stress_tests: List[StressScenario] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    criticals: List[str] = field(default_factory=list)


# ═══════════════════════════════════════
# Layer 1: 相关性矩阵
# ═══════════════════════════════════════

class CorrelationMatrix:
    """持仓+推荐池 相关性矩阵"""

    def __init__(self, lookback_days: int = 60):
        self.lookback = lookback_days

    def compute(self, holdings: List[Dict],
                pool_stocks: List[Dict] = None) -> List[CorrPairResult]:
        """
        计算所有持仓+推荐池的相关性。

        返回高相关性对 (|corr| > 0.70)
        """
        # 收集所有需要计算的股票
        positions = [(h['code'], h.get('name', '')) for h in holdings]
        if pool_stocks:
            for p in pool_stocks[:9]:
                code = str(p.get('code', ''))
                name = str(p.get('name', ''))
                if code not in [x[0] for x in positions]:
                    positions.append((code, name))

        if len(positions) < 2:
            return []

        codes = [p[0] for p in positions]
        names = dict(positions)

        # 拉历史日线
        returns_matrix = self._get_returns_matrix(codes)
        if returns_matrix is None or returns_matrix.shape[1] < 10:
            return []

        # 计算 Pearson 相关系数矩阵
        n = returns_matrix.shape[0]
        corr_pairs = []

        for i in range(n):
            for j in range(i + 1, n):
                ret_i = returns_matrix[i]
                ret_j = returns_matrix[j]
                valid = ~(np.isnan(ret_i) | np.isnan(ret_j))
                if valid.sum() < 20:
                    continue

                corr = float(np.corrcoef(ret_i[valid], ret_j[valid])[0, 1])
                if np.isnan(corr):
                    continue

                code_a, code_b = codes[i], codes[j]
                name_a, name_b = names.get(code_a, ''), names.get(code_b, '')

                if abs(corr) >= 0.80:
                    severity = 'critical'
                elif abs(corr) >= 0.70:
                    severity = 'warning'
                else:
                    continue

                corr_pairs.append(CorrPairResult(
                    code_a=code_a, name_a=name_a,
                    code_b=code_b, name_b=name_b,
                    correlation=round(corr, 3),
                    severity=severity,
                ))

        return sorted(corr_pairs, key=lambda x: abs(x.correlation), reverse=True)

    def _get_returns_matrix(self, codes: List[str]) -> Optional[np.ndarray]:
        """获取多只股票的收益率矩阵 N×T"""
        try:
            from data_pipeline import get_historical_k_with_ma
            bs_data = get_historical_k_with_ma(codes, days=self.lookback + 5)
        except Exception:
            return None

        if not bs_data:
            return None

        returns_rows = []
        for code in codes:
            bars = bs_data.get(code, [])
            if len(bars) < 20:
                continues = []
            closes = np.array([b['close'] for b in bars], dtype=float)
            rets = np.diff(closes) / closes[:-1]
            returns_rows.append(rets)

        if not returns_rows:
            return None

        # 对齐长度
        min_len = min(len(r) for r in returns_rows)
        aligned = np.array([r[-min_len:] for r in returns_rows])

        return aligned

    def compute_index_corr(self, holdings: List[Dict]) -> Dict[str, float]:
        """每只持仓与沪深300的相关性"""
        codes = [h['code'] for h in holdings]
        if not codes:
            return {}

        all_codes = codes + [HS300_INDEX_CODE]
        try:
            from data_pipeline import get_historical_k_with_ma
            bs_data = get_historical_k_with_ma(all_codes, days=self.lookback + 5)
        except Exception:
            return {}

        idx_bars = bs_data.get(HS300_INDEX_CODE, [])
        if len(idx_bars) < 20:
            return {}
        idx_closes = np.array([b['close'] for b in idx_bars], dtype=float)
        idx_rets = np.diff(idx_closes) / idx_closes[:-1]

        result = {}
        for code in codes:
            bars = bs_data.get(code, [])
            if len(bars) < 20:
                continue
            closes = np.array([b['close'] for b in bars], dtype=float)
            rets = np.diff(closes) / closes[:-1]
            min_len = min(len(rets), len(idx_rets))
            if min_len < 20:
                continue
            corr = float(np.corrcoef(rets[-min_len:], idx_rets[-min_len:])[0, 1])
            result[code] = round(corr, 3)

        return result


# ═══════════════════════════════════════
# Layer 2: VaR / CVaR
# ═══════════════════════════════════════

class VaRCalculator:
    """历史模拟法 VaR"""

    def __init__(self, lookback_days: int = 250):
        self.lookback = lookback_days

    def compute(self, holdings: List[Dict],
                net_value: float) -> Optional[VaRResult]:
        """
        计算组合 VaR/CVaR。

        用持仓权重 + 历史日收益序列 → 历史模拟法
        """
        if not holdings or net_value <= 0:
            return None

        # 获取各持仓历史收益
        codes = [h['code'] for h in holdings]
        weights = [h.get('marketValue', 0) / net_value for h in holdings]

        try:
            from data_pipeline import get_historical_k_with_ma
            bs_data = get_historical_k_with_ma(codes, days=self.lookback + 5)
        except Exception:
            return None

        if not bs_data:
            return None

        # 构建组合日收益序列
        returns_matrix = []
        valid_codes = []
        valid_weights = []

        for i, code in enumerate(codes):
            bars = bs_data.get(code, [])
            if len(bars) < 60:
                continue
            closes = np.array([b['close'] for b in bars], dtype=float)
            rets = np.diff(closes) / closes[:-1]
            returns_matrix.append(rets)
            valid_codes.append(code)
            valid_weights.append(weights[i])

        if not returns_matrix:
            return None

        # 对齐长度
        min_len = min(len(r) for r in returns_matrix)
        aligned = np.array([r[-min_len:] for r in returns_matrix])

        # 重新归一化权重
        w = np.array(valid_weights)
        w = w / w.sum() if w.sum() > 0 else np.ones(len(w)) / len(w)

        # 组合日收益 = w · R
        portfolio_returns = w @ aligned

        # VaR 95%
        var_95 = float(np.percentile(portfolio_returns, 5))
        # CVaR 95% = 尾部均值
        tail = portfolio_returns[portfolio_returns <= var_95]
        cvar_95 = float(tail.mean()) if len(tail) > 0 else var_95

        max_dd = float(self._max_drawdown(portfolio_returns))

        return VaRResult(
            var_95=round(var_95 * net_value, 0),
            cvar_95=round(cvar_95 * net_value, 0),
            var_pct=round(var_95 * 100, 2),
            cvar_pct=round(cvar_95 * 100, 2),
            confidence_95=round(float(np.percentile(portfolio_returns, 95)), 4),
            max_drawdown_hist=round(max_dd * 100, 2),
        )

    @staticmethod
    def _max_drawdown(returns: np.ndarray) -> float:
        cum = np.cumprod(1 + returns)
        peak = np.maximum.accumulate(cum)
        dd = (cum - peak) / peak
        return float(dd.min())


# ═══════════════════════════════════════
# Layer 3: 压力测试
# ═══════════════════════════════════════

STRESS_SCENARIOS = [
    StressScenario(
        name='A股崩盘',
        desc='沪深300单日-7%，持仓×各自beta',
        index_shock=-0.07,
        sector_shock=-0.07,
        liquidity_mult=3.0,
    ),
    StressScenario(
        name='行业利空',
        desc='最大权重行业单日-10%',
        index_shock=-0.03,
        sector_shock=-0.10,
        liquidity_mult=2.0,
    ),
    StressScenario(
        name='流动性枯竭',
        desc='全市场换手率降至1/5，滑点×5',
        index_shock=-0.04,
        sector_shock=-0.06,
        liquidity_mult=5.0,
    ),
    StressScenario(
        name='黑天鹅',
        desc='全A跌停-10%',
        index_shock=-0.10,
        sector_shock=-0.10,
        liquidity_mult=10.0,
    ),
    StressScenario(
        name='风格切换',
        desc='大小盘风格反转，因子暴露翻转',
        index_shock=-0.02,
        sector_shock=-0.05,
        liquidity_mult=1.5,
    ),
]


class StressTester:
    """压力测试引擎"""

    def run(self, holdings: List[Dict], net_value: float,
            beta_map: Dict[str, float] = None) -> List[StressScenario]:
        """运行5个压力场景，估算组合损失"""
        if not holdings or net_value <= 0:
            return []

        results = []
        total_value = net_value

        for scenario in STRESS_SCENARIOS:
            estimated_loss = 0.0

            for h in holdings:
                mv = h.get('marketValue', 0)
                if mv <= 0:
                    continue

                code = h['code']
                beta = beta_map.get(code, 1.0) if beta_map else 1.0

                # 损失 = 市值 × 指数冲击 × beta + 行业冲击
                stock_loss = mv * abs(scenario.index_shock * beta + scenario.sector_shock * 0.5)
                # 流动性乘数：增加额外损失
                stock_loss *= scenario.liquidity_mult

                estimated_loss += stock_loss

            scenario.estimated_loss = round(estimated_loss, 0)
            scenario.estimated_loss_pct = round(estimated_loss / total_value * 100, 2)

            results.append(scenario)

        return results


# ═══════════════════════════════════════
# 主入口
# ═══════════════════════════════════════

def run_daily_risk_check() -> PortfolioRiskReport:
    """日频组合风控：相关性 + VaR"""
    today = datetime.now().strftime('%Y-%m-%d')

    # 加载持仓
    holdings_data = {}
    if HOLDINGS_PATH.exists():
        holdings_data = json.loads(HOLDINGS_PATH.read_text())

    holdings = holdings_data.get('holdings', [])
    net_value = holdings_data.get('accountInfo', {}).get('currentNetValue', 100000)

    report = PortfolioRiskReport(
        date=today,
        net_value=net_value,
        n_positions=len(holdings),
    )

    if not holdings:
        report.warnings.append('当前无持仓，跳过组合风控')
        return report

    # Layer 1: 相关性
    corr_matrix = CorrelationMatrix()
    corr_pairs = corr_matrix.compute(holdings)
    report.correlations = corr_pairs

    # 高相关警告
    critical_pairs = [p for p in corr_pairs if p.severity == 'critical']
    if critical_pairs:
        pairs_str = ', '.join(f'{p.name_a}-{p.name_b}({p.correlation:.2f})' for p in critical_pairs[:3])
        report.criticals.append(f'🔴 高相关性警报: {pairs_str}')

    # 与沪深300相关性
    idx_corr = corr_matrix.compute_index_corr(holdings)
    high_idx = [(code, corr) for code, corr in idx_corr.items() if abs(corr) > 0.85]
    if high_idx:
        codes_str = ', '.join(f'{c}({v:.2f})' for c, v in high_idx[:3])
        report.warnings.append(f'⚠️ 系统性风险高(与HS300相关>0.85): {codes_str}')

    # Layer 2: VaR
    var_calc = VaRCalculator()
    var_result = var_calc.compute(holdings, net_value)
    report.var = var_result

    if var_result and var_result.var_pct < -3.0:
        report.criticals.append(
            f'🔴 VaR告警: 95%置信度日损失≤¥{abs(var_result.var_95):,.0f} ({abs(var_result.var_pct):.1f}%净值)'
        )
    elif var_result and var_result.var_pct < -2.0:
        report.warnings.append(
            f'⚠️ VaR偏高: 日潜在损失¥{abs(var_result.var_95):,.0f} ({abs(var_result.var_pct):.1f}%)'
        )

    return report


def run_weekly_stress_test() -> PortfolioRiskReport:
    """周频压力测试"""
    today = datetime.now().strftime('%Y-%m-%d')

    holdings_data = {}
    if HOLDINGS_PATH.exists():
        holdings_data = json.loads(HOLDINGS_PATH.read_text())

    holdings = holdings_data.get('holdings', [])
    net_value = holdings_data.get('accountInfo', {}).get('currentNetValue', 100000)

    report = PortfolioRiskReport(
        date=today,
        net_value=net_value,
        n_positions=len(holdings),
    )

    if not holdings:
        return report

    # 获取 beta
    beta_map = {}
    corr_matrix = CorrelationMatrix()
    idx_corr = corr_matrix.compute_index_corr(holdings)
    for code, corr in idx_corr.items():
        beta_map[code] = max(corr, 0.5)  # 至少0.5

    # 压力测试
    tester = StressTester()
    stress_results = tester.run(holdings, net_value, beta_map)
    report.stress_tests = stress_results

    for s in stress_results:
        if s.estimated_loss_pct > 20:
            report.criticals.append(
                f'🔴 压力测试[{s.name}]: 预估损失¥{s.estimated_loss:,.0f} ({s.estimated_loss_pct}%) - {s.desc}'
            )
        elif s.estimated_loss_pct > 10:
            report.warnings.append(
                f'⚠️ 压力测试[{s.name}]: 预估损失¥{s.estimated_loss:,.0f} ({s.estimated_loss_pct}%)'
            )

    return report


def format_report(report: PortfolioRiskReport) -> str:
    """格式化风控报告"""
    from report_formatter import Report

    has_issues = bool(report.criticals or report.warnings)
    r = Report(
        title='组合风险报告',
        icon='🛡️',
        color='red' if report.criticals else ('yellow' if report.warnings else 'green'),
    )
    r.header_meta(
        日期=report.date,
        净值=f'¥{report.net_value:,.0f}',
        持仓=f'{report.n_positions}只',
    )

    # ── 告警 ──
    if report.criticals:
        r.section('🔴 严重告警')
        for c in report.criticals:
            r.text(c)
    if report.warnings:
        r.section('⚠️ 警告')
        for w in report.warnings:
            r.text(w)

    # ── VaR ──
    if report.var:
        r.section('📉 在险价值 (VaR)')
        r.kv('VaR (95%)', f'¥{abs(report.var.var_95):,.0f}', f'{abs(report.var.var_pct):.1f}% 净值')
        r.kv('CVaR (95%)', f'¥{abs(report.var.cvar_95):,.0f}', f'{abs(report.var.cvar_pct):.1f}% 净值')
        r.kv('历史最大回撤', f'{report.var.max_drawdown_hist:.1f}%')

    # ── 相关性 ──
    if report.correlations:
        r.section('🔗 相关性矩阵')
        rows = []
        for p in report.correlations[:10]:
            icon = '🔴' if p.severity == 'critical' else '🟡'
            rows.append([
                f'{icon} {p.name_a}({p.code_a})',
                f'{p.name_b}({p.code_b})',
                f'{p.correlation:.3f}',
            ])
        r.table(['标的A', '标的B', '相关系数'], rows)

    # ── 压力测试 ──
    if report.stress_tests:
        r.section('💥 压力测试')
        stress_rows = []
        for s in report.stress_tests:
            icon = '🔴' if s.estimated_loss_pct > 15 else ('🟡' if s.estimated_loss_pct > 8 else '🟢')
            stress_rows.append([
                f'{icon} {s.name}',
                s.desc,
                f'¥{s.estimated_loss:,.0f}',
                f'{s.estimated_loss_pct}%',
            ])
        r.table(['场景', '描述', '预估损失', '损失%'], stress_rows)

    if not report.criticals and not report.warnings and not report.var and not report.correlations:
        r.section('✅ 状态')
        r.text('当前无持仓或数据不足，组合风控暂无结论')

    r.footer(f'portfolio_risk.py · {report.date}')
    return r.markdown()


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--daily', action='store_true', help='日频组合风控（相关性+VaR）')
    ap.add_argument('--weekly', action='store_true', help='周频压力测试')
    ap.add_argument('--report', action='store_true', help='输出格式化报告')
    ap.add_argument('--json', action='store_true', help='JSON输出')
    args = ap.parse_args()

    if args.weekly:
        report = run_weekly_stress_test()
    else:
        report = run_daily_risk_check()

    # 保存到文件
    RISK_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'date': report.date,
        'net_value': report.net_value,
        'n_positions': report.n_positions,
        'criticals': report.criticals,
        'warnings': report.warnings,
        'var': None,
        'correlations': [],
        'stress_tests': [],
    }
    if report.var:
        data['var'] = {
            'var_95': report.var.var_95,
            'cvar_95': report.var.cvar_95,
            'var_pct': report.var.var_pct,
            'cvar_pct': report.var.cvar_pct,
            'max_drawdown_hist': report.var.max_drawdown_hist,
        }
    data['correlations'] = [
        {'code_a': p.code_a, 'name_a': p.name_a,
         'code_b': p.code_b, 'name_b': p.name_b,
         'correlation': p.correlation, 'severity': p.severity}
        for p in report.correlations
    ]
    data['stress_tests'] = [
        {'name': s.name, 'desc': s.desc,
         'estimated_loss': s.estimated_loss,
         'estimated_loss_pct': s.estimated_loss_pct}
        for s in report.stress_tests
    ]
    RISK_REPORT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2))

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    elif args.report or args.daily or args.weekly:
        print(format_report(report))


if __name__ == '__main__':
    main()
