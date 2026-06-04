#!/bin/bash
# cron_bronze_collect.sh — 每日收盘后 Bronze 层采集
cd /home/pc/.hermes/profiles/xiaohong/scripts
/home/pc/.hermes/hermes-agent/venv/bin/python3 bronze_ingest.py --collect 2>&1
