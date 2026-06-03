     1|#!/bin/bash
     2|# cron_factor_ic.sh — 每日因子IC计算
     3|cd /home/pc/.hermes/profiles/xiaohong/scripts
     4|/home/pc/.hermes/hermes-agent/venv/bin/python3 factor_evaluator.py 2>&1
     5|