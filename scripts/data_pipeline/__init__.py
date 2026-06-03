#!/usr/bin/env python3
"""
data_pipeline/ — 统一数据管道 v2.0 (模块化拆分)
================================================
子模块:
  index    — get_index_data()          全球指数
  fund     — get_north_flow() 等        资金流向
  market   — get_stock_realtime() 等    行情数据
  financial— get_financial_summary() 等 财务指标
  health   — check_data_health()       健康检查

所有函数从 _core 重导出，保持与原 data_pipeline.py 完全兼容。
"""

from data_pipeline._core import (
    # 配置
    CACHE_EXPIRE_SECONDS,

    # 指数
    get_index_data,

    # 资金流
    get_north_flow,
    get_market_money_flow,
    get_individual_money_flow,
    get_top_flow_stocks,
    get_sector_flow_rank,

    # 行情
    get_stock_realtime,
    get_historical_k_with_ma,
    get_factor_panel,
    get_intraday_minutes,
    get_intraday_volume_alert,
    get_watchlist,

    # 财务
    get_financial_indicator,
    get_financial_summary,

    # 健康检查
    check_data_health,
)

__all__ = [
    'CACHE_EXPIRE_SECONDS',
    'get_index_data',
    'get_north_flow', 'get_market_money_flow', 'get_individual_money_flow',
    'get_top_flow_stocks', 'get_sector_flow_rank',
    'get_stock_realtime', 'get_historical_k_with_ma', 'get_factor_panel',
    'get_intraday_minutes', 'get_intraday_volume_alert', 'get_watchlist',
    'get_financial_indicator', 'get_financial_summary',
    'check_data_health',
]
