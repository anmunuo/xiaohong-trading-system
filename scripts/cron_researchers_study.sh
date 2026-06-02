#!/bin/bash
# 📚 研究员自主研学 + 数据健康 · 每日 02:00
# 1. 数据研究员: 健康检查 + 缺口发现
# 2. 5位研究员: 独立深度学习
cd /home/pc/.hermes/profiles/xiaohong/scripts
export TQDM_DISABLE=1
echo "=== 数据健康检查 ==="
python3 data_hub.py --health
echo ""
echo "=== 数据缺口发现 ==="
python3 data_hub.py --discover
echo ""
echo "=== 研究员研学 ==="
python3 researchers.py --study
