#!/bin/bash
# ╔══════════════════════════════════════════════════════════╗
# ║  安幕诺家族 · 小红 🌹 硬件盒子 v1 — 一键安装脚本         ║
# ║  Raspberry Pi 5 / 香橙派 5 Plus + 7寸触摸屏              ║
# ╚══════════════════════════════════════════════════════════╝
#
# 用法:
#   chmod +x install.sh && sudo ./install.sh
#
# 硬件需求:
#   - Raspberry Pi 5 (8GB) 或 香橙派 5 Plus
#   - 7寸 HDMI 触摸屏 (1024×600)
#   - WS2812 LED 灯带 (可选)
#   - 64GB+ microSD / NVMe SSD
#   - 散热风扇 + 外壳

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║    安幕诺家族 · 小红 🌹 硬件盒子 v1 安装程序              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# ═══════════════════════════════════════
# 0. 环境检测
# ═══════════════════════════════════════
echo -e "${YELLOW}[1/7] 环境检测...${NC}"

ARCH=$(uname -m)
if [[ "$ARCH" == "aarch64" ]] || [[ "$ARCH" == "armv7l" ]]; then
    echo -e "  ${GREEN}✅ ARM 架构: $ARCH${NC}"
else
    echo -e "  ${RED}❌ 非 ARM 架构: $ARCH (需要树莓派/香橙派)${NC}"
    exit 1
fi

TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
echo -e "  内存: ${TOTAL_MEM}MB"
if [ "$TOTAL_MEM" -lt 2000 ]; then
    echo -e "  ${YELLOW}⚠️ 内存 < 2GB，建议升级到 4GB+${NC}"
fi

# 检测 I2C（LED 灯带需要）
if ls /dev/i2c-* 2>/dev/null; then
    echo -e "  ${GREEN}✅ I2C 可用 (LED 灯带支持)${NC}"
    HAS_LED=true
else
    echo -e "  ${YELLOW}⚠️ I2C 不可用，跳过 LED 灯带${NC}"
    HAS_LED=false
fi

# ═══════════════════════════════════════
# 1. 系统依赖
# ═══════════════════════════════════════
echo -e "${YELLOW}[2/7] 安装系统依赖...${NC}"

apt-get update -qq
apt-get install -y -qq \
    python3 python3-pip python3-venv \
    git curl wget nginx \
    i2c-tools libgpiod2 \
    chromium-browser xserver-xorg x11-xserver-utils unclutter \
    2>&1 | tail -1

echo -e "  ${GREEN}✅ 系统依赖完成${NC}"

# ═══════════════════════════════════════
# 2. Docker 安装
# ═══════════════════════════════════════
echo -e "${YELLOW}[3/7] 安装 Docker...${NC}"

if command -v docker &>/dev/null; then
    echo -e "  ${GREEN}✅ Docker 已安装 ($(docker --version))${NC}"
else
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $SUDO_USER
    systemctl enable docker
    echo -e "  ${GREEN}✅ Docker 安装完成${NC}"
fi

# ═══════════════════════════════════════
# 3. 小红交易系统部署
# ═══════════════════════════════════════
echo -e "${YELLOW}[4/7] 部署小红交易系统...${NC}"

INSTALL_DIR="/opt/xiaohong"
mkdir -p $INSTALL_DIR

# 从当前目录复制
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../Dockerfile" ]; then
    cp -r "$SCRIPT_DIR/.." "$INSTALL_DIR/"
    echo -e "  ${GREEN}✅ 代码复制到 $INSTALL_DIR${NC}"
else
    echo -e "  ${YELLOW}⚠️ 未找到项目文件，请手动放置到 $INSTALL_DIR${NC}"
fi

# 创建 .env
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat > "$INSTALL_DIR/.env" << 'ENVEOF'
PAPER_TRADING=true
TRADING_MODE=paper
API_PORT=8000
TUSHARE_TOKEN=your_token_here
ENVEOF
    echo -e "  ${YELLOW}⚠️ 请编辑 $INSTALL_DIR/.env 填入 Tushare Token${NC}"
fi

# Docker build
cd "$INSTALL_DIR"
docker-compose build 2>&1 | tail -3

# ═══════════════════════════════════════
# 4. LED 灯带配置
# ═══════════════════════════════════════
if [ "$HAS_LED" = true ]; then
    echo -e "${YELLOW}[5/7] 配置 LED 灯带 (WS2812)...${NC}"
    
    pip3 install rpi_ws281x adafruit-circuitpython-neopixel 2>&1 | tail -1
    
    cp "$SCRIPT_DIR/led_controller.py" "$INSTALL_DIR/scripts/"
    chmod +x "$INSTALL_DIR/scripts/led_controller.py"
    
    # 启用 SPI
    if ! grep -q "dtparam=spi=on" /boot/config.txt; then
        echo "dtparam=spi=on" >> /boot/config.txt
    fi
    
    echo -e "  ${GREEN}✅ LED 灯带配置完成 (重启后生效)${NC}"
else
    echo -e "${YELLOW}[5/7] 跳过 LED 灯带${NC}"
fi

# ═══════════════════════════════════════
# 5. 仪表盘 + Kiosk 模式
# ═══════════════════════════════════════
echo -e "${YELLOW}[6/7] 配置仪表盘 Kiosk 模式...${NC}"

cp "$SCRIPT_DIR/dashboard.html" "$INSTALL_DIR/scripts/"

# Autostart Chromium Kiosk
AUTOSTART="/etc/xdg/openbox/autostart"
if [ ! -f "$AUTOSTART" ]; then
    mkdir -p /etc/xdg/openbox
fi

cat > "$AUTOSTART" << AUTOSTARTEOF
# 小红仪表盘 Kiosk 模式
xset s off
xset -dpms
unclutter -idle 0 &
chromium-browser --kiosk --noerrdialogs --disable-infobars \
    --app=http://localhost:8000/ \
    --window-size=1024,600 \
    --window-position=0,0 &
AUTOSTARTEOF

echo -e "  ${GREEN}✅ Kiosk 模式已配置${NC}"

# ═══════════════════════════════════════
# 6. Systemd 服务
# ═══════════════════════════════════════
echo -e "${YELLOW}[7/7] 配置系统服务...${NC}"

cat > /etc/systemd/system/xiaohong-box.service << SERVICEEOF
[Unit]
Description=安幕诺家族 · 小红 硬件盒子
After=docker.service network.target
Wants=docker.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/docker-compose up
ExecStop=/usr/bin/docker-compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl daemon-reload
systemctl enable xiaohong-box.service

echo -e "${GREEN}✅ Systemd 服务已配置${NC}"

# ═══════════════════════════════════════
# 完成
# ═══════════════════════════════════════
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗"
echo -e "║           🎉 硬件盒子 v1 安装完成！                       ║"
echo -e "╠══════════════════════════════════════════════════════════╣"
echo -e "║                                                          ║"
echo -e "║  启动:  sudo systemctl start xiaohong-box                 ║"
echo -e "║  停止:  sudo systemctl stop xiaohong-box                  ║"
echo -e "║  日志:  journalctl -u xiaohong-box -f                     ║"
echo -e "║  仪表盘: http://localhost:8000/                           ║"
echo -e "║  API文档: http://localhost:8000/docs                      ║"
echo -e "║                                                          ║"
echo -e "║  ⚠️ 请编辑 $INSTALL_DIR/.env 填入真实密钥           ║"
echo -e "║  ⚠️ 重启以启用 LED 灯带: sudo reboot                     ║"
echo -e "║                                                          ║"
echo -e "╚══════════════════════════════════════════════════════════╝${NC}"
