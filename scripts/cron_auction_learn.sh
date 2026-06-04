#!/bin/bash
# 🧠 竞价学习器 - 盘后16:00 权重更新
# no_agent cron: stdout 直接投递到飞书
cd /home/pc/.hermes/profiles/xiaohong/scripts
exec /home/pc/.hermes/hermes-agent/venv/bin/python3 auction_learner.py
