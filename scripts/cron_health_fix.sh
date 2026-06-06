#!/bin/bash
# cron_health_fix.sh — wrapper: system_health_check.py --fix
# cron 调度器的 script 参数不支持命令行参数，必须通过包装脚本传递

cd /home/pc/.hermes/profiles/xiaohong/scripts
exec /home/pc/.hermes/hermes-agent/venv/bin/python3 system_health_check.py --fix --push
