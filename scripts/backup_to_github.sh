#!/bin/bash
# ============================================
# 小红交易系统 · 每日自动备份脚本
# Cron: 0 4 * * * (每日凌晨4点)
# ============================================
set -euo pipefail

export HOME=/home/pc
REPO_DIR="/home/pc/.hermes/profiles/xiaohong"
LOG_DIR="$REPO_DIR/data/backup_logs"
LOG_FILE="$LOG_DIR/backup-$(date '+%Y%m%d-%H%M%S').log"
RETENTION_DAYS=30

mkdir -p "$LOG_DIR"

exec > >(tee -a "$LOG_FILE") 2>&1

echo "═══════════════════════════════════"
echo "  小红交易系统 · 自动备份"
echo "  时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "═══════════════════════════════════"

cd "$REPO_DIR"

# ── 1. 清理旧日志 ──
find "$LOG_DIR" -name "backup-*.log" -mtime +$RETENTION_DAYS -delete 2>/dev/null || true

# ── 2. 暂存所有变更 ──
git add -A

# ── 3. 检查是否有变更 ──
if git diff --cached --quiet; then
    echo "✅ 无变更，跳过备份"
    exit 0
fi

# ── 4. 提交 ──
COMMIT_MSG="backup: $(date '+%Y-%m-%d %H:%M') · 小红交易系统"
git commit -m "$COMMIT_MSG"

echo "📦 已提交：$(git diff --stat HEAD~1 | tail -1)"

# ── 5. 推送（SSH 密钥认证）──
export GIT_SSH_COMMAND="ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15"

if git push origin main 2>&1; then
    echo "✅ 推送成功 → github.com/anmunuo/xiaohong-trading-system"
else
    PUSH_EXIT=$?
    echo "⚠️ 推送失败 (exit=$PUSH_EXIT)，本地提交已保留"
fi

echo "═══════════════════════════════════"
echo "  备份完成: $(date '+%Y-%m-%d %H:%M:%S')"
echo "  日志: $LOG_FILE"
echo "═══════════════════════════════════"
