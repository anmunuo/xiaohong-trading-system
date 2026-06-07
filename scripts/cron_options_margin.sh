#!/bin/bash
# 期权保证金追踪 — 盘中每5分钟扫描
# 投递目标：期权专用群 oc_66726630665c67eb24517d50142b2687

exec /home/pc/.hermes/hermes-agent/venv/bin/python3 \
  /home/pc/.hermes/profiles/xiaohong/scripts/options/margin_tracker.py \
  --alerts-only
