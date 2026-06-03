     1|#!/bin/bash
     2|# 📚 知识库 · 每小时增量采集 (v7.0)
     3|# no_agent cron: stdout 本地保存，不推送飞书
     4|cd /home/pc/.hermes/profiles/xiaohong/scripts
     5|export TQDM_DISABLE=1
     6|exec /home/pc/.hermes/hermes-agent/venv/bin/python3 mega_collector.py --quiet
     7|