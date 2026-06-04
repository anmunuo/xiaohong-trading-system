#!/bin/bash
# cron_stress_test.sh — 周度压力测试
cd /home/pc/.hermes/profiles/xiaohong/scripts
/home/pc/.hermes/hermes-agent/venv/bin/python3 portfolio_risk.py --weekly --report 2>&1
