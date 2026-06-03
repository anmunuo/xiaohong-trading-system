     1|#!/bin/bash
     2|# 🛡️ 弹药库 - 收盘风控检查 (15:30)
     3|# --update 自动同步持仓 + 生成报告（v4.1 合并为一步）
     4|# no_agent cron: stdout 直接投递到飞书
     5|cd /home/pc/.hermes/profiles/xiaohong/scripts
     6|/home/pc/.hermes/hermes-agent/venv/bin/python3 ammo_risk.py --update
     7|