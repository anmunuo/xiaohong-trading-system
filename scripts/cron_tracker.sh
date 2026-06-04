#!/bin/bash
# 📊 股票跟踪器 · 每日 15:35（收盘后）
# 更新所有活跃股快照，检测止损失效/到期退场
cd /home/pc/.hermes/profiles/xiaohong/scripts
export TQDM_DISABLE=1
exec /home/pc/.hermes/hermes-agent/venv/bin/python3 stock_tracker.py --snapshot --stats
