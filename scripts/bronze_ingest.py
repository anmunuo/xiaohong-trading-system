#!/usr/bin/env python3
"""
bronze_ingest.py — Bronze 层写入引擎
=====================================
原始数据不可变写入。所有外部API调用的原始结果冻结为 gzip JSON。

原则:
  - 写入后永不修改
  - 同一日期+来源的重复写入=幂等(跳过)
  - 每批写入带 manifest 记录

目录结构:
  data/bronze/
  ├── daily_kline/2026/06/03/baostock.json.gz
  ├── fundamentals/2026/06/03/tushare.json.gz
  ├── fund_flow/2026/06/03/eastmoney.json.gz
  ├── market_index/2026/06/03/sina.json.gz
  ├── events/2026/06/03/announcements.json.gz
  ├── events/2026/06/03/limit_ups.json.gz
  ├── _meta/daily_manifest.json
  └── _meta/schema_registry.json
"""

import json, gzip, os, hashlib, time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

SCRIPT_DIR = Path(__file__).resolve().parent
BRONZE_ROOT = SCRIPT_DIR.parent / 'data' / 'bronze'
META_DIR = BRONZE_ROOT / '_meta'


# ═══════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════

@dataclass
class BronzeRecord:
    """单批 Bronze 写入记录"""
    source: str           # baostock / tushare / eastmoney / sina / akshare
    category: str         # daily_kline / fundamentals / fund_flow / events / market_index
    date: str             # YYYY-MM-DD
    fetched_at: str       # ISO timestamp
    item_count: int       # 记录数
    file_path: str        # 相对路径
    sha256: str           # 内容哈希
    fields: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class DailyManifest:
    """每日采集清单"""
    date: str
    records: List[BronzeRecord] = field(default_factory=list)
    total_items: int = 0
    completeness_pct: float = 0.0
    generated_at: str = ""

    def to_dict(self) -> Dict:
        return {
            'date': self.date,
            'records': [asdict(r) for r in self.records],
            'total_items': self.total_items,
            'completeness_pct': self.completeness_pct,
            'generated_at': self.generated_at,
        }


# ═══════════════════════════════════════
# Bronze 写入引擎
# ═══════════════════════════════════════

class BronzeWriter:
    """Bronze 层不可变写入器"""

    def __init__(self, root: Path = None):
        self.root = root or BRONZE_ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        META_DIR.mkdir(parents=True, exist_ok=True)

    def write(self, data: Any, source: str, category: str,
              date: str = None, fields: List[str] = None,
              notes: str = "") -> BronzeRecord:
        """
        写入一批原始数据到 Bronze 层。

        Args:
            data: 原始数据 (dict/list)
            source: 数据源标识 (baostock/tushare/eastmoney/sina/akshare)
            category: 数据类别 (daily_kline/fundamentals/fund_flow/events/market_index)
            date: 数据日期 (默认今天)
            fields: 字段列表
            notes: 备注

        Returns:
            BronzeRecord — 写入记录
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        # 目录: data/bronze/{category}/{YYYY}/{MM}/{DD}/
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        dir_path = self.root / category / str(date_obj.year) / f'{date_obj.month:02d}' / f'{date_obj.day:02d}'
        dir_path.mkdir(parents=True, exist_ok=True)

        # 文件名: {source}.json.gz
        file_path = dir_path / f'{source}.json.gz'

        # 序列化
        json_bytes = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        compressed = gzip.compress(json_bytes, compresslevel=6)

        # 哈希
        sha = hashlib.sha256(compressed).hexdigest()[:16]

        # 幂等检查：同文件已存在且哈希一致则跳过
        if file_path.exists():
            existing = file_path.read_bytes()
            existing_sha = hashlib.sha256(existing).hexdigest()[:16]
            if existing_sha == sha:
                return BronzeRecord(
                    source=source, category=category, date=date,
                    fetched_at=datetime.now().isoformat(),
                    item_count=self._count(data),
                    file_path=str(file_path.relative_to(self.root)),
                    sha256=sha, fields=fields or [], notes='skipped (identical)',
                )

        # 原子写入
        tmp = file_path.with_suffix('.tmp')
        tmp.write_bytes(compressed)
        tmp.rename(file_path)

        item_count = self._count(data)
        fetched_at = datetime.now().isoformat()

        record = BronzeRecord(
            source=source, category=category, date=date,
            fetched_at=fetched_at, item_count=item_count,
            file_path=str(file_path.relative_to(self.root)),
            sha256=sha, fields=fields or [], notes=notes,
        )

        # 更新 manifest
        self._update_manifest(record)

        return record

    def _count(self, data: Any) -> int:
        """统计记录数"""
        if isinstance(data, list):
            return len(data)
        elif isinstance(data, dict):
            # 尝试常见键
            for key in ['data', 'items', 'records', 'stocks']:
                if key in data and isinstance(data[key], list):
                    return len(data[key])
            return len(data)
        return 1

    def _update_manifest(self, record: BronzeRecord):
        """追加到当日 manifest"""
        manifest_path = META_DIR / 'daily_manifest.json'
        today = record.date

        if manifest_path.exists():
            manifest_data = json.loads(manifest_path.read_text())
        else:
            manifest_data = {}

        if today not in manifest_data:
            manifest_data[today] = DailyManifest(date=today).to_dict()

        # 追加或更新记录
        existing = manifest_data[today].get('records', [])
        existing = [r for r in existing if not (
            r['source'] == record.source and r['category'] == record.category
        )]
        existing.append(asdict(record))

        manifest_data[today]['records'] = existing
        manifest_data[today]['total_items'] = sum(r['item_count'] for r in existing)
        manifest_data[today]['generated_at'] = datetime.now().isoformat()

        manifest_path.write_text(json.dumps(manifest_data, ensure_ascii=False, indent=2))

    def read(self, category: str, date: str, source: str) -> Optional[Any]:
        """读取 Bronze 数据"""
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        file_path = (self.root / category / str(date_obj.year) /
                     f'{date_obj.month:02d}' / f'{date_obj.day:02d}' /
                     f'{source}.json.gz')
        if not file_path.exists():
            return None
        return json.loads(gzip.decompress(file_path.read_bytes()))

    def list_dates(self, category: str = None) -> List[str]:
        """列出可用的日期"""
        search_path = self.root / category if category else self.root
        dates = set()
        for gz_file in search_path.rglob('*.json.gz'):
            parts = gz_file.relative_to(self.root).parts
            if len(parts) >= 4:
                year, month, day = parts[-4], parts[-3], parts[-2]
                dates.add(f'{year}-{month}-{day}')
        return sorted(dates)


# ═══════════════════════════════════════
# Bronze 批量采集
# ═══════════════════════════════════════

class BronzeCollector:
    """收盘后批量采集所有数据源，写入 Bronze 层"""

    def __init__(self):
        self.writer = BronzeWriter()

    def collect_all(self, date: str = None) -> DailyManifest:
        """采集当日全量数据"""
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')

        manifest = DailyManifest(date=date)
        failed = []

        # ── 1. 日K线 (BaoStock) ──
        try:
            from data_pipeline import get_stock_realtime
            # 获取全A代码列表
            codes = self._get_all_codes()
            if codes:
                kline_data = get_stock_realtime(codes)  # 全量（Sina 批量支持~800只）
                record = self.writer.write(
                    kline_data, 'sina', 'daily_kline', date,
                    fields=['code', 'close', 'change_pct', 'open', 'high', 'low', 'volume'],
                    notes=f'{len(kline_data)}/{len(codes)} stocks'
                )
                manifest.records.append(asdict(record))
        except Exception as e:
            failed.append(f'daily_kline: {e}')

        # ── 2. 资金流向 (东方财富) ──
        try:
            from data_pipeline import get_top_flow_stocks, get_market_money_flow
            flow = get_top_flow_stocks(50, no_cache=True)
            record = self.writer.write(
                flow, 'eastmoney', 'fund_flow', date,
                fields=['code', 'name', 'net_flow', 'change_pct', 'turnover', 'volume_ratio'],
            )
            manifest.records.append(asdict(record))

            market = get_market_money_flow()
            record2 = self.writer.write(
                market, 'eastmoney', 'market_index', date,
                fields=['main_net', 'sh_index', 'sh_change'],
            )
            manifest.records.append(asdict(record2))
        except Exception as e:
            failed.append(f'fund_flow: {e}')

        # ── 3. 基本面 (tushare) ──
        try:
            from data_pipeline import get_index_data
            idx = get_index_data()
            record = self.writer.write(
                idx, 'akshare', 'market_index', date,
                fields=['asia', 'europe', 'us'],
                notes='global indices snapshot'
            )
            manifest.records.append(asdict(record))
        except Exception as e:
            failed.append(f'market_index: {e}')

        # ── 4. 公告事件 ──
        try:
            from resource_pool import build_resource_pool
            pool = build_resource_pool()
            record = self.writer.write(
                pool, 'akshare', 'events', date,
                notes=f'announcements + research + policy'
            )
            manifest.records.append(asdict(record))
        except Exception as e:
            failed.append(f'events: {e}')

        # ── 5. 涨停板 ──
        try:
            import akshare as ak
            date_str = date.replace('-', '')
            zt = ak.stock_zt_pool_em(date=date_str)
            data = zt.to_dict('records') if hasattr(zt, 'to_dict') else []
            record = self.writer.write(
                data if data else [], 'akshare', 'events', date,
                fields=['代码', '名称', '连板数', '封板资金'],
                notes=f'limit_ups: {len(data)} stocks'
            )
            manifest.records.append(asdict(record))
        except Exception:
            pass

        # ── 6. 分时K线 (收盘后全量冻结) ──
        try:
            self._collect_intraday(date, manifest)
        except Exception as e:
            failed.append(f'intraday: {e}')

        # 汇总
        manifest.total_items = sum(r['item_count'] for r in manifest.records)
        manifest.generated_at = datetime.now().isoformat()

        if failed:
            manifest.records.append({
                'source': '_system', 'category': '_errors',
                'date': date, 'notes': '; '.join(failed),
            })

        return manifest

    def _get_all_codes(self) -> List[str]:
        """获取全A代码列表"""
        codes = []
        try:
            import tushare as ts
            token = os.environ.get('TUSHARE_TOKEN', '')
            if token:
                pro = ts.pro_api(token)
                df = pro.stock_basic(exchange='', list_status='L',
                                     fields='ts_code')
                if df is not None and not df.empty:
                    codes = [c.split('.')[0] for c in df['ts_code'].tolist()]
        except Exception:
            pass

        if not codes:
            from data_pipeline import get_stock_realtime
            pool_path = SCRIPT_DIR / 'data' / 'daily_pool.json'
            if pool_path.exists():
                pool = json.loads(pool_path.read_text())
                codes = [c['code'] for c in pool.get('candidates', [])]

        return codes

    def _get_pool_codes(self) -> List[str]:
        """获取推荐池+持仓的关注代码"""
        codes = set()
        pool_path = SCRIPT_DIR / 'data' / 'daily_pool.json'
        if pool_path.exists():
            pool = json.loads(pool_path.read_text())
            for c in pool.get('candidates', []):
                if c.get('code'):
                    codes.add(str(c['code']))

        holdings_path = SCRIPT_DIR.parent / 'data' / 'holdings.json'
        if holdings_path.exists():
            holds = json.loads(holdings_path.read_text())
            for h in holds.get('holdings', []):
                if h.get('code'):
                    codes.add(str(h['code']))

        return list(codes)[:50]  # 最多50只

    def _collect_intraday(self, date: str, manifest: DailyManifest):
        """采集分时K线数据（1min + 5min），按关注代码采样"""
        from data_pipeline import get_intraday_minutes
        codes = self._get_pool_codes()
        if not codes:
            return

        all_5min = {}
        all_1min = {}
        n_ok = 0

        for code in codes:
            try:
                bars_5 = get_intraday_minutes(code, scale=5, count=48)
                if bars_5 and len(bars_5) >= 10:
                    all_5min[code] = bars_5
                    n_ok += 1

                bars_1 = get_intraday_minutes(code, scale=1, count=120)
                if bars_1 and len(bars_1) >= 20:
                    all_1min[code] = bars_1
            except Exception:
                continue

        if all_5min:
            record = self.writer.write(
                all_5min, 'sina', 'intraday', date,
                fields=['time','open','high','low','close','volume','amount'],
                notes=f'{n_ok} stocks × 5min'
            )
            manifest.records.append(asdict(record))

        if all_1min:
            record2 = self.writer.write(
                all_1min, 'sina', 'intraday', date,
                fields=['time','open','high','low','close','volume','amount'],
                notes=f'{len(all_1min)} stocks × 1min'
            )
            manifest.records.append(asdict(record2))


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--collect', action='store_true', help='采集当日全量数据')
    ap.add_argument('--date', type=str, help='指定日期 YYYY-MM-DD')
    ap.add_argument('--list', action='store_true', help='列出已有日期')
    ap.add_argument('--read', nargs=3, metavar=('CATEGORY', 'DATE', 'SOURCE'),
                    help='读取 Bronze 数据')
    args = ap.parse_args()

    if args.collect:
        date = args.date or datetime.now().strftime('%Y-%m-%d')
        collector = BronzeCollector()
        manifest = collector.collect_all(date)
        print(f'Bronze 采集完成: {date}')
        print(f'  记录数: {len(manifest.records)} 批')
        print(f'  总条目: {manifest.total_items}')
        for r in manifest.records:
            name = r.get('source', '?')
            count = r.get('item_count', 0)
            notes = r.get('notes', '')
            print(f'    {name}: {count} items {notes}')

    elif args.list:
        writer = BronzeWriter()
        dates = writer.list_dates()
        print(f'Bronze 可用日期: {len(dates)}')
        for d in dates[-10:]:
            print(f'  {d}')

    elif args.read:
        category, date, source = args.read
        writer = BronzeWriter()
        data = writer.read(category, date, source)
        if data:
            preview = str(data)[:200]
            print(f'{category}/{date}/{source}:')
            print(preview)
        else:
            print(f'{category}/{date}/{source}: 未找到')

    else:
        ap.print_help()


if __name__ == '__main__':
    main()
