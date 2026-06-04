#!/usr/bin/env python3
"""
data_quality.py — 数据真实性管理网关 v1.0
========================================
五道质检关卡: 时效 → 来源 → 值域 → 交叉 → 趋势
每道不通过 = 标记降级/拒绝，输出可执行修复指令。

架构铁律: 所有交易相关数据必须携带 QualityStamp，下游消费前必查。
"""

import json, os, sys, time
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

SCRIPT_DIR = Path(__file__).resolve().parent
QUALITY_DIR = SCRIPT_DIR / "data" / "quality"
BASELINE_DIR = QUALITY_DIR / "baselines"
REJECT_LOG_PATH = QUALITY_DIR / "reject_log.json"
ALERT_LOG_PATH = QUALITY_DIR / "alert_log.json"

__version__ = "1.0.0"

# ═══════════════════════════════════════════
# 信任等级
# ═══════════════════════════════════════════

class TrustLevel(Enum):
    BLOCKED  = 0  # 禁止使用 — P0 时效失败
    DEGRADED = 1  # 降权使用 — P1/P2 异常
    CAUTION  = 2  # 谨慎使用 — P3/P4 分歧
    VERIFIED = 3  # 已验证 — 通过所有关卡
    TRUSTED  = 4  # 完全可信 — 多源交叉验证一致


def trust_to_stars(level: TrustLevel) -> str:
    return {TrustLevel.BLOCKED: "☆☆☆☆☆", TrustLevel.DEGRADED: "★☆☆☆☆",
            TrustLevel.CAUTION: "★★☆☆☆", TrustLevel.VERIFIED: "★★★☆☆",
            TrustLevel.TRUSTED: "★★★★☆"}[level]


# ═══════════════════════════════════════════
# 数据Schema — 定义每种数据类型的合理值域
# ═══════════════════════════════════════════

DATA_SCHEMAS = {
    "north_flow": {
        "description": "北向资金净流入(亿)",
        "unit": "亿元",
        "range": (-200, 300),        # 历史单日极值范围
        "typical": (-50, 150),       # 正常波动范围
        "sla_hours": 24,             # 允许最大滞后
        "critical_fields": ["net_flow", "detail", "data_source"],
        "cross_validatable": True,   # 可多源交叉验证
        "cross_source": "tushare.moneyflow_hsgt.north_money",
        "field_trap": {              # 已知字段陷阱
            "ggt_ss": "南向(港股通沪)，不是北向!",
            "ggt_sz": "南向(港股通深)，不是北向!",
        },
    },
    "market_flow": {
        "description": "全市场主力/散户资金流向",
        "unit": "元",
        "range": (-2e10, 2e10),
        "typical": (-5e9, 5e9),
        "sla_hours": 12,
        "critical_fields": ["main_net", "retail_net"],
        "cross_validatable": False,
    },
    "index_data": {
        "description": "全球指数",
        "unit": "点",
        "range_shanghai": (2000, 6000),
        "sla_hours": 12,
        "critical_fields": ["asia.shanghai", "us.nasdaq"],
        "cross_validatable": True,
    },
    "stock_realtime": {
        "description": "个股实时行情",
        "unit": "元",
        "range_change_pct": (-20, 20),  # 非ST涨跌停
        "sla_seconds": 120,
        "critical_fields": ["close", "change_pct", "name"],
        "cross_validatable": False,
    },
    "daily_pool": {
        "description": "每日推荐池",
        "sla_hours": 24,
        "critical_fields": ["recommendations", "generated_at"],
        "cross_validatable": False,
    },
    # 🆕 v8.12
    "financial_summary": {
        "description": "财务综合评分",
        "sla_hours": 168,  # 7天，财报不天天变
        "critical_fields": ["score", "roe", "debt_to_assets"],
        "cross_validatable": True,
        "cross_source": "tushare.fina_indicator",
        "field_trap": {
            "roe": "注意区分单季ROE vs 滚动12月ROE(yearly)",
            "gross_margin": "grossprofit_margin可能为None(银行等不披露)",
        },
    },
}

# ═══════════════════════════════════════════
# QualityStamp
# ═══════════════════════════════════════════

@dataclass
class QualityStamp:
    """每条数据必须携带的质量印章"""
    data_type: str                    # 对应 DATA_SCHEMAS 的 key
    source: str                       # 数据来源函数/API
    collected_at: str                 # ISO 采集时间
    freshness: str = "unknown"        # T-0/T-1/T-2/.../EXPIRED
    trust: TrustLevel = TrustLevel.CAUTION
    passed_gates: List[str] = field(default_factory=list)
    failed_gates: List[dict] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    repair_hint: str = ""             # 如不通过，如何修复

    @property
    def stars(self) -> str:
        return trust_to_stars(self.trust)

    @property
    def is_blocked(self) -> bool:
        return self.trust == TrustLevel.BLOCKED

    @property
    def is_degraded(self) -> bool:
        return self.trust in (TrustLevel.BLOCKED, TrustLevel.DEGRADED)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["trust"] = self.trust.name
        d["stars"] = self.stars
        return d

    def summary(self) -> str:
        return (f"[{self.stars}] {self.data_type} "
                f"freshness={self.freshness} source={self.source} "
                f"gates={len(self.passed_gates)}/{len(self.passed_gates)+len(self.failed_gates)} "
                + (f"⚠️ {len(self.failed_gates)}门未过" if self.failed_gates else "✅"))


# ═══════════════════════════════════════════
# 五道质检门
# ═══════════════════════════════════════════

class DataGate:
    """单个质检门 — 可插拔，可扩展"""

    def __init__(self, name: str, priority: int, description: str):
        self.name = name
        self.priority = priority  # 0=最高
        self.description = description

    def check(self, data: Any, schema: dict, stamp: QualityStamp) -> Tuple[bool, str]:
        """
        返回 (pass, detail)。
        子类覆盖此方法实现具体检查逻辑。
        """
        return True, "ok"


class FreshnessGate(DataGate):
    """P0: 数据时效性 — 过期数据直接 BLOCKED"""

    def __init__(self):
        super().__init__("freshness", 0, "数据是否在SLA时效窗口内")

    def check(self, data, schema, stamp):
        sla_h = schema.get("sla_hours", 24)
        try:
            collected = datetime.fromisoformat(stamp.collected_at)
            age_h = (datetime.now() - collected).total_seconds() / 3600
        except Exception:
            return False, f"无法解析采集时间: {stamp.collected_at}"

        if age_h > sla_h * 3:
            stamp.freshness = "EXPIRED"
            stamp.trust = TrustLevel.BLOCKED
            return False, f"数据过期 {age_h:.0f}h > SLA×3 ({sla_h*3:.0f}h) — 禁止使用"
        elif age_h > sla_h:
            stamp.freshness = f"T-{int(age_h/24)+1}"
            stamp.warnings.append(f"数据滞后 {age_h:.0f}h，超过 SLA({sla_h}h)")
            return False, f"滞后 {age_h:.0f}h > SLA {sla_h}h"
        else:
            stamp.freshness = f"T-{max(0,int(age_h/24))}"
            return True, f"时效正常 ({age_h:.1f}h < SLA {sla_h}h)"


class SourceGate(DataGate):
    """P1: 数据来源 — schema 匹配 + 字段陷阱检测"""

    def __init__(self):
        super().__init__("source", 1, "数据来源是否可信，字段映射是否正确")

    def check(self, data, schema, stamp):
        # 检查数据是否包含关键字段
        if isinstance(data, dict):
            missing = [f for f in schema.get("critical_fields", []) if f not in data]
            if missing:
                stamp.trust = TrustLevel.DEGRADED
                return False, f"缺少关键字段: {missing}"

        # 字段陷阱检测: 已知容易混淆的字段
        traps = schema.get("field_trap", {})
        if traps and isinstance(data, dict):
            for field, warning in traps.items():
                if field in str(data):
                    stamp.warnings.append(f"数据包含陷阱字段 {field}: {warning}")
                    stamp.repair_hint = f"检查是否误用了 {field}，正确字段见 schema"

        return True, f"来源 {stamp.source} 字段完整"


class SanityGate(DataGate):
    """P2: 值域合理性 — 值是否在合理范围"""

    def __init__(self):
        super().__init__("sanity", 2, "数据值是否在合理范围内")

    def check(self, data, schema, stamp):
        rng = schema.get("range")
        typical = schema.get("typical")

        if rng and isinstance(data, dict):
            for key_field in schema.get("critical_fields", []):
                val = data.get(key_field)
                if val is None:
                    continue
                if isinstance(val, (int, float)):
                    lo, hi = rng
                    if val < lo * 0.5 or val > hi * 1.5:
                        stamp.trust = TrustLevel.DEGRADED
                        return False, f"{key_field}={val} 严重偏离合理范围[{lo},{hi}]"
                    if typical and (val < typical[0] or val > typical[1]):
                        stamp.warnings.append(f"{key_field}={val} 偏离典型范围{typical}")

        return True, "值域正常"


class CrossGate(DataGate):
    """P3: 多源交叉验证 — 独立数据源之间的数据是否一致"""

    def __init__(self):
        super().__init__("cross", 3, "多源交叉验证数据一致性")

    def check(self, data, schema, stamp):
        if not schema.get("cross_validatable"):
            return True, "skip — 无可交叉验证源"

        cross_source = schema.get("cross_source", "")
        if not cross_source:
            return True, "skip"

        # 根据 data_type 执行特定交叉验证
        if stamp.data_type == "north_flow":
            return self._cross_check_north_flow(data, stamp)

        return True, "skip — 交叉验证未实现"

    def _cross_check_north_flow(self, data, stamp):
        """北向资金: 直接查 tushare north_money 字段交叉验证"""
        try:
            import tushare as ts
            nf_val = float(data.get("net_flow", 0))
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

                    if diff_north < 1:  # 差值 < 1亿 = 一致
                        stamp.trust = TrustLevel.VERIFIED
                        return True, f"交叉验证通过: tushare north_money={north_raw:.1f}亿 ≈ 当前{nf_val:.1f}亿"
                    elif diff_south < diff_north and diff_south < 1:
                        stamp.trust = TrustLevel.DEGRADED
                        stamp.repair_hint = "字段混淆: get_north_flow() 可能使用了ggt_ss/ggt_sz(南向)而非north_money"
                        return False, (f"字段混淆: 当前{nf_val:.1f}亿≠北向({north_raw:.1f}亿)"
                                      f"而是≈南向({south_raw:.1f}亿) → 检查字段映射!")
                    else:
                        stamp.warnings.append(f"与tushare原始值偏差{diff_north:.1f}亿")
                    break
        except Exception as e:
            stamp.warnings.append(f"交叉验证失败: {e}")
        return True, "交叉验证未确认（数据源不可达）"


class TrendGate(DataGate):
    """P4: 趋势连贯性 — 与历史序列是否连贯"""

    def __init__(self):
        super().__init__("trend", 4, "数据与历史趋势是否连贯")

    def check(self, data, schema, stamp):
        baseline = _load_baseline(stamp.data_type)
        if not baseline:
            return True, "skip — 无历史基线"

        if stamp.data_type == "north_flow":
            nf_val = float(data.get("net_flow", 0)) if isinstance(data, dict) else 0
            hist_vals = baseline.get("recent_values", [])
            if hist_vals and len(hist_vals) >= 3:
                avg = sum(hist_vals) / len(hist_vals)
                if avg > 0 and abs(nf_val) > 0:
                    ratio = nf_val / avg
                    if ratio < 0.2 or ratio > 5:
                        stamp.warnings.append(f"北向{nf_val:.1f}亿与近期均值{avg:.1f}亿偏差{ratio:.1f}倍")
                        return False, f"趋势异常: 当前值是近期均值的{ratio:.1f}倍"

        return True, "趋势正常"


# ═══════════════════════════════════════════
# 质检引擎
# ═══════════════════════════════════════════

class DataQualityEngine:
    """数据真实性管理引擎 — 统一入口"""

    def __init__(self):
        self.gates = [
            FreshnessGate(),
            SourceGate(),
            SanityGate(),
            CrossGate(),
            TrendGate(),
        ]
        self.gates.sort(key=lambda g: g.priority)

    def verify(self, data: Any, data_type: str, source: str,
               collected_at: str = None, extra_schema: dict = None) -> QualityStamp:
        """
        对数据执行全量质检。

        Args:
            data: 原始数据
            data_type: 对应 DATA_SCHEMAS 的 key
            source: 数据来源标识
            collected_at: 采集时间(ISO)，默认 now
            extra_schema: 额外 schema 覆盖

        Returns:
            QualityStamp — 数据质量印章
        """
        schema = DATA_SCHEMAS.get(data_type, {})
        if extra_schema:
            schema = {**schema, **extra_schema}

        stamp = QualityStamp(
            data_type=data_type,
            source=source,
            collected_at=collected_at or datetime.now().isoformat(),
            trust=TrustLevel.CAUTION,
        )

        for gate in self.gates:
            try:
                passed, detail = gate.check(data, schema, stamp)
                if passed:
                    stamp.passed_gates.append(gate.name)
                else:
                    stamp.failed_gates.append({
                        "gate": gate.name,
                        "priority": f"P{gate.priority}",
                        "detail": detail,
                    })
                    # P0 失败 → 直接阻断后续检查
                    if gate.priority == 0:
                        break
            except Exception as e:
                stamp.failed_gates.append({
                    "gate": gate.name,
                    "priority": f"P{gate.priority}",
                    "detail": f"检查异常: {e}",
                })

        # 最终信任等级
        if stamp.trust == TrustLevel.CAUTION:  # 未被降级
            blocked = any(g["priority"] == "P0" for g in stamp.failed_gates)
            if blocked:
                stamp.trust = TrustLevel.BLOCKED
            elif stamp.failed_gates:
                stamp.trust = TrustLevel.DEGRADED
            elif len(stamp.passed_gates) >= 3:
                stamp.trust = TrustLevel.VERIFIED

        # 日志
        if stamp.failed_gates:
            _log_quality_event(stamp, "reject" if stamp.is_blocked else "warn")

        return stamp


# ═══════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════

_engine = DataQualityEngine()


def verify(data: Any, data_type: str, source: str = "unknown",
           collected_at: str = None) -> QualityStamp:
    """便捷入口: 质检一份数据"""
    return _engine.verify(data, data_type, source, collected_at)


def stamp(data_type: str):
    """装饰器: 自动为函数返回值添加质量印章

    @stamp("north_flow")
    def get_north_flow():
        return {...}
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            result = fn(*args, **kwargs)
            if isinstance(result, dict) and "_quality_stamp" not in result:
                collected = datetime.now().isoformat()
                qs = _engine.verify(result, data_type, fn.__name__, collected)
                result["_quality"] = qs.to_dict()
                result["_quality_stamp"] = qs
            return result
        return wrapper
    return decorator


def check_quality(data_type: str, data: dict, source: str) -> QualityStamp:
    """消费者调用: 使用前检查数据质量"""
    return _engine.verify(data, data_type, source,
                         data.get("_quality", {}).get("collected_at") if isinstance(data, dict) else None)


def should_reject(stamp: QualityStamp) -> bool:
    """是否应该拒绝使用这份数据"""
    return stamp.is_blocked


def get_repair_hint(stamp: QualityStamp) -> str:
    """获取修复建议"""
    if stamp.repair_hint:
        return stamp.repair_hint
    if stamp.failed_gates:
        return f"修复提示: {stamp.failed_gates[0]['detail']}"
    return "无修复需求"


def _load_baseline(data_type: str) -> dict:
    """加载历史基线数据"""
    bp = BASELINE_DIR / f"{data_type}.json"
    if bp.exists():
        try:
            return json.loads(bp.read_text())
        except Exception:
            pass
    return {}


def _save_baseline(data_type: str, snapshot: dict):
    """保存历史基线（由 cron 每小时更新）"""
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    baseline = _load_baseline(data_type)
    # 合并新值到 recent_values
    if "net_flow" in snapshot:
        vals = baseline.get("recent_values", [])
        vals.append(snapshot["net_flow"])
        baseline["recent_values"] = vals[-20:]  # 保留最近20条
    baseline["last_updated"] = datetime.now().isoformat()
    bp = BASELINE_DIR / f"{data_type}.json"
    bp.write_text(json.dumps(baseline, ensure_ascii=False, indent=2))


def _log_quality_event(stamp: QualityStamp, level: str):
    """记录质检事件"""
    log_path = REJECT_LOG_PATH if level == "reject" else ALERT_LOG_PATH
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logs = []
    if log_path.exists():
        try:
            logs = json.loads(log_path.read_text())
        except Exception:
            pass
    logs.append({
        "ts": stamp.collected_at,
        "type": stamp.data_type,
        "trust": stamp.trust.name,
        "level": level,
        "failed": stamp.failed_gates,
        "hint": stamp.repair_hint,
    })
    log_path.write_text(json.dumps(logs[-200:], ensure_ascii=False, indent=2))


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description=f'数据真实性管理网关 v{__version__}')
    ap.add_argument('--check', type=str, help='检查特定 data_type 的最新数据质量')
    ap.add_argument('--report', action='store_true', help='输出质检报告')
    ap.add_argument('--baseline', type=str, help='为指定 data_type 建立基线快照')
    args = ap.parse_args()

    if args.check:
        dt = args.check
        if dt == "north_flow":
            from data_pipeline import get_north_flow
            data = get_north_flow()
            qs = _engine.verify(data, "north_flow", "get_north_flow")
            print(qs.summary())
            if qs.failed_gates:
                for fg in qs.failed_gates:
                    print(f"  ❌ [{fg['priority']}] {fg['gate']}: {fg['detail']}")
            if qs.repair_hint:
                print(f"  🔧 修复: {qs.repair_hint}")

    if args.baseline:
        dt = args.baseline
        if dt == "north_flow":
            from data_pipeline import get_north_flow
            _save_baseline("north_flow", get_north_flow())
            print(f"✅ {dt} 基线已更新")

    if args.report:
        for log_path in [REJECT_LOG_PATH, ALERT_LOG_PATH]:
            if log_path.exists():
                logs = json.loads(log_path.read_text())
                recent = [l for l in logs if (datetime.now() - datetime.fromisoformat(l["ts"])).days < 7]
                print(f"\n## {log_path.name} (近7天: {len(recent)}条)")
                for l in recent[-5:]:
                    print(f"  [{l['ts'][:19]}] {l['type']} {l['trust']} {'🚨' if l['level']=='reject' else '⚠️'}")


if __name__ == "__main__":
    main()
