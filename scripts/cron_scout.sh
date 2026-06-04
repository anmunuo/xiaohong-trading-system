#!/bin/bash
# 🔍 侦察兵 - 开盘确认 (09:25) + 竞价分析
# no_agent cron: stdout 直接投递到飞书
cd /home/pc/.hermes/profiles/xiaohong/scripts
exec /home/pc/.hermes/hermes-agent/venv/bin/python3 scout.py --auction
