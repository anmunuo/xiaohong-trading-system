# 外部 Skills 生态参考

> 2026-05-30 调研。三个仓库的分析摘要，供小红 Skills 框架设计参考。

## 仓库速览

| 仓库 | Stars | Skills | 定位 | 小红适配度 |
|------|:--:|:--:|------|:--:|
| tradermonty/claude-trading-skills | 1.7k | 49 | 美股个人投资者全流程 | ⭐⭐⭐ 架构借鉴 |
| JoelLewis/finance_skills | 105 | 84 | 专业金融服务机构 | ⭐⭐⭐ 插件化+知识覆盖 |
| agiprolabs/claude-trading-skills | 32 | 62 | Crypto/DeFi量化工具包 | ⭐⭐ 分类借鉴 |
| algoderiv/agent-skills | 56 | 7 | 中国量化平台(CTP/天勤/米筐) | ⭐⭐⭐ 内容借鉴 |

## tradermonty 核心模式

- **四级渐进加载**：元数据(YAML frontmatter) → SKILL.md正文 → references/ → scripts/
- **Workflow YAML 编排**：`skills: [...] → steps: [...] → decision_gate: true/false`
- **Skillsets 场景套装**：按目标预组合技能
- **Skills-Index 元数据注册表**：`skills-index.yaml` 作为权威索引
- **Dual-Axis 评分**：元数据(20)+工作流(25)+安全(25)+制品(10)+测试(20)
- **Trader-Memory-Core**：投资论点生命周期追踪（idea→open→close→postmortem）

## JoelLewis 核心模式

- **分层插件架构**：core → wealth-management → trading-operations → compliance → advisory-practice → client-operations → data-integration
- **量化技能带Python / 知识技能纯SKILL.md**：只有core和wealth-management含脚本
- **符号链接安装**：`install.sh --plugin <name> [--target <dir>]`，依赖感知+去重
- **Marketplace注册**：`.claude-plugin/marketplace.json` 遵循 Anthropic 官方 schema
- **合规技能特征**：引用具体规则编号（FINRA/SEC/ERISA），场景化教学
- **技能模板**：Purpose → When to Use → Core Concepts → Worked Examples → Common Pitfalls → Cross-References

## 小红融合架构

```
Skills 层 (声明式):        MCP 层 (程序化):
  SKILL.md                 market-data-mcp (5 tools)
  workflows/*.yaml         strategy-mcp (4 tools)
  skillsets/*.yaml         execution-mcp (4 tools)
  skills-index.yaml        risk-mcp (4 tools)
                           logging-mcp (4 tools)

Skills → "做什么、何时做、怎么做"
MCP    → "拿什么数据、执行什么操作"
```

## 关键差异

| 维度 | Skills方案 | MCP方案(小红) |
|------|-----------|--------------|
| 交互模型 | AI读Markdown → 按指令执行 | AI调Tool → 拿结构化数据 |
| 知识传递 | 声明式文档 | JSON Schema接口 |
| 灵活性 | 高（任意改SKILL.md） | 低（需改代码部署） |
| 可靠性 | 依赖AI理解准确度 | 代码执行确定性 |
| 状态管理 | YAML文件+本地FS | MCP Server内部 |

## 已实施

- `skills-framework/` — 小红 Skills 框架 v2（15文件）
- `skills-framework/plugins/wealth-management/skills/historical-risk/` — 完整量化技能（SKILL.md + Python）
- `skills-framework/marketplace.json` — Claude Code 市场注册
- `skills-framework/install.sh` — 依赖感知符号链接安装器
- `skills-framework/mcp-bridge/skill-to-mcp.yaml` — MCP↔Skill映射（17 tools ↔ 8 skills）
