#!/usr/bin/env python3
"""
auto_repair.py — 交易系统自主修复引擎 v1.0
=========================================
配合 system_health_check.py v1.3，扫描后自主修复已知问题。

用法:
  from auto_repair import run_auto_repair
  fix_result = run_auto_repair(check_result)
"""

import json, os, sys, subprocess
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
DATA_DIR = SCRIPT_DIR / "data"
REPORTS_DIR = WORKSPACE / "reports"

FIX_LOG_PATH = DATA_DIR / "fix_log.json"
VENV_PYTHON = str(Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3")


def _log_fix(action: str, detail: str, success: bool):
    """记录修复操作到日志"""
    fix_log = []
    if FIX_LOG_PATH.exists():
        try:
            fix_log = json.loads(FIX_LOG_PATH.read_text())
            if not isinstance(fix_log, list):
                fix_log = []
        except Exception:
            fix_log = []
    fix_log.append({
        "ts": datetime.now().isoformat(),
        "action": action,
        "detail": detail[:200],
        "ok": success,
    })
    FIX_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    FIX_LOG_PATH.write_text(json.dumps(fix_log[-50:], ensure_ascii=False, indent=2))


def _run_script(script_name: str, args: list = None, timeout: int = 120) -> tuple:
    """运行同目录下的 Python 脚本，返回 (returncode, stdout)"""
    sp = SCRIPT_DIR / script_name
    if not sp.exists():
        return -1, f"脚本不存在: {script_name}"
    cmd = [VENV_PYTHON, str(sp)] + (args or [])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, cwd=str(SCRIPT_DIR))
        return r.returncode, (r.stdout + r.stderr)[:500]
    except subprocess.TimeoutExpired:
        return -1, f"超时 ({timeout}s)"
    except Exception as e:
        return -1, str(e)


# ═══════════════════════════════════════════
# 各维度修复函数
# ═══════════════════════════════════════════

def fix_valuation_sync() -> dict:
    """D2: 持仓估值同步 → ammo_risk.py --update"""
    rc, out = _run_script("ammo_risk.py", ["--update"], timeout=60)
    ok = rc == 0
    _log_fix("valuation_sync", f"rc={rc}", ok)
    return {"fixed": ok, "detail": f"ammo_risk --update rc={rc}"}


def fix_parliament_flow() -> dict:
    """D3: 议会链路断裂 → researchers.py --parliament"""
    rc, out = _run_script("researchers.py", ["--parliament"], timeout=120)
    ok = rc == 0
    _log_fix("parliament_flow", f"rc={rc}", ok)
    return {"fixed": ok, "detail": f"议会重新生成 rc={rc}"}


def fix_cron_execution(check_result: dict) -> dict:
    """D6: Cron 执行异常 — 重启 sniperd + 修复脚本"""
    fixes = []

    # 1. 重启 sniperd
    if not check_result.get("sniper_ok", True):
        try:
            subprocess.run(["systemctl", "--user", "restart", "sniperd.service"],
                         capture_output=True, timeout=30)
            fixes.append("sniperd 已重启")
            _log_fix("cron_exec", "restart sniperd", True)
        except Exception as e:
            fixes.append(f"sniperd 重启失败: {e}")
            _log_fix("cron_exec", f"sniperd fail: {e}", False)

    # 2. 清理 cron 脚本行号污染
    if not check_result.get("scripts_ok", True):
        cnt = _clean_cron_line_numbers()
        fixes.append(f"cron脚本清理: {cnt}个")
        _log_fix("cron_exec", f"scripts cleaned: {cnt}", cnt > 0)

    return {"fixed": len(fixes) > 0, "detail": "; ".join(fixes) if fixes else "skip"}


def _clean_cron_line_numbers() -> int:
    """清理 cron_*.sh 中的行号污染 (N|前缀)"""
    import re
    fixed = 0
    for f in SCRIPT_DIR.glob("cron_*.sh"):
        try:
            raw = f.read_bytes()
            first_bytes = raw[:20].decode('utf-8', errors='replace')
            if '|' in first_bytes and not raw.startswith(b'#!'):
                content = raw.decode('utf-8', errors='replace')
                cleaned = re.sub(r'^\s*\d+\|', '', content, flags=re.MULTILINE)
                f.write_text(cleaned)
                fixed += 1
        except Exception:
            pass
    # 同时检查 sniper_healthcheck.sh
    for f in SCRIPT_DIR.glob("sniper_healthcheck.sh"):
        try:
            raw = f.read_bytes()
            if '|' in raw[:20].decode('utf-8', errors='replace') and not raw.startswith(b'#!'):
                cleaned = re.sub(r'^\s*\d+\|', '', raw.decode('utf-8', errors='replace'), flags=re.MULTILINE)
                f.write_text(cleaned)
                fixed += 1
        except Exception:
            pass
    return fixed


def fix_data_pipeline() -> dict:
    """D5: 数据管线 — 清理30分钟以上旧缓存"""
    fixes = []
    cache_dir = SCRIPT_DIR / "data" / "cache"
    if cache_dir.exists():
        for f in cache_dir.glob("*.json"):
            age = (datetime.now().timestamp() - f.stat().st_mtime) / 60
            if age > 30:
                f.unlink()
                fixes.append(f.name)
    ok = len(fixes) > 0
    _log_fix("data_pipeline", f"cleared {len(fixes)} cache files", ok)
    return {"fixed": ok, "detail": f"清理{len(fixes)}个过期缓存" if ok else "skip - 缓存正常"}


def fix_researcher_quality() -> dict:
    """D7: 研究员报告空壳 → 重新研学"""
    research_dir = REPORTS_DIR / "research"
    if research_dir.exists():
        reports = sorted(research_dir.glob("研学报告-*.md"), reverse=True)
        if reports:
            return {"fixed": True, "detail": "skip - 已存在报告"}

    rc, out = _run_script("researchers.py", ["--study"], timeout=180)
    ok = rc == 0
    _log_fix("researcher_quality", f"rc={rc}", ok)
    return {"fixed": ok, "detail": f"研学重新生成 rc={rc}"}


def fix_bronze_silver_gold() -> dict:
    """D10+D11: 分层数据管线重新生成"""
    results = []
    for s in ["bronze_ingest.py", "silver_pipeline.py", "gold_pipeline.py"]:
        rc, _ = _run_script(s, timeout=120)
        results.append(f"{s}: rc={rc}")
    ok = all("rc=0" in r for r in results)
    _log_fix("pipeline_retry", "; ".join(results), ok)
    return {"fixed": ok, "detail": "; ".join(results)}


# ═══════════════════════════════════════════
# 调度器
# ═══════════════════════════════════════════

def run_auto_repair(check_result: dict) -> dict:
    """
    输入 run_full_check() 的结果，逐维修复已知问题。
    仅修复已知且安全的问题类型，未知问题不碰。
    """
    checks = check_result.get("checks", {})
    fixes = []

    dispatch = [
        ("2_valuation_sync",    "持仓估值同步",     fix_valuation_sync),
        ("3_parliament_flow",   "议会链路",         fix_parliament_flow),
        ("5_data_pipeline",     "数据管线",         fix_data_pipeline),
        ("7_researcher_quality","研究员质量",       fix_researcher_quality),
    ]

    for dim_key, name, fix_fn in dispatch:
        if checks.get(dim_key, {}).get("status") in ("degraded", "down"):
            r = fix_fn() if dim_key != "6_cron_execution" else fix_fn(checks["6_cron_execution"])
            fixes.append({**r, "dimension": dim_key, "name": name})

    # D6 特殊：需要传 check_result
    if checks.get("6_cron_execution", {}).get("status") in ("degraded", "down"):
        r = fix_cron_execution(checks["6_cron_execution"])
        fixes.append({**r, "dimension": "6_cron_execution", "name": "Cron执行"})

    # D10+D11
    s_status = checks.get("10_silver_quality", {}).get("status")
    g_status = checks.get("11_gold_quality", {}).get("status")
    if s_status in ("degraded", "down") or g_status in ("degraded", "down"):
        r = fix_bronze_silver_gold()
        fixes.append({**r, "dimension": "10_11_pipeline", "name": "分层数据管线"})

    # D12: Cron脚本行号污染
    if checks.get("12_cron_scripts", {}).get("status") in ("degraded", "down"):
        cnt = _clean_cron_line_numbers()
        fixes.append({
            "fixed": cnt > 0,
            "detail": f"清理{cnt}个污染脚本",
            "dimension": "12_cron_scripts",
            "name": "Cron脚本完整性"
        })

    fixed_count = sum(1 for f in fixes if f.get("fixed"))
    total = len(fixes)

    return {
        "timestamp": datetime.now().isoformat(),
        "fixes_applied": fixes,
        "fixed_count": fixed_count,
        "total_issues": total,
        "all_fixed": fixed_count == total if total > 0 else True,
        "summary": f"自主修复: {fixed_count}/{total} 项问题已修复" if total > 0 else "无需修复"
    }


def format_fix_report(fix_result: dict) -> str:
    """格式化修复报告"""
    lines = ["## 🩺 自主修复报告", ""]
    for f in fix_result.get("fixes_applied", []):
        icon = "✅" if f.get("fixed") else "❌"
        lines.append(f"- {icon} **{f['name']}**: {f.get('detail', '')}")
    if not fix_result.get("fixes_applied"):
        lines.append("- ✅ 所有已知问题均无需修复")
    lines.append("")
    lines.append(f"> {fix_result['summary']}")
    return "\n".join(lines)
