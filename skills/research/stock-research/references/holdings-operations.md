# holdings.json 操作手册

## 文件位置

`~/.hermes/profiles/xiaohong/data/holdings.json`

## 结构

```json
{
  "version": "2026.04.09.version.fix",
  "updateTime": "ISO8601",
  "accountInfo": {
    "initialCapital": 850000,
    "currentNetValue": 898697.65,
    "availableCash": 898697.65,
    "source": "招商证券交割单 20260326",
    "updateTime": "2026-05-28"
  },
  "positionCalculation": {
    "totalCapital": 850000,
    "maxPositionPerStock": 277070.9,
    "initialPosition": 94444.0,
    "addPosition": 94444.0,
    "tPosition": 94444.0,
    "totalBuilds": 3,
    "description": "..."
  },
  "holdings": [ /* 当前持仓数组 */ ],
  "closedPositions": [ /* 已平仓历史数组 */ ],
  "rules": {
    "maxPositionPerStock": 33.3,
    "maxHoldingsCount": 9,
    "positionStrategy": { /* 分批建仓规则 */ },
    "riskManagement": {
      "currentRValue": 6926.77,
      "stopLossStrategies": { /* R值止损 + 移动止盈 */ },
      "kellyCalculation": { /* 凯利公式统计 */ }
    }
  }
}
```

## 清空持仓（重新开仓）

用途：全部平仓，保留已平仓历史，净值回写。

```python
import json
from datetime import datetime

with open('data/holdings.json', 'r') as f:
    data = json.load(f)

close_date = datetime.now().strftime('%Y-%m-%d')

# 1. 将每只持仓移入 closedPositions
for h in data['holdings']:
    data['closedPositions'].append({
        "batch_id": f"CLOSE_{h['code']}_{close_date}",
        "code": h['code'],
        "name": h['name'],
        "buyDate": h.get('addDate', '?'),
        "sellDate": close_date,
        "buyPrice": h['costPrice'],
        "sellPrice": h['lastPrice'],
        "shares": h['shares'],
        "profit": round(h['unrealizedPnL'], 2),
        "profitPct": round(h['pnlPct'], 2),
        "holdingDays": 0,
        "source": "清仓重置"
    })

# 2. 回收市值到可用资金
total_mv = sum(h['marketValue'] for h in data['holdings'])
data['accountInfo']['availableCash'] += total_mv
data['accountInfo']['currentNetValue'] = data['accountInfo']['availableCash']

# 3. 清空持仓
data['holdings'] = []

# 4. 写回
with open('data/holdings.json', 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
```

**注意事项**：
- 必须用 `execute_code` 操作 JSON，不要用 patch 或 shell sed
- 清仓前先告知用户当前持仓盈亏，让用户确认
- `closedPositions` 的 `batch_id` 格式为 `CLOSE_{code}_{date}` 区别于正常平仓
- 净值 = 现金（无持仓时）
