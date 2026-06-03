     1|#!/bin/bash
     2|# 🔍 侦察兵 - 开盘确认 (09:25) + 竞价分析
     3|# no_agent cron: stdout 直接投递到飞书
     4|cd /home/pc/.hermes/profiles/xiaohong/scripts
     5|exec /home/pc/.hermes/hermes-agent/venv/bin/python3 scout.py --auction
     6|