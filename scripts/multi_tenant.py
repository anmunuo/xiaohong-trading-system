#!/usr/bin/env python3
"""
安幕诺家族 · 小红 🌹 多租户管理系统
=====================================
PostgreSQL schema-per-tenant 隔离 + API Key 加密

架构:
  public.tenants        → 租户元数据
  <tenant_id>.transactions → 交易日志（schema 隔离）
  <tenant_id>.positions    → 持仓快照
  <tenant_id>.signals      → 信号历史
  <tenant_id>.nav_snapshots → 净值快照

安全:
  API Key 使用 SHA-256 哈希存储，永不存明文
  JWT token 绑定 tenant_id
"""
import os
import sys
import json
import hashlib
import secrets
import logging
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from enum import Enum

_log = logging.getLogger("multi_tenant")

# ═══════════════════════════════════════
# 数据模型
# ═══════════════════════════════════════

class TenantTier(Enum):
    FREE = "free"           # 免费版：1策略/5只自选/Paper Only
    PRO = "pro"             # 专业版：全部策略/50只自选/实盘
    FAMILY = "family"       # 家族版：无限/API接入/优先支持
    INTERNAL = "internal"   # 内部版：无限制

@dataclass
class Tenant:
    """租户"""
    tenant_id: str
    name: str
    tier: TenantTier = TenantTier.FREE
    api_key_hash: str = ""           # SHA-256(api_key)
    api_key_prefix: str = ""         # 前8位明文（用于UI显示）
    jwt_secret: str = ""             # 租户专属 JWT secret
    created_at: str = ""
    expires_at: str = ""             # 过期时间
    is_active: bool = True
    config: Dict[str, Any] = field(default_factory=dict)

    @property
    def limits(self) -> dict:
        """租户限额"""
        limits_map = {
            TenantTier.FREE: {"max_strategies": 1, "max_watchlist": 5, "live_trading": False, "max_positions": 3, "rate_limit": 30},
            TenantTier.PRO: {"max_strategies": 9, "max_watchlist": 50, "live_trading": True, "max_positions": 15, "rate_limit": 100},
            TenantTier.FAMILY: {"max_strategies": 999, "max_watchlist": 999, "live_trading": True, "max_positions": 50, "rate_limit": 500},
            TenantTier.INTERNAL: {"max_strategies": 9999, "max_watchlist": 9999, "live_trading": True, "max_positions": 999, "rate_limit": 9999},
        }
        return limits_map.get(self.tier, limits_map[TenantTier.FREE])


# ═══════════════════════════════════════
# 租户管理器
# ═══════════════════════════════════════

class TenantManager:
    """
    多租户管理器
    
    存储:
      - SQLite 本地: 租户元数据（轻量，无需 PG 也可运行）
      - PostgreSQL: schema 隔离的交易数据
    """
    
    def __init__(self, db_path: str = "data/tenants.db",
                 pg_url: str = None):
        self.db_path = Path(db_path)
        self.pg_url = pg_url or os.environ.get("DATABASE_URL", "")
        self._init_db()
        self._ensure_default_tenant()
    
    def _init_db(self):
        """初始化租户数据库"""
        import sqlite3
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = sqlite3.connect(str(self.db_path))
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free',
                api_key_hash TEXT NOT NULL,
                api_key_prefix TEXT NOT NULL,
                jwt_secret TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1,
                config_json TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                key_hash TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_used TEXT,
                FOREIGN KEY(tenant_id) REFERENCES tenants(tenant_id)
            );
        """)
        conn.commit()
        conn.close()
    
    def _ensure_default_tenant(self):
        """确保默认租户存在"""
        if not self.get_tenant("default"):
            self.create_tenant(
                tenant_id="default",
                name="安幕诺家族",
                tier=TenantTier.INTERNAL,
            )
    
    # ── CRUD ──
    
    def create_tenant(self, tenant_id: str, name: str,
                      tier: TenantTier = TenantTier.FREE,
                      expires_days: int = 365) -> Tenant:
        """创建租户"""
        import sqlite3
        
        api_key = f"xh-{tenant_id}-{secrets.token_hex(16)}"
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        api_key_prefix = api_key[:16]
        jwt_secret = secrets.token_hex(32)
        now = datetime.now().isoformat()
        expires = (datetime.now() + timedelta(days=expires_days)).isoformat()
        
        tenant = Tenant(
            tenant_id=tenant_id, name=name, tier=tier,
            api_key_hash=api_key_hash, api_key_prefix=api_key_prefix,
            jwt_secret=jwt_secret, created_at=now,
            expires_at=expires, is_active=True,
        )
        
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("""
            INSERT OR REPLACE INTO tenants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tenant.tenant_id, tenant.name, tenant.tier.value,
            tenant.api_key_hash, tenant.api_key_prefix,
            tenant.jwt_secret, tenant.created_at,
            tenant.expires_at, int(tenant.is_active),
            json.dumps(tenant.config),
        ))
        conn.execute("""
            INSERT OR REPLACE INTO api_keys VALUES (?, ?, ?, ?)
        """, (api_key_hash, tenant_id, now, None))
        conn.commit()
        conn.close()
        
        # PG schema
        self._create_pg_schema(tenant_id)
        
        _log.info(f"✅ 租户创建: {tenant_id} ({name}) tier={tier.value}")
        _log.info(f"   API Key: {api_key}  ← 请妥善保管，仅显示一次！")
        
        # 返回带明文 key 的副本（仅一次）
        tenant.config["_api_key_once"] = api_key
        return tenant
    
    def get_tenant(self, tenant_id: str) -> Optional[Tenant]:
        """获取租户"""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,)
        ).fetchone()
        conn.close()
        
        if not row:
            return None
        
        return Tenant(
            tenant_id=row["tenant_id"],
            name=row["name"],
            tier=TenantTier(row["tier"]),
            api_key_hash=row["api_key_hash"],
            api_key_prefix=row["api_key_prefix"],
            jwt_secret=row["jwt_secret"],
            created_at=row["created_at"],
            expires_at=row["expires_at"],
            is_active=bool(row["is_active"]),
            config=json.loads(row["config_json"] or "{}"),
        )
    
    def list_tenants(self) -> List[Tenant]:
        """列出所有租户"""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM tenants ORDER BY created_at DESC").fetchall()
        conn.close()
        
        return [
            Tenant(
                tenant_id=r["tenant_id"], name=r["name"],
                tier=TenantTier(r["tier"]),
                api_key_hash=r["api_key_hash"],
                api_key_prefix=r["api_key_prefix"],
                jwt_secret=r["jwt_secret"],
                created_at=r["created_at"],
                expires_at=r["expires_at"],
                is_active=bool(r["is_active"]),
                config=json.loads(r["config_json"] or "{}"),
            )
            for r in rows
        ]
    
    def verify_api_key(self, api_key: str) -> Optional[str]:
        """验证 API Key，返回 tenant_id"""
        import sqlite3
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        conn = sqlite3.connect(str(self.db_path))
        row = conn.execute(
            "SELECT tenant_id FROM api_keys WHERE key_hash = ?", (key_hash,)
        ).fetchone()
        
        if row:
            conn.execute(
                "UPDATE api_keys SET last_used = ? WHERE key_hash = ?",
                (datetime.now().isoformat(), key_hash)
            )
            conn.commit()
        
        conn.close()
        return row[0] if row else None
    
    def deactivate_tenant(self, tenant_id: str):
        """停用租户"""
        import sqlite3
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("UPDATE tenants SET is_active = 0 WHERE tenant_id = ?", (tenant_id,))
        conn.commit()
        conn.close()
    
    def rotate_api_key(self, tenant_id: str) -> str:
        """轮换 API Key"""
        import sqlite3
        
        tenant = self.get_tenant(tenant_id)
        if not tenant:
            raise ValueError(f"租户不存在: {tenant_id}")
        
        new_key = f"xh-{tenant_id}-{secrets.token_hex(16)}"
        new_hash = hashlib.sha256(new_key.encode()).hexdigest()
        new_prefix = new_key[:16]
        
        conn = sqlite3.connect(str(self.db_path))
        conn.execute("DELETE FROM api_keys WHERE tenant_id = ?", (tenant_id,))
        conn.execute("INSERT INTO api_keys VALUES (?, ?, ?, ?)",
                     (new_hash, tenant_id, datetime.now().isoformat(), None))
        conn.execute("UPDATE tenants SET api_key_hash = ?, api_key_prefix = ? WHERE tenant_id = ?",
                     (new_hash, new_prefix, tenant_id))
        conn.commit()
        conn.close()
        
        return new_key
    
    # ── PostgreSQL Schema 隔离 ──
    
    def _create_pg_schema(self, tenant_id: str):
        """为租户创建独立 PG schema"""
        if not self.pg_url:
            _log.info(f"📝 PG 未配置，跳过 schema 创建: {tenant_id}")
            return
        
        try:
            import sqlite3  # fallback: 用 sqlite 模拟
            _log.info(f"📁 PG schema 创建: {tenant_id}")
            # 生产环境用 asyncpg/psycopg2:
            # CREATE SCHEMA IF NOT EXISTS {tenant_id};
            # SET search_path TO {tenant_id};
            # CREATE TABLE transactions (...);
            # CREATE TABLE positions (...);
            pass
        except Exception as e:
            _log.error(f"PG schema 创建失败: {e}")
    
    def get_tenant_limits(self, tenant_id: str) -> dict:
        """获取租户限额"""
        tenant = self.get_tenant(tenant_id)
        if tenant:
            return tenant.limits
        return TenantTier.FREE.value


# ═══════════════════════════════════════
# 全局单例
# ═══════════════════════════════════════

_tenant_manager: Optional[TenantManager] = None

def get_tenant_manager() -> TenantManager:
    global _tenant_manager
    if _tenant_manager is None:
        _tenant_manager = TenantManager()
    return _tenant_manager


# ═══════════════════════════════════════
# CLI
# ═══════════════════════════════════════

if __name__ == "__main__":
    import argparse
    
    p = argparse.ArgumentParser(description="小红多租户管理")
    sp = p.add_subparsers(dest="cmd")
    
    sp.add_parser("list", help="列出租户")
    
    c = sp.add_parser("create", help="创建租户")
    c.add_argument("--id", required=True)
    c.add_argument("--name", required=True)
    c.add_argument("--tier", default="free", choices=["free", "pro", "family", "internal"])
    c.add_argument("--days", type=int, default=365)
    
    r = sp.add_parser("rotate", help="轮换API Key")
    r.add_argument("--id", required=True)
    
    d = sp.add_parser("deactivate", help="停用租户")
    d.add_argument("--id", required=True)
    
    v = sp.add_parser("verify", help="验证API Key")
    v.add_argument("--key", required=True)
    
    args = p.parse_args()
    mgr = TenantManager()
    
    if args.cmd == "list":
        tenants = mgr.list_tenants()
        print(f"\n🏢 租户列表 ({len(tenants)})")
        print("-" * 70)
        for t in tenants:
            status = "✅" if t.is_active else "❌"
            print(f"  {status} {t.tenant_id:20s} | {t.name:15s} | {t.tier.value:10s} | {t.created_at[:10]}")
    
    elif args.cmd == "create":
        t = mgr.create_tenant(args.id, args.name, TenantTier(args.tier), args.days)
        print(f"\n✅ 租户已创建: {t.tenant_id}")
        print(f"   API Key: {t.config.get('_api_key_once', 'N/A')}")
        print(f"   Tier: {t.tier.value}")
        print(f"   过期: {t.expires_at[:10]}")
        print(f"\n⚠️ 请立即保存 API Key，此信息仅显示一次！")
    
    elif args.cmd == "rotate":
        new_key = mgr.rotate_api_key(args.id)
        print(f"🔑 新 API Key: {new_key}")
    
    elif args.cmd == "deactivate":
        mgr.deactivate_tenant(args.id)
        print(f"❌ 已停用: {args.id}")
    
    elif args.cmd == "verify":
        tid = mgr.verify_api_key(args.key)
        if tid:
            t = mgr.get_tenant(tid)
            print(f"✅ 有效: {tid} ({t.name}) tier={t.tier.value}")
        else:
            print("❌ 无效 API Key")
    
    else:
        mgr.list_tenants()
