#!/usr/bin/env python3
"""
安幕诺家族 · 小红  交易日志系统
=====================================
TradingSkill 风格：CSV 主存储 + SQLite 辅助查询 + PnL 统计分析

参照 gwrxuk/TradingSkill → src/trading/logger.ts
"""
import csv
import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Dict, Any
import logging

_log = logging.getLogger(__name__)


@dataclass
class TradeRecord:
    """单笔交易记录"""
    timestamp: str = ""
    symbol: str = ""
    symbol_name: str = ""
    market: str = "A"
    side: str = "BUY"
    order_type: str = "market"
    price: float = 0.0
    quantity: int = 0
    value: float = 0.0
    fee: float = 0.0
    strategy_id: str = ""
    signal_type: str = ""
    signal_strength: str = ""
    signal_confidence: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    position_pct: float = 0.0
    is_paper: bool = True
    execution_status: str = "filled"
    pnl: float = 0.0
    pnl_pct: float = 0.0
    portfolio_value: float = 0.0
    reason: str = ""
    trade_id: str = ""

    def __post_init__(self):
        if not self.trade_id:
            raw = f"{self.symbol}{self.side}{self.timestamp}{self.price}{self.quantity}"
            self.trade_id = hashlib.md5(raw.encode()).hexdigest()[:12]
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if self.value == 0 and self.price > 0:
            self.value = round(self.price * self.quantity, 2)


CSV_HEADER = [
    "Timestamp", "TradeID", "Symbol", "SymbolName", "Market",
    "Side", "OrderType", "Price", "Quantity", "Value", "Fee",
    "StrategyID", "SignalType", "SignalStrength", "SignalConfidence",
    "StopLoss", "TakeProfit", "PositionPct",
    "IsPaper", "ExecStatus",
    "PnL", "PnLPct", "PortfolioValue", "Reason",
]


class TransactionLogger:
    """TradingSkill 风格交易日志器"""

    def __init__(self, csv_path: str = "workspace/transactions.csv",
                 db_path: str = "data/transactions.db"):
        self.csv_path = Path(csv_path)
        self.db_path = Path(db_path)
        self._ensure_files()

    def _ensure_files(self):
        self.csv_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        if not self.csv_path.exists():
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(CSV_HEADER)

        conn = sqlite3.connect(str(self.db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                trade_id TEXT UNIQUE NOT NULL,
                symbol TEXT NOT NULL,
                symbol_name TEXT,
                market TEXT DEFAULT 'A',
                side TEXT NOT NULL,
                order_type TEXT DEFAULT 'market',
                price REAL NOT NULL,
                quantity INTEGER NOT NULL,
                value REAL,
                fee REAL DEFAULT 0,
                strategy_id TEXT,
                signal_type TEXT,
                signal_strength TEXT,
                signal_confidence REAL,
                stop_loss REAL,
                take_profit REAL,
                position_pct REAL,
                is_paper INTEGER DEFAULT 1,
                execution_status TEXT DEFAULT 'filled',
                pnl REAL,
                pnl_pct REAL,
                portfolio_value REAL,
                reason TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_tx_symbol
                ON transactions(symbol, timestamp);
            CREATE INDEX IF NOT EXISTS idx_tx_side
                ON transactions(side, timestamp);
        """)
        conn.commit()
        conn.close()

    def _to_row(self, r: TradeRecord) -> dict:
        return {
            "Timestamp": r.timestamp,
            "TradeID": r.trade_id,
            "Symbol": r.symbol,
            "SymbolName": r.symbol_name,
            "Market": r.market,
            "Side": r.side,
            "OrderType": r.order_type,
            "Price": str(r.price),
            "Quantity": str(r.quantity),
            "Value": str(r.value),
            "Fee": str(r.fee),
            "StrategyID": r.strategy_id,
            "SignalType": r.signal_type,
            "SignalStrength": r.signal_strength,
            "SignalConfidence": str(r.signal_confidence),
            "StopLoss": str(r.stop_loss),
            "TakeProfit": str(r.take_profit),
            "PositionPct": str(r.position_pct),
            "IsPaper": str(r.is_paper),
            "ExecStatus": r.execution_status,
            "PnL": str(r.pnl),
            "PnLPct": str(r.pnl_pct),
            "PortfolioValue": str(r.portfolio_value),
            "Reason": r.reason,
        }

    def log(self, record: TradeRecord) -> str:
        """CSV + SQLite 双写"""
        with open(self.csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER, extrasaction='ignore')
            writer.writerow(self._to_row(record))

        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO transactions VALUES (
                NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now')
            )
        """, (
            record.timestamp, record.trade_id, record.symbol,
            record.symbol_name, record.market, record.side,
            record.order_type, record.price, record.quantity,
            record.value, record.fee, record.strategy_id,
            record.signal_type, record.signal_strength,
            record.signal_confidence, record.stop_loss,
            record.take_profit, record.position_pct,
            int(record.is_paper), record.execution_status,
            record.pnl, record.pnl_pct, record.portfolio_value,
            record.reason,
        ))
        conn.commit()
        conn.close()
        return record.trade_id

    def log_buy(self, symbol, name, price, quantity, **kwargs) -> str:
        r = TradeRecord(symbol=symbol, symbol_name=name, side="BUY",
                        price=price, quantity=quantity, **kwargs)
        return self.log(r)

    def log_sell(self, symbol, name, price, quantity,
                 buy_price=0, **kwargs) -> str:
        pnl = round((price - buy_price) * quantity, 2) if buy_price > 0 else 0
        pnl_pct = round((price - buy_price) / buy_price * 100, 4) if buy_price > 0 else 0
        r = TradeRecord(symbol=symbol, symbol_name=name, side="SELL",
                        price=price, quantity=quantity, pnl=pnl,
                        pnl_pct=pnl_pct, **kwargs)
        return self.log(r)

    def get_transactions(self, symbol=None, side=None,
                         start_date=None, limit=100) -> List[TradeRecord]:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        q = "SELECT * FROM transactions WHERE 1=1"
        params = []
        if symbol:
            q += " AND symbol = ?"; params.append(symbol)
        if side:
            q += " AND side = ?"; params.append(side)
        if start_date:
            q += " AND timestamp >= ?"; params.append(start_date)
        q += " ORDER BY timestamp DESC LIMIT ?"; params.append(limit)
        rows = conn.execute(q, params).fetchall()
        conn.close()
        return [TradeRecord(
            timestamp=r["timestamp"], trade_id=r["trade_id"],
            symbol=r["symbol"], symbol_name=r["symbol_name"] or "",
            market=r["market"] or "A", side=r["side"],
            order_type=r["order_type"] or "market",
            price=float(r["price"]), quantity=int(r["quantity"]),
            value=float(r["value"] or 0), fee=float(r["fee"] or 0),
            strategy_id=r["strategy_id"] or "",
            signal_type=r["signal_type"] or "",
            signal_strength=r["signal_strength"] or "",
            signal_confidence=float(r["signal_confidence"] or 0),
            stop_loss=float(r["stop_loss"] or 0),
            take_profit=float(r["take_profit"] or 0),
            position_pct=float(r["position_pct"] or 0),
            is_paper=bool(r["is_paper"]), execution_status=r["execution_status"] or "",
            pnl=float(r["pnl"] or 0), pnl_pct=float(r["pnl_pct"] or 0),
            portfolio_value=float(r["portfolio_value"] or 0),
            reason=r["reason"] or "",
        ) for r in rows]

    def get_statistics(self, symbol=None) -> Dict[str, Any]:
        conn = sqlite3.connect(str(self.db_path))
        where = "WHERE execution_status = 'filled'"
        params = []
        if symbol:
            where += " AND symbol = ?"; params.append(symbol)

        total = conn.execute(f"SELECT COUNT(*) FROM transactions {where}", params).fetchone()[0]
        buys = conn.execute(f"SELECT COUNT(*) FROM transactions {where} AND side='BUY'", params).fetchone()[0]
        sells = conn.execute(f"SELECT COUNT(*) FROM transactions {where} AND side='SELL'", params).fetchone()[0]

        sell_rows = conn.execute(
            f"SELECT pnl FROM transactions {where} AND side='SELL' AND pnl IS NOT NULL", params
        ).fetchall()

        wins = sum(1 for r in sell_rows if r[0] > 0)
        losses = sum(1 for r in sell_rows if r[0] < 0)
        total_pnl = sum(r[0] for r in sell_rows)
        avg_win = sum(r[0] for r in sell_rows if r[0] > 0) / max(wins, 1)
        avg_loss = sum(r[0] for r in sell_rows if r[0] < 0) / max(losses, 1)
        win_rate = (wins / max(wins + losses, 1)) * 100
        pf = abs(avg_win * wins / max(avg_loss * losses, 0.01)) if losses > 0 else 999

        symbols = conn.execute(
            f"SELECT symbol, COUNT(*) c, SUM(pnl) p FROM transactions "
            f"{where} AND side='SELL' GROUP BY symbol ORDER BY p DESC"
        ).fetchall()

        last = conn.execute("SELECT portfolio_value FROM transactions ORDER BY timestamp DESC LIMIT 1").fetchone()
        conn.close()

        return {
            "total_trades": total,
            "buys": buys, "sells": sells,
            "wins": wins, "losses": losses,
            "win_rate": round(win_rate, 1),
            "total_pnl": round(total_pnl, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(pf, 2),
            "portfolio_value": round(last[0], 2) if last else 0,
            "symbol_stats": [
                {"symbol": r[0], "trades": r[1], "total_pnl": round(r[2], 2)}
                for r in symbols
            ],
        }

    def export_filtered(self, output_path, symbol=None) -> int:
        records = self.get_transactions(symbol=symbol, limit=100000)
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with open(output, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADER, extrasaction='ignore')
            writer.writeheader()
            for r in records:
                writer.writerow(self._to_row(r))
        return len(records)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    sp = p.add_subparsers(dest="cmd")
    sp.add_parser("stats")
    sp.add_parser("recent")
    e = sp.add_parser("export")
    e.add_argument("--symbol")
    e.add_argument("--output", default="workspace/filtered.csv")
    args = p.parse_args()

    logger = TransactionLogger()
    if args.cmd == "stats":
        print(json.dumps(logger.get_statistics(), indent=2, ensure_ascii=False))
    elif args.cmd == "recent":
        for r in logger.get_transactions(limit=10):
            pnl_s = f" PnL={r.pnl:+.0f}" if r.side == "SELL" else ""
            print(f"{'B' if r.side=='BUY' else 'S'} {r.timestamp[:19]} "
                  f"{r.symbol} {r.quantity}@{r.price}{pnl_s}")
    elif args.cmd == "export":
        n = logger.export_filtered(args.output, symbol=args.symbol)
        print(f"Exported {n} records")
    else:
        print("Usage: transaction_logger.py [stats|recent|export]")
