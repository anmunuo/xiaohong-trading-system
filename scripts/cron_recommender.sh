#!/bin/bash
# 🎯 选股推荐引擎 · 每日 08:35
# 数据已由 08:30 盘前采集准备完毕（调度在 08:35），用最新知识库生成推荐池
cd /home/pc/.hermes/profiles/xiaohong/scripts
export TQDM_DISABLE=1
exec /home/pc/.hermes/hermes-agent/venv/bin/python3 stock_recommender.py --top 8
