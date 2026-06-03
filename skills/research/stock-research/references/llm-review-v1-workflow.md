# LLM复盘 v1.0 实战工作流

> 基于 2026-06-03 实际执行验证。适用于 `self_evolution.py` v1.0 架构。

## 第一步：定位工作区

```bash
# ⚠️ 唯一真实工作区，不要用 find ~/.openclaw 找旧数据
# openclaw workspace 是已废弃的 v1.0 系统，包含过期持仓和历史记录
BASE="$HOME/.hermes/profiles/xiaohong"

# 验证:
ls $BASE/scripts/review.py          # 必须存在
ls $BASE/data/holdings.json         # 必须存在 (持仓)
ls $BASE/scripts/data/              # daily_pool.json 所在
```

## 第二步：收集数据（7 个数据源）

```bash
# 1. 文工团复盘日志 (17:00 cron 产出)
tail -100 $BASE/../logs/xiaohong_review.log

# 2. 推荐池
cat $BASE/scripts/data/daily_pool.json 2>/dev/null

# 3. 议会日志
find $BASE/scripts/data/ -name '*parliament*' -o -name '*议会*' 2>/dev/null

# 4. 持仓 (holdings.json 在 data/ 下)
python3 -c "
import json
with open('$BASE/data/holdings.json') as f:
    d = json.load(f)
for h in d['holdings']:
    print(f'{h[\"name\"]}({h[\"code\"]}): cost={h[\"costPrice\"]}, lastPrice={h.get(\"lastPrice\")}, pnlPct={h.get(\"pnlPct\")}')
"

# 5. 反思日志
find $BASE/scripts/data/ -name 'reflection_log.json' 2>/dev/null

# 6. 进化日志
find $BASE/scripts/data/ -name '*decisions*.json' 2>/dev/null

# 7. 各模块日志
tail -60 $BASE/../logs/xiaohong_ammo.log        # 弹药库 15:30
tail -20 $BASE/../logs/xiaohong_scout_batch5.log # 侦察兵 14:20
tail -20 $BASE/../logs/xiaohong_sniper.log       # 狙击手
tail -10 $BASE/../logs/xiaohong_jingjia.log      # 竞价
tail -20 $BASE/../logs/xiaohong_trading.log      # 交易引擎
tail -5 $BASE/../logs/xiaohong_watchtower.log    # 瞭望塔
```

## 第三步：补全实时数据（关键！）

holdings.json 的 `lastPrice`/`pnlPct` 由弹药库 `--update` 同步，盘后 15:30 自动更新。

```bash
# 用 data fetch CLI 拉持仓实时行情
for code in 300131 600481; do
    data fetch stock --symbol $code --category quote 2>/dev/null | \
        python3 -c "import sys,json; d=json.load(sys.stdin); b=d['providers_attempted'][0]['data'][0]; print(f'{b[\"ts_code\"]}: close={b[\"close\"]}, pct_chg={b.get(\"pct_chg\",\"?\")}')"
done
```

**对比 holddings.json 报告值 vs 实际值，计算真实盈亏。** 这是本次发现双良节能-36.7%隐藏亏损的关键步骤。

## 第四步：8 模块诊断

按 skill 文档第 2 步逐模块打分：

| 模块 | 关键检查 | v1.0 常见状态 |
|:--|:--|:--|
| ① 瞭望塔/推荐引擎 | daily_pool.json 存在？stock_recommender.py 存在？ | stock_recommender.py 不存在 → error |
| ② 侦察兵 | scout_recommender.py 批次有实际数据？ | batch2-5 有数据但 batch1 空 → warn |
| ③ 狙击手 | sniper_tracker.py 产出实际信号？ | 仅时间戳 → error |
| ④ 弹药库 | 现价是 ¥0.00？仓位显示 0%？ | lastPrice=None → error |
| ⑤ 知识库 | mega_collector.py 存在？kb_insights.json？ | 不存在 → error |
| ⑥ 竞价 | auction_diagnosis.json？竞价榜获取成功？ | 失败 → error |
| ⑦ 文工团 | 今日与昨天内容是否不同？ | 3天相同 → error |
| ⑧ 议会 | parliament_log.json？debate_flow.py 编入 cron？ | 未集成 → error |

## 第五步：写入 review_diagnosis.json

**必须写入的完整路径**: `$BASE/scripts/data/kb/review_diagnosis.json`

```json
{
  "date": "YYYYMMDD",
  "diagnosis": "一句话全局诊断",
  "module_scores": { "... 8个模块 ..." },
  "rule_changes_suggested": [ "... rule/change/reason/confidence ..." ],
  "no_change": false,
  "root_causes": [ "... module/cause/severity ..." ],
  "system_state": { "... account_*/holdings_*/last_* ..." }
}
```

> ⚠️ rule 关键词必须匹配 skill 文档中的精确列表，否则进化引擎无法解析。
> ⚠️ v1.0 的 self_evolution.py **不消费** review_diagnosis.json，rule_changes 仅为审计记录。

## 第六步：触发进化引擎

```bash
# v2.0 进化引擎
cd $BASE/scripts && python3 evolution_engine.py --once
```

## 验证清单

- [ ] holdings.json 实时行情已拉，报告值与实际值对比完成
- [ ] 8 模块全部有评分（不是空或"未运行"）
- [ ] review_diagnosis.json 格式正确（JSON 可解析）
- [ ] root_causes ≥ 3 条（模块休眠必须有根因）
- [ ] system_state 含实际盈亏（非仅模板值）
- [ ] 与昨天诊断对比，标注变化项（+/➡️/⬇️）
