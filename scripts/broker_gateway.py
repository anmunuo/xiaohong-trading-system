#!/usr/bin/env python3
"""
broker_gateway.py — 券商统一网关
================================
paper → live 最小闭环。优先 xtquant，easytrader 备用。

用法:
  python3 broker_gateway.py --status       # 查看连接状态
  python3 broker_gateway.py --buy CODE AMOUNT  # 下单
  python3 broker_gateway.py --sell CODE       # 卖出

架构:
  Signal → BrokerGateway.validate() → RiskManager → BrokerGateway.execute()
"""

import sys, os, json, time
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
import logging

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

_log = logging.getLogger("broker")


class BrokerType(Enum):
    PAPER = "paper"
    XTQUANT = "xtquant"
    EASYTRADER = "easytrader"
    MOCK = "mock"


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class Order:
    order_id: str
    symbol: str
    symbol_name: str = ""
    side: OrderSide = OrderSide.BUY
    price: float = 0.0
    quantity: int = 0
    filled_qty: int = 0
    status: OrderStatus = OrderStatus.PENDING
    submitted_at: str = ""
    filled_at: str = ""
    reject_reason: str = ""
    is_paper: bool = True

    def __post_init__(self):
        if not self.submitted_at:
            self.submitted_at = datetime.now().isoformat()


@dataclass
class AccountInfo:
    broker_type: BrokerType
    total_assets: float = 0.0
    available_cash: float = 0.0
    frozen_cash: float = 0.0
    total_value: float = 0.0
    positions: List[Dict] = field(default_factory=list)
    connected: bool = False

    @property
    def pnl(self) -> float:
        return self.total_value - 100000  # vs initial


# ═══════════════════════════════════════
# 抽象网关
# ═══════════════════════════════════════

class BrokerGateway:
    """券商统一网关"""

    def __init__(self, broker_type: BrokerType = BrokerType.PAPER):
        self.broker_type = broker_type
        self.connected = False
        self._client = None

    def connect(self) -> bool:
        """连接券商"""
        if self.broker_type == BrokerType.PAPER:
            self.connected = True
            _log.info("📝 Paper 模式已就绪")
            return True

        if self.broker_type == BrokerType.XTQUANT:
            return self._connect_xtquant()

        if self.broker_type == BrokerType.EASYTRADER:
            return self._connect_easytrader()

        _log.warning(f"未知券商类型: {self.broker_type}")
        return False

    def _connect_xtquant(self) -> bool:
        """连接 xtquant mini"""
        try:
            from xtquant import xtdata
            xtdata.connect()
            self._client = xtdata
            self.connected = True
            _log.info("✅ xtquant 连接成功")
            return True
        except ImportError:
            _log.warning("⚠️ xtquant 未安装，使用 paper 模式")
            _log.warning("   安装: pip install xtquant 或从 https://dict.thinktrader.net 下载")
            self.broker_type = BrokerType.PAPER
            self.connected = True
            return True
        except Exception as e:
            _log.error(f"❌ xtquant 连接失败: {e}")
            return False

    def _connect_easytrader(self) -> bool:
        """连接 easytrader"""
        try:
            import easytrader
            # 尝试自动检测券商
            user = easytrader.use('universal')
            user.prepare('ht.json')  # 华泰配置
            self._client = user
            self.connected = True
            _log.info("✅ easytrader 连接成功")
            return True
        except ImportError:
            _log.warning("⚠️ easytrader 未安装: pip install easytrader")
            return False
        except Exception as e:
            _log.error(f"❌ easytrader 连接失败: {e}")
            return False

    def disconnect(self):
        self.connected = False
        self._client = None

    def get_account(self) -> AccountInfo:
        """获取账户信息"""
        info = AccountInfo(broker_type=self.broker_type, connected=self.connected)

        if self.broker_type == BrokerType.PAPER:
            # 读 holdings.json
            h_path = SCRIPT_DIR.parent / 'data' / 'holdings.json'
            if h_path.exists():
                data = json.loads(h_path.read_text())
                acct = data.get('accountInfo', {})
                info.total_assets = acct.get('currentNetValue', 100000)
                info.available_cash = acct.get('availableCash', 100000)
                info.total_value = acct.get('currentNetValue', 100000)
                info.positions = data.get('holdings', [])
            else:
                info.total_assets = 100000
                info.available_cash = 100000
                info.total_value = 100000
            return info

        if self.broker_type == BrokerType.XTQUANT and self._client:
            try:
                acct = self._client.get_account_info()
                if acct:
                    info.total_assets = float(acct.get('总资产', 0))
                    info.available_cash = float(acct.get('可用资金', 0))
                    info.frozen_cash = float(acct.get('冻结资金', 0))
                    info.total_value = float(acct.get('总市值', 0))
                    info.positions = acct.get('持仓', [])
            except Exception as e:
                _log.error(f"获取账户失败: {e}")

        return info

    def submit_order(self, symbol: str, side: OrderSide, price: float,
                     quantity: int, symbol_name: str = "",
                     strategy_id: str = "") -> Order:
        """提交订单"""
        order_id = f"{datetime.now().strftime('%Y%m%d%H%M%S')}-{symbol}"

        order = Order(
            order_id=order_id,
            symbol=symbol,
            symbol_name=symbol_name,
            side=side,
            price=price,
            quantity=quantity,
            is_paper=(self.broker_type == BrokerType.PAPER),
        )

        if self.broker_type == BrokerType.PAPER:
            # 模拟成交
            order.status = OrderStatus.FILLED
            order.filled_qty = quantity
            order.filled_at = datetime.now().isoformat()
            _log.info(f"📝 PAPER {side.value}: {symbol_name}({symbol}) "
                      f"{quantity}股 @ ¥{price:.2f}")
            return order

        if self.broker_type == BrokerType.XTQUANT and self._client:
            try:
                # xtquant 下单
                action = 23 if side == OrderSide.BUY else 24  # 买入/卖出
                result = self._client.order_stock(
                    stock_code=f"{symbol}.{'SZ' if symbol.startswith(('0','3')) else 'SH'}",
                    order_type=action,
                    order_volume=quantity,
                    price_type=11,  # 限价
                    price=price,
                )
                if result and result.get('order_id'):
                    order.order_id = str(result['order_id'])
                    order.status = OrderStatus.SUBMITTED
                    _log.info(f"✅ 实盘 {side.value}: {symbol} {quantity}股 @ ¥{price:.2f}")
                else:
                    order.status = OrderStatus.REJECTED
                    order.reject_reason = str(result)
            except Exception as e:
                order.status = OrderStatus.REJECTED
                order.reject_reason = str(e)
                _log.error(f"❌ 下单失败: {e}")

        return order

    def cancel_order(self, order_id: str) -> bool:
        """撤单"""
        if self.broker_type == BrokerType.PAPER:
            return True
        if self.broker_type == BrokerType.XTQUANT and self._client:
            try:
                self._client.cancel_order(order_id)
                return True
            except Exception:
                return False
        return False

    def get_positions(self) -> List[Dict]:
        """获取持仓"""
        acct = self.get_account()
        return acct.positions

    def status_report(self) -> str:
        """状态报告"""
        acct = self.get_account()
        lines = [
            f"券商: {self.broker_type.value}",
            f"连接: {'✅' if self.connected else '❌'}",
            f"总资产: ¥{acct.total_assets:,.0f}",
            f"可用:   ¥{acct.available_cash:,.0f}",
            f"持仓:   {len(acct.positions)}只",
            f"浮动:   ¥{acct.pnl:+,.0f}",
        ]
        return '\n'.join(lines)


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--status', action='store_true', help='查看状态')
    ap.add_argument('--buy', nargs=2, metavar=('CODE', 'AMOUNT'), help='买入')
    ap.add_argument('--sell', type=str, metavar='CODE', help='卖出')
    ap.add_argument('--paper', action='store_true', default=True, help='Paper模式(默认)')
    ap.add_argument('--live', action='store_true', help='实盘模式')
    args = ap.parse_args()

    broker_type = BrokerType.PAPER
    if args.live:
        broker_type = BrokerType.XTQUANT

    gw = BrokerGateway(broker_type)
    gw.connect()

    if args.status:
        print(gw.status_report())

    elif args.buy:
        code, amount = args.buy
        from data_pipeline import get_stock_realtime
        rt = get_stock_realtime([code.zfill(6)])
        info = rt.get(code.zfill(6), {})
        price = info.get('close', 0)
        name = info.get('name', '')
        qty = int(float(amount) / price / 100) * 100 if price > 0 else 0
        if qty > 0:
            order = gw.submit_order(code, OrderSide.BUY, price, qty, name)
            print(f"订单: {order.order_id} | {order.status.value} | "
                  f"{order.symbol_name} {order.quantity}股 @ ¥{order.price:.2f}")

    elif args.sell:
        code = args.sell
        from data_pipeline import get_stock_realtime
        rt = get_stock_realtime([code.zfill(6)])
        info = rt.get(code.zfill(6), {})
        price = info.get('close', 0)
        name = info.get('name', '')
        # 查持仓数量
        positions = gw.get_positions()
        qty = 0
        for p in positions:
            if str(p.get('code', '')) == code:
                qty = p.get('quantity', 0)
                break
        if qty > 0:
            order = gw.submit_order(code, OrderSide.SELL, price, qty, name)
            print(f"订单: {order.order_id} | {order.status.value} | "
                  f"{order.symbol_name} {order.quantity}股 @ ¥{order.price:.2f}")

    else:
        ap.print_help()


if __name__ == '__main__':
    main()
