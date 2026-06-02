#!/bin/bash
# 🛡️ 弹药库 - 收盘风控检查 (15:30)
# --update 自动同步持仓 + 生成报告（v4.1 合并为一步）
# no_agent cron: stdout 直接投递到飞书
cd /home/pc/.hermes/profiles/xiaohong/scripts
python3 ammo_risk.py --update
