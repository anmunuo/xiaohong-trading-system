#!/bin/bash
# 📊 市场统一快照 · 每日 08:28（推荐引擎前2分钟）
cd /home/pc/.hermes/profiles/xiaohong/scripts
export TQDM_DISABLE=1
exec python3 market_snapshot.py
