# LLM复盘 · 工作流陷阱与模式

> 从 2026-06-04 LLM 复盘 session 中提炼的跨模块陷阱和操作模式。

## 陷阱 1: 议会静默停摆 + 僵尸条目 (v8.12 升级)

**症状 (v8.12 发现)**: parliament_log.json 有40条记录，时间戳新鲜（今天 08:15/15:16），但**零条有真实裁决**。所有条目要么 rounds=0（健康检查空壳），要么 Round 3 的 `decision.bias` 和 `decision.confidence` 全为空/null。

**关键诊断发现 (2026-06-08)**:
1. **Round 3 key 命名**: 实际使用 `decision` 而非 `verdict` ——旧代码查 `verdict.bias` 永远返回 null
2. **bias/confidence 为空**: `decision` 对象存在但 `bias` 和 `confidence` 字段值全为空字符串/None
3. **rounds=0 条目**: 后38条由 health_check 或系统进程创建的空壳，非真实议会产物
4. **前2条有结构无内容**: 6/2 01:32-01:33 的条目有 3 轮结构（data/fundamental/technical/bull/bear → debate → decision），但 decision 内无实质裁决

**检测方法 (v8.12 升级 — 不只查时间戳，必须查内容)**:
```bash
python3 -c "
import json
log = json.load(open('scripts/data/research/parliament_log.json'))
# 不只查最新时间，查是否有真实裁决
real = []
for e in log:
    rounds = e.get('rounds',[])
    if len(rounds) >= 3:
        rd3 = rounds[2].get('data',{})
        # ⚠️ key 是 'decision' 不是 'verdict'
        d = rd3.get('decision',{}) or rd3.get('verdict',{})
        if d.get('bias') and d.get('bias') != '?':
            real.append(e)
print(f'总条目: {len(log)}, 有真实裁决: {len(real)}')
if real:
    last = real[-1]
    d = last['rounds'][2]['data'].get('decision',{})
    print(f'最新真实议会: {last[\"timestamp\"][:19]} bias={d.get(\"bias\")} conf={d.get(\"confidence\")}')
else:
    print('🔴 零真实裁决 — 议会从未产出过有效多空判断！')
"
```
**预期**: 总条目>0 且 有真实裁决>0。若后者=0 → 议会是僵尸——可能从未工作过。

**根因层次**:
- L1: crontab 中只有 `researchers.py --study` 和 `--winners`，无 `--parliament` 模式调度
- L2: 即使手动运行，`decision` 对象写入时 bias/confidence 字段为空
- L3: health_check 每次运行写入空条目（rounds=0）污染日志

**修复方向**: 
1. crontab 添加 `researchers.py --parliament` 调度（建议每日 01:00 和 13:00）
2. 修复 parliament 模式中 `decision` 对象的 bias/confidence 写入逻辑
3. health_check 写入 parliament_log 时区分「系统条目」和「议会条目」（加 `source: health_check` 标记）

---

## 陷阱 2: 进化引擎 ±20% + 基线追踪 (v8.12 升级)

**症状**: 建议「市值上限 2400→2000 亿」(变更幅度 16.7%，在 20% 内)被进化引擎拒绝，报「变更幅度 33% 超出上限 20%」。

**根因 (v8.12 发现)**: 进化引擎使用**原始基线**（参数首次定义值）计算变更幅度，而非**当前值**。市值上限原始值 3000→6/4 v5 落地 2400→6/8 建议 2000。引擎计算 (3000-2000)/3000 = 33% 而非 (2400-2000)/2400 = 16.7%。

**影响**: 多步递进的参数变更会在中间步被误拒。即使每一步 ≤20%，引擎仍以原始基线判断——这导致分步计划无法自动执行。

**正确做法**:
- 分步计划中，每步的目标值需确保**从原始基线算**也在 20% 内
- 市值上限: 3000→2400 (20% ✅) → 1920 (从原始算 36% ❌) → 需改为 3000→2400→2000→1000，但要接受中间步可能被拒
- **或**: 在 review_diagnosis.json 的 `change` 字段中不写「从X到Y」，只写「目标新值: Y」——让引擎自己读当前源码值计算

**工作区 (v8.12 验证)**: 如果源码中市值已经是 30-2000 亿（6/4 已落地），则无需再建议——直接标记 `no_change: true` 并注明「源码已是目标值」。

---

## 陷阱 3: Gold ETL cron 路径双写 + 自主修复全管线失败 (v8.12 修正根因)

**症状**:
1. 15:50 Gold ETL cron 报错:
```
can't open file '/home/pc/.hermes/profiles/xiaohong/home/.hermes/profiles/xiaohong/scripts/gold_pipeline.py'
```
路径出现双重 `home/.hermes/profiles/xiaohong`。

2. `auto_repair.py` 所有管线修复返回 rc=-1:
```
bronze_ingest.py: rc=-1
silver_pipeline.py: rc=-1
gold_pipeline.py: rc=-1
```

**真正的根因 (v8.12 修正)**: **不是** hermes cron 调度层路径拼接 bug。根因是 **hermes profile 系统将 `$HOME` 环境变量覆盖为 `/home/pc/.hermes/profiles/xiaohong/home`**（而非真实 `/home/pc`）。这导致：

| 受影响代码 | 原始写法 | 展开结果（错误） | 正确路径 |
|:--|:--|:--|:--|
| `auto_repair.py:22` | `Path.home() / ".hermes"/.../python3` | `.../xiaohong/home/.hermes/.../python3` ❌ | `/home/pc/.hermes/.../python3` |
| `cron_gold.sh:8` | `cd "$HOME/.hermes/..."` | `.../xiaohong/home/.hermes/...` ❌ | `/home/pc/.hermes/...` |

**影响范围**:
- `auto_repair.py` VENV_PYTHON 指向不存在文件 → 所有 `_run_script()` 返回 rc=-1 → 全管线修复静默失败
- `cron_gold.sh` cd 失败 → Gold ETL 不执行
- 其他 28 个 `.sh` 脚本无影响（已用绝对路径）

**修复**:
```python
# auto_repair.py — 使用绝对路径，不依赖 $HOME
VENV_PYTHON = "/home/pc/.hermes/hermes-agent/venv/bin/python3"
```
```bash
# cron_gold.sh — 使用绝对路径，不依赖 $HOME
cd /home/pc/.hermes/profiles/xiaohong/scripts
```

**检测**:
```bash
echo "HOME=$HOME"  # 若输出为 profile home 而非真实 home，问题存在
grep -rn '\$HOME\|Path\.home()' scripts/*.sh scripts/auto_repair.py  # 扫描残留
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

---

## 陷阱 5: 市场快照三重静默降级 (v8.12 发现)

**症状 (2026-06-08 实例)**: market_snapshot.json 08:28 生成，但三个核心字段同时失效：
- `north_flow._quality = "T-28"` — 北向数据是 28 天前的
- `market_money_flow.main_net = "?"` — 全市场主力资金流空
- `sector_flow` — 板块排名列表为空

**根因**: 三条数据管线独立断连但都被静默吞掉。北向=AKShare `stock_hsgt_fund_flow_summary_em()` 永久返回 0→tushare 回退但最新数据 28 天前。资金流=东方财富 `_em_api_get` RemoteDisconnected→无重试→空。板块流=同样 `_em_api_get` 断连→空。

**为什么危险**: 瞭望塔/决策官 LLM 读取 market_snapshot.json 时只看字段有值（北向 42.4 亿），不看 `_quality` 标记。基于 T-28 假数据做出「资金面偏多」的错误宏观判断。

**检测方法**:
```bash
python3 -c "
import json
m = json.load(open('scripts/data/market_snapshot.json'))
nf = m.get('north_flow',{})
mf = m.get('market_money_flow',{})
sf = m.get('sector_flow',[])
issues = []
if nf.get('_quality','').startswith('T-') and int(nf.get('_quality','T-1')[2:]) > 3:
    issues.append(f'北向{nf[\"_quality\"]}天前')
if not mf.get('main_net') or mf.get('main_net') == '?':
    issues.append('资金流空')
if len(sf) == 0:
    issues.append('板块流空')
if issues:
    print(f'🔴 快照降级: {\" + \".join(issues)}')
else:
    print('✅ 快照正常')
"
```

**修复方向**:
1. 瞭望塔/决策官 LLM prompt 增加「数据质量前置检查」— 北向 T-N>3 天时禁止引用具体数字
2. 降级时市场快照字段不写假值，写 `null` 而非 28 天前的 42.4 亿
3. 三路 API 增加独立重试 + 退避 + 完整 UA

---

## 陷阱 6: 进化引擎基线追踪 (v8.12 发现)

**症状 (2026-06-08)**: 建议「市值上限 2400→2000 亿」被进化引擎拒绝，报「变更幅度 33% 超出上限 20%」。但从当前值 2400 算，2000 是 -16.7%（在 20% 内）。引擎实际计算的是 (3000-2000)/3000 = 33%——用了原始基线而非当前值。

**根因**: 进化引擎使用**参数首次定义值**（原始基线）计算变更幅度。市值上限原始值=3000→6/4 v5 落地 2400→6/8 建议 2000。引擎不看 v5 已落地的中间值。

**应对**:
1. 如果在分步递进中（如 3000→2400→2000→1000），中间步可能被引擎误拒
2. **正确做法**: 提交建议前先 `grep` 源码确认**当前实际值**，计算 (当前值-目标值)/当前值 确保 ≤20%
3. 如果源码已是目标值（如 30-2000 亿已硬编码），直接标记 `no_change: true`
4. 在 review_diagnosis.json 的 `change` 字段中**只写目标新值**不写「从X到Y」，以减少歧义

---

## 参考: 关键文件路径确认 (v8.12)

LLM 复盘写入和读取的核心路径：
- `review_diagnosis.json`: **`scripts/data/kb/review_diagnosis.json`** (不是 `scripts/kb/`)
- `parliament_log.json`: `scripts/data/research/parliament_log.json`
- `daily_pool.json`: `scripts/data/daily_pool.json`
- `holdings.json`: `<workspace>/data/holdings.json` (不是 `scripts/data/`)
- `market_snapshot.json`: `scripts/data/market_snapshot.json`
- `evolution_action_items.json`: `scripts/data/evolution_action_items.json`
- `evolution_log.json`: `scripts/data/evolution/evolution_log.json`
