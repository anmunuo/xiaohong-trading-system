#!/usr/bin/env python3
"""
stock_tracker.py — 股票持续跟踪系统 v1.0
========================================
跟踪推荐池中每只股票的后续走势，记录每日快照，检测止损失效/到期退场。

数据模型:
  tracked_pool.json
  ├── pools: [{date, stock_count, stocks:[code]}]
  └── stocks: [{code, name, entry_date, entry_close, ...,
                snapshots: [{date, close, vs_entry_pct, volume}],
                exit: {date, close, return_pct, reason},
                status: active|stopped_out|expired}]

用法:
  python3 stock_tracker.py --add-pool       # 从 daily_pool.json 同步新增
  python3 stock_tracker.py --snapshot       # 更新所有活跃股今日快照
  python3 stock_tracker.py --stats          # 输出跟踪统计
  python3 stock_tracker.py --add-pool --snapshot  # 一键新增+快照
"""

import json, os, sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR / "data"
TRACKED_PATH = DATA_DIR / "tracked_pool.json"
POOL_PATH = SCRIPT_DIR / "data" / "daily_pool.json"
TRACK_DAYS = 60  # 跟踪天数上限
STOP_LOSS_THRESHOLD = -7.0  # 默认止损线（%）
ARCHIVE_DIR = DATA_DIR / "tracked_archive"


def _now() -> str:
    return datetime.now().strftime('%Y-%m-%d')

def _date_str() -> str:
    return datetime.now().strftime('%Y%m%d')


class StockTracker:
    """股票跟踪器"""

    def __init__(self):
        self.data = {"pools": [], "stocks": []}
        self._load()

    def _load(self):
        if TRACKED_PATH.exists():
            try:
                with open(TRACKED_PATH) as f:
                    self.data = json.load(f)
            except Exception:
                self.data = {"pools": [], "stocks": []}
        # 确保数据结构
        if "pools" not in self.data:
            self.data["pools"] = []
        if "stocks" not in self.data:
            self.data["stocks"] = []

    def _save(self):
        TRACKED_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TRACKED_PATH, 'w') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)

    def _find_stock(self, code: str) -> Optional[Dict]:
        for s in self.data["stocks"]:
            if s["code"] == code:
                return s
        return None

    def _is_already_tracking(self, code: str) -> bool:
        """同一代码3个月内不重复追踪"""
        s = self._find_stock(code)
        if not s:
            return False
        if s.get("status") == "active":
            return True
        # 已退场的，检查是否在3个月内
        exit_date = s.get("exit", {}).get("date", "")
        if exit_date:
            try:
                exit_dt = datetime.strptime(exit_date, "%Y-%m-%d")
                if (datetime.now() - exit_dt).days < 90:
                    return True
            except Exception:
                pass
        return False

    # ── P0: 新增追踪 ──

    def add_pool(self, pool_date: str = None, recommendations: List[Dict] = None):
        """从 daily_pool.json 同步新增标的到跟踪池"""
        if recommendations is None:
            if not POOL_PATH.exists():
                print(f"⚠️ daily_pool.json 不存在，跳过")
                return
            try:
                with open(POOL_PATH) as f:
                    pool = json.load(f)
                recommendations = pool.get("recommendations", [])
                pool_date = pool.get("date", _date_str())
            except Exception as e:
                print(f"⚠️ 读取 daily_pool.json 失败: {e}")
                return

        if not recommendations:
            print("⚠️ 推荐池为空，无新增")
            return

        today_str = pool_date or _date_str()
        added = 0
        skipped = 0
        pool_entry = {"date": today_str, "stock_count": 0, "stocks": []}

        for rec in recommendations:
            code = str(rec.get("code", ""))
            if not code:
                continue

            if self._is_already_tracking(code):
                skipped += 1
                continue

            # 获取收盘价
            close = self._get_close(code, rec)

            stop_loss = rec.get("stop_loss", {})
            stop_price = stop_loss.get("price", round(close * 0.95, 2))

            stock = {
                "code": code,
                "name": str(rec.get("name", "")),
                "entry_date": today_str,
                "entry_close": close,
                "entry_score": rec.get("total_score", 0),
                "entry_factors": rec.get("factor_scores", {}),
                "entry_sector": rec.get("sector", ""),
                "stop_loss_price": stop_price,
                "target_period": TRACK_DAYS,
                "status": "active",
                "snapshots": [{
                    "date": today_str,
                    "close": close,
                    "change_pct": 0,
                    "vs_entry_pct": 0,
                    "volume": 0,
                }],
                "exit": {},
            }
            self.data["stocks"].append(stock)
            pool_entry["stocks"].append(code)
            added += 1

        pool_entry["stock_count"] = added
        if added > 0:
            self.data["pools"].append(pool_entry)
            self._save()
            print(f"✅ 新增追踪 {added} 只（跳过 {skipped} 只已在追踪中）")
        else:
            print(f"⚠️ 无新增（{skipped} 只已在追踪中）")

    def _get_close(self, code: str, rec: Dict) -> float:
        """获取收盘价：优先行情缓存，其次推荐数据"""
        try:
            from data_pipeline import get_stock_realtime
            rt = get_stock_realtime([code])
            if code in rt:
                close = float(rt[code].get("close", 0))
                if close > 0:
                    return round(close, 2)
        except Exception:
            pass
        return 0.0

    # ── P2: 每日快照 ──

    def update_snapshots(self):
        """更新所有活跃股的最新行情快照，检测退场"""
        active = [s for s in self.data["stocks"] if s.get("status") == "active"]
        if not active:
            print("⚠️ 无活跃追踪标的")
            return

        # 批量拉取行情
        codes = [s["code"] for s in active]
        quotes = {}
        try:
            from data_pipeline import get_stock_realtime
            quotes = get_stock_realtime(codes)
        except Exception as e:
            print(f"⚠️ 行情拉取失败: {e}")
            return

        today = _now()
        updated = 0
        stopped = 0
        expired = 0

        for s in active:
            code = s["code"]
            q = quotes.get(code, {})
            close = float(q.get("close", 0))
            if close <= 0:
                # 停牌或无数据，沿用上次收盘价
                if s["snapshots"]:
                    close = s["snapshots"][-1].get("close", s["entry_close"])
                else:
                    close = s["entry_close"]

            # 跳过同一天重复快照
            if s["snapshots"] and s["snapshots"][-1].get("date") == today:
                continue

            if s["entry_close"] <= 0:
                vs_entry = 0  # entry_close 缺失，无法计算相对收益率
            else:
                vs_entry = round((close - s["entry_close"]) / s["entry_close"] * 100, 2)
            change_pct = 0
            if len(s["snapshots"]) >= 1:
                prev_close = s["snapshots"][-1].get("close", close)
                if prev_close > 0:
                    change_pct = round((close - prev_close) / prev_close * 100, 2)

            snap = {
                "date": today,
                "close": close,
                "change_pct": change_pct,
                "vs_entry_pct": vs_entry,
                "volume": float(q.get("volume", 0)),
            }
            s["snapshots"].append(snap)
            updated += 1

            # 检测止损失效
            stop_price = s.get("stop_loss_price") or 0
            if stop_price is not None and stop_price > 0 and close <= stop_price and close > 0:
                s["status"] = "stopped_out"
                s["exit"] = {
                    "date": today,
                    "close": close,
                    "return_pct": vs_entry,
                    "reason": f"触发止损价 {stop_price}（收盘 {close}）",
                }
                stopped += 1
                continue

            # 检测到期
            days_tracked = len(s["snapshots"])
            if days_tracked >= s.get("target_period", TRACK_DAYS):
                s["status"] = "expired"
                s["exit"] = {
                    "date": today,
                    "close": close,
                    "return_pct": vs_entry,
                    "reason": f"跟踪期满 ({days_tracked}天)",
                }
                expired += 1

        self._save()
        print(f"✅ 快照更新: {updated} 只 | 止损失效: {stopped} | 到期: {expired} | 活跃: {updated - stopped - expired}")

    # ── 统计 ──

    def stats(self) -> Dict:
        """返回跟踪统计"""
        all_stocks = self.data["stocks"]
        active = [s for s in all_stocks if s["status"] == "active"]
        stopped = [s for s in all_stocks if s["status"] == "stopped_out"]
        expired = [s for s in all_stocks if s["status"] == "expired"]

        def _avg_return(stocks):
            if not stocks:
                return 0
            returns = [s.get("exit", {}).get("return_pct", 0) or
                       (s["snapshots"][-1]["vs_entry_pct"] if s["snapshots"] else 0)
                       for s in stocks]
            return round(sum(returns) / len(returns), 2)

        def _win_rate(stocks):
            if not stocks:
                return 0
            wins = 0
            for s in stocks:
                ret = s.get("exit", {}).get("return_pct", 0) or \
                      (s["snapshots"][-1]["vs_entry_pct"] if s["snapshots"] else 0)
                if ret > 0:
                    wins += 1
            return round(wins / len(stocks) * 100, 1)

        return {
            "total_tracked": len(all_stocks),
            "active": len(active),
            "stopped_out": len(stopped),
            "expired": len(expired),
            "pools_tracked": len(self.data["pools"]),
            "stopped_out_pct": round(len(stopped) / max(len(all_stocks), 1) * 100, 1),
            "avg_return_active": _avg_return(active),
            "avg_return_stopped": _avg_return(stopped),
            "avg_return_expired": _avg_return(expired),
            "win_rate_stopped": _win_rate(stopped),
            "win_rate_expired": _win_rate(expired),
            "total_win_rate": _win_rate(stopped + expired),
        }

    def print_stats(self):
        """打印统计报告"""
        s = self.stats()
        print(f"\n{'='*50}")
        print(f"  📊 股票跟踪统计  {_now()}")
        print(f"  {'='*50}")
        print(f"  总跟踪: {s['total_tracked']}只 | 活跃: {s['active']} | 已退场: {s['stopped_out']+s['expired']}")
        print(f"  止损失效: {s['stopped_out']}只 ({s['stopped_out_pct']}%) | 到期: {s['expired']}只")
        print(f"  {'='*50}")
        if s['stopped_out'] > 0:
            print(f"  止损组: 平均收益 {s['avg_return_stopped']:+.1f}% | 胜率 {s['win_rate_stopped']}%")
        if s['expired'] > 0:
            print(f"  到期组: 平均收益 {s['avg_return_expired']:+.1f}% | 胜率 {s['win_rate_expired']}%")
        if s['stopped_out'] + s['expired'] > 0:
            print(f"  综合胜率: {s['total_win_rate']}%")
        if s['active'] > 0:
            print(f"  活跃组: 平均浮动 {s['avg_return_active']:+.1f}%")
        print()

    def list_active(self):
        """列出所有活跃股"""
        active = [s for s in self.data["stocks"] if s["status"] == "active"]
        if not active:
            print("无活跃追踪标的")
            return
        print(f"\n{'代码':<8} {'名称':<8} {'入场日':<12} {'入场价':>7} {'最新':>7} {'浮动':>7} {'已跟':>4}天")
        print("-" * 60)
        for s in sorted(active, key=lambda x: -(x["snapshots"][-1]["vs_entry_pct"] if x["snapshots"] else 0)):
            entry = s["entry_close"]
            latest = s["snapshots"][-1]["close"] if s["snapshots"] else entry
            vs_entry = s["snapshots"][-1]["vs_entry_pct"] if s["snapshots"] else 0
            days = len(s["snapshots"])
            print(f"{s['code']:<8} {s['name']:<8} {s['entry_date']:<12} {entry:>7.2f} {latest:>7.2f} {vs_entry:>+6.1f}% {days:>4}")
        print()


# ── CLI ──

def main():
    import argparse
    p = argparse.ArgumentParser(description="股票持续跟踪系统 v1.0")
    p.add_argument("--add-pool", action="store_true", help="从 daily_pool.json 同步新增")
    p.add_argument("--snapshot", action="store_true", help="更新所有活跃股今日快照")
    p.add_argument("--stats", action="store_true", help="输出跟踪统计")
    p.add_argument("--list", action="store_true", help="列出活跃股")
    args = p.parse_args()

    tracker = StockTracker()

    if args.add_pool:
        tracker.add_pool()

    if args.snapshot:
        tracker.update_snapshots()

    if args.stats:
        tracker.print_stats()

    if args.list:
        tracker.list_active()

    # 默认: 全部执行
    if not any([args.add_pool, args.snapshot, args.stats, args.list]):
        tracker.add_pool()
        tracker.update_snapshots()
        tracker.print_stats()


if __name__ == "__main__":
    main()
