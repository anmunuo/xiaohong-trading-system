#!/bin/bash
# 🔬 竞价采集器 - 09:15 启动（延迟10秒避开API冷启动）
# no_agent cron: stdout 直接投递到飞书
cd /home/pc/.hermes/profiles/xiaohong/scripts
sleep 10  # 等东方财富API数据就绪
TQDM_DISABLE=1 python3 auction_collector.py --live
