#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 LED 灯带控制器
=====================================
WS2812 可编程 RGB LED 状态指示

灯带布局 (8 LEDs):
  [0] 系统状态    — 绿=正常 / 红=异常 / 蓝=启动中
  [1] 市场情绪    — 绿=偏多 / 黄=震荡 / 红=偏空
  [2] 盈亏信号    — 绿=浮盈 / 红=浮亏 / 灭=空仓
  [3] 信号强度    — 亮度=置信度
  [4] 告警级别    — 红闪=P0 / 黄闪=P1 / 蓝=P2
  [5] 数据连接    — 绿=正常 / 灭=断连
  [6] CPU温度     — 蓝→黄→红 渐变
  [7] 网络状态    — 绿=在线 / 灭=离线

依赖:
  pip3 install rpi_ws281x adafruit-circuitpython-neopixel
"""
import os
import sys
import json
import time
import math
import threading
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Tuple

_log = logging.getLogger("led_controller")

# ═══════════════════════════════════════
# LED 配置
# ═══════════════════════════════════════

LED_COUNT = 8
LED_PIN = 18          # GPIO 18 (PWM)
LED_FREQ_HZ = 800000
LED_DMA = 10
LED_BRIGHTNESS = 64   # 0-255
LED_INVERT = False

# 颜色定义 (GRB 格式 for WS2812)
COLORS = {
    "green":   (0, 255, 0),
    "red":     (255, 0, 0),
    "blue":    (0, 0, 255),
    "yellow":  (255, 200, 0),
    "orange":  (255, 100, 0),
    "purple":  (128, 0, 128),
    "cyan":    (0, 255, 255),
    "white":   (255, 255, 255),
    "off":     (0, 0, 0),
}


class LEDController:
    """WS2812 LED 灯带控制器"""
    
    def __init__(self, count: int = LED_COUNT, pin: int = LED_PIN,
                 brightness: int = LED_BRIGHTNESS):
        self.count = count
        self.leds = [(0, 0, 0)] * count
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # 尝试初始化硬件
        try:
            from rpi_ws281x import PixelStrip, Color
            self.strip = PixelStrip(count, pin, LED_FREQ_HZ, LED_DMA,
                                     LED_INVERT, brightness)
            self.strip.begin()
            self._hw_available = True
            _log.info(f"✅ LED 灯带初始化: {count} LEDs @ GPIO{pin}")
        except ImportError:
            _log.warning("⚠️ rpi_ws281x 未安装，LED 模拟模式")
            self._hw_available = False
        except Exception as e:
            _log.warning(f"⚠️ LED 硬件不可用: {e}")
            self._hw_available = False
    
    def set(self, index: int, color: Tuple[int, int, int]):
        """设置单个 LED 颜色"""
        if 0 <= index < self.count:
            self.leds[index] = color
    
    def set_all(self, color: Tuple[int, int, int]):
        """设置全部 LED"""
        self.leds = [color] * self.count
    
    def pulse(self, index: int, color: Tuple[int, int, int],
              duration: float = 1.0, times: int = 3):
        """脉冲闪烁"""
        for _ in range(times):
            self.set(index, color)
            self._show()
            time.sleep(duration / 2)
            self.set(index, COLORS["off"])
            self._show()
            time.sleep(duration / 2)
    
    def _show(self):
        """刷新硬件"""
        if self._hw_available:
            from rpi_ws281x import Color
            for i, (r, g, b) in enumerate(self.leds):
                self.strip.setPixelColor(i, Color(r, g, b))
            self.strip.show()
    
    def status_display(self, status: dict):
        """根据系统状态更新全部 LED"""
        # [0] 系统状态
        sys_status = status.get("system", "ok")
        self.set(0, COLORS["green"] if sys_status == "ok" else 
                    COLORS["red"] if sys_status == "error" else COLORS["blue"])
        
        # [1] 市场情绪
        score = status.get("score", 50)
        if score >= 65:
            self.set(1, COLORS["green"])
        elif score >= 50:
            self.set(1, COLORS["yellow"])
        else:
            self.set(1, COLORS["red"])
        
        # [2] 盈亏
        pnl = status.get("pnl", 0)
        if pnl > 0:
            self.set(2, COLORS["green"])
        elif pnl < 0:
            self.set(2, COLORS["red"])
        else:
            self.set(2, COLORS["off"])
        
        # [3] 信号强度
        confidence = status.get("signal_confidence", 0)
        if confidence > 0:
            intensity = int(min(255, confidence * 2.55))
            self.set(3, (0, intensity, 0) if confidence > 50 else (intensity, intensity, 0))
        else:
            self.set(3, COLORS["off"])
        
        # [4] 告警级别
        alert = status.get("alert_level", "")
        if alert == "P0":
            self.set(4, COLORS["red"])
        elif alert == "P1":
            self.set(4, COLORS["yellow"])
        elif alert == "P2":
            self.set(4, COLORS["blue"])
        else:
            self.set(4, COLORS["off"])
        
        # [5] 数据连接
        self.set(5, COLORS["green"] if status.get("data_ok", True) else COLORS["off"])
        
        # [6] CPU 温度
        temp = status.get("cpu_temp", 50)
        if temp < 50:
            self.set(6, COLORS["green"])
        elif temp < 70:
            ratio = (temp - 50) / 20
            self.set(6, (int(255 * ratio), int(255 * (1 - ratio)), 0))
        else:
            self.set(6, COLORS["red"])
        
        # [7] 网络
        self.set(7, COLORS["green"] if status.get("network_ok", True) else COLORS["off"])
        
        self._show()
    
    def startup_animation(self):
        """启动动画"""
        for i in range(self.count):
            self.set(i, COLORS["green"])
            self._show()
            time.sleep(0.1)
        time.sleep(0.3)
        for i in range(self.count):
            self.set(i, COLORS["off"])
            self._show()
            time.sleep(0.05)
    
    def shutdown_animation(self):
        """关机动画"""
        for i in range(self.count - 1, -1, -1):
            self.set(i, COLORS["red"])
            self._show()
            time.sleep(0.1)
        time.sleep(0.3)
        self.set_all(COLORS["off"])
        self._show()


# ═══════════════════════════════════════
# 监控线程
# ═══════════════════════════════════════

class LEDMonitorThread(threading.Thread):
    """LED 状态监控线程 — 定时更新"""
    
    def __init__(self, led: LEDController, api_url: str = "http://localhost:8000",
                 interval: float = 5.0):
        super().__init__(daemon=True)
        self.led = led
        self.api_url = api_url
        self.interval = interval
        self._running = False
    
    def run(self):
        self._running = True
        self.led.startup_animation()
        
        while self._running:
            try:
                status = self._fetch_status()
                self.led.status_display(status)
            except Exception as e:
                _log.error(f"LED 更新失败: {e}")
                self.led.set(0, COLORS["red"])
                self.led._show()
            
            time.sleep(self.interval)
    
    def stop(self):
        self._running = False
        self.led.shutdown_animation()
    
    def _fetch_status(self) -> dict:
        """从 API 获取状态"""
        import requests
        try:
            r = requests.get(f"{self.api_url}/health", timeout=5)
            health = r.json()
            
            # 获取交易统计
            r2 = requests.get(f"{self.api_url}/log/stats", timeout=5)
            stats = r2.json()
            
            # CPU 温度
            cpu_temp = 50
            try:
                with open("/sys/class/thermal/thermal_zone0/temp") as f:
                    cpu_temp = int(f.read()) / 1000
            except:
                pass
            
            return {
                "system": "ok" if health.get("status") == "ok" else "error",
                "score": 50,  # 后续可以从瞭望塔获取
                "pnl": stats.get("total_pnl", 0),
                "signal_confidence": stats.get("win_rate", 0),
                "alert_level": "",
                "data_ok": True,
                "cpu_temp": cpu_temp,
                "network_ok": True,
            }
        except Exception:
            return {"system": "error"}


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    p = argparse.ArgumentParser(description="小红 LED 灯带控制器")
    p.add_argument("--test", action="store_true", help="测试动画")
    p.add_argument("--monitor", action="store_true", help="启动监控")
    p.add_argument("--api", default="http://localhost:8000", help="API 地址")
    args = p.parse_args()
    
    led = LEDController()
    
    if args.test:
        print("🎨 启动动画...")
        led.startup_animation()
        time.sleep(0.5)
        
        print("🟢 全绿")
        led.set_all(COLORS["green"]); led._show(); time.sleep(1)
        
        print("🔴 全红")
        led.set_all(COLORS["red"]); led._show(); time.sleep(1)
        
        print("🔵 全蓝")
        led.set_all(COLORS["blue"]); led._show(); time.sleep(1)
        
        print("💡 关闭")
        led.set_all(COLORS["off"]); led._show()
    
    elif args.monitor:
        print(f"🔄 启动 LED 监控 (API: {args.api})")
        monitor = LEDMonitorThread(led, api_url=args.api)
        try:
            monitor.start()
            monitor.join()
        except KeyboardInterrupt:
            monitor.stop()
    
    else:
        # 快速状态更新
        led.status_display({
            "system": "ok", "score": 60, "pnl": 10000,
            "signal_confidence": 75, "alert_level": "",
            "data_ok": True, "cpu_temp": 55, "network_ok": True,
        })
        led._show()
        print("✅ LED 状态已更新")
