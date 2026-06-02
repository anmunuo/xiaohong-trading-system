# 小红 Skills 框架 — CLAUDE.md
# ================================
# Claude Code 项目级配置指引
# 对标 tradermonty/claude-trading-skills → CLAUDE.md

## 项目概述

这是安幕诺家族小红的 AI 交易辅助 Skills 框架。采用 tradermonty/claude-trading-skills 的声明式技能架构，与 MCP 工具层互补协作。

## 目录结构

```
skills-framework/
├── CLAUDE.md                    ← 本文件
├── skills-index.yaml            ← 权威技能注册表
├── skills/                      ← 8 个技能（SKILL.md + references + scripts）
├── workflows/                   ← 3 个操作流程 YAML
├── skillsets/                   ← 4 个场景安装包
├── mcp-bridge/                  ← MCP ↔ Skill 映射
└── docs/                        ← 文档
```

## 如何使用

### 加载技能索引

读取 `skills-index.yaml` 了解全部可用技能。

### 执行单个技能

阅读对应 `skills/<name>/SKILL.md`，按其 Workflow 步骤执行。

### 执行工作流

读取 `workflows/<name>.yaml`，按 steps 顺序链式调用技能。

### 安装技能套装

根据用户需求选择 `skillsets/skillsets.yaml` 中的套装，加载其中列出的所有技能。

## 四级加载机制

1. **元数据**: skills-index.yaml（技能发现阶段）
2. **正文**: SKILL.md（技能被调用时）
3. **references/**: 按需加载（详细方法论）
4. **scripts/**: 手动执行（CLI 命令）

## 与 MCP 工具的关系

Skills 告诉 Claude "做什么" → Claude 调用 MCP 工具 "拿数据/执行操作"

映射关系见 `mcp-bridge/skill-to-mcp.yaml`

## 关键约定

- 所有技能必须先在 skills-index.yaml 注册
- SKILL.md 使用 YAML frontmatter + Markdown 正文
- 工作流中的 decision_gate 步骤需要人工确认
- MCP 工具调用通过 Hermes Agent 自动路由
