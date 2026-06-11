# Cron 升级模式：no_agent → LLM

2026-06-02 执行，将 3 个 cron 从 no_agent 升级为 LLM 驱动。

## 判断标准

| 当前 no_agent 特征 | LLM 价值 | 升级建议 |
|:--|:--|:--|
| 纯计算（记价格、算涨跌、比阈值） | ❌ 无 | **保持 no_agent** |
| 定量筛选+定性过滤 | ✅ 有（两阶段已有 LLM） | **保持 no_agent + LLM 联动** |
| 盲打 patch/写代码 | ✅ 高（需判断合理性） | **→ LLM** |
| 数据汇总 | ✅ 高（需叙事分析） | **→ LLM** |
| 健康检查/缺口发现 | 🟡 部分 | **no_agent + LLM 并行** |

## 升级步骤

### 1. 改造 cron 配置

```
cronjob action=update
  no_agent: false           # 去掉 no_agent
  script: ""                # 清空 script
  prompt: "..."             # 写 LLM 自主执行提示词
  skills: [stock-research, strategy-trading]
  enabled_toolsets: [terminal, file]
  workdir: ~/.hermes/profiles/xiaohong
  profile: xiaohong
```

### 2. LLM Prompt 设计原则

- **自包含**：cron 运行无用户交互，prompt 必须完整描述数据源路径、步骤、输出格式
- **安全边界**：涉及代码修改的 prompt 必须明确 ±20% 限制、语法验证步骤、回滚机制
- **工具声明**：明确告诉 LLM 可以用 terminal + file 读数据、patch 改代码
- **输出规范**：要求用 report_formatter.Report 生成结构化报告

### 3. 已执行的升级

| 模块 | job_id | 变更 | 特性 |
|:--|:--|:--|:--|
| 进化引擎 | e6b2b24c7316 | no_agent→LLM | 读action→评估→patch+验证→记录 |
| 研究员研学 | 1a0ebb16ec85 | 🆕 新增并行LLM | 02:05 5维诊断打分 |
| 文工团·周报 | 1de9a545a043 | no_agent→LLM | 叙事性复盘+行为偏差+6维评分 |
| 竞价采集器 | 99d740ca2dc6 | no_agent→LLM 🆕 v9.1 | 120s timeout→LLM 300s，解决 API 预热+采集耗时问题 |
| 涨幅榜学习 | ac4772979e24 | no_agent→LLM 🆕 v9.1 | 50只串行 >120s→LLM 300s，解决 --winners timeout |

### 4. 保留的 no_agent 脚本

进化引擎 `evolution_engine.py` (1234行) 保留为手动备选和参考，但主要逻辑改由 LLM cron 执行。同样 `weekly_review.py` 保留。
