#!/bin/bash
# 🎯 狙击手 · 日内监控 v3.0 (09:35起每30分钟)
# no_agent cron: stdout 直接投递到飞书
cd /home/pc/.hermes/profiles/xiaohong/scripts
exec /home/pc/.hermes/hermes-agent/venv/bin/python3 sniper.py
