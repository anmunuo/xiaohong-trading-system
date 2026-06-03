#!/usr/bin/env python3
"""
data_pipeline/financial.py — 财务指标数据

数据源: tushare fina_indicator + daily_basic
"""

from data_pipeline._core import (
    get_financial_indicator,
    get_financial_summary,
)

__all__ = ['get_financial_indicator', 'get_financial_summary']
