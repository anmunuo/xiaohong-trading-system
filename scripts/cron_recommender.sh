#!/bin/bash
# 🎯 选股推荐引擎 · 每日 08:25
# 数据已由 08:30 盘前采集准备完毕，用最新知识库生成推荐池
cd /home/pc/.hermes/profiles/xiaohong/scripts
export TQDM_DISABLE=1
exec python3 stock_recommender.py --top 8
