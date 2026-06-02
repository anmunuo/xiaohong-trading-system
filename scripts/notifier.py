#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 通知中心
================================
四通道通知：飞书 | 微信服务通知 | 邮件 | 短信
三级告警：  P0(紧急) | P1(警告) | P2(信息)

架构：
  NotificationCenter
    ├─ FeishuNotifier    → 飞书 Webhook / API
    ├─ WechatNotifier    → 微信服务号模板消息
    ├─ EmailNotifier     → SMTP 邮件
    └─ SMSNotifier       → 阿里云短信 / Twilio

参照 TradingSkill 的 slack MCP server 模式
"""
import os
import json
import time
import smtplib
import logging
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum
from collections import deque

_log = logging.getLogger("notifier")


# ═══════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════

class AlertLevel(Enum):
    P0_CRITICAL = "P0"   # 紧急：止损触发/爆仓风险
    P1_WARNING = "P1"     # 警告：接近止损/仓位超标
    P2_INFO = "P2"        # 信息：信号提醒/报告生成

class Channel(Enum):
    FEISHU = "feishu"
    WECHAT = "wechat"  
    EMAIL = "email"
    SMS = "sms"

@dataclass
class Alert:
    """告警消息"""
    level: AlertLevel
    title: str
    message: str
    timestamp: str = ""
    source: str = "xiaohong-engine"
    data: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def emoji(self) -> str:
        return {"P0": "🔴", "P1": "🟡", "P2": "🔵"}.get(self.level.value, "⚪")

    def to_feishu_card(self) -> dict:
        """飞书卡片消息"""
        colors = {"P0": "red", "P1": "yellow", "P2": "blue"}
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": f"{self.emoji} {self.title}"},
                    "template": colors.get(self.level.value, "blue"),
                },
                "elements": [
                    {"tag": "div", "text": {"tag": "lark_md", "content": self.message}},
                    {"tag": "hr"},
                    {"tag": "note", "elements": [
                        {"tag": "plain_text", "content": f"来源: {self.source} · {self.timestamp[:19]}"}
                    ]},
                ],
            },
        }


# ═══════════════════════════════════════
# 通道基类
# ═══════════════════════════════════════

class BaseNotifier:
    """通知通道基类"""
    channel: Channel
    enabled: bool = True

    async def send(self, alert: Alert) -> bool:
        raise NotImplementedError


# ═══════════════════════════════════════
# 飞书通知
# ═══════════════════════════════════════

class FeishuNotifier(BaseNotifier):
    """飞书通知 — Webhook + 卡片消息"""
    channel = Channel.FEISHU

    def __init__(self, webhook_url: str = None):
        self.webhook_url = webhook_url or os.environ.get("FEISHU_WEBHOOK_URL", "")
        self.app_id = os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = os.environ.get("FEISHU_APP_SECRET", "")
        self.enabled = bool(self.webhook_url or self.app_id)

    async def send(self, alert: Alert) -> bool:
        if not self.enabled:
            return False
        
        try:
            import requests
            if self.webhook_url:
                # Webhook 模式
                card = alert.to_feishu_card()
                resp = requests.post(self.webhook_url, json=card, timeout=10)
                ok = resp.status_code == 200
                if ok:
                    _log.info(f"📤 飞书: {alert.title}")
                return ok
            elif self.app_id:
                # API 模式（需 tenant_access_token）
                _log.warning("飞书 API 模式需要额外配置，当前回退到日志")
                return False
        except Exception as e:
            _log.error(f"飞书推送失败: {e}")
            return False


# ═══════════════════════════════════════
# 微信通知
# ═══════════════════════════════════════

class WechatNotifier(BaseNotifier):
    """微信服务号模板消息通知"""
    channel = Channel.WECHAT

    def __init__(self):
        self.appid = os.environ.get("WECHAT_APPID", "")
        self.appsecret = os.environ.get("WECHAT_APPSECRET", "")
        self.template_id = os.environ.get("WECHAT_TEMPLATE_ID", "")
        self.openids = (os.environ.get("WECHAT_OPENIDS", "")).split(",")
        self.enabled = bool(self.appid and self.appsecret and self.template_id)

    async def send(self, alert: Alert) -> bool:
        if not self.enabled:
            return False
        
        try:
            import requests
            # 获取 access_token
            token_resp = requests.get(
                "https://api.weixin.qq.com/cgi-bin/token",
                params={
                    "grant_type": "client_credential",
                    "appid": self.appid,
                    "secret": self.appsecret,
                },
                timeout=10,
            ).json()
            access_token = token_resp.get("access_token")
            if not access_token:
                _log.error(f"微信 token 获取失败: {token_resp}")
                return False

            # 发送模板消息
            for openid in self.openids:
                if not openid.strip():
                    continue
                data = {
                    "touser": openid.strip(),
                    "template_id": self.template_id,
                    "data": {
                        "first": {"value": f"{alert.emoji} {alert.title}", "color": "#ff0000" if alert.level == AlertLevel.P0_CRITICAL else "#ffaa00"},
                        "keyword1": {"value": alert.level.value},
                        "keyword2": {"value": alert.source},
                        "keyword3": {"value": alert.timestamp[:19]},
                        "remark": {"value": alert.message[:100]},
                    },
                }
                resp = requests.post(
                    f"https://api.weixin.qq.com/cgi-bin/message/template/send?access_token={access_token}",
                    json=data, timeout=10,
                )
            
            _log.info(f"📱 微信: {alert.title} → {len(self.openids)} 用户")
            return True
        except Exception as e:
            _log.error(f"微信推送失败: {e}")
            return False


# ═══════════════════════════════════════
# 邮件通知
# ═══════════════════════════════════════

class EmailNotifier(BaseNotifier):
    """邮件通知 — SMTP"""
    channel = Channel.EMAIL

    def __init__(self):
        self.host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.environ.get("SMTP_PORT", 587))
        self.user = os.environ.get("SMTP_USER", "")
        self.password = os.environ.get("SMTP_PASSWORD", "")
        self.to_addrs = (os.environ.get("ALERT_EMAILS", "")).split(",")
        self.enabled = bool(self.user and self.password and self.to_addrs[0])

    async def send(self, alert: Alert) -> bool:
        if not self.enabled:
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = self.user
            msg["To"] = ", ".join(a.strip() for a in self.to_addrs if a.strip())
            msg["Subject"] = f"[{alert.level.value}] {alert.emoji} {alert.title} — 小红"
            
            body = f"""
<html>
<body style="font-family: sans-serif; max-width: 600px;">
    <div style="background: {'#ef4444' if alert.level == AlertLevel.P0_CRITICAL else '#f59e0b' if alert.level == AlertLevel.P1_WARNING else '#3b82f6'}; color: white; padding: 16px; border-radius: 8px 8px 0 0;">
        <h2 style="margin: 0;">{alert.emoji} {alert.level.value} — {alert.title}</h2>
    </div>
    <div style="border: 1px solid #e5e7eb; padding: 16px; border-radius: 0 0 8px 8px;">
        <p>{alert.message}</p>
        <hr>
        <p style="color: #6b7280; font-size: 12px;">
            来源: {alert.source} · {alert.timestamp[:19]}<br>
            安幕诺家族 · 小红 🌹 交易系统
        </p>
    </div>
</body>
</html>
            """
            msg.attach(MIMEText(body, "html", "utf-8"))

            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                server.starttls()
                server.login(self.user, self.password)
                server.send_message(msg)

            _log.info(f"📧 邮件: {alert.title} → {len(self.to_addrs)} 收件人")
            return True
        except Exception as e:
            _log.error(f"邮件发送失败: {e}")
            return False


# ═══════════════════════════════════════
# 短信通知
# ═══════════════════════════════════════

class SMSNotifier(BaseNotifier):
    """短信通知 — 仅 P0 级别"""
    channel = Channel.SMS
    
    def __init__(self):
        self.provider = os.environ.get("SMS_PROVIDER", "")  # aliyun / twilio
        self.enabled = bool(self.provider)

    async def send(self, alert: Alert) -> bool:
        if not self.enabled or alert.level != AlertLevel.P0_CRITICAL:
            return False
        
        # 仅 P0 用短信（占位）
        _log.info(f"📱 SMS(P0): {alert.title}")
        return False  # 需要真实服务商配置


# ═══════════════════════════════════════
# 通知中心
# ═══════════════════════════════════════

class NotificationCenter:
    """统一通知中心 — TradingSkill 风格"""
    
    def __init__(self):
        self.channels: Dict[Channel, BaseNotifier] = {
            Channel.FEISHU: FeishuNotifier(),
            Channel.WECHAT: WechatNotifier(),
            Channel.EMAIL: EmailNotifier(),
            Channel.SMS: SMSNotifier(),
        }
        
        # 历史记录（防重复）
        self.history: deque = deque(maxlen=200)
        
        # P0 通道白名单：所有通道
        self.p0_channels = [Channel.FEISHU, Channel.WECHAT, Channel.EMAIL]
        # P1 通道
        self.p1_channels = [Channel.FEISHU, Channel.EMAIL]
        # P2 通道
        self.p2_channels = [Channel.FEISHU]

    async def alert(self, level: AlertLevel, title: str, message: str,
                    source: str = "xiaohong-engine", data: dict = None):
        """发送告警"""
        alert = Alert(level=level, title=title, message=message,
                      source=source, data=data or {})
        
        # 去重（相同标题5分钟内不重复）
        key = f"{level.value}:{title}:{message[:50]}"
        now = time.time()
        for h_key, h_time in self.history:
            if h_key == key and now - h_time < 300:
                return
        
        self.history.append((key, now))
        
        # 选择通道
        channel_map = {
            AlertLevel.P0_CRITICAL: self.p0_channels,
            AlertLevel.P1_WARNING: self.p1_channels,
            AlertLevel.P2_INFO: self.p2_channels,
        }
        targets = channel_map.get(level, self.p2_channels)
        
        results = {}
        for ch in targets:
            notifier = self.channels.get(ch)
            if notifier and notifier.enabled:
                try:
                    ok = await notifier.send(alert)
                    results[ch.value] = "OK" if ok else "FAIL"
                except Exception as e:
                    results[ch.value] = f"ERROR: {e}"
        
        _log.info(f"🔔 告警 [{level.value}] {title} → {results}")
        return results

    def status(self) -> dict:
        """各通道状态"""
        return {
            ch.value: {
                "enabled": self.channels[ch].enabled,
                "type": self.channels[ch].__class__.__name__,
            }
            for ch in Channel
        }


# ═══════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════

_notification_center: Optional[NotificationCenter] = None

def get_notification_center() -> NotificationCenter:
    global _notification_center
    if _notification_center is None:
        _notification_center = NotificationCenter()
    return _notification_center


# ═══════════════════════════════════════
# 便捷函数
# ═══════════════════════════════════════

async def alert_critical(title: str, message: str, **kwargs):
    """P0 紧急告警"""
    return await get_notification_center().alert(AlertLevel.P0_CRITICAL, title, message, **kwargs)

async def alert_warning(title: str, message: str, **kwargs):
    """P1 警告"""
    return await get_notification_center().alert(AlertLevel.P1_WARNING, title, message, **kwargs)

async def alert_info(title: str, message: str, **kwargs):
    """P2 信息"""
    return await get_notification_center().alert(AlertLevel.P2_INFO, title, message, **kwargs)


# ═══════════════════════════════════════
# CLI 测试
# ═══════════════════════════════════════

if __name__ == "__main__":
    import asyncio
    
    async def test():
        nc = NotificationCenter()
        print("📡 通知中心状态:")
        for ch, info in nc.status().items():
            icon = "✅" if info["enabled"] else "❌"
            print(f"  {icon} {ch}: {info['type']}")
        
        print("\n🔔 发送测试告警...")
        await nc.alert(AlertLevel.P2_INFO, "系统测试", "通知中心初始化完成", source="test")
        print("✅ 测试完成")
    
    asyncio.run(test())
