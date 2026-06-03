     1|#!/bin/bash
     2|# 🧠 竞价学习器 - 盘后16:00 权重更新
     3|# no_agent cron: stdout 直接投递到飞书
     4|cd /home/pc/.hermes/profiles/xiaohong/scripts
     5|exec /home/pc/.hermes/hermes-agent/venv/bin/python3 auction_learner.py
     6|