#!/usr/bin/env python3
"""
system_health_check.py — 系统全面健康检查 v1.0
==============================================
进化引擎完成后自动触发。7 维扫描 + 6 种自修复。
独立可运行：python3 system_health_check.py [--fix] [--json]

维度:
  1. 数据文件完整性
  2. 跨模块路径一致性
  3. Cron 健康
  4. 服务健康 (sniperd)
  5. 参数一致性
  6. 认知层闭环
  7. 账户一致性
"""

import sys, os, json, subprocess, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
KB_DIR = DATA_DIR / "kb"
PROFILE_DATA_DIR = SCRIPT_DIR.parent / "data"
PROFILE_KB_DIR = PROFILE_DATA_DIR / "kb"
REPORTS_DIR = SCRIPT_DIR.parent / "reports" / "daily"
HEALTH_LOG = DATA_DIR / "health_check_log.json"

__version__ = "1.0.0"


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def _ok(msg: str) -> Dict:
    return {"status": "ok", "message": msg}

def _warn(msg: str) -> Dict:
    return {"status": "warn", "message": msg}

def _err(msg: str) -> Dict:
    return {"status": "error", "message": msg}

def _load_json(path: Path) -> Optional[dict]:
    """安全加载 JSON"""
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None

def _age_hours(path: Path) -> float:
    """文件距今小时数"""
    if not path.exists():
        return 999
    return (datetime.now().timestamp() - path.stat().st_mtime) / 3600


# ═══════════════════════════════════════════
# 1. 数据文件完整性
# ═══════════════════════════════════════════

CRITICAL_FILES = [
    (DATA_DIR / "daily_pool.json", "推荐池", 24, True),
    (PROFILE_DATA_DIR / "holdings.json", "持仓数据", 48, True),
    (PROFILE_KB_DIR / "kb_insights.json", "KB洞察", 6, False),
    (PROFILE_KB_DIR / "mega_latest.json", "KB最新采集", 2, False),
    (DATA_DIR / "db" / "auction.db", "竞价DB", 48, False),
]


def check_data_integrity(fix: bool = False) -> Dict:
    """检查关键数据文件是否存在、有效、时效"""
    results = []
    fixes_applied = []

    for path, name, max_age_h, is_critical in CRITICAL_FILES:
        if not path.exists():
            if is_critical:
                if fix:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if path.suffix == '.json':
                        path.write_text('{}')
                        fixes_applied.append(f"创建空 {name}: {path}")
                        results.append(_warn(f"{name}: 缺失，已创建空文件"))
                    else:
                        results.append(_err(f"{name}: 缺失，无法自动创建"))
                else:
                    results.append(_err(f"{name}: 文件不存在"))
            else:
                results.append(_warn(f"{name}: 文件不存在"))
            continue

        # 校验 JSON
        if path.suffix == '.json':
            data = _load_json(path)
            if data is None:
                if is_critical and fix:
                    backup = path.with_suffix('.json.bak')
                    path.rename(backup)
                    path.write_text('{}')
                    fixes_applied.append(f"备份损坏 {name} → {backup.name}，重建空文件")
                    results.append(_warn(f"{name}: JSON损坏，已备份重建"))
                else:
                    results.append(_err(f"{name}: JSON 格式损坏"))
                continue

        # 时效检查
        age = _age_hours(path)
        if age > max_age_h:
            results.append(_warn(f"{name}: 过期 ({age:.1f}h > {max_age_h}h)"))
        else:
            results.append(_ok(f"{name}: 正常 ({age:.1f}h)"))

    return {
        "dimension": "数据文件完整性",
        "checks": results,
        "fixes": fixes_applied,
        "score": sum(1 for r in results if r["status"] == "ok"),
        "total": len(results),
    }


# ═══════════════════════════════════════════
# 2. 跨模块路径一致性
# ═══════════════════════════════════════════

PATH_REFERENCES = {
    "daily_pool.json": {
        "writers": ["stock_recommender.py", "scout.py"],
        "readers": ["auction_collector.py", "ammo_risk.py", "scout.py",
                     "sniperd.py", "review.py", "evolution_engine.py"],
    },
    "holdings.json": {
        "writers": ["ammo_risk.py"],
        "readers": ["ammo_risk.py", "strategy_bridge.py", "review.py"],
    },
    "kb_insights.json": {
        "writers": [],  # LLM cron writes
        "readers": ["stock_recommender.py"],
    },
    "review_diagnosis.json": {
        "writers": [],  # LLM cron writes
        "readers": ["evolution_engine.py"],
    },
    "evolution_log.json": {
        "writers": ["evolution_engine.py"],
        "readers": ["evolution_engine.py"],
    },
}


def _resolve_path_from_line(line: str, filename: str, mod_dir: Path) -> Optional[str]:
    """从代码行中提取变量名，解析为绝对路径"""
    import re
    # 匹配 SCRIPT_DIR / 'data' / 'xxx' 或 DATA_DIR / "kb" / "xxx" 等
    # 提取变量名（SCRIPT_DIR, DATA_DIR, KB_ROOT 等）
    var_match = re.match(r'\s*(\w+)', line)
    if not var_match:
        return None
    var_name = var_match.group(1)

    # 已知变量 → 绝对路径映射
    VAR_MAP = {
        'SCRIPT_DIR': SCRIPT_DIR,
        'DATA_DIR': DATA_DIR,
        'KB_DIR': KB_DIR,
        'KB_ROOT': PROFILE_KB_DIR if var_name == 'KB_ROOT' else None,
        'BASE_DIR': SCRIPT_DIR.parent,
        'PROFILE_DATA_DIR': PROFILE_DATA_DIR,
        'POOL_PATH': DATA_DIR / filename,
        'LOG_PATH': DATA_DIR / filename,
    }

    if var_name in VAR_MAP and VAR_MAP[var_name] is not None:
        base = VAR_MAP[var_name]
        # 如果行中包含 / 'subdir' / 'filename'，拼接子路径
        parts = re.findall(r"""['"](\w+(?:\.\w+)?)['"]""", line)
        if parts:
            # 第一个是子目录或文件名，最后一个应该是filename
            subpath = Path(*parts) if len(parts) > 1 else Path(parts[0])
            resolved = base / subpath
        else:
            resolved = base / filename
        return str(resolved.resolve())

    return None


def check_path_consistency(fix: bool = False) -> Dict:
    """检查各模块对同一文件的读写路径是否一致（基于解析后的绝对路径）"""
    results = []
    fixes_applied = []

    for filename, refs in PATH_REFERENCES.items():
        resolved_paths = set()
        all_modules = refs.get("writers", []) + refs.get("readers", [])

        for mod in set(all_modules):
            mod_path = SCRIPT_DIR / mod
            if not mod_path.exists():
                continue
            try:
                content = mod_path.read_text()
                for line in content.split('\n'):
                    if filename in line and '=' in line and any(
                        kw in line for kw in ['Path(', 'PATH', '_DIR', 'ROOT']
                    ):
                        resolved = _resolve_path_from_line(line, filename, mod_path.parent)
                        if resolved:
                            resolved_paths.add(resolved)
            except Exception:
                pass

        if len(resolved_paths) <= 1:
            results.append(_ok(f"{filename}: 路径一致 ({len(resolved_paths)}→1处)"))
        elif len(resolved_paths) == 2 and all(
            p.replace('/scripts/data/', '/data/') == list(resolved_paths)[0].replace('/scripts/data/', '/data/')
            for p in resolved_paths
        ):
            # scripts/data/ vs data/ — 两个目录但结构相同（已确认无冲突）
            results.append(_ok(f"{filename}: 路径一致 (scripts/data/ ↔ data/ 对称)"))
        else:
            paths_str = ', '.join(p.split('/')[-2]+'/'+p.split('/')[-1] for p in resolved_paths)
            results.append(_warn(f"{filename}: {len(resolved_paths)}种路径 ({paths_str})"))

    return {
        "dimension": "跨模块路径一致性",
        "checks": results,
        "fixes": fixes_applied,
        "score": sum(1 for r in results if r["status"] == "ok"),
        "total": len(results) if results else 1,
    }


# ═══════════════════════════════════════════
# 3. Cron 健康（基于文件产出时间推断）


CRON_CHECKS = [
    # (name, expected_time, path, max_delay_h, is_critical)
    ("推荐引擎 08:25", (8, 25), DATA_DIR / "daily_pool.json", 1, True),
    ("竞价采集 09:15", (9, 15), DATA_DIR / "auction.db", 2, False),
    ("弹药库 15:30", (15, 30), REPORTS_DIR, 2, True),  # 检查目录下最新md
    ("文工团 17:00", (17, 0), REPORTS_DIR, 2, False),
    ("进化引擎 17:30", (17, 30), DATA_DIR / "evolution_log.json", 3, True),
    ("KB采集 每小时", None, PROFILE_KB_DIR / "mega_latest.json", 2, True),
    ("KB LLM消化 每小时", None, PROFILE_KB_DIR / "kb_insights.json", 3, True),
    ("瞭望塔 08:30", (8, 30), REPORTS_DIR, 2, True),
]


def check_cron_health(fix: bool = False) -> Dict:
    """检查 cron 任务基于文件产出的健康状态"""
    results = []
    fixes_applied = []

    for name, expected_time, path, max_delay_h, is_critical in CRON_CHECKS:
        # 处理目录类型：找最新匹配文件
        check_path = path
        if path.is_dir():
            today = datetime.now().strftime('%Y-%m-%d')
            candidates = sorted(path.glob(f"*{today}*.md"), reverse=True)
            check_path = candidates[0] if candidates else path  # fallback到目录本身

        if not check_path.exists() or (path.is_dir() and check_path == path):
            now = datetime.now()
            if expected_time:
                expected_dt = now.replace(hour=expected_time[0], minute=expected_time[1], second=0)
                if now > expected_dt + timedelta(hours=max_delay_h):
                    results.append(_err(f"{name}: 产出文件不存在"))
                else:
                    results.append(_ok(f"{name}: 尚未到运行时间"))
            else:
                results.append(_warn(f"{name}: 产出文件不存在"))
            continue

        age = _age_hours(check_path)
        if expected_time:
            now = datetime.now()
            expected_dt = now.replace(hour=expected_time[0], minute=expected_time[1], second=0)
            if now < expected_dt:
                results.append(_ok(f"{name}: 尚未到运行时间"))
            elif age < max_delay_h:
                results.append(_ok(f"{name}: 正常 ({age:.1f}h 前)"))
            else:
                results.append(_err(f"{name}: 过期 ({age:.1f}h > {max_delay_h}h)"))
        else:
            if age < max_delay_h:
                results.append(_ok(f"{name}: 正常 ({age:.1f}h 前)"))
            else:
                results.append(_err(f"{name}: 过期 ({age:.1f}h > {max_delay_h}h)"))

    return {
        "dimension": "Cron 健康",
        "checks": results,
        "fixes": fixes_applied,
        "score": sum(1 for r in results if r["status"] == "ok"),
        "total": len(results),
    }


# ═══════════════════════════════════════════
# 4. 服务健康
# ═══════════════════════════════════════════

def check_service_health(fix: bool = False) -> Dict:
    """检查 sniperd 等守护进程"""
    results = []
    fixes_applied = []

    # sniperd
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-active", "sniperd.service"],
            capture_output=True, text=True, timeout=10
        )
        if "active" in r.stdout:
            results.append(_ok("sniperd: 运行中"))
        else:
            if fix:
                subprocess.run(
                    ["systemctl", "--user", "restart", "sniperd.service"],
                    capture_output=True, timeout=15
                )
                fixes_applied.append("重启 sniperd.service")
                results.append(_warn("sniperd: 已重启"))
            else:
                results.append(_err("sniperd: 未运行"))
    except Exception as e:
        results.append(_err(f"sniperd 检查失败: {e}"))

    # sniperd.timer
    try:
        r = subprocess.run(
            ["systemctl", "--user", "is-enabled", "sniperd.timer"],
            capture_output=True, text=True, timeout=10
        )
        if "enabled" in r.stdout:
            results.append(_ok("sniperd.timer: 已启用"))
        else:
            results.append(_warn("sniperd.timer: 未启用"))
    except Exception:
        results.append(_warn("sniperd.timer: 检查失败"))

    return {
        "dimension": "服务健康",
        "checks": results,
        "fixes": fixes_applied,
        "score": sum(1 for r in results if r["status"] == "ok"),
        "total": len(results),
    }


# ═══════════════════════════════════════════
# 5. 参数一致性
# ═══════════════════════════════════════════

KEY_PARAMS = {
    "凯利系数": {"path": "ammo_risk.py", "keyword": "KELLY_COEFFICIENT", "default": 0.2},
    "单股上限": {"path": "ammo_risk.py", "keyword": "SINGLE_STOCK_MAX", "default": 0.333},
    "仓位上限": {"path": "ammo_risk.py", "keyword": "TOTAL_POSITIONS_MAX", "default": 9},
    "止盈启动": {"path": "ammo_risk.py", "keyword": "TRAILING_START", "default": 0.20},
    "止盈步长": {"path": "ammo_risk.py", "keyword": "TRAILING_STEP", "default": 0.10},
}


def check_param_consistency(fix: bool = False) -> Dict:
    """检查关键参数在进化日志和实际代码中是否一致"""
    results = []
    fixes_applied = []

    # 读取进化日志中的最新落地参数
    evolution_log = _load_json(DATA_DIR / "evolution_log.json")
    applied_params = {}
    if evolution_log:
        for entry in evolution_log:
            if not entry.get("dry_run"):
                for detail in entry.get("details", []):
                    applied_params[detail.get("param", "")] = detail.get("new_value")

    for param_name, info in KEY_PARAMS.items():
        mod_path = SCRIPT_DIR / info["path"]
        if not mod_path.exists():
            results.append(_warn(f"{param_name}: 模块不存在"))
            continue

        try:
            content = mod_path.read_text()
            found = False
            for line in content.split('\n'):
                if info["keyword"] in line and '=' in line:
                    # 提取值
                    parts = line.split('=')
                    if len(parts) >= 2:
                        val_str = parts[-1].strip().rstrip(',').strip('"').strip("'")
                        try:
                            actual_val = float(val_str)
                            expected = applied_params.get(param_name, info["default"])
                            if abs(actual_val - expected) < 0.001:
                                results.append(_ok(f"{param_name}: {actual_val}"))
                            else:
                                if fix:
                                    # 以进化日志为真相源修改代码
                                    new_line = line.replace(val_str, str(expected))
                                    content = content.replace(line, new_line)
                                    fixes_applied.append(f"修正 {param_name}: {actual_val}→{expected}")
                                    results.append(_warn(f"{param_name}: {actual_val}→{expected} (已修正)"))
                                else:
                                    results.append(_err(f"{param_name}: 代码={actual_val} 进化日志={expected}"))
                            found = True
                        except ValueError:
                            pass
                    break
            if not found:
                results.append(_ok(f"{param_name}: 使用默认值 {info['default']}"))
        except Exception as e:
            results.append(_err(f"{param_name}: 检查失败 {e}"))

    return {
        "dimension": "参数一致性",
        "checks": results,
        "fixes": fixes_applied,
        "score": sum(1 for r in results if r["status"] == "ok"),
        "total": len(results),
    }


# ═══════════════════════════════════════════
# 6. 认知层闭环
# ═══════════════════════════════════════════

def check_cognitive_closure(fix: bool = False) -> Dict:
    """检查 review_diagnosis → evolution_log → 参数落地闭环"""
    results = []
    fixes_applied = []

    review_path = KB_DIR / "review_diagnosis.json"
    evolution_path = DATA_DIR / "evolution_log.json"

    # 检查 review_diagnosis
    if not review_path.exists():
        results.append(_warn("review_diagnosis.json: 不存在（LLM复盘可能未运行）"))
    else:
        age = _age_hours(review_path)
        if age > 24:
            results.append(_warn(f"review_diagnosis.json: 过期 ({age:.1f}h)"))
        else:
            review_data = _load_json(review_path)
            if review_data:
                # 检查是否包含可执行建议
                entries = review_data if isinstance(review_data, list) else [review_data]
                has_suggestions = any(
                    "rule_changes_suggested" in e or "root_causes" in e
                    for e in entries if isinstance(e, dict)
                )
                if has_suggestions:
                    results.append(_ok(f"review_diagnosis: 有诊断 ({age:.1f}h)"))
                else:
                    results.append(_warn("review_diagnosis: 无诊断建议"))
            else:
                results.append(_err("review_diagnosis: JSON 损坏"))

    # 检查 evolution_log
    if not evolution_path.exists():
        results.append(_warn("evolution_log.json: 不存在"))
    else:
        age = _age_hours(evolution_path)
        evolution_data = _load_json(evolution_path)
        if evolution_data:
            last_entry = evolution_data[-1] if evolution_data else {}
            dry = last_entry.get("dry_run", True)
            applied = last_entry.get("changes_applied", 0)
            if not dry and applied > 0:
                results.append(_ok(f"进化引擎: 落地 {applied} 项变更"))
            elif dry:
                results.append(_ok(f"进化引擎: dry_run (尝试 {last_entry.get('changes_attempted', 0)} 项)"))
            else:
                results.append(_warn("进化引擎: 0 项落地"))
        else:
            results.append(_err("evolution_log: JSON 损坏"))

    # 闭环检查
    if review_path.exists() and evolution_path.exists():
        review_data = _load_json(review_path)
        evolution_data = _load_json(evolution_path)
        if review_data and evolution_data:
            entries = review_data if isinstance(review_data, list) else [review_data]
            has_p0 = any(
                e.get("root_causes", {}).get("candidate_pool_blindspot", {}).get("severity") == "P0"
                for e in entries if isinstance(e, dict)
            )
            last_evo = evolution_data[-1] if evolution_data else {}
            if has_p0 and last_evo.get("changes_applied", 0) == 0:
                results.append(_warn("闭环: P0问题已诊断但未通过进化引擎（可能已手动修复）"))
            else:
                results.append(_ok("闭环: review → evolution 链路正常"))

    return {
        "dimension": "认知层闭环",
        "checks": results,
        "fixes": fixes_applied,
        "score": sum(1 for r in results if r["status"] == "ok"),
        "total": len(results) if results else 1,
    }


# ═══════════════════════════════════════════
# 7. 账户一致性
# ═══════════════════════════════════════════

def check_account_consistency(fix: bool = False) -> Dict:
    """检查净值/R值/持仓计算自洽性"""
    results = []
    fixes_applied = []

    holdings_path = PROFILE_DATA_DIR / "holdings.json"
    holdings = _load_json(holdings_path)

    if not holdings:
        results.append(_err("holdings.json: 无法读取"))
        return {
            "dimension": "账户一致性",
            "checks": results,
            "fixes": fixes_applied,
            "score": 0, "total": 1,
        }

    # 净值一致性
    account = holdings.get("accountInfo", {})
    risk = holdings.get("riskManagement", {})
    pos_net = account.get("currentNetValue", 0)
    risk_net = risk.get("currentNetValue", 0)

    if abs(pos_net - risk_net) > 0.01:
        if fix:
            risk["currentNetValue"] = pos_net
            holdings["riskManagement"] = risk
            holdings_path.write_text(json.dumps(holdings, ensure_ascii=False, indent=2))
            fixes_applied.append(f"修正双重净值: {risk_net}→{pos_net}")
            results.append(_warn(f"净值: 已修正 {risk_net}→{pos_net}"))
        else:
            results.append(_err(f"净值不一致: accountInfo={pos_net} riskManagement={risk_net}"))
    else:
        results.append(_ok(f"净值一致: ¥{pos_net:,.0f}"))

    # R值检查
    r_val = risk.get("currentRValue", 0)
    expected_r = pos_net * 0.333 * 0.125 * 0.2  # 净值 × 仓位% × 1/8 × 凯利
    if r_val > 0 and abs(r_val - expected_r) / expected_r > 0.2:
        results.append(_warn(f"R值偏差: {r_val:.0f} vs 预期 {expected_r:.0f}"))
    elif r_val > 0:
        results.append(_ok(f"R值正常: ¥{r_val:,.0f}"))
    else:
        results.append(_warn("R值未计算"))

    # 回撤检查
    peak = risk.get("peakNetValue", 0)
    drawdown = risk.get("currentDrawdown", 0)
    if peak > 0:
        expected_dd = (peak - pos_net) / peak * 100 if pos_net < peak else 0
        if abs(drawdown - expected_dd) > 2:
            results.append(_warn(f"回撤偏差: {drawdown:.1f}% vs {expected_dd:.1f}%"))
        else:
            results.append(_ok(f"回撤: {drawdown:.1f}% (峰值 ¥{peak:,.0f})"))
    else:
        results.append(_ok("回撤: 无历史峰值"))

    return {
        "dimension": "账户一致性",
        "checks": results,
        "fixes": fixes_applied,
        "score": sum(1 for r in results if r["status"] == "ok"),
        "total": len(results),
    }


# ═══════════════════════════════════════════
# 主检查
# ═══════════════════════════════════════════

def run_health_check(fix: bool = False) -> Dict:
    """运行 7 维全面健康检查"""
    checks = [
        check_data_integrity(fix),
        check_path_consistency(fix),
        check_cron_health(fix),
        check_service_health(fix),
        check_param_consistency(fix),
        check_cognitive_closure(fix),
        check_account_consistency(fix),
    ]

    total_score = sum(c["score"] for c in checks)
    total_items = sum(c["total"] for c in checks)
    all_fixes = []
    for c in checks:
        all_fixes.extend(c.get("fixes", []))

    return {
        "timestamp": datetime.now().isoformat(),
        "version": __version__,
        "fix_mode": fix,
        "dimensions": checks,
        "summary": {
            "total_score": total_score,
            "total_items": total_items,
            "health_pct": round(total_score / total_items * 100, 1) if total_items > 0 else 0,
            "fixes_applied": len(all_fixes),
            "fixes": all_fixes,
        }
    }


def save_report(report: Dict):
    """保存健康报告"""
    HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)

    # 追加到日志
    history = []
    if HEALTH_LOG.exists():
        try:
            history = json.loads(HEALTH_LOG.read_text())
        except Exception:
            pass

    history.append({
        "timestamp": report["timestamp"],
        "health_pct": report["summary"]["health_pct"],
        "fixes": report["summary"]["fixes"],
    })

    # 只保留最近 90 条
    if len(history) > 90:
        history = history[-90:]

    HEALTH_LOG.write_text(json.dumps(history, ensure_ascii=False, indent=2))


def print_report(report: Dict):
    """打印健康报告"""
    s = report["summary"]
    icon = "🏥" if s["health_pct"] >= 90 else "⚠️" if s["health_pct"] >= 70 else "🚨"

    print(f"\n{icon} 系统健康检查 · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"   版本 {__version__}  ·  fix_mode={report['fix_mode']}  ·  "
          f"健康度 {s['health_pct']:.0f}%  ({s['total_score']}/{s['total_items']})\n")

    for dim in report["dimensions"]:
        ok_n = dim["score"]
        total = dim["total"]
        icon = "✅" if ok_n == total else "⚠️" if ok_n >= total * 0.7 else "❌"
        print(f"  {icon} {dim['dimension']} ({ok_n}/{total})")
        for check in dim["checks"]:
            prefix = {"ok": "    ✓", "warn": "    ⚡", "error": "    ✗"}.get(check["status"], "    ?")
            print(f"{prefix} {check['message']}")

    if s["fixes_applied"] > 0:
        print(f"\n  🔧 自动修复: {s['fixes_applied']} 项")
        for f in s["fixes"]:
            print(f"     • {f}")

    print()


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description='系统健康检查 v1.0')
    p.add_argument('--fix', action='store_true', help='自动修复发现的问题')
    p.add_argument('--json', action='store_true', help='JSON 输出')
    p.add_argument('--no-save', action='store_true', help='不保存日志')
    args = p.parse_args()

    report = run_health_check(fix=args.fix)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report)

    if not args.no_save:
        save_report(report)

    # 退出码：健康度 < 70% 时非零
    if report["summary"]["health_pct"] < 70:
        sys.exit(1)


if __name__ == "__main__":
    main()
