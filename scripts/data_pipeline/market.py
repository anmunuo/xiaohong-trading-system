#!/usr/bin/env python3
"""
data_pipeline/market.py — 行情数据

数据源: Sina批量HTTP + BaoStock ProcessPool + tushare
"""

from data_pipeline._core import (
    get_stock_realtime,
    get_historical_k_with_ma,
    get_factor_panel,
    get_intraday_minutes,
    get_intraday_volume_alert,
    get_watchlist,
)

__all__ = [
    'get_stock_realtime', 'get_historical_k_with_ma',
    'get_factor_panel', 'get_intraday_minutes',
    'get_intraday_volume_alert', 'get_watchlist',
]
