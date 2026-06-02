#!/bin/bash
# ============================================================
# 小红 · 市场数据采集器
# 用法: bash market_data_collector.sh [pre|intra|post|weekly]
# ============================================================
set -e

WIKI="/home/pc/.hermes/profiles/xiaohong/home/wiki"
DOWNLOADS="$WIKI/下载收藏"
SCRIPT_DIR="/home/pc/.hermes/profiles/xiaohong/scripts"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DATE=$(date +%Y%m%d)
MODE="${1:-post}"

# 自选股列表
WATCHLIST=(
  "600519"  # 贵州茅台 - 消费标杆
  "000858"  # 五粮液
  "300750"  # 宁德时代 - 新能源龙头
  "002594"  # 比亚迪
  "600481"  # 双良节能 - 困境反转观察
  "601899"  # 紫金矿业 - 周期联动
  "300274"  # 阳光电源 - 光伏逆变器
  "002475"  # 立讯精密 - 消费电子
  "688981"  # 中芯国际 - 半导体
  "600036"  # 招商银行 - 金融
  "300124"  # 汇川技术 - 工控
  "600900"  # 长江电力 - 防御
)

log() { echo "[$(date '+%H:%M:%S')] $*"; }
fetch_save() {
  local source=$1 symbol=$2 type=$3 extra=$4
  local out="$DOWNLOADS/${source}_${symbol}_${type}_${DATE}.json"
  mkdir -p "$DOWNLOADS"
  log "拉取: $source $symbol $type"
  data fetch "$source" --symbol "$symbol" --type "$type" $extra > "$out" 2>/dev/null && \
    log "  ✓ 已保存: $out" || log "  ✗ 失败: $source $symbol $type"
}

# ---- 盘前模式 ----
pre_market() {
  log "=== 🕗 盘前数据采集 $(date) ==="

  # A50 期货 + 恒生期货
  log "--- 期货参考 ---"
  fetch_save futures "XINA50" "quote" ""
  fetch_save futures "HSI" "quote" ""

  # 隔夜美股核心标的
  log "--- 美股参考 ---"
  for sym in "AAPL" "MSFT" "NVDA" "TSLA" "TSM"; do
    fetch_save stock "$sym" "quote" "--market us"
  done

  # 自选股昨日收盘
  log "--- A股自选行情 ---"
  for sym in "${WATCHLIST[@]}"; do
    fetch_save stock "$sym" "quote" ""
  done

  # 北向资金（fetch_northbound.py → data_pipeline.get_north_flow()）
  log "--- 北向资金 ---"
  north_out="$DOWNLOADS/stock__northbound_${DATE}.json"
  python3 "$SCRIPT_DIR/fetch_northbound.py" "$north_out" 2>/dev/null || log "  ✗ 北向数据获取失败"

  # 重大新闻
  log "--- 新闻事件 ---"
  fetch_save news "" "headlines" ""

  log "=== 盘前采集完成 ==="
}

# ---- 盘中模式 ----
intra_market() {
  log "=== 🕚 盘中扫描 $(date) ==="

  # 自选股实时 + 量比
  log "--- 自选股实时行情 ---"
  for sym in "${WATCHLIST[@]}"; do
    fetch_save stock "$sym" "realtime" ""
  done

  # 板块异动
  log "--- 板块行情 ---"
  fetch_save stock "" "sector" ""

  log "=== 盘中扫描完成 ==="
}

# ---- 盘后模式 ----
post_market() {
  log "=== 🕓 盘后复盘 $(date) ==="

  # 自选股日线
  log "--- 自选股日线 ---"
  for sym in "${WATCHLIST[@]}"; do
    fetch_save stock "$sym" "quote" ""
    fetch_save stock "$sym" "daily" "--days 30"
  done

  # 龙虎榜
  log "--- 龙虎榜 ---"
  fetch_save stock "" "lhb" ""

  # 北向资金（fetch_northbound.py → data_pipeline.get_north_flow()）
  log "--- 北向资金 ---"
  north_out="$DOWNLOADS/stock__northbound_${DATE}.json"
  python3 "$SCRIPT_DIR/fetch_northbound.py" "$north_out" 2>/dev/null || log "  ✗ 北向数据获取失败"

  # 涨跌幅排行
  log "--- 涨跌幅排行 ---"
  fetch_save stock "" "toplist" ""

  # 行业新闻
  log "--- 行业新闻 ---"
  fetch_save news "" "industry" ""

  # 连板股
  log "--- 连板股 ---"
  fetch_save stock "" "limitup" ""

  log "=== 盘后复盘完成 ==="
}

# ---- 周度模式 ----
weekly_review() {
  log "=== 📅 周度深度复盘 $(date) ==="

  # 自选股财报更新
  log "--- 财报数据更新 ---"
  for sym in "${WATCHLIST[@]}"; do
    fetch_save company "$sym" "overview" ""
    fetch_save company "$sym" "financial" ""
  done

  # 行业资金流向
  log "--- 行业资金流向 ---"
  fetch_save stock "" "moneyflow" ""

  # 融资融券
  log "--- 融资融券 ---"
  fetch_save stock "" "margin" ""

  # 宏观数据
  log "--- 宏观指标 ---"
  fetch_save macro "" "overview" ""

  # 自选股估值指标
  log "--- 估值指标 ---"
  for sym in "${WATCHLIST[@]}"; do
    fetch_save stock "$sym" "indicators" ""
  done

  log "=== 周度复盘完成 ==="
}

# ---- 主流程 ----
case "$MODE" in
  pre)    pre_market ;;
  intra)  intra_market ;;
  post)   post_market ;;
  weekly) weekly_review ;;
  *)      echo "用法: $0 [pre|intra|post|weekly]" && exit 1 ;;
esac
