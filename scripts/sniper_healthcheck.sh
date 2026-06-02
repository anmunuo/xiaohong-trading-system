#!/bin/bash
# 狙击手守护进程存活检测
# 交易日 09:30-15:00 每 5 分钟运行，检测 sniperd.service 是否存活
# 异常时输出告警信息，由 cron 投递到飞书

SERVICE="sniperd.service"
NOW=$(date +%H:%M)

# 检查是否在交易时段
HOUR=$(date +%H)
MINUTE=$(date +%M)
T=$((10#$HOUR * 60 + 10#$MINUTE))
if [ $T -lt 570 ] || [ $T -gt 900 ]; then
    # 不在 09:30-15:00，静默退出
    exit 0
fi

# 检查服务状态
STATUS=$(systemctl --user is-active "$SERVICE" 2>/dev/null)

if [ "$STATUS" != "active" ]; then
    # 服务异常：输出告警
    echo "🔴 狙击手守护进程异常"
    echo ""
    echo "⏰ ${NOW} | 状态: \`${STATUS:-unknown}\`"
    echo ""
    # 尝试获取最近日志
    echo "---"
    echo "最近日志:"
    systemctl --user status "$SERVICE" --no-pager -l 2>/dev/null | tail -20
    echo ""
    echo "> 建议立即检查: \`systemctl --user restart sniperd.service\`"

    # 尝试自动恢复
    systemctl --user reset-failed "$SERVICE" 2>/dev/null
    systemctl --user restart "$SERVICE" 2>/dev/null
    sleep 2
    NEW_STATUS=$(systemctl --user is-active "$SERVICE" 2>/dev/null)
    echo ""
    if [ "$NEW_STATUS" = "active" ]; then
        echo "✅ 自动恢复成功"
    else
        echo "❌ 自动恢复失败，需人工介入"
    fi
    exit 1
fi

# 一切正常，静默
exit 0
