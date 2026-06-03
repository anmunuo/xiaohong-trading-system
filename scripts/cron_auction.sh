     1|#!/bin/bash
     2|# 🔬 竞价采集器 - 09:15 启动（延迟10秒避开API冷启动）
     3|# no_agent cron: stdout 直接投递到飞书
     4|cd /home/pc/.hermes/profiles/xiaohong/scripts
     5|sleep 10  # 等东方财富API数据就绪
     6|TQDM_DISABLE=1 /home/pc/.hermes/hermes-agent/venv/bin/python3 auction_collector.py --live
     7|