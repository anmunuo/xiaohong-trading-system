     1|#!/bin/bash
     2|# cron_stress_test.sh — 周度压力测试
     3|cd /home/pc/.hermes/profiles/xiaohong/scripts
     4|/home/pc/.hermes/hermes-agent/venv/bin/python3 portfolio_risk.py --weekly --report 2>&1
     5|