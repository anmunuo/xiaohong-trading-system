#!/bin/bash
# 盘前数据采集 - cron 静默版
LOG=/tmp/xiaohong_pre_$(date +%Y%m%d).log
bash /home/pc/.hermes/profiles/xiaohong/scripts/market_data_collector.sh pre > "$LOG" 2>&1
EXIT=$?
if [ $EXIT -ne 0 ]; then
  echo "⚠️ 盘前采集异常 (exit=$EXIT)"
  tail -20 "$LOG"
  exit $EXIT
fi
# 成功静默，不输出
