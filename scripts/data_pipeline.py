#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
安幕诺家族 - 小红 🌹 统一数据管道 (兼容壳)
============================================
v2.0 模块化拆分后，此文件作为向后兼容入口。

所有函数实际定义在 data_pipeline/_core.py 中。
新代码推荐使用子模块导入:
  from data_pipeline.index import get_index_data
  from data_pipeline.fund import get_north_flow
  from data_pipeline.market import get_stock_realtime

旧代码无需修改:
  from data_pipeline import get_index_data  # 仍可工作

作者: 弯弯 🌙
版本: 2.0.0
"""

# Re-export everything from the package
from data_pipeline import *  # noqa: F401, F403
