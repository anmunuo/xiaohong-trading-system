     1|#!/bin/bash
     2|# cron_silver_etl.sh — 每日 Silver ETL (Bronze→清洗)
     3|cd /home/pc/.hermes/profiles/xiaohong/scripts
     4|/home/pc/.hermes/hermes-agent/venv/bin/python3 silver_pipeline.py --date $(date +%Y-%m-%d) 2>&1
     5|