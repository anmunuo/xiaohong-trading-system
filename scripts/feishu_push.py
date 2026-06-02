#!/usr/bin/env python3.11
# -*- coding: utf-8 -*-
"""
飞书推送助手

根据报告类型自动选择推送目标，避免推送错群

作者：小红 🌹
创建：2026-04-06 02:15
"""

import os
import json
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent

# 加载配置
load_dotenv(SCRIPT_DIR.parent / '.env.feishu')

# Webhook 映射
WEBHOOK_MAP = {
    'watchtower': 'FEISHU_WEBHOOK_WATCHTOWER',  # 瞭望塔群 - 宏观战略
    'scout': 'FEISHU_WEBHOOK_SCOUT',            # 侦察兵群 - 选股推荐
    'sniper': 'FEISHU_WEBHOOK_SNIPER',          # 狙击手群 - 交易信号
    'ammo': 'FEISHU_WEBHOOK_AMMO',              # 弹药库群 - 风控报告
    'review': 'FEISHU_WEBHOOK_REVIEW',          # 文工团群 - 复盘报告
}

# 群名称映射
GROUP_NAME_MAP = {
    'watchtower': '瞭望塔群',
    'scout': '侦察兵群',
    'sniper': '狙击手群',
    'ammo': '弹药库群',
    'review': '文工团群',
}


def get_token() -> str:
    """获取飞书 token"""
    app_id = os.getenv('FEISHU_APP_ID')
    app_secret = os.getenv('FEISHU_APP_SECRET')
    
    token_url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    token_response = requests.post(token_url, json={"app_id": app_id, "app_secret": app_secret}, timeout=10)
    
    return token_response.json().get('tenant_access_token')


def push_report(report_type: str, title: str, content: str, doc_link: str = None, pdf_path: str = None) -> bool:
    """
    推送报告到对应群聊
    
    Args:
        report_type: 报告类型
          - 'watchtower': 宏观战略报告 → 瞭望塔群
          - 'scout': 选股推荐报告 → 侦察兵群
          - 'sniper': 交易信号报告 → 狙击手群
          - 'ammo': 风控报告 → 弹药库群
          - 'review': 复盘报告 → 文工团群
        
        title: 报告标题
        
        content: 报告内容摘要
        
        doc_link: 云文档链接（可选）
        
        pdf_path: PDF 文件路径（可选）
    
    Returns:
        推送是否成功
    
    Examples:
        # 推送宏观战略报告
        push_report('watchtower', '瞭望塔宏观战略报告', '核心观点：市场偏暖...')
        
        # 推送个股分析报告
        push_report('scout', '双良节能深度分析', '评级：4 星，目标 +15-20%')
        
        # 推送交易信号
        push_report('sniper', '中微公司买入信号', '技术面突破，资金流入')
    """
    # 验证报告类型
    if report_type not in WEBHOOK_MAP:
        print(f"❌ 无效的报告类型：{report_type}")
        print(f"   有效类型：{list(WEBHOOK_MAP.keys())}")
        return False
    
    # 获取 webhook
    webhook_env = WEBHOOK_MAP[report_type]
    webhook_url = os.getenv(webhook_env)
    
    if not webhook_url:
        print(f"❌ 未找到 webhook：{webhook_env}")
        return False
    
    # 获取群名称
    group_name = GROUP_NAME_MAP.get(report_type, '未知群')
    print(f"📤 推送到：{group_name}")
    
    # 获取 token
    token = get_token()
    if not token:
        print(f"❌ 获取 token 失败")
        return False
    
    # 上传 PDF 文件（如果有）
    file_key = None
    if pdf_path and os.path.exists(pdf_path):
        print(f"📄 上传 PDF: {pdf_path}")
        print(f"📊 文件大小：{os.path.getsize(pdf_path)/1024:.1f}KB")
        
        file_url = "https://open.feishu.cn/open-apis/im/v1/files"
        file_headers = {"Authorization": f"Bearer {token}"}
        
        with open(pdf_path, 'rb') as f:
            file_response = requests.post(file_url, headers=file_headers, files={'file': f}, data={'file_type': 'pdf'}, timeout=60)
        
        file_result = file_response.json()
        
        if file_result.get('code') == 0:
            file_key = file_result['data']['file_key']
            print(f"✅ PDF 上传成功：{file_key}")
        else:
            print(f"❌ PDF 上传失败：{file_result}")
    
    # 构建卡片消息
    card_content = f'**{title}**\n\n📅 {datetime.now().strftime("%Y-%m-%d %H:%M")}\n\n{content}'
    
    if file_key:
        card_content += f'\n\n📊 PDF: {os.path.getsize(pdf_path)/1024:.1f}KB'
    
    card = {
        'msg_type': 'interactive',
        'card': {
            'config': {'wide_screen_mode': True},
            'elements': [
                {
                    'tag': 'div',
                    'text': {
                        'tag': 'lark_md',
                        'content': card_content
                    }
                }
            ]
        }
    }
    
    # 添加按钮（如果有链接）
    if doc_link or file_key:
        actions = []
        
        if doc_link:
            actions.append({
                'tag': 'button',
                'text': {'tag': 'plain_text', 'content': '📄 查看云文档'},
                'url': doc_link,
                'type': 'primary'
            })
        
        if file_key:
            actions.append({
                'tag': 'button',
                'text': {'tag': 'plain_text', 'content': '💾 下载 PDF'},
                'url': f'https://open.feishu.cn/open-apis/drive/v1/files/{file_key}/download',
                'type': 'default'
            })
        
        card['card']['elements'].append({
            'tag': 'action',
            'actions': actions
        })
    
    # 添加备注
    note_text = {
        'watchtower': '💡 宏观战略 · 市场研判',
        'scout': '💡 个股分析 · 侦察兵推荐',
        'sniper': '💡 交易信号 · 狙击手执行',
        'ammo': '💡 风控管理 · 持仓监控',
        'review': '💡 复盘总结 · 策略优化',
    }
    
    card['card']['elements'].append({
        'tag': 'note',
        'elements': [{'tag': 'plain_text', 'content': note_text.get(report_type, '')}]
    })
    
    # 发送消息（带重试机制）
    import time
    max_retries = 3
    result = None
    for attempt in range(max_retries):
        try:
            result = requests.post(webhook_url, json=card, timeout=30).json()
            print(f'\n卡片推送结果：{result}')
            
            # 成功
            if result.get('code') == 0 or result.get('StatusCode') == 0:
                break
            
            # 频率限制 → 等待后重试
            if result.get('code') == 11232:
                wait = 10 * (attempt + 1)  # 10s, 20s, 30s
                print(f"⏳ 频率限制，等待 {wait}s 后重试 ({attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            
            # 其他错误不重试
            break
        except Exception as e:
            print(f"⚠️ 请求异常：{e}")
            if attempt < max_retries - 1:
                time.sleep(5)
            result = {'code': -1, 'msg': str(e)}
    
    if result.get('code') == 0 or result.get('StatusCode') == 0:
        print(f"✅ 报告已推送到{group_name}！")
        return True
    else:
        print(f"❌ 推送失败：{result}")
        _send_alert(report_type, title, result)
        return False


def _send_alert(report_type: str, title: str, error_detail: dict):
    """
    推送失败时，通过飞书 API 直接通知老大（绕过 webhook 限流）
    """
    alert_open_ids = os.getenv('ALERT_OPEN_IDS', '')
    if not alert_open_ids:
        print("⚠️ 未配置 ALERT_OPEN_IDS，跳过告警")
        return

    app_id = os.getenv('FEISHU_APP_ID')
    app_secret = os.getenv('FEISHU_APP_SECRET')
    if not app_id or not app_secret:
        print("⚠️ 缺少飞书凭证，无法发送告警")
        return

    try:
        token = get_token()
        if not token:
            print("⚠️ 获取 token 失败，无法发送告警")
            return

        group_name = GROUP_NAME_MAP.get(report_type, '未知群')
        error_msg = error_detail.get('msg', str(error_detail))
        error_code = error_detail.get('code', 'unknown')

        alert_text = (
            f"🚨 推送失败告警\n\n"
            f"📋 报告：{title}\n"
            f"📤 目标群：{group_name}\n"
            f"❌ 错误码：{error_code}\n"
            f"💬 错误信息：{error_msg}\n"
            f"⏰ 时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"💡 报告已生成，但推送受阻。可手动查看日志获取内容。"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        for open_id in alert_open_ids.split(','):
            open_id = open_id.strip()
            if not open_id:
                continue

            msg_url = "https://open.feishu.cn/open-apis/im/v1/messages"
            params = {"receive_id_type": "open_id"}
            payload = {
                "receive_id": open_id,
                "msg_type": "text",
                "content": json.dumps({"text": alert_text})
            }

            resp = requests.post(msg_url, headers=headers, params=params, json=payload, timeout=10)
            resp_result = resp.json()
            if resp_result.get('code') == 0:
                print(f"🚨 告警已发送至 {open_id}")
            else:
                print(f"⚠️ 告警发送失败 ({open_id}): {resp_result}")

    except Exception as e:
        print(f"⚠️ 告警发送异常: {e}")


def push_text(group_type: str, text: str) -> bool:
    """
    推送纯文本消息
    
    Args:
        group_type: 群类型（watchtower/scout/sniper/ammo/review）
        text: 文本内容
    
    Returns:
        推送是否成功
    """
    if group_type not in WEBHOOK_MAP:
        print(f"❌ 无效的群类型：{group_type}")
        return False
    
    webhook_url = os.getenv(WEBHOOK_MAP[group_type])
    if not webhook_url:
        print(f"❌ 未找到 webhook")
        return False
    
    message = {
        'msg_type': 'text',
        'content': {'text': text}
    }
    
    result = requests.post(webhook_url, json=message, timeout=30).json()
    
    if result.get('code') == 0 or result.get('StatusCode') == 0:
        print(f"✅ 文本消息已推送到{GROUP_NAME_MAP.get(group_type, '未知群')}！")
        return True
    else:
        print(f"❌ 推送失败：{result}")
        return False


# 快捷函数
def push_watchtower(title: str, content: str, **kwargs) -> bool:
    """推送宏观战略报告到瞭望塔群"""
    return push_report('watchtower', title, content, **kwargs)


def push_scout(title: str, content: str, **kwargs) -> bool:
    """推送选股推荐到侦察兵群"""
    return push_report('scout', title, content, **kwargs)


def push_sniper(title: str, content: str, **kwargs) -> bool:
    """推送交易信号到狙击手群"""
    return push_report('sniper', title, content, **kwargs)


def push_ammo(title: str, content: str, **kwargs) -> bool:
    """推送风控报告到弹药库群"""
    return push_report('ammo', title, content, **kwargs)


def push_review(title: str, content: str, **kwargs) -> bool:
    """推送复盘报告到文工团群"""
    return push_report('review', title, content, **kwargs)


if __name__ == "__main__":
    # 测试
    print("=" * 80)
    print("🧪 飞书推送助手测试")
    print("=" * 80)
    
    # 测试 1: 推送宏观战略报告
    print("\n1. 测试推送宏观战略报告:")
    result = push_watchtower(
        title='🔭 瞭望塔宏观战略报告',
        content='核心观点：市场偏暖，建议 7-8 成仓位',
    )
    print(f"   结果：{'✅ 成功' if result else '❌ 失败'}")
    
    # 测试 2: 推送个股分析报告
    print("\n2. 测试推送个股分析报告:")
    result = push_scout(
        title='📊 双良节能 (600481) - 深度分析',
        content='评级：⭐⭐⭐⭐ (4/5 星)\n目标：+15-20%\n止损：R 值止损 (3:1 盈亏比)',
    )
    print(f"   结果：{'✅ 成功' if result else '❌ 失败'}")
    
    print("\n" + "=" * 80)
    print("✅ 测试完成")
    print("=" * 80)
