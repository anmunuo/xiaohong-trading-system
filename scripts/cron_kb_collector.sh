#!/bin/bash
# 📚 知识库 · 每小时增量采集 (v7.0)
# no_agent cron: stdout 本地保存，不推送飞书
cd /home/pc/.hermes/profiles/xiaohong/scripts
export TQDM_DISABLE=1
exec python3 mega_collector.py --quiet
