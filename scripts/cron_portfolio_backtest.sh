#!/bin/bash
# cron_portfolio_backtest.sh — 每日组合回测
cd /home/pc/.hermes/profiles/xiaohong/scripts
/home/pc/.hermes/hermes-agent/venv/bin/python3 portfolio_backtest.py --days 60 --report 2>&1
