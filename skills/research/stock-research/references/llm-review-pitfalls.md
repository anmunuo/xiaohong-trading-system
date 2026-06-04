# LLM复盘 · 工作流陷阱与模式

> 从 2026-06-04 LLM 复盘 session 中提炼的跨模块陷阱和操作模式。

## 陷阱 1: 议会静默停摆无人感知

**症状**: parliament_log.json 停在 6/2，6/3 和 6/4 完全无产出。daily_pool.json 的 parliament section 引用 2 天前旧裁决（bias=偏空, bull=1, bear=8）。认知层在陈旧数据上运行。

**根因**: 议会 cron 未运行或静默失败。KB 数据持续采集但无人消费。无监控机制检测 parliament 数据新鲜度。

**检测方法**:
```bash
# 检查 parliament_log.json 最新时间戳
python3 -c "
import json
log = json.load(open('scripts/data/research/parliament_log.json'))
latest = max(entry['timestamp'] for entry in log)
print(f'最新议会: {latest}')
"
# 预期: 日期应为今天或昨天。超过 24h = 议会停摆。
```

**修复方向**: system_health_check 增加第13维「议会数据新鲜度」—检测 parliament_log.json 最新记录是否在 24h 内。

---

## 陷阱 2: 进化引擎 ±20% 安全边界拒绝大跨步变更

**症状**: 建议「市值下限 50→30 亿」(变更幅度 40%)被进化引擎 --dry-run 拒绝。同样「市值上限 2000→1000 亿」(67%)被拒。

**根因**: 进化引擎铁律「单次参数调整 ≤±20%」自动拦截。40% 和 67% 远超上限。

**后果**: 0/2 项通过验证。参数变更需要手动分步执行或分多天递进。

**正确做法**:
- 单次建议的变更幅度必须 ≤20%
- 50→30 需分步: 50→40→32→30 (3天完成)
- 在 review_diagnosis.json 的 `change` 字段中写分步目标:
  ```json
  {"rule": "市值下限", "change": "市值下限从50亿降低到40亿（第一步：50→40→...→30）", "confidence": "high"}
  ```

---

## 陷阱 3: Gold ETL cron 路径双写

**症状**: 15:50 Gold ETL cron 报错:
```
can't open file '/home/pc/.hermes/profiles/xiaohong/home/.hermes/profiles/xiaohong/scripts/gold_pipeline.py'
```
路径出现双重 `home/.hermes/profiles/xiaohong`。

**根因**: 非 `cron_gold.sh` 脚本本身问题（脚本用 `cd $HOME/...` + 相对路径 `gold_pipeline.py` 正常）。可能在 hermes cron 调度层将工作目录前缀重复拼接。

**影响**: Gold 层因子面板 + ML 数据集 + Pool 归档今日未产出。

**检测**:
```bash
cat cron/output/<gold_dir>/stderr  # 检查路径是否双写
```

---

## 模式: cron 修复追赶窗口

**场景**: review.py 在 15:30 cron 崩溃（`_em_api_get` 导入错误），修复在 15:33 应用。3 分钟窗口导致 cron 失败但修复已就位。

**教训**:
1. 修复后不要假设修复立即生效——cron 可能已经运行过旧版本
2. LLM 复盘 (17:05) 应验证当日 cron 的退出码，判断是否需要手动重跑
3. 关键脚本的 import 路径应在 system_health_check 中静态检测，而非等 cron 报错

---

## 模式: 三链路断裂检测

**推荐池 → 侦察兵 → 狙击手 → 下单** 是核心交易链路。三者独立故障时系统整体失效：

| 6/4 状态 | 推荐池 | 侦察兵 | 狙击手 | 下单 |
|:--|:--|:--|:--|:--|
| 运行 | ✅ 9只 | ⚠️ 日志缺失 | 🔴 守护进程未启 | 🔴 无执行 |

**检测**: LLM 复盘应检查这三者是否全部在线。任一环节断裂 → 系统处于「有信号无行动」状态，需在 diagnosis 首句标注。
