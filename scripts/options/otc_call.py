#!/usr/bin/env python3
"""
场外个股看涨分成期权 — 结构定义 + 盈亏计算引擎

产品规则：
  保证金   ¥100,000      风险资金，亏损先扣保证金
  期权费   ¥8,000        固定通道成本（开仓即扣，不可退）
  名义本金 ¥1,000,000    对应股票市值敞口
  收益分成  个人 70% : 券商 30%（仅上涨时）
  下跌承担  个人 100%（亏损从保证金扣除）
  强平线    保证金剩余 ≤ 20%（即亏损 ≥ ¥80,000）

用法：
  from options.otc_call import OTCCallEngine
  engine = OTCCallEngine()
  pos = engine.open_position(code='000001', name='平安银行', entry_price=12.50)
  pnl = engine.calc_pnl(pos, current_price=13.00)
  alert = engine.check_margin(pos, current_price=10.50)
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, Dict, Tuple
import json
import os

# ═══════════════════════════════════════════════════════════════
# 产品参数（可通过进化引擎调整）
# ═══════════════════════════════════════════════════════════════

@dataclass
class OTCParams:
    """场外看涨分成期权产品参数 — 可以被进化引擎 patch"""
    margin: float = 100_000.0          # 保证金
    option_fee: float = 8_000.0        # 期权费
    notional: float = 1_000_000.0      # 名义本金
    split_personal: float = 0.70       # 个人分成比例
    split_broker: float = 0.30         # 券商分成比例
    liq_threshold: float = 0.20        # 强平线（保证金剩余比例）
    warn_threshold: float = 0.40       # 预警线（保证金剩余比例）


# ═══════════════════════════════════════════════════════════════
# 期权持仓数据模型
# ═══════════════════════════════════════════════════════════════

@dataclass
class OTCPosition:
    """单笔场外看涨期权持仓"""
    position_id: str                   # 唯一持仓 ID
    code: str                          # 股票代码
    name: str                          # 股票名称
    entry_price: float                 # 开仓时标的股价
    notional: float                    # 名义本金
    margin: float                      # 保证金
    option_fee: float                  # 期权费
    split_personal: float              # 分成比例
    split_broker: float                # 券商分成
    entry_date: str                    # 开仓日期 ISO
    status: str = "active"             # active / closed / liquidated
    close_price: Optional[float] = None  # 平仓价
    close_date: Optional[str] = None   # 平仓日期
    realized_pnl: float = 0.0          # 已实现盈亏
    notes: str = ""                    # 备注

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════
# 盈亏计算引擎
# ═══════════════════════════════════════════════════════════════

class OTCCallEngine:
    """场外看涨分成期权引擎"""

    def __init__(self, params: OTCParams = None,
                 data_dir: str = None):
        self.params = params or OTCParams()
        if data_dir is None:
            data_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                '..', 'data', 'options'
            )
        self.data_dir = os.path.abspath(data_dir)
        os.makedirs(self.data_dir, exist_ok=True)
        self._positions: Dict[str, OTCPosition] = {}
        self._load_positions()

    # ── 开仓 ──────────────────────────────────────────

    def open_position(
        self,
        code: str,
        name: str,
        entry_price: float,
        margin: float = None,
        option_fee: float = None,
        notional: float = None,
    ) -> OTCPosition:
        """开立场外看涨期权仓位"""
        margin = margin or self.params.margin
        option_fee = option_fee or self.params.option_fee
        notional = notional or self.params.notional

        pid = self._gen_position_id(code)
        pos = OTCPosition(
            position_id=pid,
            code=code,
            name=name,
            entry_price=entry_price,
            notional=notional,
            margin=margin,
            option_fee=option_fee,
            split_personal=self.params.split_personal,
            split_broker=self.params.split_broker,
            entry_date=datetime.now().isoformat(),
            status="active",
        )
        self._positions[pid] = pos
        self._save_positions()
        return pos

    # ── 盈亏计算 ──────────────────────────────────────

    def calc_pnl(
        self, pos: OTCPosition, current_price: float
    ) -> dict:
        """
        计算持仓盈亏（含分成逻辑）

        返回:
          {
            'change_pct': 标的涨跌幅,
            'gross_pnl': 毛盈亏（基于名义本金）,
            'margin_consumed': 已消耗保证金,
            'margin_remaining': 剩余保证金,
            'margin_health': 保证金健康度 (0~1),
            'personal_pnl': 个人净盈亏（扣期权费后）,
            'broker_pnl': 券商分成,
            'unrealized_pnl': 浮动盈亏,
            'in_profit': 是否盈利,
          }
        """
        p = self.params
        change_pct = (current_price - pos.entry_price) / pos.entry_price
        gross_pnl = change_pct * pos.notional

        if gross_pnl >= 0:
            # ═══ 上涨：分成 ═══
            total_profit = gross_pnl - pos.option_fee  # 先扣期权费
            if total_profit > 0:
                personal_pnl = total_profit * pos.split_personal
                broker_pnl = total_profit * pos.split_broker
            else:
                # 涨幅不够覆盖期权费 → 个人承担全部
                personal_pnl = total_profit
                broker_pnl = 0.0

            margin_consumed = 0.0
            margin_remaining = pos.margin
            margin_health = 1.0
            in_profit = gross_pnl > pos.option_fee

        else:
            # ═══ 下跌：从保证金扣 ═══
            margin_consumed = min(abs(gross_pnl), pos.margin)
            margin_remaining = max(pos.margin - margin_consumed, 0.0)
            margin_health = margin_remaining / pos.margin
            personal_pnl = -margin_consumed - pos.option_fee
            broker_pnl = 0.0
            in_profit = False

        return {
            'change_pct': round(change_pct * 100, 2),
            'gross_pnl': round(gross_pnl, 2),
            'margin_consumed': round(margin_consumed, 2),
            'margin_remaining': round(margin_remaining, 2),
            'margin_health': round(margin_health, 4),
            'personal_pnl': round(personal_pnl, 2),
            'broker_pnl': round(broker_pnl, 2),
            'unrealized_pnl': round(personal_pnl, 2),
            'in_profit': in_profit,
        }

    # ── 保证金检查 ────────────────────────────────────

    def check_margin(
        self, pos: OTCPosition, current_price: float
    ) -> dict:
        """
        保证金健康检查 → 返回告警级别

        返回:
          {
            'status': 'ok' | 'warning' | 'danger' | 'liquidate',
            'level': 0~3,
            'message': 人读信息,
            'action': 建议操作,
            ...calc_pnl 的所有字段
          }
        """
        pnl = self.calc_pnl(pos, current_price)
        health = pnl['margin_health']

        if health <= self.params.liq_threshold:
            status, level = 'liquidate', 3
            msg = f"🔴 强平警告"
            action = "立即平仓 — 保证金仅剩 {:.0f}%".format(health * 100)
        elif health <= self.params.warn_threshold:
            status, level = 'danger', 2
            msg = f"🟠 危险预警"
            action = "需补充保证金或减仓"
        elif health <= 0.60:
            status, level = 'warning', 1
            msg = f"🟡 关注"
            action = f"保证金消耗 {int((1-health)*100)}%，密切监控"
        else:
            status, level = 'ok', 0
            msg = "✅ 保证金安全"
            action = ""

        return {
            **pnl,
            'status': status,
            'level': level,
            'message': msg,
            'action': action,
        }

    # ── 平仓 ──────────────────────────────────────────

    def close_position(
        self, pos: OTCPosition, close_price: float
    ) -> dict:
        """平仓 — 计算最终盈亏"""
        pnl = self.calc_pnl(pos, close_price)
        pos.status = "closed"
        pos.close_price = close_price
        pos.close_date = datetime.now().isoformat()
        pos.realized_pnl = pnl['personal_pnl']
        self._save_positions()
        return {
            **pnl,
            'realized_pnl': pos.realized_pnl,
            'position_id': pos.position_id,
        }

    # ── 强平 ──────────────────────────────────────────

    def liquidate(self, pos: OTCPosition, close_price: float) -> dict:
        """强制平仓"""
        pnl = self.calc_pnl(pos, close_price)
        pos.status = "liquidated"
        pos.close_price = close_price
        pos.close_date = datetime.now().isoformat()
        # 保证金归零
        actual_loss = pnl['margin_consumed'] + pos.option_fee
        pos.realized_pnl = -actual_loss
        self._save_positions()
        return {
            **pnl,
            'status': 'liquidated',
            'realized_pnl': pos.realized_pnl,
            'position_id': pos.position_id,
            'message': f"🔴 强制平仓 — 保证金耗尽，净亏 ¥{actual_loss:,.0f}",
        }

    # ── 组合视图 ──────────────────────────────────────

    def get_portfolio_summary(self, current_prices: dict) -> dict:
        """
        全持仓汇总 {code: current_price}

        返回:
          {
            'positions': [pos_dicts...],
            'total_margin': 总保证金,
            'total_margin_consumed': 已消耗,
            'total_margin_remaining': 剩余,
            'total_unrealized_pnl': 总浮动盈亏,
            'liq_risk_count': 强平风险持仓数,
            'alert_level': 最高告警级别,
          }
        """
        active = [p for p in self._positions.values() if p.status == "active"]
        if not active:
            return {
                'positions': [],
                'total_margin': 0,
                'total_margin_consumed': 0,
                'total_margin_remaining': 0,
                'total_unrealized_pnl': 0,
                'liq_risk_count': 0,
                'alert_level': 0,
            }

        results = []
        total_margin = 0
        total_consumed = 0
        total_remaining = 0
        total_upnl = 0
        liq_count = 0
        max_level = 0

        for pos in active:
            price = current_prices.get(pos.code)
            if price is None:
                continue
            check = self.check_margin(pos, price)
            check['name'] = pos.name
            check['code'] = pos.code
            check['position_id'] = pos.position_id
            results.append(check)

            total_margin += pos.margin
            total_consumed += check['margin_consumed']
            total_remaining += check['margin_remaining']
            total_upnl += check['unrealized_pnl']
            if check['level'] >= 3:
                liq_count += 1
            max_level = max(max_level, check['level'])

        return {
            'positions': results,
            'total_margin': round(total_margin, 2),
            'total_margin_consumed': round(total_consumed, 2),
            'total_margin_remaining': round(total_remaining, 2),
            'total_unrealized_pnl': round(total_upnl, 2),
            'liq_risk_count': liq_count,
            'alert_level': max_level,
        }

    # ── 持仓持久化 ────────────────────────────────────

    def _gen_position_id(self, code: str) -> str:
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"OTC-{code}-{ts}"

    def _positions_path(self) -> str:
        return os.path.join(self.data_dir, "otc_positions.json")

    def _save_positions(self):
        data = {
            pid: pos.to_dict()
            for pid, pos in self._positions.items()
        }
        with open(self._positions_path(), "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_positions(self):
        path = self._positions_path()
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                data = json.load(f)
            for pid, d in data.items():
                self._positions[pid] = OTCPosition(**d)
        except Exception as e:
            print(f"[OTC] 加载持仓失败: {e}")

    def get_active_positions(self) -> list:
        return [p for p in self._positions.values() if p.status == "active"]


# ═══════════════════════════════════════════════════════════════
# 自测
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    engine = OTCCallEngine()

    # ── 场景1：上涨盈利 ──
    print("═══ 场景1：股价上涨 15% ═══")
    pos1 = engine.open_position("000001", "平安银行", entry_price=12.00)
    pnl1 = engine.calc_pnl(pos1, current_price=13.80)  # +15%
    for k, v in pnl1.items():
        print(f"  {k}: {v}")
    close1 = engine.close_position(pos1, 13.80)
    print(f"  最终盈亏: ¥{close1['realized_pnl']:,.0f}\n")

    # ── 场景2：小幅下跌 ──
    print("═══ 场景2：股价下跌 5% ═══")
    pos2 = engine.open_position("000001", "平安银行", entry_price=12.00)
    pnl2 = engine.calc_pnl(pos2, current_price=11.40)  # -5%
    for k, v in pnl2.items():
        print(f"  {k}: {v}")
    check2 = engine.check_margin(pos2, 11.40)
    print(f"  告警: {check2['message']} | {check2['action']}\n")

    # ── 场景3：深度下跌 → 强平 ──
    print("═══ 场景3：股价下跌 9% → 强平 ═══")
    pos3 = engine.open_position("000001", "平安银行", entry_price=12.00)
    pnl3 = engine.calc_pnl(pos3, current_price=10.92)  # -9%
    for k, v in pnl3.items():
        print(f"  {k}: {v}")
    check3 = engine.check_margin(pos3, 10.92)
    print(f"  告警: {check3['message']} | {check3['action']}")
    liq = engine.liquidate(pos3, 10.92)
    print(f"  强平: {liq['message']}\n")

    # ── 场景4：微涨不够覆盖期权费 ──
    print("═══ 场景4：股价微涨 0.5%（不够覆盖期权费） ═══")
    pos4 = engine.open_position("000001", "平安银行", entry_price=12.00)
    pnl4 = engine.calc_pnl(pos4, current_price=12.06)  # +0.5%
    for k, v in pnl4.items():
        print(f"  {k}: {v}")
    print(f"  盈利? {pnl4['in_profit']}（涨幅收益 ¥600 < 期权费 ¥8000）")

    # 清理测试数据
    import os as _os
    _os.remove(engine._positions_path())
