     1|#!/bin/bash
     2|# 📊 市场统一快照 · 每日 08:28（推荐引擎前2分钟）
     3|cd /home/pc/.hermes/profiles/xiaohong/scripts
     4|export TQDM_DISABLE=1
     5|exec /home/pc/.hermes/hermes-agent/venv/bin/python3 market_snapshot.py
     6|