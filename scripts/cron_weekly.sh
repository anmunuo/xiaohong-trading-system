#!/bin/bash
# 📊 文工团 - 周度复盘 (周六 09:00)
# no_agent cron: stdout 直接投递到飞书
cd /home/pc/.hermes/profiles/xiaohong/scripts
exec python3 weekly_review.py
