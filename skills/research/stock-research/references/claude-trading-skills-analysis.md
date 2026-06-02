# Claude Trading Skills 生态分析

> 三个关键仓库的深度对比，以及对小红系统的借鉴

## 三大仓库

| 仓库 | Stars | Skills | 定位 | 借鉴价值 |
|------|:--:|:--:|------|:--:|
| tradermonty/claude-trading-skills | 1.7k | 49 | 美股全流程 | 架构骨架 |
| agiprolabs/claude-trading-skills | 32 | 62 | Crypto/DeFi 工具包 | 分类参考 |
| algoderiv/agent-skills | 56 | 7 | 中国量化平台(CTP/天勤/米筐) | 内容适配 |

## Skills vs MCP：互补关系

```
Skills 方案                     MCP 方案
AI读SKILL.md → 按指令执行      AI调MCP Tool → 拿结构化数据
声明式文档 (Markdown)          程序化接口 (JSON Schema)
灵活修改，无需部署              确定性强，可测试
知识传递为主                    数据获取+执行为主
```

## 小红融合架构

```
┌────────────────────────────────┐
│         小红 Agent              │
│  ┌──────────────┐ ┌──────────┐ │
│  │ Skills 引擎   │ │ MCP工具层 │ │
│  │ 8 skills      │ │ 17 tools │ │
│  │ 3 workflows   │ │ 5 servers│ │
│  │ 4 skillsets   │ │          │ │
│  └──────────────┘ └──────────┘ │
│  Skills → "做什么、何时做"       │
│  MCP    → "拿数据、执行操作"      │
└────────────────────────────────┘
```

## 四级渐进加载（来自 tradermonty）

1. **元数据** (skills-index.yaml) — 技能发现阶段
2. **正文** (SKILL.md) — 技能被调用时
3. **references/** — 按需条件加载
4. **scripts/** — 手动执行，不自动加载

## 关键设计模式

- **Workflow YAML**：声明式多技能链式调用，含决策门
- **Skillsets**：按目标场景预组合技能套装
- **Dual-Axis 评分**：元数据+工作流+执行安全+制品+测试
- **MCP Bridge**：Skill ↔ MCP Tool 双向映射
