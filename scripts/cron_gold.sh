     1|#!/bin/bash
     2|# cron_gold.sh — Gold 层每日自动 ETL
     3|# 时间: 15:50 (Silver ETL 之后)
     4|# 从 Silver → Gold: 因子面板 + ML 数据集 + Pool 归档
     5|
     6|set -euo pipefail
     7|
     8|cd "$HOME/.hermes/profiles/xiaohong/scripts"
     9|
    10|DATE=$(date +%Y-%m-%d)
    11|
    12|# 1. 执行 Gold ETL
    13|echo "[Gold ETL] $DATE"
    14|/home/pc/.hermes/hermes-agent/venv/bin/python3 gold_pipeline.py --date "$DATE"
    15|
    16|# 2. 验证
    17|echo "[Gold Verify] $DATE"
    18|/home/pc/.hermes/hermes-agent/venv/bin/python3 gold_verifier.py --date "$DATE"
    19|
    20|echo "[Gold] Done."
    21|