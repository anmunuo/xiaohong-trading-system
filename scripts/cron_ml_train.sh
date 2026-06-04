#!/bin/bash
# cron_ml_train.sh — 每日增量训练ML模型
cd /home/pc/.hermes/profiles/xiaohong/scripts
/home/pc/.hermes/hermes-agent/venv/bin/python3 ml_predictor.py --train 2>&1
