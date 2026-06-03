#!/usr/bin/env python3
"""
silver_pipeline.py — Silver 层 ETL 引擎
========================================
从 Bronze 层读取原始数据 → 清洗 → 统一格式 → 写入 Silver 层。

原则:
  - Silver 只读 Bronze，不调任何外部 API
  - 每个日期×代码 有且仅有一行
  - 所有清洗规则可复现

用法:
  python3 silver_pipeline.py --date 2026-06-03    # 单日ETL
  python3 silver_pipeline.py --backfill 30          # 回填近30天
  python3 silver_pipeline.py --build-master         # 构建股票主表
"""

import json, gzip, os, math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict

SCRIPT_DIR = Path(__file__).resolve().parent
BRONZE_ROOT = SCRIPT_DIR.parent / 'data' / 'bronze'
SILVER_ROOT = SCRIPT_DIR.parent / 'data' / 'silver'
MASTER_PATH = SILVER_ROOT / '_meta' / 'stock_master.json.gz'


# ═══════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════

@dataclass
class SilverRow:
    """Silver 层单行——一只股票在某一天的全部清洗后数据"""
    code: str
    name: str = ""
    date: str = ""

    # 行情 (来源: Bronze daily_kline)
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    pre_close: float = 0.0
    change_pct: float = 0.0
    volume: float = 0.0
    amount: float = 0.0

    # 估值 (来源: Bronze fundamentals + daily_kline)
    pe_ttm: float = 0.0
    pb: float = 0.0
    total_mv: float = 0.0        # 总市值(亿)
    circ_mv: float = 0.0          # 流通市值(亿)

    # 资金 (来源: Bronze fund_flow)
    net_flow: float = 0.0          # 主力净流入(万)
    turnover: float = 0.0          # 换手率(%)
    volume_ratio: float = 0.0      # 量比

    # 行业
    industry: str = ""

    # 状态标记
    is_suspended: bool = False       # 停牌
    is_st: bool = False              # ST
    is_new_listing: bool = False     # 次新股(<60天)

    # 质量标记
    quality_flags: List[str] = field(default_factory=list)  # ['outlier_price','stale','low_volume']


@dataclass
class SilverManifest:
    date: str
    n_stocks: int = 0
    n_clean: int = 0
    n_suspended: int = 0
    n_outliers: int = 0
    n_missing: int = 0
    quality_issues: List[str] = field(default_factory=list)
    generated_at: str = ""


# ═══════════════════════════════════════
# 清洗规则
# ═══════════════════════════════════════

class SilverCleaner:
    """数据清洗规则集"""

    @staticmethod
    def is_outlier_price(close: float, pre_close: float) -> bool:
        """价格异常：变化>20% 且非涨跌停"""
        if pre_close <= 0 or close <= 0:
            return False
        chg = abs(close - pre_close) / pre_close
        return chg > 0.20 and chg < 0.30  # 涨跌停约10-20%, 20-30%属异常

    @staticmethod
    def is_low_volume(volume: float, avg_volume: float = None) -> bool:
        """成交量异常低"""
        if volume <= 0:
            return True
        if avg_volume and avg_volume > 0:
            return volume < avg_volume * 0.05  # 不到均量5%
        return False

    @staticmethod
    def is_stale_data(change_pct: float, close: float) -> bool:
        """数据陈旧：涨跌幅和收盘价双零"""
        return change_pct == 0.0 and close == 0.0

    @staticmethod
    def normalize_code(code: str) -> str:
        """统一代码格式：6位数字"""
        return str(code).zfill(6)


# ═══════════════════════════════════════
# Silver ETL 引擎
# ═══════════════════════════════════════

class SilverPipeline:
    """Bronze → Silver ETL"""

    def __init__(self):
        self.cleaner = SilverCleaner()
        self.stock_master: Dict[str, Dict] = {}
        self._load_master()

    def _load_master(self):
        if MASTER_PATH.exists():
            self.stock_master = json.loads(gzip.decompress(MASTER_PATH.read_bytes()))

    def build_stock_master(self) -> Dict[str, Dict]:
        """从 tushare 构建股票主表（一次性操作）"""
        master = {}
        try:
            import tushare as ts
            token = os.environ.get('TUSHARE_TOKEN', '')
            if token:
                pro = ts.pro_api(token)
                df = pro.stock_basic(exchange='', list_status='L',
                                     fields='ts_code,name,industry,list_date,delist_date')
                if df is not None and not df.empty:
                    for _, row in df.iterrows():
                        code = row['ts_code'].split('.')[0]
                        master[code] = {
                            'code': code,
                            'name': str(row.get('name', '')),
                            'industry': str(row.get('industry', '')),
                            'list_date': str(row.get('list_date', '')),
                            'delist_date': str(row.get('delist_date', '')) if row.get('delist_date') else '',
                            'is_st': 'ST' in str(row.get('name', '')),
                        }
        except Exception as e:
            print(f'[Silver] 股票主表构建失败(tushare): {e}')

        if not master:
            # fallback: 从 Bronze daily_kline 提取
            for gz_file in BRONZE_ROOT.rglob('daily_kline/**/*.json.gz'):
                try:
                    data = json.loads(gzip.decompress(gz_file.read_bytes()))
                    for code, info in data.items() if isinstance(data, dict) else []:
                        if code not in master:
                            master[code] = {
                                'code': code,
                                'name': info.get('name', ''),
                                'industry': '',
                                'list_date': '',
                                'delist_date': '',
                                'is_st': False,
                            }
                except Exception:
                    continue

        self.stock_master = master
        MASTER_PATH.parent.mkdir(parents=True, exist_ok=True)
        MASTER_PATH.write_bytes(gzip.compress(
            json.dumps(master, ensure_ascii=False).encode('utf-8')))
        print(f'[Silver] 股票主表: {len(master)} 只')
        return master

    def run(self, date: str) -> Tuple[List[SilverRow], SilverManifest]:
        """执行单日 ETL：Bronze → Silver"""
        manifest = SilverManifest(date=date)

        # ── Step 1: 读取 Bronze ──
        bronze_kline = self._read_bronze('daily_kline', date, 'sina')
        bronze_flow = self._read_bronze('fund_flow', date, 'eastmoney')

        if not bronze_kline:
            manifest.quality_issues.append('无日K线数据')
            return [], manifest

        # ── Step 2: 构建代码集合 ──
        all_codes = set()
        if isinstance(bronze_kline, dict):
            all_codes.update(bronze_kline.keys())

        # ── Step 3: 逐代码清洗 ──
        rows = []
        for code in all_codes:
            row = self._clean_row(code, date, bronze_kline, bronze_flow)
            if row:
                rows.append(row)

        # ── Step 4: 统计 ──
        manifest.n_stocks = len(rows)
        manifest.n_suspended = sum(1 for r in rows if r.is_suspended)
        manifest.n_outliers = sum(1 for r in rows if r.quality_flags)
        manifest.n_missing = len(all_codes) - len(rows)
        manifest.generated_at = datetime.now().isoformat()

        # ── Step 5: 写入 Silver ──
        self._write_silver(date, rows)

        return rows, manifest

    def _read_bronze(self, category: str, date: str, source: str) -> Optional[Any]:
        """读取 Bronze 数据"""
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        path = (BRONZE_ROOT / category / str(date_obj.year) /
                f'{date_obj.month:02d}' / f'{date_obj.day:02d}' /
                f'{source}.json.gz')
        if not path.exists():
            return None
        try:
            return json.loads(gzip.decompress(path.read_bytes()))
        except Exception:
            return None

    def _clean_row(self, code: str, date: str,
                   bronze_kline: Dict, bronze_flow: Dict) -> Optional[SilverRow]:
        """清洗单只股票的一行数据"""
        code = self.cleaner.normalize_code(code)
        master = self.stock_master.get(code, {})
        row = SilverRow(code=code, date=date)

        # ── 行情 ──
        kline = bronze_kline.get(code, {}) if isinstance(bronze_kline, dict) else {}
        row.name = kline.get('name', master.get('name', ''))
        row.close = float(kline.get('close', 0))
        row.open = float(kline.get('open', 0))
        row.high = float(kline.get('high', 0))
        row.low = float(kline.get('low', 0))
        row.change_pct = float(kline.get('change_pct', 0))
        row.volume = float(kline.get('volume', 0))
        row.amount = float(kline.get('amount', 0))

        # 推算 pre_close
        if row.close > 0 and row.change_pct != 0:
            row.pre_close = round(row.close / (1 + row.change_pct / 100), 2)

        # ── 资金 ──
        if isinstance(bronze_flow, list):
            for f in bronze_flow:
                if str(f.get('code', '')) == code:
                    row.net_flow = float(f.get('net_flow', 0) or 0)
                    row.turnover = float(f.get('turnover', 0) or 0)
                    row.volume_ratio = float(f.get('volume_ratio', 0) or 0)
                    break

        # ── 基本面 ──
        row.industry = master.get('industry', '')
        row.is_st = master.get('is_st', False)

        # 次新股检测
        list_date = master.get('list_date', '')
        if list_date and len(list_date) == 8:
            days = (datetime.strptime(date, '%Y-%m-%d') -
                    datetime.strptime(list_date, '%Y%m%d')).days
            row.is_new_listing = days < 60

        # ── 状态判定 ──
        row.is_suspended = self.cleaner.is_stale_data(row.change_pct, row.close)

        # ── 质量标记 ──
        if self.cleaner.is_outlier_price(row.close, row.pre_close):
            row.quality_flags.append('outlier_price')
        if self.cleaner.is_low_volume(row.volume):
            row.quality_flags.append('low_volume')

        return row

    def _write_silver(self, date: str, rows: List[SilverRow]):
        """写入 Silver 层"""
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        dir_path = (SILVER_ROOT / 'stock_daily' / str(date_obj.year) /
                    f'{date_obj.month:02d}' / f'{date_obj.day:02d}')
        dir_path.mkdir(parents=True, exist_ok=True)

        data = [asdict(r) for r in rows]
        compressed = gzip.compress(json.dumps(data, ensure_ascii=False).encode('utf-8'))

        file_path = dir_path / 'all.json.gz'
        tmp = file_path.with_suffix('.tmp')
        tmp.write_bytes(compressed)
        tmp.rename(file_path)

        # 写 manifest
        manifest = SilverManifest(
            date=date, n_stocks=len(rows),
            n_suspended=sum(1 for r in rows if r.is_suspended),
            n_outliers=sum(1 for r in rows if r.quality_flags),
            generated_at=datetime.now().isoformat(),
        )
        manifest_path = dir_path / '_manifest.json'
        manifest_path.write_text(json.dumps(asdict(manifest), ensure_ascii=False, indent=2))

        print(f'[Silver] {date}: {len(rows)} stocks → {file_path}')

    def backfill(self, days: int = 30):
        """回填最近 N 天"""
        today = datetime.now()
        for i in range(days):
            date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
            rows, manifest = self.run(date)
            if manifest.n_stocks == 0:
                print(f'[Silver] {date}: 跳过 (无数据)')
            if manifest.quality_issues:
                print(f'  ⚠️ {"; ".join(manifest.quality_issues)}')


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', type=str, help='执行单日 ETL')
    ap.add_argument('--backfill', type=int, default=0, help='回填最近N天')
    ap.add_argument('--build-master', action='store_true', help='构建股票主表')
    ap.add_argument('--verify', type=str, help='验证指定日期')
    args = ap.parse_args()

    pipeline = SilverPipeline()

    if args.build_master:
        master = pipeline.build_stock_master()
        return

    if args.backfill:
        pipeline.backfill(args.backfill)
        return

    date = args.date or datetime.now().strftime('%Y-%m-%d')
    rows, manifest = pipeline.run(date)
    print(f'[Silver] {date}: {manifest.n_stocks} 行, '
          f'停牌={manifest.n_suspended}, 异常={manifest.n_outliers}')


if __name__ == '__main__':
    main()
