#!/bin/bash
# cron_silver_etl.sh — 每日 Silver ETL (Bronze→清洗)
cd /home/pc/.hermes/profiles/xiaohong/scripts
/home/pc/.hermes/hermes-agent/venv/bin/python3 silver_pipeline.py --date $(date +%Y-%m-%d) 2>&1
