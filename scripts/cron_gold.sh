#!/bin/bash
# cron_gold.sh — Gold 层每日自动 ETL
# 时间: 15:50 (Silver ETL 之后)
# 从 Silver → Gold: 因子面板 + ML 数据集 + Pool 归档

set -euo pipefail

cd "$HOME/.hermes/profiles/xiaohong/scripts"

DATE=$(date +%Y-%m-%d)

# 1. 执行 Gold ETL
echo "[Gold ETL] $DATE"
/home/pc/.hermes/hermes-agent/venv/bin/python3 gold_pipeline.py --date "$DATE"

# 2. 验证
echo "[Gold Verify] $DATE"
/home/pc/.hermes/hermes-agent/venv/bin/python3 gold_verifier.py --date "$DATE"

echo "[Gold] Done."
