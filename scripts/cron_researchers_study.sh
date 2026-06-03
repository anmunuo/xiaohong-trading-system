     1|#!/bin/bash
     2|# 📚 研究员自主研学 + 数据健康 · 每日 02:00
     3|# 1. 数据研究员: 健康检查 + 缺口发现
     4|# 2. 5位研究员: 独立深度学习
     5|cd /home/pc/.hermes/profiles/xiaohong/scripts
     6|export TQDM_DISABLE=1
     7|echo "=== 数据健康检查 ==="
     8|/home/pc/.hermes/hermes-agent/venv/bin/python3 data_hub.py --health
     9|echo ""
    10|echo "=== 数据缺口发现 ==="
    11|/home/pc/.hermes/hermes-agent/venv/bin/python3 data_hub.py --discover
    12|echo ""
    13|echo "=== 研究员研学 ==="
    14|/home/pc/.hermes/hermes-agent/venv/bin/python3 researchers.py --study
    15|