#!/bin/bash
# 📰 研究员周报 · 每周六 09:00
# 5位研究员独立报告 + 进化引擎 action_items
cd /home/pc/.hermes/profiles/xiaohong/scripts
export TQDM_DISABLE=1
exec /home/pc/.hermes/hermes-agent/venv/bin/python3 research_weekly.py
