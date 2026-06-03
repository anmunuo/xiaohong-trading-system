     1|#!/bin/bash
     2|# cron_intraday_freeze.sh — 15:05 收盘后冻结分时K线到 Bronze
     3|cd /home/pc/.hermes/profiles/xiaohong/scripts
     4|/home/pc/.hermes/hermes-agent/venv/bin/python3 -c "
     5|from bronze_ingest import BronzeCollector
     6|import json
     7|c = BronzeCollector()
     8|date = __import__('datetime').datetime.now().strftime('%Y-%m-%d')
     9|# 仅采集分时
    10|c._collect_intraday(date, c.writer)
    11|print('分时K线冻结完成')
    12|" 2>&1
    13|