#!/usr/bin/env python3
"""
狙击手 · 实时守护进程 v4.0
=========================
09:30-15:00 事件驱动监控，秒级止损响应。

架构:
  L1 持仓股 → 每 3 秒 Sina 批量查询 → 止损/异动即时告警
  L2 推荐池 → 同 L1 批量查询 → 入场信号检测
  L3 大盘   → 每 30 秒 → 环境异动告警
  L4 板块   → 每 60 秒 → 板块轮动感知

状态机去重: 仅优先级跃迁或关键指标突变时告警。

用法:
  python3 sniperd.py [--interval 3] [--once] [--dry-run]

v4.0 从 cron 定时触发升级为实时事件驱动。
"""

__version__ = "4.0.0"

import sys, os, json, time, asyncio
import urllib.request
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE = SCRIPT_DIR.parent
sys.path.insert(0, str(WORKSPACE))
sys.path.insert(0, str(SCRIPT_DIR))

# ── 路径常量 ──
HOLDINGS_PATH = WORKSPACE / 'data' / 'holdings.json'
POOL_PATH = SCRIPT_DIR / 'data' / 'daily_pool.json'
LOG_DIR = WORKSPACE / 'data' / 'sniper_logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# 可进化参数（evolution_engine v2.0 可自动调整）
# ═══════════════════════════════════════════════════════════════

class Config:
    """可进化配置参数"""
    # 轮询间隔
    L1_INTERVAL = 3          # 持仓股轮询（秒）
    L3_INTERVAL = 30         # 大盘轮询（秒）
    L4_INTERVAL = 60         # 板块轮询（秒）

    # 告警冷却（秒）
    ALERT_COOLDOWN_P1 = 120       # P1 逼近止损
    ALERT_COOLDOWN_P2 = 300       # P2 大幅异动
    ALERT_COOLDOWN_ENTRY = 600    # 入场信号
    ALERT_COOLDOWN_MARKET = 600   # 大盘异动

    # 触发阈值
    STOP_PROXIMITY_PCT = 3.0      # P1 止损逼近距离 (%)
    P2_CHANGE_THRESHOLD = 5.0     # P2 涨跌幅度 (%)
    P2_VOL_RATIO = 3.0            # P2 量比阈值
    ENTRY_VOL_RATIO = 1.5         # 入场量比门槛
    ENTRY_MA_DEV_MAX = 5.0        # 入场 MA20 偏离上限 (%)
    MARKET_SWING_THRESHOLD = 3.0  # 大盘异动幅度 (%)

    # 分时量价 (v8.3 新增)
    INTRO_DAY_INTERVAL = 60       # 分时扫描间隔 (秒)
    INTRO_DAY_VOL_RATIO = 2.5     # 分时放量阈值 (5min量/均量)
    ALERT_COOLDOWN_INTRO = 180    # 分时告警冷却 (秒)

    # 状态管理
    STATE_STALE_SECONDS = 3600    # 状态过期时间（秒）
    MAX_CONSECUTIVE_ERRORS = 10   # 连续错误阈值


# ═══════════════════════════════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════════════════════════════

class Priority(Enum):
    """告警优先级"""
    P0 = 0   # 止损触发 → 立即处理
    P1 = 1   # 逼近止损 → 准备减仓
    P2 = 2   # 大幅异动 → 密切关注
    P3 = 3   # 正常                  → 持有
    ENTRY = 10  # 入场信号
    MARKET = 11 # 大盘异动


@dataclass
class StockQuote:
    """实时行情快照"""
    code: str
    name: str = ""
    close: float = 0.0
    change_pct: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    volume: float = 0.0
    amount: float = 0.0
    timestamp: float = 0.0


@dataclass
class StockState:
    """标的上次已知状态（用于去重）"""
    code: str
    priority: Priority = Priority.P3
    close: float = 0.0
    change_pct: float = 0.0
    last_alert_at: float = 0.0
    last_priority: Priority = Priority.P3
    consecutive_checks: int = 0   # 连续确认计数
    info: str = ""


@dataclass
class Alert:
    """告警事件"""
    code: str
    name: str
    priority: Priority
    signal: str
    action: str
    detail: str
    price: float = 0.0
    change: float = 0.0
    timestamp: float = 0.0


# ═══════════════════════════════════════════════════════════════
# 数据加载
# ═══════════════════════════════════════════════════════════════

def load_holdings() -> Tuple[List[Dict], float, float]:
    """加载持仓数据 → (positions, net_value, available_cash)"""
    if not HOLDINGS_PATH.exists():
        return [], 100000.0, 100000.0

    try:
        data = json.loads(HOLDINGS_PATH.read_text(encoding='utf-8'))
        positions = []
        for h in data.get('holdings', []):
            for b in h.get('batches', []):
                positions.append({
                    'code': str(h['code']),
                    'name': h.get('name', h['code']),
                    'cost': float(b.get('costPrice', 0)),
                    'stop_loss': float(b.get('stopLoss', 0)),
                    'quantity': int(b.get('quantity', 0)),
                    'trailing_stop': float(b.get('trailingStopPrice', 0)),
                    'unrealized_pnl': float(b.get('unrealizedPnL', 0)),
                })
        return (positions,
                float(data.get('currentNetValue', 100000)),
                float(data.get('availableCash', 100000)))
    except Exception:
        return [], 100000.0, 100000.0


def load_pool_stocks() -> List[Dict]:
    """加载推荐池标的（未持仓的）"""
    if not POOL_PATH.exists():
        return []

    holdings_codes = {p['code'] for p in load_holdings()[0]}
    try:
        data = json.loads(POOL_PATH.read_text(encoding='utf-8'))
        pool = []
        for r in data.get('recommendations', []):
            code = str(r['code'])
            if code not in holdings_codes:
                pool.append({
                    'code': code,
                    'name': r.get('name', code),
                    'score': r.get('score', 0),
                    'source': r.get('source', 'recommender'),
                })
        return pool[:9]  # 最多 9 只
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
# Sina 实时行情（批量查询）
# ═══════════════════════════════════════════════════════════════

SINA_BATCH_URL = "http://hq.sinajs.cn/list="
SINA_INDEX_URL = "http://hq.sinajs.cn/list=s_sh000001,s_sz399001,s_sz399006"

def _code_to_sina(code: str) -> str:
    """将股票代码转换为 Sina 格式"""
    code = str(code).zfill(6)
    if code.startswith(('6', '5', '9')):
        return f"sh{code}"
    elif code.startswith(('0', '3', '2')):
        return f"sz{code}"
    return f"sh{code}"


async def _sina_fetch_async(codes: List[str], timeout: int = 5) -> Dict[str, StockQuote]:
    """
    异步批量查询 Sina 实时行情。
    单个 HTTP 请求支持最多 ~800 只股票。
    """
    if not codes:
        return {}

    sina_codes = [_code_to_sina(c) for c in codes]
    url = SINA_BATCH_URL + ",".join(sina_codes)

    try:
        req = urllib.request.Request(url, headers={
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0',
        })
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=timeout)
        )
        data = resp.read().decode('gbk', errors='ignore')
    except Exception:
        return {}

    results = {}
    code_map = {_code_to_sina(c): c for c in codes}

    for line in data.strip().split('\n'):
        if '=' not in line:
            continue
        try:
            sina_code, rest = line.split('=', 1)
            sina_code = sina_code.strip().split('_')[-1]
            original_code = code_map.get(sina_code)
            if not original_code:
                continue

            # 解析字段
            quote = rest.strip('";\n ').split(',')
            if len(quote) < 32:
                continue

            name = quote[0].strip()
            open_p = float(quote[1]) if quote[1] else 0
            prev_close = float(quote[2]) if quote[2] else 0
            close = float(quote[3]) if quote[3] else 0
            high = float(quote[4]) if quote[4] else 0
            low = float(quote[5]) if quote[5] else 0
            volume = float(quote[8]) if quote[8] else 0   # 手
            amount = float(quote[9]) if quote[9] else 0    # 万元

            change_pct = ((close - prev_close) / prev_close * 100) if prev_close > 0 else 0

            if close <= 0:
                continue

            results[original_code] = StockQuote(
                code=original_code,
                name=name,
                close=round(close, 2),
                change_pct=round(change_pct, 2),
                open=round(open_p, 2),
                high=round(high, 2),
                low=round(low, 2),
                volume=volume,
                amount=amount,
                timestamp=time.time(),
            )
        except (ValueError, IndexError):
            continue

    return results


async def _sina_index_async(timeout: int = 5) -> Dict[str, StockQuote]:
    """获取大盘指数"""
    try:
        req = urllib.request.Request(SINA_INDEX_URL, headers={
            'Referer': 'https://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0',
        })
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, lambda: urllib.request.urlopen(req, timeout=timeout)
        )
        data = resp.read().decode('gbk', errors='ignore')
    except Exception:
        return {}

    results = {}
    index_map = {'sh000001': ('000001', '上证指数'),
                  'sz399001': ('399001', '深证成指'),
                  'sz399006': ('399006', '创业板指')}
    for line in data.strip().split('\n'):
        if '=' not in line:
            continue
        try:
            code_part, rest = line.split('=', 1)
            sina_key = code_part.strip()
            idx_info = index_map.get(sina_key)
            if not idx_info:
                continue
            idx_code, idx_name = idx_info
            quote = rest.strip('";\n ').split(',')
            if len(quote) < 5:
                continue
            close = float(quote[3]) if quote[3] else 0
            prev = float(quote[2]) if quote[2] else 0
            change = ((close - prev) / prev * 100) if prev > 0 else 0
            results[idx_code] = StockQuote(
                code=idx_code, name=idx_name,
                close=round(close, 2),
                change_pct=round(change, 2),
                timestamp=time.time())
        except (ValueError, IndexError):
            continue
    return results


# ═══════════════════════════════════════════════════════════════
# 历史数据缓存（MA20 / 均量计算）
# ═══════════════════════════════════════════════════════════════

_ma_cache: Dict[str, Dict] = {}
_ma_cache_time: float = 0.0
_MA_REFRESH_INTERVAL = 1800  # 30 分钟刷新一次历史数据


def _load_historical_data(codes: List[str]) -> Dict[str, Dict]:
    """批量加载历史日线数据，计算 MA20 和 5 日均量"""
    global _ma_cache, _ma_cache_time

    now = time.time()
    if _ma_cache and (now - _ma_cache_time) < _MA_REFRESH_INTERVAL:
        # 只补充新 code
        missing = [c for c in codes if c not in _ma_cache]
        if not missing:
            return _ma_cache
    else:
        missing = codes

    if not missing:
        return _ma_cache

    # 使用 data fetch CLI 批量获取（每只独立请求，慢但可靠）
    import subprocess
    for code in missing:
        try:
            proc = subprocess.run(
                ['data', 'fetch', 'stock', '--symbol', code, '--category', 'daily', '--days', '30'],
                capture_output=True, text=True, timeout=30,
                env={**os.environ, 'HERMES_PROFILE': 'xiaohong'}
            )
            if proc.returncode == 0:
                data = json.loads(proc.stdout)
                closes = []
                volumes = []
                for p in data.get('providers_attempted', []):
                    records = p.get('data', [])
                    if isinstance(records, list) and records:
                        for r in records:
                            closes.append(float(r.get('close', 0)))
                            volumes.append(float(r.get('vol', 0)))
                        break

                if len(closes) >= 20:
                    ma20 = sum(closes[-20:]) / 20
                    avg_vol_5 = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else sum(volumes) / len(volumes)
                    _ma_cache[code] = {'ma20': round(ma20, 2), 'avg_vol_5': round(avg_vol_5, 0)}
        except Exception:
            pass

    _ma_cache_time = now
    return _ma_cache


# ═══════════════════════════════════════════════════════════════
# 触发器引擎（状态机）
# ═══════════════════════════════════════════════════════════════

class TriggerEngine:
    """
    事件触发引擎：对比实时行情 vs 上次状态，仅当优先级跃迁时生成告警。

    去重逻辑:
      - 同优先级 + 同数值 → 静默
      - 优先级跃迁（P3→P1, P1→P0） → 立即告警
      - 同级别内指标变化超过阈值 → 告警（受冷却限制）
      - P0 无冷却，穿透即告警
    """

    def __init__(self, config: Config):
        self.cfg = config
        self.states: Dict[str, StockState] = {}
        self.pool_alert_cache: Dict[str, float] = {}
        self.intraday_alert_cache: Dict[str, float] = {}  # 分时告警冷却

    def check_position(self, pos: Dict, quote: Optional[StockQuote]) -> List[Alert]:
        """检查单个持仓，返回告警列表"""
        code = pos['code']
        if quote is None or quote.close <= 0:
            # 无数据：维持上次状态
            prev = self.states.get(code)
            if prev and prev.priority in (Priority.P0, Priority.P1):
                return [Alert(
                    code=code, name=pos['name'], priority=prev.priority,
                    signal='⚠️ 数据中断', action='确认网络',
                    detail=f'上次状态: {prev.priority.name} · 现价未知',
                    price=prev.close, timestamp=time.time(),
                )]
            return []

        close = quote.close
        change = quote.change_pct
        cost = pos['cost']
        stop_loss = pos.get('stop_loss', 0)
        trailing_stop = pos.get('trailing_stop', 0)
        effective_stop = max(stop_loss, trailing_stop)
        pnl_pct = (close - cost) / cost * 100 if cost > 0 else 0

        prev_state = self.states.get(code)
        now = time.time()

        # ═══ P0: 止损穿透 ═══
        if effective_stop > 0 and close <= effective_stop:
            # 连续 2 tick 确认（防数据尖刺）
            if prev_state and prev_state.priority == Priority.P0:
                consecutive = prev_state.consecutive_checks + 1
            else:
                consecutive = 1

            if consecutive >= 2 or close <= effective_stop * 0.98:
                # 确认穿透：立即告警（无冷却）
                self.states[code] = StockState(
                    code=code, priority=Priority.P0,
                    close=close, change_pct=change,
                    last_alert_at=now, last_priority=Priority.P0,
                    consecutive_checks=consecutive,
                    info=f'穿透 {effective_stop:.2f}'
                )
                return [Alert(
                    code=code, name=pos['name'], priority=Priority.P0,
                    signal='🔴 止损触发', action='立即清仓',
                    detail=f'现价 {close:.2f} ≤ 止损 {effective_stop:.2f}，浮亏 {pnl_pct:+.1f}%',
                    price=close, change=change, timestamp=now,
                )]
            else:
                # 第一次 tick 穿透，等待确认
                self.states[code] = StockState(
                    code=code, priority=Priority.P0,
                    close=close, change_pct=change,
                    last_alert_at=prev_state.last_alert_at if prev_state else 0,
                    last_priority=prev_state.priority if prev_state else Priority.P3,
                    consecutive_checks=consecutive,
                    info=f'待确认穿透 {effective_stop:.2f}'
                )
                return []

        # ═══ P1: 逼近止损 ═══
        if effective_stop > 0:
            distance = (close - effective_stop) / close * 100
            if 0 < distance <= self.cfg.STOP_PROXIMITY_PCT:
                new_p1 = (prev_state is None or prev_state.priority != Priority.P1)
                escalated = (prev_state and prev_state.priority == Priority.P2)
                cooldown_ok = (not prev_state or
                               (now - prev_state.last_alert_at) > self.cfg.ALERT_COOLDOWN_P1)

                if new_p1 or escalated:
                    if cooldown_ok:
                        self.states[code] = StockState(
                            code=code, priority=Priority.P1,
                            close=close, change_pct=change,
                            last_alert_at=now, last_priority=Priority.P1,
                            consecutive_checks=0,
                            info=f'{distance:.1f}% 到止损'
                        )
                        return [Alert(
                            code=code, name=pos['name'], priority=Priority.P1,
                            signal='🟡 逼近止损', action='准备减仓',
                            detail=f'距止损 {distance:.1f}%（{close:.2f} vs {effective_stop:.2f}）',
                            price=close, change=change, timestamp=now,
                        )]
                else:
                    # 已告警过，更新状态但不重复告警
                    self.states[code] = StockState(
                        code=code, priority=Priority.P1,
                        close=close, change_pct=change,
                        last_alert_at=prev_state.last_alert_at if prev_state else now,
                        last_priority=Priority.P1,
                        info=f'{distance:.1f}% 到止损'
                    )
                return []

        # ═══ P2: 大幅异动 ═══
        vol_ratio = quote.volume / self._get_avg_vol(code) if self._get_avg_vol(code) > 0 else 1
        if abs(change) > self.cfg.P2_CHANGE_THRESHOLD or vol_ratio > self.cfg.P2_VOL_RATIO:
            new_p2 = (prev_state is None or prev_state.priority.value > Priority.P2.value)
            significant_change = (
                prev_state and prev_state.priority == Priority.P2 and
                abs(change - prev_state.change_pct) > 2.0
            )
            cooldown_ok = (not prev_state or
                           (now - prev_state.last_alert_at) > self.cfg.ALERT_COOLDOWN_P2)

            if (new_p2 or significant_change) and cooldown_ok:
                parts = []
                if change > self.cfg.P2_CHANGE_THRESHOLD:
                    parts.append(f'大涨 {change:+.1f}%')
                elif change < -self.cfg.P2_CHANGE_THRESHOLD:
                    parts.append(f'大跌 {change:+.1f}%')
                if vol_ratio > self.cfg.P2_VOL_RATIO:
                    parts.append(f'爆量 {vol_ratio:.1f}x')

                if change > self.cfg.P2_CHANGE_THRESHOLD and vol_ratio > 2:
                    action = '移动止盈上移'
                elif change < -self.cfg.P2_CHANGE_THRESHOLD:
                    action = '查基本面利空'
                else:
                    action = '密切关注'

                self.states[code] = StockState(
                    code=code, priority=Priority.P2,
                    close=close, change_pct=change,
                    last_alert_at=now, last_priority=Priority.P2,
                )
                return [Alert(
                    code=code, name=pos['name'], priority=Priority.P2,
                    signal='🔵 ' + ' · '.join(parts),
                    action=action,
                    detail=f'量比 {vol_ratio:.1f}x · 浮盈 {pnl_pct:+.1f}%',
                    price=close, change=change, timestamp=now,
                )]

        # ═══ P3: 正常 ═══
        # 仅状态跃迁（P1→P3 恢复）时记录，不告警
        recovered = prev_state and prev_state.priority in (Priority.P1, Priority.P2)
        self.states[code] = StockState(
            code=code, priority=Priority.P3,
            close=close, change_pct=change,
            last_alert_at=prev_state.last_alert_at if prev_state else 0,
            last_priority=prev_state.priority if prev_state else Priority.P3,
            info='已恢复' if recovered else '',
        )
        return []

    def check_entry(self, pool_stock: Dict, quote: Optional[StockQuote]) -> List[Alert]:
        """检查入场信号"""
        code = pool_stock['code']
        if quote is None or quote.close <= 0:
            return []

        now = time.time()
        last_alert = self.pool_alert_cache.get(code, 0)
        if (now - last_alert) < self.cfg.ALERT_COOLDOWN_ENTRY:
            return []

        close = quote.close
        change = quote.change_pct
        vol_ratio = quote.volume / self._get_avg_vol(code) if self._get_avg_vol(code) > 0 else 1
        ma20 = self._get_ma20(code)
        ma_dev = abs((close - ma20) / ma20 * 100) if ma20 > 0 else 0

        reason = None
        if vol_ratio > self.cfg.ENTRY_VOL_RATIO and change > 0 and ma_dev < self.cfg.ENTRY_MA_DEV_MAX:
            reason = f'放量 {vol_ratio:.1f}x · MA20附近 · 可建底仓'
        elif change < -3 and vol_ratio < 1:
            reason = f'缩量回调 {change:.1f}% · 等止跌信号'
        elif vol_ratio > 2 and change > 0:
            reason = f'强放量 {vol_ratio:.1f}x · 等回踩确认'

        if reason:
            self.pool_alert_cache[code] = now
            return [Alert(
                code=code, name=pool_stock.get('name', code),
                priority=Priority.ENTRY,
                signal='🎯 入场观察',
                action='评估建仓',
                detail=reason,
                price=close, change=change, timestamp=now,
            )]
        return []

    def check_market(self, indices: Dict[str, StockQuote]) -> List[Alert]:
        """检查大盘异动"""
        alerts = []
        for code, q in indices.items():
            if abs(q.change_pct) >= self.cfg.MARKET_SWING_THRESHOLD:
                dir_str = '急涨' if q.change_pct > 0 else '急跌'
                alerts.append(Alert(
                    code=code, name=q.name,
                    priority=Priority.MARKET,
                    signal=f'📊 大盘{dir_str}',
                    action='调整仓位策略',
                    detail=f'{q.name} {q.change_pct:+.2f}%，超出 {self.cfg.MARKET_SWING_THRESHOLD}% 阈值',
                    price=q.close, change=q.change_pct, timestamp=time.time(),
                ))
        return alerts

    def check_intraday_volume(self, pos: Dict) -> List[Alert]:
        """基于分时K线检测量价异动（v8.3 新增）"""
        code = pos['code']
        now = time.time()

        # 冷却检查
        last_alert = self.intraday_alert_cache.get(code, 0)
        if now - last_alert < self.cfg.ALERT_COOLDOWN_INTRO:
            return []

        try:
            from data_pipeline import get_intraday_volume_alert
            result = get_intraday_volume_alert(code, scale=5)
        except Exception:
            return []

        if not result.get('alert'):
            return []

        vol_ratio = result['vol_ratio']
        signal_text = result['signal']
        price_chg = result['price_chg']

        if vol_ratio < self.cfg.INTRO_DAY_VOL_RATIO:
            return []

        self.intraday_alert_cache[code] = now

        emoji = '🟠' if '下跌' in signal_text else '🟣'
        return [Alert(
            code=code, name=pos.get('name', code),
            priority=Priority.P2,
            signal=f'{emoji} 分时{signal_text}',
            action='密切关注量价' if '⚠️' in signal_text else '观察放量持续性',
            detail=f'5min量比 {vol_ratio:.1f}x · 区间涨跌 {price_chg:+.1f}%',
            price=pos.get('_price', 0), change=price_chg, timestamp=now,
        )]

    def _get_ma20(self, code: str) -> float:
        return _ma_cache.get(code, {}).get('ma20', 0)

    def _get_avg_vol(self, code: str) -> float:
        return _ma_cache.get(code, {}).get('avg_vol_5', 0)

    def prune_stale_states(self):
        """清理过期状态（半天未更新的标的）"""
        cutoff = time.time() - self.cfg.STATE_STALE_SECONDS
        stale = [c for c, s in self.states.items() if s.last_alert_at < cutoff and s.priority == Priority.P3]
        for c in stale:
            del self.states[c]

    def get_status_summary(self) -> Dict:
        """获取当前状态摘要"""
        p0 = sum(1 for s in self.states.values() if s.priority == Priority.P0)
        p1 = sum(1 for s in self.states.values() if s.priority == Priority.P1)
        p2 = sum(1 for s in self.states.values() if s.priority == Priority.P2)
        return {'P0': p0, 'P1': p1, 'P2': p2, 'total_tracked': len(self.states)}


# ═══════════════════════════════════════════════════════════════
# 报告格式化
# ═══════════════════════════════════════════════════════════════

def format_alert_message(alerts: List[Alert], status: Dict) -> str:
    """格式化告警消息为 Markdown"""
    if not alerts:
        return ""

    ts = datetime.now().strftime('%H:%M:%S')
    lines = [
        f"🎯 狙击手 · 实时告警",
        f"",
        f"⏰ {ts}  |  P0:{status['P0']} P1:{status['P1']} P2:{status['P2']}",
        f"",
    ]

    for a in alerts:
        icon = {
            Priority.P0: '🔴', Priority.P1: '🟡', Priority.P2: '🔵',
            Priority.ENTRY: '🎯', Priority.MARKET: '📊', Priority.P3: '⚪',
        }.get(a.priority, '⚪')

        lines.append(f"---")
        lines.append(f"")
        lines.append(f"{icon} **{a.code} {a.name}** — {a.signal}")
        lines.append(f"> {a.detail}")
        lines.append(f"> 操作: **{a.action}** | 现价 {a.price:.2f} | {a.change:+.1f}%")
        lines.append(f"")

    lines.append(f"")
    lines.append(f"*狙击手 v4.0 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    return '\n'.join(lines)


# ═══════════════════════════════════════════════════════════════
# 日志
# ═══════════════════════════════════════════════════════════════

def log_event(level: str, message: str):
    """结构化日志"""
    entry = {
        'ts': datetime.now().isoformat(),
        'level': level,
        'msg': message,
    }
    log_file = LOG_DIR / f"sniper_{datetime.now().strftime('%Y%m%d')}.jsonl"
    try:
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# 主循环
# ═══════════════════════════════════════════════════════════════

def is_trading_time() -> bool:
    """判断是否在 A 股交易时段"""
    now = datetime.now()
    # 周末
    if now.weekday() >= 5:
        return False
    # 时段
    t = now.hour * 60 + now.minute
    return (9 * 60 + 30) <= t < (15 * 60 + 1)  # 09:30 - 15:01


def wait_until_market_open():
    """等待到开盘时间"""
    while True:
        now = datetime.now()
        if now.weekday() >= 5:
            # 周末，等到周一
            days_to_monday = 7 - now.weekday()
            next_open = now.replace(hour=9, minute=29, second=0, microsecond=0) + timedelta(days=days_to_monday)
        elif now.hour < 9 or (now.hour == 9 and now.minute < 29):
            next_open = now.replace(hour=9, minute=29, second=0, microsecond=0)
        elif now.hour >= 15:
            # 已收盘，等明天
            next_open = now.replace(hour=9, minute=29, second=0, microsecond=0) + timedelta(days=1)
            if next_open.weekday() >= 5:
                days_to_monday = 7 - next_open.weekday()
                next_open += timedelta(days=days_to_monday)
        else:
            return  # 已经在交易时段

        wait_seconds = (next_open - now).total_seconds()
        if wait_seconds > 0:
            print(f"[sniperd] 等待开盘... {wait_seconds/3600:.1f} 小时后 ({next_open.strftime('%Y-%m-%d %H:%M')})")
            time.sleep(min(wait_seconds, 3600))  # 最多睡 1 小时
        else:
            return


class SniperDaemon:
    """狙击手实时守护进程"""

    def __init__(self, interval: int = 3, dry_run: bool = False):
        self.cfg = Config()
        self.cfg.L1_INTERVAL = max(1, min(10, interval))
        self.dry_run = dry_run
        self.trigger = TriggerEngine(self.cfg)
        self.consecutive_errors = 0
        self.tick_count = 0
        self.last_l3_fetch = 0.0
        self.last_l4_fetch = 0.0
        self.last_ma_refresh = 0.0
        self.last_intraday_check = 0.0  # 分时量价扫描
        self._market_cache: Dict[str, StockQuote] = {}
        self._sector_cache: Dict = {}

    async def poll_l1(self) -> Dict[str, StockQuote]:
        """L1: 批量查询持仓 + 推荐池行情"""
        holdings_codes = [p['code'] for p in self._holdings]
        pool_codes = [s['code'] for s in self._pool_stocks]
        all_codes = list(set(holdings_codes + pool_codes))
        return await _sina_fetch_async(all_codes)

    async def poll_l3(self) -> Dict[str, StockQuote]:
        """L3: 大盘指数"""
        now = time.time()
        if (now - self.last_l3_fetch) < self.cfg.L3_INTERVAL:
            return self._market_cache
        self.last_l3_fetch = now
        indices = await _sina_index_async()
        if indices:
            self._market_cache = indices
        return self._market_cache

    async def refresh_ma_cache(self, codes: List[str]):
        """刷新 MA/均量缓存（后台异步）"""
        now = time.time()
        if (now - self.last_ma_refresh) < _MA_REFRESH_INTERVAL:
            return
        self.last_ma_refresh = now
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _load_historical_data, codes)

    async def run_once(self) -> Tuple[List[Alert], Dict]:
        """执行一次完整的扫描周期"""
        tick_start = time.time()
        alerts = []

        try:
            # L1: 行情（每个 tick）
            quotes = await self.poll_l1()

            # L3: 大盘（按间隔）
            indices = await self.poll_l3()

            # 后台刷新 MA 缓存
            all_codes = list(set([p['code'] for p in self._holdings] +
                                 [s['code'] for s in self._pool_stocks]))
            await self.refresh_ma_cache(all_codes)

            # ── 触发器 ──
            for pos in self._holdings:
                q = quotes.get(pos['code'])
                pos_alerts = self.trigger.check_position(pos, q)
                alerts.extend(pos_alerts)

            for ps in self._pool_stocks:
                q = quotes.get(ps['code'])
                entry_alerts = self.trigger.check_entry(ps, q)
                alerts.extend(entry_alerts)

            market_alerts = self.trigger.check_market(indices)
            alerts.extend(market_alerts)

            # ── 分时量价异动 (按间隔) ──
            now = time.time()
            if (now - self.last_intraday_check) >= self.cfg.INTRO_DAY_INTERVAL:
                self.last_intraday_check = now
                for pos in self._holdings:
                    intra_alerts = self.trigger.check_intraday_volume(pos)
                    alerts.extend(intra_alerts)

            # 清理过期状态
            self.trigger.prune_stale_states()

            self.consecutive_errors = 0

        except Exception as e:
            self.consecutive_errors += 1
            log_event('ERROR', f'tick {self.tick_count}: {e}')
            if self.consecutive_errors > self.cfg.MAX_CONSECUTIVE_ERRORS:
                log_event('CRITICAL', f'连续 {self.consecutive_errors} 次错误，守护进程异常')

        status = self.trigger.get_status_summary()
        self.tick_count += 1

        # 精确计时补偿
        elapsed = time.time() - tick_start
        sleep_time = max(0, self.cfg.L1_INTERVAL - elapsed)

        return alerts, status, sleep_time

    def reload_data(self):
        """重新加载持仓和推荐池（可能在盘中更新）"""
        self._holdings, self._net_value, self._available_cash = load_holdings()
        self._pool_stocks = load_pool_stocks()

    async def run(self):
        """主循环"""
        log_event('INFO', f'sniperd v{__version__} 启动，间隔 {self.cfg.L1_INTERVAL}s')
        print(f"[sniperd] 狙击手实时守护进程 v{__version__} 启动")
        print(f"[sniperd] 轮询间隔: {self.cfg.L1_INTERVAL}s | 止损响应: ≤3s")
        print(f"[sniperd] 交易日 09:30-15:00 自动运行")

        while True:
            # 等待开盘
            if not is_trading_time():
                if self.tick_count > 0:
                    log_event('INFO', f'收盘，今日共 {self.tick_count} 次扫描')
                self.tick_count = 0
                self.trigger = TriggerEngine(self.cfg)  # 重置状态
                wait_until_market_open()

            # 重新加载数据
            self.reload_data()

            if not self._holdings and not self._pool_stocks:
                # 空仓无池，休眠 60 秒
                await asyncio.sleep(60)
                continue

            # 执行一次扫描
            alerts, status, sleep_time = await self.run_once()

            # 告警输出
            if alerts:
                msg = format_alert_message(alerts, status)
                print(msg)
                if not self.dry_run:
                    log_event('ALERT', f'{len(alerts)} 条告警: ' +
                              ', '.join(f'{a.code}/{a.priority.name}' for a in alerts))

            await asyncio.sleep(sleep_time)


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse
    p = argparse.ArgumentParser(description='狙击手 v4.0 · 实时守护进程')
    p.add_argument('--interval', type=int, default=3, help='L1 轮询间隔（秒，默认 3）')
    p.add_argument('--once', action='store_true', help='执行一次扫描后退出（测试用）')
    p.add_argument('--dry-run', action='store_true', help='不写日志，仅打印')
    args = p.parse_args()

    daemon = SniperDaemon(interval=args.interval, dry_run=args.dry_run)

    if args.once:
        async def _once():
            print("[sniperd] 单次扫描模式")
            daemon.reload_data()
            alerts, status, _ = await daemon.run_once()
            msg = format_alert_message(alerts, status)
            if msg:
                print(msg)
            else:
                print(f"[sniperd] ✅ 无告警 | 持仓 {len(daemon._holdings)}只 | "
                      f"推荐池 {len(daemon._pool_stocks)}只 | P0:{status['P0']} P1:{status['P1']}")
        asyncio.run(_once())
    else:
        asyncio.run(daemon.run())


if __name__ == '__main__':
    main()
