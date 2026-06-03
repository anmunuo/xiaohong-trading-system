#!/usr/bin/env python3
"""
algo_executor.py — 算法执行器 (TWAP/VWAP)
===========================================
基于日内分时 Volume Profile，TWAP/VWAP 拆单减少冲击成本。

用法:
  python3 algo_executor.py --twap CODE QTY --slices 10
  python3 algo_executor.py --vwap CODE QTY --hours 2
  python3 algo_executor.py --profile CODE       # 查看分时量分布
"""

import sys, os, json, math, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

_log = __import__('logging').getLogger("algo")


@dataclass
class TimeSlice:
    """时间切片"""
    time_label: str       # "09:30-09:35"
    volume_pct: float     # 历史该时段成交量占比
    price_range: Tuple[float, float] = (0, 0)  # (low, high)


@dataclass
class AlgoOrder:
    """算法订单"""
    symbol: str
    symbol_name: str = ""
    total_qty: int = 0
    algo_type: str = "TWAP"       # TWAP / VWAP
    n_slices: int = 10
    slices: List[Dict] = field(default_factory=list)
    submitted_slices: int = 0
    filled_qty: int = 0
    avg_price: float = 0.0
    status: str = "PENDING"


@dataclass
class VolumeProfile:
    """日内成交量分布"""
    symbol: str
    date: str
    slices: List[TimeSlice] = field(default_factory=list)
    total_volume: int = 0


# ═══════════════════════════════════════
# Volume Profile 构建
# ═══════════════════════════════════════

class VolumeProfileBuilder:
    """从分时K线构建成交量分布"""

    # A股交易时段（分钟）
    TRADING_SESSIONS = [
        ("09:30", "11:30"),   # 上午
        ("13:00", "15:00"),   # 下午
    ]

    # 默认30分钟切片
    DEFAULT_SLICES = [
        ("09:30-10:00", 0.12),
        ("10:00-10:30", 0.10),
        ("10:30-11:00", 0.10),
        ("11:00-11:30", 0.08),
        ("13:00-13:30", 0.10),
        ("13:30-14:00", 0.10),
        ("14:00-14:30", 0.12),
        ("14:30-15:00", 0.18),
    ]

    def __init__(self):
        self._cache: Dict[str, VolumeProfile] = {}

    def get_profile(self, code: str,
                    use_live: bool = True) -> VolumeProfile:
        """获取日内成交量分布。

        优先用历史分时K线统计，无数据时用默认分布。
        """
        if code in self._cache:
            return self._cache[code]

        profile = VolumeProfile(
            symbol=code,
            date=datetime.now().strftime('%Y-%m-%d'),
        )

        # 尝试从分时K线获取
        try:
            from data_pipeline import get_intraday_minutes
            bars = get_intraday_minutes(code, scale=5, count=48)
            if bars and len(bars) >= 20:
                profile = self._from_intraday(code, bars)
                self._cache[code] = profile
                return profile
        except Exception:
            pass

        # 回退到默认分布
        for label, pct in self.DEFAULT_SLICES:
            n_slices = len(self.DEFAULT_SLICES)
            profile.slices.append(TimeSlice(
                time_label=label,
                volume_pct=pct,
            ))

        self._cache[code] = profile
        return profile

    def _from_intraday(self, code: str,
                        bars: List[Dict]) -> VolumeProfile:
        """从分时K线数据构建分布"""
        profile = VolumeProfile(
            symbol=code,
            date=datetime.now().strftime('%Y-%m-%d'),
        )
        if not bars:
            return profile

        total_vol = sum(b.get('volume', 0) for b in bars)
        if total_vol == 0:
            return profile

        profile.total_volume = int(total_vol)

        # 按30分钟聚合
        window = 6  # 5min × 6 = 30min
        for i in range(0, len(bars), window):
            chunk = bars[i:i+window]
            if not chunk:
                continue

            vol_sum = sum(b.get('volume', 0) for b in chunk)
            prices = [b.get('close', 0) for b in chunk if b.get('close', 0) > 0]

            # 时间标签
            first_time = chunk[0].get('time', '')
            last_time = chunk[-1].get('time', '')
            label = f"{first_time}-{last_time}" if first_time and last_time else f"slice{i//window}"

            profile.slices.append(TimeSlice(
                time_label=label,
                volume_pct=round(vol_sum / total_vol, 4) if total_vol > 0 else 1/len(bars),
                price_range=(min(prices) if prices else 0, max(prices) if prices else 0),
            ))

        return profile


# ═══════════════════════════════════════
# TWAP 执行器
# ═══════════════════════════════════════

class TWAPExecutor:
    """时间加权平均价格执行"""

    def __init__(self):
        self.profile_builder = VolumeProfileBuilder()

    def plan(self, code: str, total_qty: int,
             n_slices: int = 10,
             symbol_name: str = "") -> AlgoOrder:
        """生成 TWAP 拆单计划——等时间片均分"""

        profile = self.profile_builder.get_profile(code)

        order = AlgoOrder(
            symbol=code,
            symbol_name=symbol_name,
            total_qty=total_qty,
            algo_type="TWAP",
            n_slices=n_slices,
        )

        qty_per_slice = total_qty // n_slices
        remainder = total_qty % n_slices

        # 每个时间片等量
        for i in range(n_slices):
            qty = qty_per_slice + (1 if i < remainder else 0)
            if qty <= 0:
                continue

            time_slot = (profile.slices[i % len(profile.slices)]
                         if profile.slices else None)
            label = time_slot.time_label if time_slot else f"slice_{i+1}"

            order.slices.append({
                'index': i,
                'time': label,
                'quantity': qty,
                'type': 'TWAP',
                'pct': round(qty / total_qty * 100, 1),
            })

        return order

    def estimate_impact(self, code: str, total_qty: int,
                         avg_daily_volume: int = None) -> Dict:
        """
        估算冲击成本。

        Almgren-Chriss 简化版:
          冲击 ≈ σ × (Q/V)^γ × spread_factor
        """
        # 获取波动率
        try:
            from data_pipeline import get_historical_k_with_ma
            bs = get_historical_k_with_ma([code], days=20)
            bars = bs.get(code, [])
            if bars and len(bars) >= 10:
                closes = [b['close'] for b in bars]
                rets = [(closes[i]-closes[i-1])/closes[i-1] for i in range(1,len(closes))]
                sigma = float(np.std(rets)) if rets else 0.02
            else:
                sigma = 0.02
        except Exception:
            sigma = 0.02

        # 日均成交量
        if not avg_daily_volume:
            try:
                from data_pipeline import get_stock_realtime
                rt = get_stock_realtime([code])
                avg_daily_volume = rt.get(code, {}).get('volume', 1000000)
            except Exception:
                avg_daily_volume = 1000000

        participation = total_qty / max(avg_daily_volume, 1)

        # 冲击估算 (bps)
        impact_bps = sigma * (participation ** 0.5) * 10000
        impact_bps = min(impact_bps, 50)  # 上限 50 bps

        return {
            'sigma': round(sigma * 100, 2),
            'participation_rate': round(participation * 100, 2),
            'estimated_impact_bps': round(impact_bps, 1),
            'estimated_cost': round(total_qty * impact_bps / 10000, 2),
            'twap_reduction': round(impact_bps * 0.3, 1),  # TWAP 约减 30%
        }


# ═══════════════════════════════════════
# VWAP 执行器
# ═══════════════════════════════════════

class VWAPExecutor:
    """成交量加权平均价格执行"""

    def __init__(self):
        self.profile_builder = VolumeProfileBuilder()

    def plan(self, code: str, total_qty: int,
             symbol_name: str = "") -> AlgoOrder:
        """生成 VWAP 拆单计划——按历史成交量分布加权"""

        profile = self.profile_builder.get_profile(code)

        order = AlgoOrder(
            symbol=code,
            symbol_name=symbol_name,
            total_qty=total_qty,
            algo_type="VWAP",
            n_slices=len(profile.slices),
        )

        remaining = total_qty
        for i, ts in enumerate(profile.slices):
            if i == len(profile.slices) - 1:
                qty = remaining  # 最后一片兜底
            else:
                qty = int(total_qty * ts.volume_pct)
                qty = max(qty, 100)  # 最少 1 手
                qty = (qty // 100) * 100

            if qty <= 0:
                continue
            remaining -= qty

            order.slices.append({
                'index': i,
                'time': ts.time_label,
                'quantity': qty,
                'volume_pct': round(ts.volume_pct * 100, 1),
                'type': 'VWAP',
                'price_range': ts.price_range,
            })

        return order

    def estimate_impact(self, code: str, total_qty: int,
                         avg_daily_volume: int = None) -> Dict:
        """VWAP 冲击估算（比 TWAP 约多减 10-20%）"""
        twap = TWAPExecutor()
        twap_impact = twap.estimate_impact(code, total_qty, avg_daily_volume)
        twap_impact['vwap_reduction'] = round(
            twap_impact['estimated_impact_bps'] * 0.45, 1)  # VWAP约减45%
        twap_impact['algo'] = 'VWAP'
        return twap_impact


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--twap', nargs=2, metavar=('CODE', 'QTY'), help='TWAP拆单计划')
    ap.add_argument('--vwap', nargs=2, metavar=('CODE', 'QTY'), help='VWAP拆单计划')
    ap.add_argument('--slices', type=int, default=10, help='TWAP切片数')
    ap.add_argument('--impact', type=str, metavar='CODE', help='估算冲击成本')
    ap.add_argument('--profile', type=str, metavar='CODE', help='查看分时量分布')
    args = ap.parse_args()

    if args.twap:
        code, qty_str = args.twap
        code = code.zfill(6)
        qty = int(float(qty_str))

        twap = TWAPExecutor()
        order = twap.plan(code, qty, args.slices)
        impact = twap.estimate_impact(code, qty)

        print(f'\n📊 TWAP 拆单计划: {code}')
        print(f'   总数量: {qty} 股 | 切片: {args.slices}')
        print(f'   预计冲击: {impact["estimated_impact_bps"]} bps')
        print(f'   TWAP可减: {impact["twap_reduction"]} bps')
        print(f'\n   {"时间":<16s} {"数量":>8s}  {"占比":>6s}')
        print(f'   {"─"*34}')
        for s in order.slices:
            print(f'   {s["time"]:<16s} {s["quantity"]:>8d}  {s["pct"]:>5.1f}%')

    elif args.vwap:
        code, qty_str = args.vwap
        code = code.zfill(6)
        qty = int(float(qty_str))

        vwap = VWAPExecutor()
        order = vwap.plan(code, qty)
        impact = vwap.estimate_impact(code, qty)

        print(f'\n📊 VWAP 拆单计划: {code}')
        print(f'   总数量: {qty} 股 | 切片: {len(order.slices)} (基于历史量分布)')
        print(f'   预计冲击: {impact["estimated_impact_bps"]} bps')
        print(f'   VWAP可减: {impact.get("vwap_reduction", 0)} bps')
        print(f'\n   {"时间":<16s} {"数量":>8s}  {"量占比":>7s}')
        print(f'   {"─"*35}')
        for s in order.slices:
            print(f'   {s["time"]:<16s} {s["quantity"]:>8d}  {s.get("volume_pct",0):>6.1f}%')

    elif args.impact:
        code = args.impact.zfill(6)
        twap = TWAPExecutor()
        # 默认估算100手
        impact = twap.estimate_impact(code, 10000)
        print(f'\n📊 冲击成本估算: {code}')
        print(f'   波动率: {impact["sigma"]}%')
        print(f'   参与率: {impact["participation_rate"]}%')
        print(f'   预计冲击: {impact["estimated_impact_bps"]} bps')
        print(f'   TWAP减:  {impact["twap_reduction"]} bps')
        print(f'   VWAP减:  ~{round(impact["estimated_impact_bps"]*0.45,1)} bps')

    elif args.profile:
        code = args.profile.zfill(6)
        builder = VolumeProfileBuilder()
        profile = builder.get_profile(code)
        print(f'\n📊 分时量分布: {code} ({profile.date})')
        print(f'   总成交量: {profile.total_volume:,}')
        print(f'\n   {"时段":<16s} {"量占比":>7s}  {"价格区间":>12s}')
        print(f'   {"─"*38}')
        for ts in profile.slices:
            price_range = f'{ts.price_range[0]:.2f}-{ts.price_range[1]:.2f}' if ts.price_range[0] > 0 else 'N/A'
            print(f'   {ts.time_label:<16s} {ts.volume_pct*100:>6.1f}%  {price_range:>12s}')

    else:
        ap.print_help()


if __name__ == '__main__':
    main()
