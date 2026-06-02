#!/bin/bash
# ============================================================
# 通用数据采集器模板
# 用法: bash collector.sh [pre|intra|post|weekly]
# 适配: 修改 WIKI, WATCHLIST, 各模式的 fetch_save 调用
# ============================================================
set -e

# ⚠️ 用绝对路径！$HOME 在 profile 环境会解析到 profile home
WIKI="/home/pc/.hermes/profiles/<PROFILE>/home/wiki"
DOWNLOADS="$WIKI/下载收藏"
DATE=$(date +%Y%m%d)
MODE="${1:-post}"

# 你的数据列表
WATCHLIST=(
  "SYMBOL1"
  "SYMBOL2"
)

log() { echo "[$(date '+%H:%M:%S')] $*"; }
fetch_save() {
  local source=$1 symbol=$2 type=$3 extra=$4
  local out="$DOWNLOADS/${source}_${symbol}_${type}_${DATE}.json"
  mkdir -p "$DOWNLOADS"
  log "拉取: $source $symbol $type"
  data fetch "$source" --symbol "$symbol" --type "$type" $extra > "$out" 2>/dev/null \
    && log "  ✓ 已保存: $out" || log "  ✗ 失败: $source $symbol $type"
}

pre_market() {
  log "=== 盘前采集 ==="
  fetch_save futures "XINA50" "quote" ""
  fetch_save stock "AAPL" "quote" "--market us"
  for sym in "${WATCHLIST[@]}"; do
    fetch_save stock "$sym" "quote" ""
  done
  fetch_save news "" "headlines" ""
}

intra_market() {
  log "=== 盘中扫描 ==="
  for sym in "${WATCHLIST[@]}"; do
    fetch_save stock "$sym" "realtime" ""
  done
  fetch_save stock "" "sector" ""
}

post_market() {
  log "=== 盘后复盘 ==="
  for sym in "${WATCHLIST[@]}"; do
    fetch_save stock "$sym" "quote" ""
    fetch_save stock "$sym" "daily" "--days 30"
  done
  fetch_save stock "" "lhb" ""
  fetch_save stock "" "northbound" ""
  fetch_save stock "" "toplist" ""
  fetch_save news "" "industry" ""
}

weekly_review() {
  log "=== 周度复盘 ==="
  for sym in "${WATCHLIST[@]}"; do
    fetch_save company "$sym" "overview" ""
    fetch_save company "$sym" "financial" ""
    fetch_save stock "$sym" "indicators" ""
  done
  fetch_save stock "" "moneyflow" ""
  fetch_save macro "" "overview" ""
}

case "$MODE" in
  pre)    pre_market ;;
  intra)  intra_market ;;
  post)   post_market ;;
  weekly) weekly_review ;;
  *)      echo "用法: $0 [pre|intra|post|weekly]" && exit 1 ;;
esac
