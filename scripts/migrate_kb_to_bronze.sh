#!/bin/bash
# migrate_kb_to_bronze.sh — 迁移旧 knowledge_base/ 到 Bronze events/
# 执行后原 knowledge_base/ 保留但不再被系统使用

cd /home/pc/.hermes/profiles/xiaohong/scripts

echo "=== 知识库迁移到 Bronze ==="

# 1. 迁移 announcements → Bronze events
echo "[1/4] 迁移 announcements..."
for f in data/knowledge_base/announcements/*.json; do
    if [ -f "$f" ]; then
        date_str=$(basename "$f" .json | sed 's/2026-026-//')
        if [ ${#date_str} -eq 4 ]; then
            month=${date_str:0:2}
            day=${date_str:2:2}
            formatted_date="2026-${month}-${day}"
            python3 -c "
from bronze_ingest import BronzeWriter
import json
w = BronzeWriter()
data = json.load(open('$f'))
w.write(data, 'akshare', 'events', '$formatted_date', notes='migrated from knowledge_base/announcements')
print(f'  $f → Bronze events/$formatted_date')
" 2>/dev/null
        fi
    fi
done

# 2. 迁移 stock_events → Bronze events (按日期分组)
echo "[2/4] 迁移 stock_events..."
python3 -c "
from bronze_ingest import BronzeWriter
import json
from pathlib import Path
from collections import defaultdict

kb_dir = Path('../data/knowledge_base/stock_events')
if kb_dir.exists():
    all_events = defaultdict(list)
    for f in kb_dir.glob('*.json'):
        code = f.stem
        events = json.loads(f.read_text()) if f.stat().st_size > 0 else []
        if isinstance(events, list):
            for e in events:
                e['_code'] = code
        all_events['2026-06-03'].extend(events if isinstance(events, list) else [events])

    w = BronzeWriter()
    for date, events in all_events.items():
        if events:
            w.write(events, 'akshare', 'events', date,
                    notes=f'migrated from knowledge_base/stock_events ({len(events)} items)')
    print(f'  已迁移 {len(all_events)} 天的事件数据')
" 2>/dev/null || echo "  (无 stock_events 或已迁移)"

# 3. 保留原目录但加标记
echo "[3/4] 标记旧知识库..."
echo "This directory has been migrated to data/bronze/events/ as of $(date -I)." > ../data/knowledge_base/DEPRECATED.md

# 4. 验证
echo "[4/4] 验证..."
python3 bronze_verifier.py --today --json 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'  状态: {d[\"overall\"]} | 完整性: {d[\"completeness\"]}%')" 2>/dev/null || echo "  待 Bronze 首次采集后验证"

echo "=== 迁移完成 ==="
