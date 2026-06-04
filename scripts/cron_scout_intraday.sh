#!/bin/bash
# 🔍 侦察兵 · 盘中扫描 (v4.0)
# 交易时段每小时扫描资金异动，自动更新推荐池
# no_agent cron: stdout 直接投递到飞书
cd /home/pc/.hermes/profiles/xiaohong/scripts
exec /home/pc/.hermes/hermes-agent/venv/bin/python3 scout.py --intraday
