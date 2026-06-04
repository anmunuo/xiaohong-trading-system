#!/bin/bash
# cron_intraday_freeze.sh — 15:05 收盘后冻结分时K线到 Bronze
cd /home/pc/.hermes/profiles/xiaohong/scripts
/home/pc/.hermes/hermes-agent/venv/bin/python3 -c "
from bronze_ingest import BronzeCollector
import json
c = BronzeCollector()
date = __import__('datetime').datetime.now().strftime('%Y-%m-%d')
# 仅采集分时
c._collect_intraday(date, c.writer)
print('分时K线冻结完成')
" 2>&1
