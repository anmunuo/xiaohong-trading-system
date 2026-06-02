# 研究员议会 v1.1 — 设计文档

> 2026-06-02 落地并完成全链路集成。5研究员协同研究，3轮辩论协议，小红终审决策。

---

## 五位研究员

| 角色 | role_id | 侧重 | 核心输入 |
|:--|:--|:--|:--|
| 📊 数据研究员 | `data` | 数据质量/隐藏信息/新数据源 | 全量数据源、API文档 |
| 🏢 基本面研究员 | `fundamental` | 财报/公告/研报/行业轮动/情绪 | KB知识库、mega_latest |
| 📈 技术面研究员 | `technical` | K线形态/量价关系/指标/关键位 | 历史日线、实时行情 |
| 🐂 多方研究员 | `bull` | 增长逻辑/估值空间/催化事件 | 全模块交叉 |
| 🐻 空方研究员 | `bear` | 风险隐患/利空逻辑/估值泡沫 | 全模块交叉 |

## 两种工作模式

### 模式一：每日自主研学（02:00 cron）

各研究员独立运行结构化分析（不调LLM），产出定量报告。

```bash
python3 researchers.py --study
# → reports/research/研学报告-{date}.md
```

### 模式二：决策时议会

**触发节点**：

| 节点 | 参与者 | 说明 |
|:--|:--|:--|
| 推荐引擎 08:25 (Step 6.5) | 全5位 | 候选池多视角交叉验证 |
| 进化引擎 17:30 | 全5位 | 参数变更风险和收益评审 |

**议会协议 — 3轮辩论**：

```
Round 1: 独立研判
  └─ 5位研究员各自基于专业视角独立分析 → 独立报告

Round 2: 交叉辩论
  ├─ 多方 vs 空方互驳 → 找共识和分歧
  ├─ 基本面 vs 技术面交叉验证
  └─ 数据研究员做裁判（数据验证各方论据）

Round 3: 小红终审
  └─ 综合所有报告和辩论 → 形成统一结论 → 自动执行
```

## 报告输出

| 输出 | 路径 |
|:--|:--|
| 议会报告 | `reports/research/议会报告-{date}.md` |
| 结构化日志 | `scripts/data/research/parliament_log.json`（最近90条） |

## 集成点

| 模块 | 调用方式 | 议会结论消费 |
|:--|:--|:--|
| `stock_recommender.py` | `_parliament_consult()` — Step 6.5，非阻塞 | `_save_pool()` → `daily_pool.json.parliament` |
| `evolution_engine.py` | `_parliament_review(changes, dry_run)` — 返回值裁决 | veto(≥75%)→终止 / bearish(≥60%)→跳过风险参数 |
| 瞭望塔 08:30 (LLM cron) | 读取 daily_pool.json.parliament | 融入「一个判断」+ 标注红旗 + 仓位降档 |
| 决策官 14:30 (LLM cron) | 读取 daily_pool.json.parliament | 新增 🏛️ 议会结论 section |
| LLM复盘 17:05 (LLM cron) | 读取 parliament_log.json | 新增 ⑧ 议会模块诊断 |
| cron | `cron_researchers_study.sh` → 02:00 no_agent | — |

## 全链路数据流（v1.1）

```
08:25 推荐引擎 ──→ _parliament_consult() ──→ _save_pool() 写入 parliament 字段
                      │                              │
                      ▼                              ▼
08:30 瞭望塔晨报 ←── 读取 parliament.bias/red_flags → 融入判断+风险标注
                      │
14:30 决策官     ←── 读取 parliament → 新增 🏛️ 议会结论 section
                      │
17:05 LLM复盘    ←── 读取 parliament_log.json → 新增 ⑧ 议会模块诊断
                      │
17:30 进化引擎   ←── _parliament_review() → veto/bearish 拦截生效
```

## 议会裁决结构

`daily_pool.json` 中的 `parliament` 字段 (v2.3+)：

```json
{
  "bias": "bullish | bearish | neutral | veto",
  "confidence": 0.75,
  "bull_signals": 3,
  "bear_signals": 5,
  "red_flags": ["嘉美包装 KB洞察风险信号"],
  "recommendation": "维持观望，等待更明确的多方信号",
  "timestamp": "2026-06-02T01:32:30"
}
```

## 进化引擎 veto 机制

```
veto + 置信度≥75%  → 🚫 终止本轮进化，输出红旗列表
bearish/veto + 置信度≥60% → ⚠️ 跳过 verdict.risky_params 中的参数
bullish            → ✅ 放行全部变更
议会不可用         → ⚠️ 按常规流程执行
```

## 关键设计决策

- **结构化分析优先**：默认模式不调LLM——每位研究员用结构化数据分析产出报告，议会只用关键词匹配做辩论匹配。仅在需要深度自然语言推理时才加LLM。
- **非阻塞集成**：议会失败不影响主流程（try/except pass），但进化引擎会降级到"按常规流程执行"。
- **轻量触发**：每天2次完整议会（推荐引擎+进化引擎），不随盘中扫描等高频率节点触发。

## 常见问题

| 症状 | 根因 |
|------|------|
| daily_pool.json 无 parliament 字段 | 版本 < v2.3（旧版 _save_pool 未写入）；或议会调用失败（parliament_log 为空） |
| 瞭望塔未提议会结论 | LLM cron prompt 未包含议会引用指令（已修复 v1.1） |
| 进化引擎 veto 不生效 | _parliament_review() 旧版只打印不拦截（已修复 v1.1，增加返回值+三级拦截） |
| parliament_log 嵌套了两层 data | researchers.py 序列化 bug，解包时需多取一层 |
| ⭐ `_save_pool()` 议会字段全空 | **字段名不匹配**：Round 3 裁决用 `bull_strength`/`bear_strength`/`critical_flags`，但 `_save_pool()` 若误用 `bull_signals`/`bear_signals`/`red_flags` 会全部读到默认值。已修复（v2.3），务必用 `verdict.get('bull_strength', 0)` 等正确字段名 |
| 手动跑推荐引擎超时（120s+） | `_prefetch_indicators` 对候选池全部股票逐只拉 tushare 日线，392只约需 94s，全流程 3-5 分钟。验证议会集成时可用 `python3 researchers.py` 独立跑议会 + 手动注入 daily_pool.json 替代完整推荐引擎 |
