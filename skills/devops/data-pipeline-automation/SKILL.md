---
name: data-pipeline-automation
description: Build automated data collection → knowledge base → AI analysis pipelines with cron jobs. Covers script patterns, cronjob mechanics, wiki organization, and profile-aware path handling.
triggers:
  - Setting up automated recurring data collection
  - Building agent-driven analysis pipelines on top of collected data
  - User asks to "automate" or "schedule" data gathering + reporting
  - Creating a knowledge base that feeds into periodic AI summaries
---

# Data Pipeline Automation

Build automated pipelines that collect data on schedule, store it in a wiki knowledge base, then run AI-driven analysis reports.

## Architecture

```
Data Sources (data fetch CLI)
        ↓
Collection Scripts (shell, runs on cron)
        ↓
Wiki Knowledge Base (~/wiki/)
        ↓
AI Analysis Cron Jobs (agent-driven, reads wiki)
        ↓
Report Delivery (push to chat)
```

## Two Job Types

| Type | `no_agent` | Use Case |
|------|-----------|----------|
| **Data Collector** | `true` | Pure script that pulls data and saves to wiki. Silent on success. |
| **AI Analyst** | `false` (default) | Reads wiki data, reasons, produces formatted report. Needs `enabled_toolsets`. |

## Step 1: Wiki Directory Structure

Organize by domain. Standard layout:

```
~/wiki/
├── 下载收藏/          ← raw data dumps (JSON from data fetch)
├── <domain>研究/      ← domain-specific analysis
│   ├── <sub-topic>/
│   └── README.md      ← curated index
├── <datatype>/        ← by data category (资金面, 新闻, etc.)
└── 策略研究/          ← strategy backtests, factor monitoring
```

Create with `mkdir -p` in one shot. Use **absolute paths** — `$HOME` is unreliable in profile contexts.

## Step 2: Data Collection Script

Template (shell):

```bash
#!/bin/bash
set -e

# Use ABSOLUTE path — $HOME resolves differently per profile
WIKI="/home/pc/.hermes/profiles/<profile>/home/wiki"
DOWNLOADS="$WIKI/下载收藏"
DATE=$(date +%Y%m%d)

fetch_save() {
  local source=$1 symbol=$2 type=$3 extra=$4
  local out="$DOWNLOADS/${source}_${symbol}_${type}_${DATE}.json"
  mkdir -p "$DOWNLOADS"
  data fetch "$source" --symbol "$symbol" --type "$type" $extra > "$out" 2>/dev/null \
    && echo "  ✓ $symbol" || echo "  ✗ $symbol FAILED"
}

# Pull data
fetch_save stock "600519" "quote" ""
fetch_save news "" "headlines" ""
# ... more fetch_save calls ...
```

Save as `~/.hermes/scripts/<name>.sh`.

## Step 3: Silent Cron Wrapper

Cron jobs with `no_agent=true` deliver stdout verbatim. To avoid spam, wrap:

```bash
#!/bin/bash
LOG=/tmp/<job>_$(date +%Y%m%d).log
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
bash "$SCRIPT_DIR/<collector>.sh" <mode> > "$LOG" 2>&1
EXIT=$?
if [ $EXIT -ne 0 ]; then
  echo "⚠️ <description> failed (exit=$EXIT)"
  tail -20 "$LOG"
  exit $EXIT
fi
# Successful: no output → silent delivery
```

Key detail: use `SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"` — do NOT use `$HOME` or relative paths that may resolve differently in the cron runtime.

## Step 4: Cron Job Creation

### Critical Mechanics

- **Script path**: Must be relative filename only. Place scripts in `~/.hermes/scripts/` and pass just the filename (e.g. `cron_post.sh`, not `/absolute/path/cron_post.sh`).
- **`$HOME` in profile context**: When running under a named profile, `$HOME` resolves to `/home/pc/.hermes/profiles/<name>/home`, NOT `/home/pc`. Scripts must use `SCRIPT_DIR` relative patterns or hard-coded absolute paths.
- **Schedule format**: Standard cron — `"30 8 * * 1-5"` for 8:30 AM weekdays. Timezone is the server's local time.

### Data Collector Job

```bash
cronjob action=create \
  name="<Name>" \
  schedule="30 8 * * 1-5" \
  script="cron_wrapper.sh" \
  no_agent=true \
  deliver="origin"
```

### AI Analyst Job

```bash
cronjob action=create \
  name="<Name>" \
  schedule="45 8 * * 1-5" \
  enabled_toolsets='["terminal","file","web"]' \
  prompt="<detailed multi-step prompt>"
```

## Step 5: AI Analyst Prompt Template

```
你是<角色>，现在执行<任务名>。

## 任务
<一句话目标>

## 步骤
1. 读取 ~/wiki/下载收藏/ 中今日/本周的数据文件
2. 读取 ~/wiki/<domain>/README.md 获取配置
3. 分析：<具体分析维度>
4. 生成报告：<格式模板>

## 风格要求
- <角色语气、格式约束>
```

## Pitfalls

1. **`$HOME` sabotage**: In profile cron contexts, `$HOME` points to profile home, not real home. Always use absolute paths or `$(dirname "$0")`.
2. **Script path rejection**: `cronjob` rejects absolute paths for `script`. Only filenames; they must live in `~/.hermes/scripts/`.
3. **`set -e` in wrappers**: The collector script may have individual `data fetch` failures that shouldn't abort the whole run. Wrappers should NOT use `set -e` (or use `|| true` on each fetch).
4. **mkdir before write**: The download directory must exist before the first fetch_save call. Include `mkdir -p` in the fetch function.
5. **Silent success pattern**: `no_agent=true` jobs with empty stdout deliver nothing — perfect for data collectors. Any output = an alert.

## Verification

1. Trigger manually: `cronjob action=run job_id=<id>`
2. Check collected files: `ls ~/wiki/下载收藏/ | wc -l`
3. Verify a sample: `head -c 200 ~/wiki/下载收藏/<file>.json`
4. Check all jobs: `cronjob action=list`

## Reference Implementations

See `references/stock-research-pipeline.md` for the complete stock research automation built from this pattern — 12-stock watchlist, 6 cron jobs, wiki knowledge base.
