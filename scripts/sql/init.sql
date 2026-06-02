-- 安幕诺家族 · 小红 🌹 交易系统
-- PostgreSQL 初始化脚本

-- ═══════════════════════════════════════
-- 多租户：每个用户独立 schema
-- ═══════════════════════════════════════

-- 扩展
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ═══════════════════════════════════════
-- 交易日志表（所有租户共享一张物理表，schema 隔离）
-- ═══════════════════════════════════════

CREATE TABLE IF NOT EXISTS transactions (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       VARCHAR(64) NOT NULL DEFAULT 'default',
    trade_id        UUID NOT NULL DEFAULT uuid_generate_v4(),
    
    -- 交易信息
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(64),
    market          VARCHAR(10) NOT NULL DEFAULT 'A',  -- A/HK/US/Crypto
    side            VARCHAR(4) NOT NULL,                -- BUY/SELL
    order_type      VARCHAR(10) NOT NULL DEFAULT 'market',  -- market/limit
    
    -- 价格与数量
    price           DECIMAL(18, 4) NOT NULL,
    quantity        INTEGER NOT NULL,
    value           DECIMAL(18, 2) NOT NULL,            -- price × quantity
    fee             DECIMAL(18, 2) DEFAULT 0,
    
    -- 信号元数据
    strategy_id     VARCHAR(32),
    signal_type     VARCHAR(32),             -- buy/sell/hold
    signal_strength VARCHAR(16),             -- strong/moderate/weak
    signal_confidence DECIMAL(5, 2),          -- 0-100
    
    -- 风控
    stop_loss       DECIMAL(18, 4),
    take_profit     DECIMAL(18, 4),
    position_pct    DECIMAL(8, 4),            -- 仓位百分比
    
    -- 模拟/实盘
    is_paper        BOOLEAN NOT NULL DEFAULT TRUE,
    execution_status VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending/filled/cancelled/rejected
    
    -- PnL（卖出时计算）
    pnl             DECIMAL(18, 2),
    pnl_pct         DECIMAL(8, 4),
    portfolio_value DECIMAL(18, 2),
    
    -- 备注
    reason          TEXT,
    
    -- 时间戳
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at     TIMESTAMPTZ,
    
    CONSTRAINT valid_side CHECK (side IN ('BUY', 'SELL')),
    CONSTRAINT valid_status CHECK (execution_status IN ('pending', 'filled', 'cancelled', 'rejected'))
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_tx_tenant_symbol ON transactions(tenant_id, symbol);
CREATE INDEX IF NOT EXISTS idx_tx_tenant_time ON transactions(tenant_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_tx_tenant_paper ON transactions(tenant_id, is_paper);
CREATE INDEX IF NOT EXISTS idx_tx_trade_id ON transactions(trade_id);

-- ═══════════════════════════════════════
-- 持仓快照表
-- ═══════════════════════════════════════

CREATE TABLE IF NOT EXISTS positions (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       VARCHAR(64) NOT NULL DEFAULT 'default',
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(64),
    market          VARCHAR(10) NOT NULL DEFAULT 'A',
    
    avg_cost        DECIMAL(18, 4) NOT NULL,
    quantity        INTEGER NOT NULL,
    market_value    DECIMAL(18, 2),
    unrealized_pnl  DECIMAL(18, 2),
    pnl_pct         DECIMAL(8, 4),
    last_price      DECIMAL(18, 4),
    
    stop_loss       DECIMAL(18, 4),
    take_profit     DECIMAL(18, 4),
    trailing_stop   BOOLEAN DEFAULT FALSE,
    
    strategy_id     VARCHAR(32),
    is_paper        BOOLEAN NOT NULL DEFAULT TRUE,
    
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    UNIQUE(tenant_id, symbol, is_paper)
);

-- ═══════════════════════════════════════
-- 信号历史表
-- ═══════════════════════════════════════

CREATE TABLE IF NOT EXISTS signals (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       VARCHAR(64) NOT NULL DEFAULT 'default',
    symbol          VARCHAR(20) NOT NULL,
    symbol_name     VARCHAR(64),
    
    strategy_id     VARCHAR(32),
    signal_type     VARCHAR(16),     -- buy/sell/hold
    signal_strength VARCHAR(16),
    confidence      DECIMAL(5, 2),
    
    price_at_signal DECIMAL(18, 4),
    indicators      JSONB,           -- {rsi: 45.2, macd: {...}, ma_cross: true}
    
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signal_tenant_time ON signals(tenant_id, created_at DESC);

-- ═══════════════════════════════════════
-- 净值快照表
-- ═══════════════════════════════════════

CREATE TABLE IF NOT EXISTS nav_snapshots (
    id              BIGSERIAL PRIMARY KEY,
    tenant_id       VARCHAR(64) NOT NULL DEFAULT 'default',
    nav             DECIMAL(18, 2) NOT NULL,
    available_cash  DECIMAL(18, 2),
    market_value    DECIMAL(18, 2),
    total_pnl       DECIMAL(18, 2),
    position_count  INTEGER,
    is_paper        BOOLEAN NOT NULL DEFAULT TRUE,
    snapshot_time   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nav_tenant_time ON nav_snapshots(tenant_id, snapshot_time DESC);
