#!/usr/bin/env python3
"""
报告美化模块 - v1.0
==================
统一报告输出格式化，支持两种模式：
  1. markdown  — cron no_agent stdout 投递（Feishu 渲染友好）
  2. card      — 飞书交互卡片（标题栏颜色、分栏、分割线、按钮）

用法:
  from report_formatter import Report
  r = Report(title="弹药库风控", icon="🛡️", color="red")
  r.section("持仓概览")
  r.kv("英唐智控", "🟢 +42.4%", "仓位 39.7% ⚠️")
  r.alert("双良节能 4/5 批次止损触发", "critical")
  print(r.markdown())   # 或 r.card() 用于飞书卡片
"""

from datetime import datetime
from typing import List, Tuple, Optional


class Report:
    """统一报告构建器"""

    def __init__(self, title: str, icon: str = "📊", color: str = "blue"):
        self.title = title
        self.icon = icon
        self.color = color  # blue/green/red/yellow/purple
        self._sections: List[dict] = []  # {type, content}
        self._alerts: List[Tuple[str, str]] = []  # (msg, level)
        self._footer = ""
        self._header_meta = {}  # {key: value} for subtitle info

    def header_meta(self, **kwargs):
        """设置标题下方的元信息"""
        self._header_meta.update(kwargs)
        return self

    def section(self, title: str):
        """添加章节标题"""
        self._sections.append({"type": "section", "title": title})
        return self

    def text(self, content: str):
        """添加文本段落"""
        self._sections.append({"type": "text", "content": content})
        return self

    def kv(self, key: str, value: str, sub: str = ""):
        """添加键值对"""
        self._sections.append({"type": "kv", "key": key, "value": value, "sub": sub})
        return self

    def table(self, headers: list, rows: list):
        """添加表格"""
        self._sections.append({"type": "table", "headers": headers, "rows": rows})
        return self

    def divider(self):
        """添加分割线"""
        self._sections.append({"type": "divider"})
        return self

    def alert(self, msg: str, level: str = "warning"):
        """添加告警 (critical/warning/info)"""
        self._alerts.append((msg, level))
        return self

    def footer(self, text: str):
        """设置页脚"""
        self._footer = text
        return self

    # ==================== Markdown 输出 ====================

    def markdown(self) -> str:
        """生成增强 Markdown（Feishu 渲染优化）"""
        lines = []

        # 标题
        color_hex = {"red": "#D32F2F", "green": "#388E3C", "blue": "#1976D2",
                     "yellow": "#F57C00", "purple": "#7B1FA2"}.get(self.color, "#1976D2")
        lines.append(f"**{self.icon} {self.title}**")
        lines.append("")

        # 元信息
        if self._header_meta:
            meta_parts = []
            for k, v in self._header_meta.items():
                meta_parts.append(f"{k}：{v}")
            lines.append(" | ".join(meta_parts))
            lines.append("")

        has_content = False

        for sec in self._sections:
            t = sec["type"]

            if t == "section":
                lines.append(f"**▸ {sec['title']}**")
                lines.append("")
                has_content = True

            elif t == "text":
                lines.append(sec["content"])
                lines.append("")
                has_content = True

            elif t == "kv":
                sub_str = f"  {sec['sub']}" if sec.get("sub") else ""
                lines.append(f"  {sec['key']}：{sec['value']}{sub_str}")
                has_content = True

            elif t == "table":
                h = sec["headers"]
                r = sec["rows"]
                lines.append("| " + " | ".join(h) + " |")
                lines.append("|" + "|".join(["------"] * len(h)) + "|")
                for row in r:
                    lines.append("| " + " | ".join(str(c) for c in row) + " |")
                lines.append("")
                has_content = True

            elif t == "divider":
                if has_content:
                    lines.append("---")
                    lines.append("")
                    has_content = False

        # 告警汇总
        if self._alerts:
            lines.append("")
            for msg, level in self._alerts:
                icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
                lines.append(f"{icons.get(level, '⚪')} {msg}")

        # 页脚
        if self._footer:
            lines.append("")
            lines.append(f"*{self._footer}*")

        return "\n".join(lines)

    # ==================== 飞书卡片输出 ====================

    def card(self) -> dict:
        """生成飞书交互卡片 JSON"""
        elements = []

        # 颜色映射
        template_colors = {"blue": "blue", "green": "green", "red": "red",
                          "yellow": "yellow", "purple": "purple"}

        # 标题栏
        title_text = f"{self.icon} {self.title}"
        if self._header_meta:
            subtitle = " | ".join(f"**{k}** {v}" for k, v in self._header_meta.items())
        else:
            subtitle = ""

        for sec in self._sections:
            t = sec["type"]

            if t == "section":
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"**▸ {sec['title']}**"}
                })

            elif t == "text":
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": sec["content"]}
                })

            elif t == "kv":
                sub_part = f"  <font color='grey'>{sec['sub']}</font>" if sec.get("sub") else ""
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": f"{sec['key']}：{sec['value']}{sub_part}"}
                })

            elif t == "table":
                # 转为 markdown 表格
                h = sec["headers"]
                r = sec["rows"]
                md = "\n" + "| " + " | ".join(h) + " |\n"
                md += "|" + "|".join(["------"] * len(h)) + "|\n"
                for row in r:
                    md += "| " + " | ".join(str(c) for c in row) + " |\n"
                elements.append({
                    "tag": "div",
                    "text": {"tag": "lark_md", "content": md}
                })

            elif t == "divider":
                elements.append({"tag": "hr"})

        # 告警汇总
        if self._alerts:
            alert_lines = []
            for msg, level in self._alerts:
                icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
                color_tag = {"critical": "red", "warning": "orange", "info": "grey"}
                c = color_tag.get(level, "grey")
                alert_lines.append(f"<font color='{c}'>{icons.get(level, '⚪')} {msg}</font>")
            elements.append({
                "tag": "div",
                "text": {"tag": "lark_md", "content": "\n".join(alert_lines)}
            })

        # 页脚
        if self._footer:
            elements.append({"tag": "hr"})
            elements.append({
                "tag": "note",
                "elements": [{"tag": "plain_text", "content": self._footer}]
            })

        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title_text},
                "template": template_colors.get(self.color, "blue"),
            },
            "elements": elements,
        }

        if subtitle:
            card["header"]["subtitle"] = {"tag": "plain_text", "content": subtitle}

        return card
