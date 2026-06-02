#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 REST API 服务器
=====================================
FastAPI 统一接口层 — JWT 认证 + 多租户 + Redis 限流 + Swagger 文档

对标 TradingSkill 的 MCP 工具层，REST 接口供：
  - 家族小程序 (WeChat Mini Program)
  - Web 管理后台 (React SPA)
  - 硬件盒子仪表盘 (Pi 5 + 触摸屏)
  - 第三方集成
"""
import os
import sys
import json
import time
import hashlib
import secrets
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from fastapi import FastAPI, HTTPException, Depends, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from contextlib import asynccontextmanager

# 添加项目路径
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from transaction_logger import TransactionLogger

# ═══════════════════════════════════════
# 配置
# ═══════════════════════════════════════

API_TITLE = "安幕诺家族 · 小红交易API"
API_VERSION = "2.0.0"
JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
RATE_LIMIT_WINDOW = 60   # 秒
RATE_LIMIT_MAX = 100      # 每窗口最大请求数

# 简易多租户（Phase 4 迁移到 PostgreSQL）
TENANTS: Dict[str, Dict] = {
    "default": {"name": "安幕诺家族", "tier": "internal", "rate_limit": 200},
}

# 简易 API Key 存储（Phase 4 加密到 DB）
API_KEYS: Dict[str, str] = {
    "xh-internal-dev": "default",
}

# ═══════════════════════════════════════
# 限流（内存版，Phase 4 迁 Redis）
# ═══════════════════════════════════════

_rate_buckets: Dict[str, List[float]] = {}

def check_rate_limit(tenant_id: str) -> bool:
    now = time.time()
    bucket = _rate_buckets.setdefault(tenant_id, [])
    bucket[:] = [t for t in bucket if t > now - RATE_LIMIT_WINDOW]
    limit = TENANTS.get(tenant_id, {}).get("rate_limit", RATE_LIMIT_MAX)
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


# ═══════════════════════════════════════
# JWT 认证
# ═══════════════════════════════════════

security = HTTPBearer(auto_error=False)

def create_token(tenant_id: str, expires_hours: int = 24) -> str:
    """创建 JWT token（简易版，Phase 4 换 python-jose）"""
    payload = {
        "tenant_id": tenant_id,
        "exp": (datetime.utcnow() + timedelta(hours=expires_hours)).timestamp(),
        "iat": datetime.utcnow().timestamp(),
    }
    payload_str = json.dumps(payload, sort_keys=True)
    signature = hashlib.sha256(f"{payload_str}{JWT_SECRET}".encode()).hexdigest()
    token = f"{payload_str}.{signature}"
    return token

def verify_token(token: str) -> Optional[str]:
    """验证 JWT token，返回 tenant_id"""
    try:
        parts = token.rsplit(".", 1)
        if len(parts) != 2:
            return None
        payload_str, signature = parts
        expected = hashlib.sha256(f"{payload_str}{JWT_SECRET}".encode()).hexdigest()
        if signature != expected:
            return None
        payload = json.loads(payload_str)
        if payload.get("exp", 0) < datetime.utcnow().timestamp():
            return None
        return payload.get("tenant_id")
    except Exception:
        return None

async def get_tenant(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> str:
    """认证中间件：JWT > API Key > default"""
    if credentials:
        tenant = verify_token(credentials.credentials)
        if tenant:
            return tenant
    
    if x_api_key and x_api_key in API_KEYS:
        return API_KEYS[x_api_key]
    
    # 开发模式允许无认证
    return "default"


# ═══════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════

class LoginRequest(BaseModel):
    api_key: str = Field(..., description="API Key")
    
class LoginResponse(BaseModel):
    token: str
    tenant_id: str
    expires_in: int = 86400

class OrderRequest(BaseModel):
    symbol: str = Field(..., description="股票代码", examples=["600519"])
    symbol_name: str = Field("", description="股票名称")
    side: str = Field(..., pattern="^(BUY|SELL)$", description="买卖方向")
    price: float = Field(..., gt=0, description="价格")
    quantity: int = Field(..., gt=0, description="数量(股)")
    order_type: str = Field("market", pattern="^(market|limit)$")
    stop_loss: float = Field(0, description="止损价")
    take_profit: float = Field(0, description="止盈价")
    strategy_id: str = Field("", description="策略ID")
    reason: str = Field("", description="理由")

class OrderResponse(BaseModel):
    trade_id: str
    status: str
    symbol: str
    message: str = ""

class StatsResponse(BaseModel):
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    portfolio_value: float

class PositionItem(BaseModel):
    symbol: str
    name: str
    quantity: int
    avg_cost: float
    current_price: float
    market_value: float
    unrealized_pnl: float
    pnl_pct: float

class AccountResponse(BaseModel):
    total_value: float
    available_cash: float
    positions: List[PositionItem]
    position_count: int

class TradeItem(BaseModel):
    trade_id: str
    timestamp: str
    symbol: str
    name: str
    side: str
    price: float
    quantity: int
    value: float
    pnl: float
    pnl_pct: float
    strategy: str
    reason: str

class SignalResponse(BaseModel):
    symbol: str
    action: str
    severity: str
    reason: str

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = API_VERSION
    uptime: float = 0
    tenants: int = 0


# ═══════════════════════════════════════
# 应用初始化
# ═══════════════════════════════════════

start_time = time.time()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    import logging
    logging.basicConfig(level=logging.INFO)
    _log = logging.getLogger("api")
    _log.info(f"🚀 {API_TITLE} v{API_VERSION} 启动")
    yield
    _log.info("⏹ API 服务关闭")

app = FastAPI(
    title=API_TITLE,
    version=API_VERSION,
    description="""
## 安幕诺家族 · 小红 🌹 交易 API

TradingSkill 风格的 AI 交易辅助系统 REST 接口。

### 功能模块
- **🔐 认证**: JWT Token + API Key 双模式
- **📊 行情**: 指数/个股/北向资金/板块流向
- **🧠 策略**: 多因子选股/策略信号/回测
- **⚡ 交易**: 下单/撤单/订单查询（Paper Trading）
- **🛡️ 风控**: 仓位检查/止损计算/R值
- **📝 日志**: 交易统计/PnL曲线/导出

### 认证方式
1. `Authorization: Bearer <token>` (推荐)
2. `X-API-Key: <key>` (简易模式)
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════
# 中间件
# ═══════════════════════════════════════

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """限流中间件"""
    tenant = request.headers.get("X-Tenant-ID", "default")
    if not check_rate_limit(tenant):
        return JSONResponse(
            status_code=429,
            content={"error": "请求过于频繁，请稍后再试", "retry_after": RATE_LIMIT_WINDOW}
        )
    return await call_next(request)


# ═══════════════════════════════════════
# 路由: 系统
# ═══════════════════════════════════════

@app.get("/health", response_model=HealthResponse, tags=["系统"])
async def health():
    """健康检查"""
    return {
        "status": "ok",
        "version": API_VERSION,
        "uptime": round(time.time() - start_time, 1),
        "tenants": len(TENANTS),
    }

@app.post("/auth/login", response_model=LoginResponse, tags=["认证"])
async def login(req: LoginRequest):
    """API Key 换取 JWT Token"""
    if req.api_key not in API_KEYS:
        raise HTTPException(401, "无效的 API Key")
    tenant = API_KEYS[req.api_key]
    token = create_token(tenant)
    return {"token": token, "tenant_id": tenant, "expires_in": 86400}


# ═══════════════════════════════════════
# 路由: 行情
# ═══════════════════════════════════════

@app.get("/market/index", tags=["📊 行情"])
async def get_index(tenant: str = Depends(get_tenant)):
    """全球指数数据"""
    try:
        from data_pipeline import get_index_data
        return get_index_data()
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/market/quote/{symbol}", tags=["📊 行情"])
async def get_quote(symbol: str, tenant: str = Depends(get_tenant)):
    """个股行情"""
    try:
        from data_pipeline import get_stock_realtime
        result = get_stock_realtime([symbol])
        if symbol in result:
            return result[symbol]
        raise HTTPException(404, f"未找到 {symbol}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/market/north-flow", tags=["📊 行情"])
async def get_north_flow(tenant: str = Depends(get_tenant)):
    """北向资金"""
    try:
        from data_pipeline import get_north_flow
        return get_north_flow()
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/market/sectors", tags=["📊 行情"])
async def get_sectors(top_n: int = 10, tenant: str = Depends(get_tenant)):
    """板块资金排名"""
    try:
        from data_pipeline import get_sector_flow_rank
        result = get_sector_flow_rank()
        return result[:top_n] if result else []
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════
# 路由: 交易
# ═══════════════════════════════════════

@app.post("/trade/order", response_model=OrderResponse, tags=["⚡ 交易"])
async def place_order(req: OrderRequest, tenant: str = Depends(get_tenant)):
    """下单（Paper Trading）"""
    try:
        from auto_executor import AutoExecutor, Signal, SignalStrength
        
        executor = AutoExecutor(mode="paper")
        signal = Signal(
            symbol=req.symbol,
            symbol_name=req.symbol_name,
            side=req.side,
            price=req.price,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
            strategy_id=req.strategy_id,
            reason=req.reason,
            strength=SignalStrength.MODERATE,
        )
        # 强制设置数量
        signal.quantity_hint = req.quantity
        
        trade_id = executor.process_signal(signal)
        
        if "REJECTED" in str(trade_id):
            raise HTTPException(400, str(trade_id))
        
        return {
            "trade_id": trade_id,
            "status": "filled" if executor.is_paper else "pending",
            "symbol": req.symbol,
            "message": f"{req.side} {req.quantity}股 @ {req.price}"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/trade/positions", response_model=AccountResponse, tags=["⚡ 交易"])
async def get_positions(tenant: str = Depends(get_tenant)):
    """查询持仓"""
    try:
        from auto_executor import AutoExecutor
        executor = AutoExecutor(mode="paper")
        
        positions = []
        for p in executor.account.positions.values():
            positions.append({
                "symbol": p.symbol,
                "name": p.symbol_name,
                "quantity": p.quantity,
                "avg_cost": p.avg_cost,
                "current_price": p.current_price,
                "market_value": p.market_value,
                "unrealized_pnl": p.unrealized_pnl,
                "pnl_pct": p.pnl_pct,
            })
        
        return {
            "total_value": executor.account.total_value,
            "available_cash": executor.account.available_cash,
            "positions": positions,
            "position_count": len(positions),
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ═══════════════════════════════════════
# 路由: 策略
# ═══════════════════════════════════════

@app.get("/strategy/signals", response_model=List[SignalResponse], tags=["🧠 策略"])
async def get_signals(tenant: str = Depends(get_tenant)):
    """获取交易信号"""
    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "strategy_bridge.py"), "signal"],
            capture_output=True, text=True, timeout=30,
            cwd=str(SCRIPT_DIR),
        )
        data = json.loads(result.stdout)
        signals = []
        for rec in data.get("recommendations", []):
            signals.append({
                "symbol": rec.get("code", ""),
                "action": rec.get("action", "HOLD"),
                "severity": rec.get("severity", "info"),
                "reason": rec.get("reason", ""),
            })
        return signals
    except Exception as e:
        raise HTTPException(500, str(e))

@app.get("/strategy/list", tags=["🧠 策略"])
async def list_strategies(tenant: str = Depends(get_tenant)):
    """策略列表"""
    return {
        "strategies": [
            {"id": "CMP-001", "name": "保守组合策略", "desc": "选股+仓位+止损三合一"},
            {"id": "SEL-001", "name": "趋势跟随选股", "desc": "基于均线和动量"},
            {"id": "POS-002", "name": "R值仓位管理", "desc": "凯利公式仓位分配"},
            {"id": "STP-001", "name": "R值止损止盈", "desc": "技术面止损+移动止盈"},
            {"id": "MA-CROSS", "name": "均线交叉 (TradingSkill)", "status": "planned"},
            {"id": "RSI-001", "name": "RSI策略 (TradingSkill)", "status": "planned"},
            {"id": "MACD-001", "name": "MACD策略 (TradingSkill)", "status": "planned"},
            {"id": "BB-001", "name": "布林带 (TradingSkill)", "status": "planned"},
            {"id": "COMBINED", "name": "多指标共识 (TradingSkill)", "status": "planned"},
        ]
    }


# ═══════════════════════════════════════
# 路由: 日志
# ═══════════════════════════════════════

@app.get("/log/stats", response_model=StatsResponse, tags=["📝 日志"])
async def get_stats(symbol: str = None, tenant: str = Depends(get_tenant)):
    """交易统计"""
    logger = TransactionLogger()
    stats = logger.get_statistics(symbol=symbol)
    return stats

@app.get("/log/trades", response_model=List[TradeItem], tags=["📝 日志"])
async def get_trades(
    symbol: str = None,
    side: str = None,
    limit: int = 20,
    tenant: str = Depends(get_tenant),
):
    """交易列表"""
    logger = TransactionLogger()
    records = logger.get_transactions(symbol=symbol, side=side, limit=limit)
    return [
        {
            "trade_id": r.trade_id,
            "timestamp": r.timestamp,
            "symbol": r.symbol,
            "name": r.symbol_name,
            "side": r.side,
            "price": r.price,
            "quantity": r.quantity,
            "value": r.value,
            "pnl": r.pnl,
            "pnl_pct": r.pnl_pct,
            "strategy": r.strategy_id,
            "reason": r.reason,
        }
        for r in records
    ]

@app.get("/log/pnl-curve", tags=["📝 日志"])
async def get_pnl_curve(symbol: str = None, tenant: str = Depends(get_tenant)):
    """PnL 曲线"""
    logger = TransactionLogger()
    stats = logger.get_statistics(symbol=symbol)
    return {"symbol_stats": stats.get("symbol_stats", []), "total_pnl": stats["total_pnl"]}


# ═══════════════════════════════════════
# 路由: 风控
# ═══════════════════════════════════════

@app.get("/risk/check/{symbol}", tags=["🛡️ 风控"])
async def check_position(
    symbol: str,
    price: float = Query(..., gt=0),
    quantity: int = Query(0, ge=0),
    tenant: str = Depends(get_tenant),
):
    """仓位检查"""
    from auto_executor import AutoExecutor, Signal, SignalStrength, RiskManager
    executor = AutoExecutor(mode="paper")
    rm = RiskManager(executor.account)
    sig = Signal(symbol=symbol, side="BUY", price=price, stop_loss=price * 0.95)
    ok, reason = rm.check_buy(sig)
    shares = rm._calc_shares(sig)
    return {
        "passed": ok,
        "reason": reason,
        "suggested_shares": shares,
        "current_positions": len(executor.account.positions),
        "max_positions": executor.account.max_positions,
        "available_cash": executor.account.available_cash,
    }

@app.get("/risk/r-value", tags=["🛡️ 风控"])
async def calc_r_value(
    price: float = Query(..., gt=0),
    stop_loss: float = Query(..., gt=0),
    tenant: str = Depends(get_tenant),
):
    """R值仓位计算"""
    from auto_executor import Account, RiskManager
    acct = Account()
    rm = RiskManager(acct)
    r_value = acct.total_value * acct.kelly_fraction
    shares = int(r_value / (price * 100)) * 100
    shares = max(100, shares)
    return {
        "r_value": round(r_value, 2),
        "price": price,
        "stop_loss": stop_loss,
        "risk_per_share": round(price - stop_loss, 2),
        "suggested_shares": shares,
        "suggested_value": round(price * shares, 2),
        "max_risk": round((price - stop_loss) * shares, 2),
    }


# ═══════════════════════════════════════
# Web 管理后台（简易 SPA 入口）
# ═══════════════════════════════════════

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Web 仪表盘"""
    return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{API_TITLE}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }}
        h1 {{ font-size: 24px; margin-bottom: 16px; }}
        h1 span {{ color: #f43f5e; }}
        .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin: 24px 0; }}
        .card {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }}
        .card h3 {{ font-size: 13px; color: #94a3b8; margin-bottom: 8px; }}
        .card .value {{ font-size: 28px; font-weight: 700; }}
        .card .green {{ color: #22c55e; }}
        .card .red {{ color: #ef4444; }}
        .endpoints {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }}
        .ep {{ background: #1e293b; border-radius: 8px; padding: 14px; border: 1px solid #334155; }}
        .ep .method {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; margin-right: 8px; }}
        .ep .method.get {{ background: #166534; color: #22c55e; }}
        .ep .method.post {{ background: #1e3a5f; color: #3b82f6; }}
        .ep .path {{ font-family: monospace; font-size: 14px; }}
        .ep .desc {{ font-size: 12px; color: #94a3b8; margin-top: 4px; }}
        a {{ color: #60a5fa; }}
    </style>
</head>
<body>
    <h1>🏰 安幕诺家族 · <span>小红 🌹</span> 交易系统</h1>
    <p style="color: #94a3b8;">TradingSkill 风格 · v{API_VERSION} · <a href="/docs">Swagger 文档</a> · <a href="/redoc">ReDoc</a></p>
    
    <div class="cards">
        <div class="card"><h3>📊 总交易</h3><div class="value" id="total_trades">—</div></div>
        <div class="card"><h3>🎯 胜率</h3><div class="value" id="win_rate">—</div></div>
        <div class="card"><h3>💰 总盈亏</h3><div class="value" id="total_pnl">—</div></div>
        <div class="card"><h3>📈 盈亏比</h3><div class="value" id="profit_factor">—</div></div>
    </div>
    
    <h2 style="margin: 24px 0 12px;">📡 API 端点</h2>
    <div class="endpoints">
        <div class="ep"><span class="method get">GET</span><span class="path">/health</span><div class="desc">健康检查</div></div>
        <div class="ep"><span class="method post">POST</span><span class="path">/auth/login</span><div class="desc">API Key 换取 JWT</div></div>
        <div class="ep"><span class="method get">GET</span><span class="path">/market/index</span><div class="desc">全球指数</div></div>
        <div class="ep"><span class="method get">GET</span><span class="path">/market/quote/{{symbol}}</span><div class="desc">个股行情</div></div>
        <div class="ep"><span class="method get">GET</span><span class="path">/market/sectors</span><div class="desc">板块资金排名</div></div>
        <div class="ep"><span class="method get">GET</span><span class="path">/strategy/signals</span><div class="desc">交易信号</div></div>
        <div class="ep"><span class="method post">POST</span><span class="path">/trade/order</span><div class="desc">下单交易</div></div>
        <div class="ep"><span class="method get">GET</span><span class="path">/trade/positions</span><div class="desc">当前持仓</div></div>
        <div class="ep"><span class="method get">GET</span><span class="path">/log/stats</span><div class="desc">交易统计</div></div>
        <div class="ep"><span class="method get">GET</span><span class="path">/risk/check/{{symbol}}</span><div class="desc">仓位检查</div></div>
        <div class="ep"><span class="method get">GET</span><span class="path">/risk/r-value</span><div class="desc">R值计算</div></div>
    </div>
    
    <script>
        fetch('/log/stats').then(r => r.json()).then(d => {{
            document.getElementById('total_trades').textContent = d.total_trades;
            document.getElementById('win_rate').innerHTML = `<span class="${{d.win_rate>=50?'green':'red'}}">${{d.win_rate}}%</span>`;
            const pnlEl = document.getElementById('total_pnl');
            pnlEl.innerHTML = `<span class="${{d.total_pnl>=0?'green':'red'}}">¥${{d.total_pnl.toLocaleString()}}</span>`;
            document.getElementById('profit_factor').textContent = d.profit_factor;
        }});
    </script>
</body>
</html>
"""


# ═══════════════════════════════════════
# 启动入口
# ═══════════════════════════════════════

def main():
    import uvicorn
    port = int(os.environ.get("API_PORT", 8000))
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
    )

if __name__ == "__main__":
    main()
