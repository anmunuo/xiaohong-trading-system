#!/bin/bash
# 🧬 进化引擎 - 每日 17:30 自动进化
# no_agent cron: stdout 直接投递到飞书
cd /home/pc/.hermes/profiles/xiaohong/scripts
exec /home/pc/.hermes/hermes-agent/venv/bin/python3 evolution_engine.py
