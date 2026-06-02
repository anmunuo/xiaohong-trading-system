/**
 * 安幕诺家族 · 小红 🌹 API 客户端 SDK (TypeScript)
 * =================================================
 * 小程序 + Web 后台共享的 API 调用层
 * 
 * 用法:
 *   import { XiaohongAPI } from './xiaohong-api';
 *   const api = new XiaohongAPI({ baseUrl: 'https://api.xiaohong.family', apiKey: 'xh-xxx' });
 *   const stats = await api.getStats();
 */

// ═══════════════════════════════════════
// 类型定义
// ═══════════════════════════════════════

export interface HealthResponse {
  status: string;
  version: string;
  uptime: number;
  tenants: number;
}

export interface LoginResponse {
  token: string;
  tenant_id: string;
  expires_in: number;
}

export interface IndexData {
  asia?: {
    shanghai?: [number, number];
    shenzhen?: [number, number];
    hang_seng?: [number, number];
  };
  us?: {
    nasdaq?: [number, number];
    sp500?: [number, number];
    dow?: [number, number];
  };
  europe?: {
    dax?: [number, number];
  };
}

export interface StockQuote {
  close: number;
  change_pct: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  data_source: string;
  trade_date: string;
}

export interface NorthFlow {
  net_flow: number;
  status: string;
}

export interface SectorFlow {
  sector: string;
  net_flow: number;
  change_pct: number;
}

export interface TradeStats {
  total_trades: number;
  buys: number;
  sells: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_pnl: number;
  avg_win: number;
  avg_loss: number;
  profit_factor: number;
  portfolio_value: number;
  symbol_stats: Array<{ symbol: string; trades: number; total_pnl: number }>;
}

export interface TradeItem {
  trade_id: string;
  timestamp: string;
  symbol: string;
  name: string;
  side: "BUY" | "SELL";
  price: number;
  quantity: number;
  value: number;
  pnl: number;
  pnl_pct: number;
  strategy: string;
  reason: string;
}

export interface PositionItem {
  symbol: string;
  name: string;
  quantity: number;
  avg_cost: number;
  current_price: number;
  market_value: number;
  unrealized_pnl: number;
  pnl_pct: number;
}

export interface AccountResponse {
  total_value: number;
  available_cash: number;
  positions: PositionItem[];
  position_count: number;
}

export interface StrategySignal {
  symbol: string;
  action: string;
  severity: "critical" | "warning" | "info" | "ok";
  reason: string;
}

export interface StrategyListItem {
  id: string;
  name: string;
  desc: string;
  status?: string;
}

export interface OrderRequest {
  symbol: string;
  symbol_name?: string;
  side: "BUY" | "SELL";
  price: number;
  quantity: number;
  order_type?: "market" | "limit";
  stop_loss?: number;
  take_profit?: number;
  strategy_id?: string;
  reason?: string;
}

export interface OrderResponse {
  trade_id: string;
  status: string;
  symbol: string;
  message: string;
}

export interface RiskCheck {
  passed: boolean;
  reason: string;
  suggested_shares: number;
  current_positions: number;
  max_positions: number;
  available_cash: number;
}

export interface RValue {
  r_value: number;
  price: number;
  stop_loss: number;
  risk_per_share: number;
  suggested_shares: number;
  suggested_value: number;
  max_risk: number;
}

export interface TenantInfo {
  tenant_id: string;
  name: string;
  tier: string;
  is_active: boolean;
  created_at: string;
  expires_at: string;
}

// ═══════════════════════════════════════
// 配置
// ═══════════════════════════════════════

export interface XiaohongAPIConfig {
  baseUrl: string;
  apiKey?: string;
  token?: string;
  tenantId?: string;
}

// ═══════════════════════════════════════
// API 客户端
// ═══════════════════════════════════════

export class XiaohongAPI {
  private baseUrl: string;
  private apiKey?: string;
  private token?: string;
  private tenantId?: string;

  constructor(config: XiaohongAPIConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, "");
    this.apiKey = config.apiKey;
    this.token = config.token;
    this.tenantId = config.tenantId;
  }

  private async request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...((options.headers as Record<string, string>) || {}),
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    } else if (this.apiKey) {
      headers["X-API-Key"] = this.apiKey;
    }

    const res = await fetch(`${this.baseUrl}${path}`, { ...options, headers });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ error: res.statusText }));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  }

  // ── 认证 ──

  async login(apiKey: string): Promise<LoginResponse> {
    const res = await this.request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ api_key: apiKey }),
    });
    this.token = res.token;
    this.tenantId = res.tenant_id;
    return res;
  }

  // ── 系统 ──

  async health(): Promise<HealthResponse> {
    return this.request("/health");
  }

  // ── 行情 ──

  async getIndex(): Promise<IndexData> {
    return this.request("/market/index");
  }

  async getQuote(symbol: string): Promise<StockQuote> {
    return this.request(`/market/quote/${symbol}`);
  }

  async getNorthFlow(): Promise<NorthFlow> {
    return this.request("/market/north-flow");
  }

  async getSectors(topN: number = 10): Promise<SectorFlow[]> {
    return this.request(`/market/sectors?top_n=${topN}`);
  }

  // ── 交易 ──

  async placeOrder(req: OrderRequest): Promise<OrderResponse> {
    return this.request("/trade/order", {
      method: "POST",
      body: JSON.stringify(req),
    });
  }

  async getPositions(): Promise<AccountResponse> {
    return this.request("/trade/positions");
  }

  // ── 策略 ──

  async getSignals(): Promise<StrategySignal[]> {
    return this.request("/strategy/signals");
  }

  async listStrategies(): Promise<{ strategies: StrategyListItem[] }> {
    return this.request("/strategy/list");
  }

  // ── 日志 ──

  async getStats(symbol?: string): Promise<TradeStats> {
    const qs = symbol ? `?symbol=${symbol}` : "";
    return this.request(`/log/stats${qs}`);
  }

  async getTrades(symbol?: string, side?: string, limit: number = 20): Promise<TradeItem[]> {
    const params = new URLSearchParams();
    if (symbol) params.set("symbol", symbol);
    if (side) params.set("side", side);
    params.set("limit", String(limit));
    return this.request(`/log/trades?${params.toString()}`);
  }

  async getPnlCurve(symbol?: string): Promise<any> {
    const qs = symbol ? `?symbol=${symbol}` : "";
    return this.request(`/log/pnl-curve${qs}`);
  }

  // ── 风控 ──

  async checkPosition(symbol: string, price: number, quantity?: number): Promise<RiskCheck> {
    const qs = `?price=${price}${quantity ? `&quantity=${quantity}` : ""}`;
    return this.request(`/risk/check/${symbol}${qs}`);
  }

  async calcRValue(price: number, stopLoss: number): Promise<RValue> {
    return this.request(`/risk/r-value?price=${price}&stop_loss=${stopLoss}`);
  }
}

// ═══════════════════════════════════════
// 默认导出
// ═══════════════════════════════════════

export default XiaohongAPI;
