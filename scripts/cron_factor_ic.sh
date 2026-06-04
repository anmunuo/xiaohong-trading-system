#!/bin/bash
# cron_factor_ic.sh — 每日因子IC计算
cd /home/pc/.hermes/profiles/xiaohong/scripts
/home/pc/.hermes/hermes-agent/venv/bin/python3 factor_evaluator.py 2>&1
