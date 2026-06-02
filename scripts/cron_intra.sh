#!/bin/bash
# 盘中扫描 - cron 静默版
LOG=/tmp/xiaohong_intra_$(date +%Y%m%d).log
bash /home/pc/.hermes/profiles/xiaohong/scripts/market_data_collector.sh intra > "$LOG" 2>&1
EXIT=$?
if [ $EXIT -ne 0 ]; then
  echo "⚠️ 盘中扫描异常 (exit=$EXIT)"
  tail -20 "$LOG"
  exit $EXIT
fi
