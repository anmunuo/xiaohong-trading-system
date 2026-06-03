     1|#!/bin/bash
     2|# cron_ml_train.sh — 每日增量训练ML模型
     3|cd /home/pc/.hermes/profiles/xiaohong/scripts
     4|/home/pc/.hermes/hermes-agent/venv/bin/python3 ml_predictor.py --train 2>&1
     5|