#!/bin/bash
# 盘后复盘 - cron 静默版
LOG=/tmp/xiaohong_post_$(date +%Y%m%d).log
bash /home/pc/.hermes/profiles/xiaohong/scripts/market_data_collector.sh post > "$LOG" 2>&1
EXIT=$?
if [ $EXIT -ne 0 ]; then
  echo "⚠️ 盘后复盘异常 (exit=$EXIT)"
  tail -20 "$LOG"
  exit $EXIT
fi
