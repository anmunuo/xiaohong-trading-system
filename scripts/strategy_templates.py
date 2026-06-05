#!/usr/bin/env python3
"""
strategy_templates.py — 策略模板参数化引擎 v1.0
==============================================
借鉴 VibetradingLabs 策略模板思路，将推荐引擎+侦察兵+止损规则打包为可切换模板。

用法:
  python3 strategy_templates.py --list           # 列出所有模板
  python3 strategy_templates.py --apply balanced # 应用指定模板
  python3 strategy_templates.py --show aggressive # 查看模板详情

架构:
  LLM(瞭望塔宏观判断) → 选择模板 → 覆盖 stock_recommender 因子权重
                                      → 覆盖 scout.py 资金门槛
                                      → 覆盖 止损/仓位规则
"""

import json, os, sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
TEMPLATE_PATH = SCRIPT_DIR / 'data' / 'strategy_templates.json'
ACTIVE_PATH = SCRIPT_DIR / 'data' / 'active_template.json'

__version__ = "1.0.0"

# ═══════════════════════════════════════════
# 内置模板定义
# ═══════════════════════════════════════════

BUILTIN_TEMPLATES = {
    "balanced": {
        "name": "均衡模板",
        "description": "日常默认，五因子均衡配置，适合震荡市",
        "version": "1.0",
        "market_condition": ["震荡", "方向不明", "中性"],
        "recommender": {
            "factor_weights": {
                "event":     0.30,
                "fund":      0.25,
                "sentiment": 0.18,
                "technical": 0.15,
                "research":  0.07,
                "new_factors": 0.05
            },
            "weight_sum": 1.00,
            "exclude": {
                "min_market_cap": 30,    # 亿
                "max_market_cap": 2000,  # 亿
                "max_lianban": 2,        # ≥2连板排除
                "max_change_pct": 9      # 涨超9%不追
            }
        },
        "scout": {
            "flow_threshold_neutral": 5000,  # 万
            "flow_threshold_strong": 3000,
            "flow_threshold_weak": 8000,
            "max_picks_double": 6,
            "max_picks_new": 4,
            "min_change_pct": -3,
            "max_change_pct": 9
        },
        "risk": {
            "default_stop_loss": -5.0,    # %
            "chinext_stop_loss": -7.0,
            "star_stop_loss": -8.0,       # 科创板
            "max_position_pct": 33.3,     # 单票上限
            "max_portfolio_stocks": 9,
            "r_value_target": 2.0         # % 单笔风险
        },
        "position": {
            "light": 0.30,   # 轻仓 30%
            "medium": 0.50,  # 中仓 50%
            "heavy": 0.70,   # 重仓 70%
            "full": 0.90     # 满仓 90%
        }
    },

    "aggressive": {
        "name": "进取模板",
        "description": "强势市场：重事件+技术，降低基本面权重，放宽止损",
        "version": "1.0",
        "market_condition": ["强势上涨", "放量突破", "北向持续流入"],
        "recommender": {
            "factor_weights": {
                "event":     0.35,
                "fund":      0.15,
                "sentiment": 0.20,
                "technical": 0.20,
                "research":  0.05,
                "new_factors": 0.05
            },
            "weight_sum": 1.00,
            "exclude": {
                "min_market_cap": 40,
                "max_market_cap": 3000,
                "max_lianban": 3,
                "max_change_pct": 11
            }
        },
        "scout": {
            "flow_threshold_neutral": 3000,
            "flow_threshold_strong": 2000,
            "flow_threshold_weak": 5000,
            "max_picks_double": 8,
            "max_picks_new": 6,
            "min_change_pct": -5,
            "max_change_pct": 11
        },
        "risk": {
            "default_stop_loss": -3.0,
            "chinext_stop_loss": -5.0,
            "star_stop_loss": -7.0,
            "max_position_pct": 40.0,
            "max_portfolio_stocks": 12,
            "r_value_target": 3.0
        },
        "position": {
            "light": 0.40,
            "medium": 0.65,
            "heavy": 0.85,
            "full": 1.00
        }
    },

    "defensive": {
        "name": "防御模板",
        "description": "弱势/高估值：重基本面+研究，收紧止损，降低仓位上限",
        "version": "1.0",
        "market_condition": ["弱势下跌", "高估值", "去杠杆", "外盘风险"],
        "recommender": {
            "factor_weights": {
                "event":     0.15,
                "fund":      0.35,
                "sentiment": 0.15,
                "technical": 0.10,
                "research":  0.20,
                "new_factors": 0.05
            },
            "weight_sum": 1.00,
            "exclude": {
                "min_market_cap": 50,
                "max_market_cap": 1500,
                "max_lianban": 2,
                "max_change_pct": 7
            }
        },
        "scout": {
            "flow_threshold_neutral": 8000,
            "flow_threshold_strong": 5000,
            "flow_threshold_weak": 10000,
            "max_picks_double": 4,
            "max_picks_new": 2,
            "min_change_pct": -2,
            "max_change_pct": 7
        },
        "risk": {
            "default_stop_loss": -7.0,
            "chinext_stop_loss": -10.0,
            "star_stop_loss": -10.0,
            "max_position_pct": 20.0,
            "max_portfolio_stocks": 6,
            "r_value_target": 1.0
        },
        "position": {
            "light": 0.15,
            "medium": 0.30,
            "heavy": 0.50,
            "full": 0.65
        }
    }
}


# ═══════════════════════════════════════════
# 模板管理器
# ═══════════════════════════════════════════

class TemplateManager:
    """加载/切换/查询策略模板"""

    def __init__(self):
        self._templates = {}
        self._active = None
        self._load()

    def _load(self):
        """加载模板（内置 + 用户自定义）"""
        self._templates = dict(BUILTIN_TEMPLATES)

        # 合并用户自定义模板
        if TEMPLATE_PATH.exists():
            try:
                custom = json.loads(TEMPLATE_PATH.read_text())
                for name, tmpl in custom.items():
                    self._templates[name] = tmpl
            except Exception:
                pass

        # 读取当前激活模板
        if ACTIVE_PATH.exists():
            try:
                active_data = json.loads(ACTIVE_PATH.read_text())
                self._active = active_data.get('active', 'balanced')
                self._applied_at = active_data.get('applied_at', '')
                self._applied_by = active_data.get('applied_by', '')
            except Exception:
                self._active = 'balanced'
        else:
            self._active = 'balanced'

    @property
    def active(self) -> str:
        return self._active or 'balanced'

    def list_templates(self) -> list:
        return [{
            'id': name,
            'name': t['name'],
            'description': t['description'],
            'market_condition': t.get('market_condition', []),
            'active': name == self.active
        } for name, t in self._templates.items()]

    def get(self, name: str = None) -> Optional[Dict]:
        """获取模板完整定义"""
        name = name or self.active
        return self._templates.get(name)

    def apply(self, name: str, applied_by: str = "manual") -> bool:
        """激活指定模板并持久化"""
        if name not in self._templates:
            print(f"❌ 模板 '{name}' 不存在。可用: {list(self._templates.keys())}")
            return False

        self._active = name
        self._applied_at = datetime.now().isoformat()
        self._applied_by = applied_by

        ACTIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        ACTIVE_PATH.write_text(json.dumps({
            'active': name,
            'applied_at': self._applied_at,
            'applied_by': self._applied_by,
            'template': self._templates[name]
        }, ensure_ascii=False, indent=2))

        print(f"✅ 策略模板已切换: {self._templates[name]['name']} ({name})")
        return True

    def get_factor_weights(self) -> Dict[str, float]:
        """获取当前激活模板的因子权重（供 stock_recommender 调用）"""
        tmpl = self.get()
        if not tmpl:
            # fallback 默认权重
            return {"event": 0.30, "fund": 0.25, "sentiment": 0.18,
                    "technical": 0.15, "research": 0.07, "new_factors": 0.05}
        return tmpl['recommender']['factor_weights']

    def get_scout_config(self) -> Dict:
        """获取侦察兵配置"""
        tmpl = self.get()
        if not tmpl:
            return {}
        return tmpl.get('scout', {})

    def get_risk_config(self) -> Dict:
        """获取风控配置"""
        tmpl = self.get()
        if not tmpl:
            return {}
        return tmpl.get('risk', {})

    def get_position_config(self) -> Dict:
        """获取仓位配置"""
        tmpl = self.get()
        if not tmpl:
            return {}
        return tmpl.get('position', {})

    def show(self, name: str = None) -> str:
        """格式化展示模板详情"""
        name = name or self.active
        tmpl = self.get(name)
        if not tmpl:
            return f"❌ 模板 '{name}' 不存在"

        fw = tmpl['recommender']['factor_weights']
        risk = tmpl['risk']
        pos = tmpl['position']
        active_mark = " ★ 当前激活" if name == self.active else ""

        lines = [
            f"## {tmpl['name']} (`{name}`){active_mark}",
            f"",
            f"> {tmpl['description']}",
            f"",
            f"**适用市场**: {', '.join(tmpl.get('market_condition', []))}",
            f"",
            f"### 因子权重",
            f"| 因子 | 权重 | 可视化 |",
            f"|------|------|--------|",
        ]
        bar_len = 20
        for fid, w in fw.items():
            bar = '█' * int(w * bar_len) + '░' * (bar_len - int(w * bar_len))
            lines.append(f"| {fid:15s} | {w:.2f} | {bar} |")

        lines.extend([
            f"",
            f"### 风控",
            f"| 参数 | 值 |",
            f"|------|-----|",
            f"| 默认止损 | {risk['default_stop_loss']:+.1f}% |",
            f"| 创业板止损 | {risk['chinext_stop_loss']:+.1f}% |",
            f"| 单票上限 | {risk['max_position_pct']:.0f}% |",
            f"| 持仓上限 | {risk['max_portfolio_stocks']}只 |",
            f"| R值目标 | {risk['r_value_target']:.1f}% |",
            f"",
            f"### 仓位",
            f"| 档位 | 比例 |",
            f"|------|------|",
            f"| 轻仓 | {pos['light']:.0%} |",
            f"| 中仓 | {pos['medium']:.0%} |",
            f"| 重仓 | {pos['heavy']:.0%} |",
            f"| 满仓 | {pos['full']:.0%} |",
        ])

        return '\n'.join(lines)


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description='策略模板参数化引擎 v1.0')
    ap.add_argument('--list', action='store_true', help='列出所有模板')
    ap.add_argument('--show', type=str, nargs='?', const='__active__', help='查看模板详情')
    ap.add_argument('--apply', type=str, help='激活指定模板')
    ap.add_argument('--json', action='store_true', help='JSON 输出')
    args = ap.parse_args()

    mgr = TemplateManager()

    if args.list:
        templates = mgr.list_templates()
        if args.json:
            print(json.dumps(templates, ensure_ascii=False, indent=2))
        else:
            print(f"{'模板ID':15s} {'名称':10s} {'状态':6s} {'描述'}")
            print(f"{'-'*15} {'-'*10} {'-'*6} {'-'*40}")
            for t in templates:
                status = '★ 激活' if t['active'] else ''
                print(f"{t['id']:15s} {t['name']:10s} {status:6s} {t['description']}")
        return

    if args.apply:
        mgr.apply(args.apply, applied_by="cli")
        return

    if args.show:
        name = None if args.show == '__active__' else args.show
        print(mgr.show(name))
        return

    # 默认：显示当前模板
    print(mgr.show())


if __name__ == '__main__':
    main()
