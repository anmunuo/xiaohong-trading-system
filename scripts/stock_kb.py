#!/usr/bin/env python3
"""
stock_kb.py — SQLite 本地股票知识库 v1.0
=========================================
将所有 A 股历史数据爬取到本地 SQLite，支持毫秒级查询。

架构:
  爬虫层 (akshare / baostock / tushare)
    ↓
  SQLite 存储 (WAL 模式, 多索引, 分批写入)
    ↓
  查询 API (按代码/日期/因子/条件筛选)

表结构:
  stocks        — 全A股票主表 (代码/名称/行业/市值/上市日期)
  daily_kline   — 日K线 (OHLCV + PE/PB + 换手率 + MA)
  financials    — 财务指标 (ROE/毛利率/净利率/负债率/现金流)
  fund_flow     — 资金流向 (主力/超大单/大单/中单/小单)
  index_daily   — 指数日线 (上证/深证/创业板/沪深300/科创50)
  crawl_log     — 爬取日志 (最后更新时间/状态)

用法:
  python3 stock_kb.py --init              # 初始化数据库 + 爬全量数据
  python3 stock_kb.py --update            # 增量更新最近交易日
  python3 stock_kb.py --query 600519      # 查询单只股票
  python3 stock_kb.py --query "ROE>15 PE<20"  # 条件筛选
  python3 stock_kb.py --stats             # 数据库统计
"""

import os
import sys
import json
import time
import logging
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass

# 路径
SCRIPT_DIR = Path(__file__).resolve().parent
DB_PATH = SCRIPT_DIR / 'data' / 'stock_kb.db'
ENV_PATH = SCRIPT_DIR.parent / '.env'

__version__ = "1.0.0"

# 日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
_log = logging.getLogger("stock_kb")

# ═══════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-65536;
PRAGMA busy_timeout=30000;

-- 股票主表
CREATE TABLE IF NOT EXISTS stocks (
    code        TEXT PRIMARY KEY,         -- 纯数字代码 000001
    ts_code     TEXT UNIQUE,              -- tushare格式 000001.SZ
    name        TEXT NOT NULL,            -- 名称
    market      TEXT,                     -- SH/SZ/BJ
    industry    TEXT,                     -- 申万行业
    list_date   TEXT,                     -- 上市日期 YYYYMMDD
    total_mv    REAL,                     -- 总市值（亿）
    circ_mv     REAL,                     -- 流通市值（亿）
    is_active   INTEGER DEFAULT 1,        -- 是否正常交易
    updated_at  TEXT                      -- 最后更新
);

CREATE INDEX IF NOT EXISTS idx_stocks_industry ON stocks(industry);
CREATE INDEX IF NOT EXISTS idx_stocks_market ON stocks(market);
CREATE INDEX IF NOT EXISTS idx_stocks_mv ON stocks(total_mv);

-- 日K线
CREATE TABLE IF NOT EXISTS daily_kline (
    code        TEXT NOT NULL,            -- 股票代码
    trade_date  TEXT NOT NULL,            -- 交易日期 YYYYMMDD
    open        REAL,                     -- 开盘价
    high        REAL,                     -- 最高价
    low         REAL,                     -- 最低价
    close       REAL,                     -- 收盘价
    pre_close   REAL,                     -- 昨收
    change_pct  REAL,                     -- 涨跌幅 %
    volume      REAL,                     -- 成交量（手）
    amount      REAL,                     -- 成交额（万元）
    turnover    REAL,                     -- 换手率 %
    pe_ttm      REAL,                     -- 滚动市盈率
    pb_mrq      REAL,                     -- 市净率
    ma5         REAL,                     -- 5日均线
    ma10        REAL,                     -- 10日均线
    ma20        REAL,                     -- 20日均线
    PRIMARY KEY (code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_kline_date ON daily_kline(trade_date);
CREATE INDEX IF NOT EXISTS idx_kline_pe ON daily_kline(pe_ttm);
CREATE INDEX IF NOT EXISTS idx_kline_change ON daily_kline(trade_date, change_pct);

-- 财务指标（季频）
CREATE TABLE IF NOT EXISTS financials (
    code            TEXT NOT NULL,        -- 股票代码
    end_date        TEXT NOT NULL,        -- 报告期 YYYYMMDD
    roe             REAL,                 -- ROE %
    roa             REAL,                 -- ROA %
    gross_margin    REAL,                 -- 毛利率 %
    net_margin      REAL,                 -- 净利率 %
    eps             REAL,                 -- 每股收益
    bps             REAL,                 -- 每股净资产
    debt_ratio      REAL,                 -- 资产负债率 %
    current_ratio   REAL,                 -- 流动比率
    revenue_yoy     REAL,                 -- 营收同比 %
    profit_yoy      REAL,                 -- 利润同比 %
    ocf_per_share   REAL,                 -- 每股经营现金流
    PRIMARY KEY (code, end_date)
);

CREATE INDEX IF NOT EXISTS idx_fin_date ON financials(end_date);
CREATE INDEX IF NOT EXISTS idx_fin_roe ON financials(roe);

-- 资金流向（日频）
CREATE TABLE IF NOT EXISTS fund_flow (
    code            TEXT NOT NULL,        -- 股票代码
    trade_date      TEXT NOT NULL,        -- 交易日期
    main_net        REAL,                 -- 主力净流入（万元）
    main_pct        REAL,                 -- 主力净流入占比 %
    super_large_net REAL,                 -- 超大单净流入（万元）
    large_net       REAL,                 -- 大单净流入（万元）
    mid_net         REAL,                 -- 中单净流入（万元）
    small_net       REAL,                 -- 小单净流入（万元）
    PRIMARY KEY (code, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_flow_date ON fund_flow(trade_date);
CREATE INDEX IF NOT EXISTS idx_flow_main ON fund_flow(trade_date, main_net);

-- 指数日线
CREATE TABLE IF NOT EXISTS index_daily (
    code        TEXT NOT NULL,            -- sh000001/sz399001/sz399006/sh000300/sh000688
    name        TEXT,                     -- 指数名称
    trade_date  TEXT NOT NULL,
    open        REAL,
    high        REAL,
    low         REAL,
    close       REAL,
    change_pct  REAL,
    volume      REAL,
    amount      REAL,
    PRIMARY KEY (code, trade_date)
);

-- 爬取日志
CREATE TABLE IF NOT EXISTS crawl_log (
    table_name  TEXT NOT NULL,
    data_date   TEXT NOT NULL,            -- 数据日期（最新爬取到的交易日）
    crawl_time  TEXT,                     -- 爬取时间
    row_count   INTEGER,
    status      TEXT,                     -- ok/partial/failed
    PRIMARY KEY (table_name, data_date)
);

CREATE INDEX IF NOT EXISTS idx_crawl_log ON crawl_log(table_name, data_date);
"""

# ═══════════════════════════════════════════
# 爬虫引擎
# ═══════════════════════════════════════════

class StockKBCrawler:
    """爬取全A股票数据到 SQLite"""

    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or DB_PATH)
        self.db_path = os.path.expanduser(self.db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def init_schema(self):
        """初始化数据库结构"""
        _log.info("初始化数据库 Schema...")
        with self._get_conn() as conn:
            conn.executescript(SCHEMA_SQL)
        _log.info("Schema 创建完成")

    def crawl_stock_list(self) -> int:
        """爬取全A股票列表"""
        _log.info("爬取全A股票列表...")
        import akshare as ak

        # 沪市
        try:
            df_sh = ak.stock_info_sh_name_code()
            df_sh = df_sh.rename(columns={'证券代码': 'code', '证券简称': 'name'})
            df_sh['market'] = 'SH'
        except Exception as e:
            _log.warning(f"沪市列表失败: {e}, 用 tushare")
            df_sh = self._get_stock_list_tushare('SH')

        # 深市
        try:
            df_sz = ak.stock_info_sz_name_code()
            df_sz = df_sz.rename(columns={'A股代码': 'code', 'A股简称': 'name'})
            df_sz['market'] = 'SZ'
        except Exception as e:
            _log.warning(f"深市列表失败: {e}, 用 tushare")
            df_sz = self._get_stock_list_tushare('SZ')

        # 北交所
        try:
            df_bj = ak.stock_info_bj_name_code()
            df_bj = df_bj.rename(columns={'证券代码': 'code', '证券简称': 'name'})
            df_bj['market'] = 'BJ'
        except Exception:
            _log.warning("北交所列表获取失败，跳过")
            df_bj = None

        frames = [df_sh[['code', 'name', 'market']], df_sz[['code', 'name', 'market']]]
        if df_bj is not None and not df_bj.empty:
            frames.append(df_bj[['code', 'name', 'market']])

        import pandas as pd
        df_all = pd.concat(frames, ignore_index=True)
        df_all['code'] = df_all['code'].astype(str).str.zfill(6)

        count = 0
        with self._get_conn() as conn:
            for _, row in df_all.iterrows():
                code = row['code']
                name = row['name']
                market = row.get('market', '')
                ts_code = f"{code}.{market}" if market else f"{code}.{'SH' if code.startswith(('6','9')) else 'SZ'}"

                conn.execute(
                    """INSERT OR REPLACE INTO stocks (code, ts_code, name, market, is_active, updated_at)
                       VALUES (?, ?, ?, ?, 1, ?)""",
                    (code, ts_code, name, market, datetime.now().isoformat())
                )
                count += 1

        _log.info(f"股票列表: {count} 只")
        return count

    def _get_stock_list_tushare(self, market: str):
        """备用：tushare 获取股票列表"""
        import tushare as ts
        token = self._load_tushare_token()
        if not token:
            raise RuntimeError("无 tushare token")

        pro = ts.pro_api(token)
        if market == 'SH':
            df = pro.stock_basic(exchange='SSE', list_status='L', fields='ts_code,symbol,name')
        else:
            df = pro.stock_basic(exchange='SZSE', list_status='L', fields='ts_code,symbol,name')

        df = df.rename(columns={'symbol': 'code', 'name': 'name'})
        df['market'] = market
        return df

    def crawl_daily_kline(self, start_date: str = '2020-01-01', codes: List[str] = None) -> int:
        """爬取日K线数据 (使用 baostock)"""
        import baostock as bs
        bs.login()

        if codes is None:
            codes = self._get_all_codes()

        today = datetime.now().strftime('%Y-%m-%d')
        # 确保日期为 YYYY-MM-DD 格式（baostock 需要）
        if len(start_date) == 8:
            start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        total = 0
        batch_size = 100

        for i in range(0, len(codes), batch_size):
            batch = codes[i:i+batch_size]
            for code in batch:
                try:
                    prefix = 'sh' if code.startswith(('6', '9')) else 'sz'
                    rs = bs.query_history_k_data_plus(
                        f'{prefix}.{code}',
                        'date,open,high,low,close,preclose,volume,amount,turn,peTTM,pbMRQ',
                        start_date=start_date, end_date=today,
                        frequency='d', adjustflag='2'
                    )
                    rows = rs.data if rs else []
                    if not rows:
                        continue

                    with self._get_conn() as conn:
                        for row in rows:
                            d, o, h, l, c, pc, v, amt, turn, pe, pb = row
                            if not d or not c:
                                continue
                            try:
                                change_pct = round((float(c) / float(pc) - 1) * 100, 2) if pc and float(pc) > 0 else None
                                conn.execute(
                                    """INSERT OR REPLACE INTO daily_kline
                                       (code, trade_date, open, high, low, close, pre_close,
                                        change_pct, volume, amount, turnover, pe_ttm, pb_mrq)
                                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                                    (code, d,
                                     float(o) if o else None,
                                     float(h) if h else None,
                                     float(l) if l else None,
                                     float(c) if c else None,
                                     float(pc) if pc else None,
                                     change_pct,
                                     float(v) if v else None,
                                     float(amt) if amt else None,
                                     float(turn) if turn else None,
                                     float(pe) if pe and pe != '' else None,
                                     float(pb) if pb and pb != '' else None)
                                )
                                total += 1
                            except Exception:
                                # 静默跳过单行 INSERT 失败
                                continue
                except Exception:
                    continue

            _log.info(f"进度: {min(i+batch_size, len(codes))}/{len(codes)}, 累计 {total} 条")

        bs.logout()

        # 计算 MA
        _log.info("计算 MA 均线...")
        self._compute_ma()

        # 记录日志
        self._log_crawl('daily_kline', today.replace('-', ''), total)
        _log.info(f"日K线: {total} 条")
        return total

    def _compute_ma(self):
        """计算 MA5/MA10/MA20（SQLite 窗口函数）"""
        with self._get_conn() as conn:
            # 获取所有code
            codes = [r[0] for r in conn.execute("SELECT DISTINCT code FROM daily_kline")]

            for code in codes:
                rows = conn.execute(
                    """SELECT trade_date, close FROM daily_kline
                       WHERE code=? ORDER BY trade_date""", (code,)
                ).fetchall()

                closes = [r['close'] for r in rows if r['close']]
                dates = [r['trade_date'] for r in rows]

                for i in range(len(closes)):
                    d = dates[i]
                    ma5 = round(sum(closes[max(0,i-4):i+1]) / min(i+1, 5), 2) if closes[i] else None
                    ma10 = round(sum(closes[max(0,i-9):i+1]) / min(i+1, 10), 2) if i >= 9 and closes[i] else None
                    ma20 = round(sum(closes[max(0,i-19):i+1]) / min(i+1, 20), 2) if i >= 19 and closes[i] else None

                    conn.execute(
                        "UPDATE daily_kline SET ma5=?, ma10=?, ma20=? WHERE code=? AND trade_date=?",
                        (ma5, ma10, ma20, code, d)
                    )

    def crawl_financials(self, codes: List[str] = None, years: int = 5) -> int:
        """爬取财务指标 (使用 akshare)"""
        import akshare as ak
        import pandas as pd

        if codes is None:
            codes = self._get_all_codes()

        total = 0
        for i, code in enumerate(codes):
            try:
                df = ak.stock_financial_analysis_indicator(symbol=code)
                if df.empty:
                    continue

                # 找最近几年的季度数据
                df = df.sort_values('日期', ascending=False)
                cutoff = datetime.now() - timedelta(days=years*365)
                df = df[df['日期'] >= cutoff.strftime('%Y%m%d')]

                with self._get_conn() as conn:
                    for _, r in df.iterrows():
                        try:
                            conn.execute(
                                """INSERT OR REPLACE INTO financials
                                   (code, end_date, roe, roa, gross_margin, net_margin,
                                    eps, bps, debt_ratio, current_ratio, revenue_yoy, profit_yoy, ocf_per_share)
                                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                                (
                                    code,
                                    r.get('日期', ''),
                                    self._safe_float(r.get('净资产收益率(%)')),
                                    self._safe_float(r.get('总资产报酬率ROA(%)')),
                                    self._safe_float(r.get('销售毛利率(%)')),
                                    self._safe_float(r.get('销售净利率(%)')),
                                    self._safe_float(r.get('每股收益')),
                                    self._safe_float(r.get('每股净资产')),
                                    self._safe_float(r.get('资产负债率(%)')),
                                    self._safe_float(r.get('流动比率')),
                                    self._safe_float(r.get('营业收入同比增长率(%)')),
                                    self._safe_float(r.get('净利润同比增长率(%)')),
                                    self._safe_float(r.get('每股经营性现金流(元)')),
                                )
                            )
                            total += 1
                        except Exception:
                            continue
            except Exception:
                continue

            if (i+1) % 100 == 0:
                _log.info(f"财务进度: {i+1}/{len(codes)}, 累计 {total} 条")

        _log.info(f"财务数据: {total} 条")
        return total

    def crawl_fund_flow(self, start_date: str = '20240101', codes: List[str] = None) -> int:
        """爬取资金流向 (使用 akshare)"""
        import akshare as ak

        if codes is None:
            codes = self._get_all_codes()

        total = 0
        for code in codes:
            try:
                df = ak.stock_individual_fund_flow(stock=code, market=self._get_market(code))
                if df.empty:
                    continue

                df = df[df['日期'] >= start_date]
                with self._get_conn() as conn:
                    for _, r in df.iterrows():
                        try:
                            conn.execute(
                                """INSERT OR REPLACE INTO fund_flow
                                   (code, trade_date, main_net, main_pct,
                                    super_large_net, large_net, mid_net, small_net)
                                   VALUES (?,?,?,?,?,?,?,?)""",
                                (
                                    code, r.get('日期', ''),
                                    self._safe_float(r.get('主力净流入-净额')),
                                    self._safe_float(r.get('主力净流入-净占比')),
                                    self._safe_float(r.get('超大单净流入-净额')),
                                    self._safe_float(r.get('大单净流入-净额')),
                                    self._safe_float(r.get('中单净流入-净额')),
                                    self._safe_float(r.get('小单净流入-净额')),
                                )
                            )
                            total += 1
                        except Exception:
                            continue
            except Exception:
                continue

            if (codes.index(code)+1) % 100 == 0:
                _log.info(f"资金流进度: {codes.index(code)+1}/{len(codes)}, 累计 {total} 条")

        _log.info(f"资金流向: {total} 条")
        return total

    def crawl_indices(self) -> int:
        """爬取主要指数"""
        import baostock as bs
        bs.login()

        indices = {
            'sh.000001': '上证指数',
            'sz.399001': '深证成指',
            'sz.399006': '创业板指',
            'sh.000300': '沪深300',
            'sh.000688': '科创50',
        }

        total = 0
        for bs_code, name in indices.items():
            try:
                rs = bs.query_history_k_data_plus(
                    bs_code, 'date,open,high,low,close,preclose,volume,amount',
                    start_date='2018-01-01', end_date=datetime.now().strftime('%Y-%m-%d'),
                    frequency='d', adjustflag='1'
                )
                rows = rs.data if rs else []

                code = bs_code.replace('.', '')
                with self._get_conn() as conn:
                    for row in rows:
                        d, o, h, l, c, pc, v, amt = row
                        if not d: continue
                        try:
                            change = round((float(c)/float(pc)-1)*100, 2) if pc and float(pc)>0 else None
                            conn.execute(
                                """INSERT OR REPLACE INTO index_daily
                                   (code, name, trade_date, open, high, low, close, change_pct, volume, amount)
                                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                                (code, name, d,
                                 float(o) if o else None, float(h) if h else None,
                                 float(l) if l else None, float(c) if c else None,
                                 change,
                                 float(v) if v else None, float(amt) if amt else None)
                            )
                            total += 1
                        except Exception:
                            continue
            except Exception as e:
                _log.warning(f"指数 {name} 爬取失败: {e}")

        bs.logout()
        _log.info(f"指数数据: {total} 条")
        return total

    def crawl_all(self, start_date: str = '2020-01-01'):
        """一键爬取所有数据"""
        _log.info("=" * 50)
        _log.info("开始全量爬取...")
        _log.info("=" * 50)

        t0 = time.time()

        self.init_schema()

        n_stocks = self.crawl_stock_list()
        _log.info(f"[1/4] 股票列表: {n_stocks} 只 ({time.time()-t0:.0f}s)")

        n_kline = self.crawl_daily_kline(start_date=start_date)
        _log.info(f"[2/4] 日K线: {n_kline} 条 ({time.time()-t0:.0f}s)")

        n_fin = self.crawl_financials()
        _log.info(f"[3/4] 财务数据: {n_fin} 条 ({time.time()-t0:.0f}s)")

        n_idx = self.crawl_indices()
        _log.info(f"[4/4] 指数: {n_idx} 条 ({time.time()-t0:.0f}s)")

        _log.info(f"全量爬取完成! 总耗时 {time.time()-t0:.0f}s")
        return {
            'stocks': n_stocks, 'kline': n_kline,
            'financials': n_fin, 'indices': n_idx
        }

    def update_recent(self, days: int = 7):
        """增量更新最近 N 天数据"""
        _log.info(f"增量更新最近 {days} 天...")
        from datetime import timedelta
        start = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        self.crawl_daily_kline(start_date=start)

    # --- 工具方法 ---

    def _get_all_codes(self) -> List[str]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT code FROM stocks WHERE is_active=1 ORDER BY code").fetchall()
        return [r['code'] for r in rows]

    def _get_market(self, code: str) -> str:
        if code.startswith(('6','9')): return 'sh'
        return 'sz'

    def _load_tushare_token(self) -> str:
        if ENV_PATH.exists():
            for line in ENV_PATH.read_text().splitlines():
                if line.startswith('TUSHARE_TOKEN='):
                    return line.split('=', 1)[1].strip()
        return os.environ.get('TUSHARE_TOKEN', '')

    def _safe_float(self, val) -> Optional[float]:
        if val is None or val == '' or val == '-' or val == '--':
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    def _log_crawl(self, table: str, data_date: str, row_count: int, status: str = 'ok'):
        with self._get_conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO crawl_log (table_name, data_date, crawl_time, row_count, status)
                   VALUES (?, ?, ?, ?, ?)""",
                (table, data_date, datetime.now().isoformat(), row_count, status)
            )


# ═══════════════════════════════════════════
# 查询引擎
# ═══════════════════════════════════════════

class StockKBQuery:
    """快速查询股票知识库"""

    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or DB_PATH)

    def _get_conn(self):
        conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn

    def get_stock_info(self, code: str) -> Optional[Dict]:
        """获取股票基本信息"""
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM stocks WHERE code=?", (code,)).fetchone()
        return dict(row) if row else None

    def get_kline(self, code: str, start: str = None, end: str = None, limit: int = 100) -> List[Dict]:
        """获取日K线"""
        with self._get_conn() as conn:
            sql = "SELECT * FROM daily_kline WHERE code=? "
            params = [code]
            if start:
                sql += "AND trade_date >= ? "
                params.append(start)
            if end:
                sql += "AND trade_date <= ? "
                params.append(end)
            sql += "ORDER BY trade_date DESC LIMIT ?"
            params.append(limit)
            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_latest_price(self, code: str) -> Optional[Dict]:
        """获取最近一个交易日行情"""
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT * FROM daily_kline WHERE code=? ORDER BY trade_date DESC LIMIT 1",
                (code,)
            ).fetchone()
        return dict(row) if row else None

    def get_financials(self, code: str, limit: int = 8) -> List[Dict]:
        """获取最近 N 期财务数据"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM financials WHERE code=? ORDER BY end_date DESC LIMIT ?",
                (code, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_fund_flow(self, code: str, limit: int = 20) -> List[Dict]:
        """获取资金流向"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM fund_flow WHERE code=? ORDER BY trade_date DESC LIMIT ?",
                (code, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_index(self, index_code: str = 'sh000001', limit: int = 100) -> List[Dict]:
        """获取指数日线"""
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM index_daily WHERE code=? ORDER BY trade_date DESC LIMIT ?",
                (index_code, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def screen_stocks(self, conditions: Dict[str, Any]) -> List[Dict]:
        """
        条件筛选股票

        conditions:
          min_roe, max_pe, min_change_pct, max_change_pct,
          min_market_cap, max_market_cap, industry, market,
          min_main_net, limit
        """
        limit = conditions.pop('limit', 50)

        with self._get_conn() as conn:
            sql = """
                SELECT DISTINCT s.code, s.name, s.industry, s.total_mv, s.circ_mv,
                       k.close, k.change_pct, k.pe_ttm, k.pb_mrq, k.turnover, k.volume,
                       f.roe, f.gross_margin, f.net_margin
                FROM stocks s
                LEFT JOIN daily_kline k ON s.code = k.code
                LEFT JOIN financials f ON s.code = f.code
                WHERE s.is_active = 1
            """
            params = []

            # 获取最近交易日
            last_date_row = conn.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()
            last_date = last_date_row[0] if last_date_row else ''
            if last_date:
                sql += " AND k.trade_date = ?"
                params.append(last_date)

            # 获取最新财季
            fin_date_row = conn.execute("SELECT MAX(end_date) FROM financials").fetchone()
            fin_date = fin_date_row[0] if fin_date_row else ''
            if fin_date:
                sql += " AND f.end_date = ?"
                params.append(fin_date)

            # 条件过滤
            if 'min_roe' in conditions:
                sql += " AND f.roe >= ?"
                params.append(conditions['min_roe'])
            if 'min_pe' in conditions:
                sql += " AND k.pe_ttm >= ?"
                params.append(conditions['min_pe'])
            if 'max_pe' in conditions:
                sql += " AND k.pe_ttm <= ?"
                params.append(conditions['max_pe'])
            if 'min_change_pct' in conditions:
                sql += " AND k.change_pct >= ?"
                params.append(conditions['min_change_pct'])
            if 'min_market_cap' in conditions:
                sql += " AND s.total_mv >= ?"
                params.append(conditions['min_market_cap'])
            if 'max_market_cap' in conditions:
                sql += " AND s.total_mv <= ?"
                params.append(conditions['max_market_cap'])
            if 'industry' in conditions:
                sql += " AND s.industry = ?"
                params.append(conditions['industry'])
            if 'market' in conditions:
                sql += " AND s.market = ?"
                params.append(conditions['market'])

            sql += " ORDER BY k.pe_ttm ASC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_top_gainers(self, date: str = None, limit: int = 30) -> List[Dict]:
        """获取某日涨幅榜"""
        with self._get_conn() as conn:
            if not date:
                date = conn.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()[0]

            rows = conn.execute(
                """SELECT d.code, s.name, d.change_pct, d.close, d.volume, d.turnover,
                          d.pe_ttm, s.industry
                   FROM daily_kline d
                   JOIN stocks s ON d.code = s.code
                   WHERE d.trade_date = ? AND d.change_pct IS NOT NULL
                   ORDER BY d.change_pct DESC LIMIT ?""",
                (date, limit)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> Dict:
        """获取数据库统计"""
        with self._get_conn() as conn:
            tables = ['stocks', 'daily_kline', 'financials', 'fund_flow', 'index_daily']
            stats = {}
            for t in tables:
                row = conn.execute(f"SELECT COUNT(*) as cnt FROM {t}").fetchone()
                stats[t] = row['cnt']

            # 最新数据日期
            row = conn.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()
            stats['latest_kline_date'] = row[0] if row else None

            row = conn.execute("SELECT MAX(end_date) FROM financials").fetchone()
            stats['latest_fin_date'] = row[0] if row else None

            row = conn.execute("SELECT COUNT(DISTINCT code) FROM daily_kline").fetchone()
            stats['stocks_with_kline'] = row[0] if row else 0

            row = conn.execute("SELECT COUNT(DISTINCT code) FROM financials").fetchone()
            stats['stocks_with_fin'] = row[0] if row else 0

        return stats

    def get_market_snapshot(self, date: str = None) -> Dict:
        """获取某日全市场快照"""
        with self._get_conn() as conn:
            if not date:
                date = conn.execute("SELECT MAX(trade_date) FROM daily_kline").fetchone()[0]

            # 涨跌统计
            stats = conn.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN change_pct > 0 THEN 1 ELSE 0 END) as up_count,
                    SUM(CASE WHEN change_pct < 0 THEN 1 ELSE 0 END) as down_count,
                    SUM(CASE WHEN change_pct >= 9.8 THEN 1 ELSE 0 END) as limit_up,
                    SUM(CASE WHEN change_pct <= -9.8 THEN 1 ELSE 0 END) as limit_down,
                    AVG(change_pct) as avg_change,
                    AVG(CASE WHEN change_pct>0 THEN change_pct END) as avg_up,
                    AVG(CASE WHEN change_pct<0 THEN change_pct END) as avg_down
                FROM daily_kline WHERE trade_date = ?
            """, (date,)).fetchone()

            # 成交额 TOP
            top_amount = conn.execute("""
                SELECT d.code, s.name, d.amount
                FROM daily_kline d
                JOIN stocks s ON d.code=s.code
                WHERE d.trade_date=? AND d.amount IS NOT NULL
                ORDER BY d.amount DESC LIMIT 5
            """, (date,)).fetchall()

            return {
                'date': date,
                'total_stocks': stats['total'],
                'up': stats['up_count'],
                'down': stats['down_count'],
                'limit_up': stats['limit_up'],
                'limit_down': stats['limit_down'],
                'avg_change': round(stats['avg_change'], 2) if stats['avg_change'] else 0,
                'avg_up': round(stats['avg_up'], 2) if stats['avg_up'] else 0,
                'avg_down': round(stats['avg_down'], 2) if stats['avg_down'] else 0,
                'top_amount': [dict(r) for r in top_amount],
            }


# ═══════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════

def main():
    import argparse
    ap = argparse.ArgumentParser(description='SQLite 本地股票知识库 v1.0')
    ap.add_argument('--init', action='store_true', help='初始化数据库 + 全量爬取')
    ap.add_argument('--init-fast', action='store_true', help='仅爬股票列表+最近1年K线(快速体验)')
    ap.add_argument('--update', action='store_true', help='增量更新最近7天')
    ap.add_argument('--query', type=str, help='查询: 代码(如600519) 或 条件(如"ROE>15 PE<20")')
    ap.add_argument('--query-type', type=str, default='stock', choices=['stock', 'screen', 'top', 'snapshot', 'stats', 'index'],
                    help='查询类型')
    ap.add_argument('--limit', type=int, default=30, help='结果数量')
    ap.add_argument('--date', type=str, help='指定日期 YYYYMMDD')
    ap.add_argument('--stats', action='store_true', help='显示数据库统计')
    ap.add_argument('--db', type=str, help='数据库路径')
    args = ap.parse_args()

    db_path = args.db or str(DB_PATH)

    if args.init:
        crawler = StockKBCrawler(db_path)
        result = crawler.crawl_all()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.init_fast:
        crawler = StockKBCrawler(db_path)
        crawler.init_schema()
        crawler.crawl_stock_list()
        crawler.crawl_daily_kline(start_date='2025-01-01')
        crawler.crawl_indices()
        print("✅ 快速初始化完成")

    if args.update:
        crawler = StockKBCrawler(db_path)
        crawler.update_recent()
        print("✅ 增量更新完成")
        return

    if args.stats:
        q = StockKBQuery(db_path)
        s = q.get_stats()
        print(f"\n{'='*50}")
        print(f"  📊 数据库统计")
        print(f"{'='*50}")
        print(f"  股票总数:      {s['stocks']:,}")
        print(f"  日K线记录:     {s['daily_kline']:,}")
        print(f"  覆盖个股:      {s.get('stocks_with_kline', 0):,}")
        print(f"  最新K线日期:   {s.get('latest_kline_date', '无')}")
        print(f"  财务记录:      {s.get('financials', 0):,}")
        print(f"  最新财报期:    {s.get('latest_fin_date', '无')}")
        print(f"  指数记录:      {s.get('index_daily', 0):,}")
        print(f"  资金流记录:    {s.get('fund_flow', 0):,}")
        print(f"{'='*50}")
        return

    if args.query:
        q = StockKBQuery(db_path)
        query_type = args.query_type

        if query_type == 'stock':
            # 单票信息
            code = args.query.strip()
            info = q.get_stock_info(code)
            if info:
                print(f"\n{'='*60}")
                print(f"  📈 {info['name']} ({info['code']})")
                print(f"{'='*60}")
                print(f"  行业: {info.get('industry', '未知')}")
                print(f"  市值: {info.get('total_mv', '?')} 亿")
                print()

                # 最新行情
                k = q.get_latest_price(code)
                if k:
                    print(f"  📊 最新行情 ({k['trade_date']})")
                    print(f"  收盘: ¥{k.get('close', '?')}  涨跌: {k.get('change_pct', '?')}%")
                    print(f"  PE(TTM): {k.get('pe_ttm', '?')}  PB: {k.get('pb_mrq', '?')}")
                    print(f"  成交额: {k.get('amount', '?')} 万  换手率: {k.get('turnover', '?')}%")
                    print(f"  MA5: {k.get('ma5', '?')}  MA10: {k.get('ma10', '?')}  MA20: {k.get('ma20', '?')}")
                    print()

                # 财务
                fin = q.get_financials(code, limit=4)
                if fin:
                    print(f"  💰 最近财报")
                    for f in fin:
                        print(f"  {f['end_date']}: ROE={f.get('roe','?')}% 毛利率={f.get('gross_margin','?')}% 净利率={f.get('net_margin','?')}%")
                    print()

                # 资金流
                flow = q.get_fund_flow(code, limit=5)
                if flow:
                    print(f"  💵 资金流向")
                    for fl in flow:
                        main = fl.get('main_net', 0) or 0
                        sign = '+' if main >= 0 else ''
                        print(f"  {fl['trade_date']}: 主力 {sign}{main:.0f}万  占比 {fl.get('main_pct','?')}%")
            else:
                print(f"❌ 未找到股票: {code}")

        elif query_type == 'screen':
            # 条件筛选
            conditions = {}
            for part in args.query.strip().split():
                if '>' in part:
                    k, v = part.split('>')
                    if k.upper() in ('ROE',):
                        conditions['min_roe'] = float(v)
                    elif k.upper() in ('PE',):
                        conditions['min_pe'] = float(v)
                elif '<' in part:
                    k, v = part.split('<')
                    if k.upper() == 'PE':
                        conditions['max_pe'] = float(v)
            conditions['limit'] = args.limit

            results = q.screen_stocks(conditions)
            print(f"\n{'='*80}")
            print(f"  🔍 筛选条件: {args.query} → {len(results)} 只")
            print(f"{'='*80}")
            print(f"  {'代码':<8} {'名称':<10} {'PE':>6} {'ROE':>6} {'涨跌':>6} {'市值(亿)':>8} {'行业':<12}")
            print(f"  {'-'*70}")
            for r in results:
                print(f"  {r.get('code',''):<8} {r.get('name',''):<10} "
                      f"{r.get('pe_ttm') or '?':>6} {r.get('roe') or '?':>6} "
                      f"{r.get('change_pct') or '?':>6} {r.get('total_mv') or '?':>8} "
                      f"{(r.get('industry') or '')[:10]:<12}")

        elif query_type == 'top':
            results = q.get_top_gainers(date=args.date, limit=args.limit)
            print(f"\n  🔥 涨幅榜 TOP{len(results)}")
            for i, r in enumerate(results, 1):
                print(f"  {i:2}. {r.get('code','')} {r.get('name',''):<10} {r.get('change_pct',0):>+6.1f}%  "
                      f"PE={r.get('pe_ttm','?')}  {r.get('industry','')[:10]}")

        elif query_type == 'snapshot':
            snap = q.get_market_snapshot(args.date)
            print(f"\n  📊 市场快照 ({snap['date']})")
            print(f"  涨: {snap['up']}  跌: {snap['down']}  涨停: {snap['limit_up']}  跌停: {snap['limit_down']}")
            print(f"  平均涨跌: {snap['avg_change']}%")
            print(f"  成交额 TOP5:")
            for r in snap['top_amount']:
                print(f"    {r['code']} {r['name']:<10} ¥{r['amount']/10000:.1f}亿")

        elif query_type == 'index':
            rows = q.get_index(args.query, limit=args.limit)
            if rows:
                print(f"\n  📊 {rows[0].get('name', args.query)} 最近 {len(rows)} 天")
                for r in rows[:10]:
                    print(f"  {r['trade_date']}: {r.get('close','?')}  {r.get('change_pct',0):>+.2f}%")
        return


if __name__ == '__main__':
    main()
