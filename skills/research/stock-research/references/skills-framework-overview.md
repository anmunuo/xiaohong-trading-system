# 小红 Skills 框架总览

> 对标 tradermonty/claude-trading-skills 的声明式技能架构

## 目录结构

```
skills-framework/
├── CLAUDE.md                       # Claude Code 项目配置
├── skills-index.yaml                # 权威技能注册表（8 skills × 4 类别）
├── skills/                          # 8 个技能
│   ├── a-share-market-regime/       # 市场体制分析（五因子评分）
│   ├── a-share-screener/            # 多因子选股（PE/PB/ROE/动量/北向）
│   ├── position-sizer-cn/           # 仓位计算（固定分数/ATR/凯利）
│   ├── risk-manager-cn/             # 风控管理（止损/移动止盈/凯利）
│   ├── trade-journal-cn/            # 交易日志（CSV+SQLite+统计）
│   ├── watchtower-skill/            # 瞭望塔盘前宏观（v6.0多维交叉验证）
│   ├── decision-officer/            # 决策官盘中决策（LLM驱动）
│   └── post-market-review/          # 盘后复盘
├── workflows/                       # 3 个操作流程
│   ├── daily-market-scan.yaml       # 每日盘前市场扫描
│   ├── daily-decision.yaml          # 盘中综合决策
│   └── weekly-review.yaml           # 周度深度复盘
├── skillsets/skillsets.yaml         # 4 个场景套装
├── mcp-bridge/skill-to-mcp.yaml     # MCP ↔ Skill 双向映射
└── docs/                            # 文档
```

## 技能模板 (SKILL.md)

```yaml
---
name: skill-name
description: 简短描述（触发条件包含在内）
mcp_servers: [server1, server2]
api_profile: basic|pro
estimated_minutes: N
---

# 技能标题

## Overview       — 一句话说明
## When to Use    — 触发条件
## Prerequisites  — 前置条件
## Workflow       — 分步骤执行流程（Step 1 → Step N）
## Output         — 产出物说明
## Resources      — references/ + scripts/ 索引
```

## 与 MCP 工具的关系

技能内的 Workflow 步骤通过 `mcp: tool_name` 标记调用 MCP 工具。
MCP 工具提供数据获取和执行能力，技能提供领域知识和决策框架。

详见 `mcp-bridge/skill-to-mcp.yaml` 的完整映射。
