/**
 * 小红 MCP Client — TradingSkill 风格核心
 * 
 * 参照 gwrxuk/TradingSkill → src/client.ts
 * 
 * 职责:
 *   1. 注册所有 MCP 服务器工具
 *   2. 提供统一调用接口
 *   3. 工具发现与按需加载
 */
import {
  marketDataTools,
  handleGetIndexData,
  handleGetStockQuote,
  handleGetNorthFlow,
  handleGetSectorFlow,
  handleGetDailyBars,
} from "./servers/market-data/index.js";

import {
  strategyTools,
  handleListStrategies,
  handleRunStrategy,
  handleGetSignals,
  handleRunScreener,
} from "./servers/strategy/index.js";

import {
  executionTools,
  handlePlaceOrder,
  handleCancelOrder,
  handleGetOrders,
  handleGetPositions,
} from "./servers/execution/index.js";

import {
  riskTools,
  handleCheckPositionLimit,
  handleCheckStopLoss,
  handleCalcPositionSize,
  handleGetRiskReport,
} from "./servers/risk/index.js";

import {
  loggingTools,
  handleGetTradeStats,
  handleGetRecentTrades,
  handleExportTrades,
  handleGetPnlCurve,
} from "./servers/logging/index.js";

// ═══════════════════════════════════════
// Tool Registry
// ═══════════════════════════════════════

interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: any;
}

interface ToolHandler {
  (args: any): Promise<string>;
}

const toolRegistry = new Map<string, { definition: ToolDefinition; handler: ToolHandler }>();

function register(name: string, definition: ToolDefinition, handler: ToolHandler) {
  toolRegistry.set(name, { definition, handler });
}

// 注册全部 17 个工具
(function registerAll() {
  // 行情数据 (5)
  register("get_index_data", marketDataTools[0], handleGetIndexData);
  register("get_stock_quote", marketDataTools[1], handleGetStockQuote);
  register("get_north_flow", marketDataTools[2], handleGetNorthFlow);
  register("get_sector_flow", marketDataTools[3], handleGetSectorFlow);
  register("get_daily_bars", marketDataTools[4], handleGetDailyBars);

  // 策略引擎 (4)
  register("list_strategies", strategyTools[0], handleListStrategies);
  register("run_strategy", strategyTools[1], handleRunStrategy);
  register("get_signals", strategyTools[2], handleGetSignals);
  register("run_screener", strategyTools[3], handleRunScreener);

  // 执行服务 (4)
  register("place_order", executionTools[0], handlePlaceOrder);
  register("cancel_order", executionTools[1], handleCancelOrder);
  register("get_orders", executionTools[2], handleGetOrders);
  register("get_positions", executionTools[3], handleGetPositions);

  // 风控服务 (4)
  register("check_position_limit", riskTools[0], handleCheckPositionLimit);
  register("check_stop_loss", riskTools[1], handleCheckStopLoss);
  register("calc_position_size", riskTools[2], handleCalcPositionSize);
  register("get_risk_report", riskTools[3], handleGetRiskReport);

  // 日志服务 (4)
  register("get_trade_stats", loggingTools[0], handleGetTradeStats);
  register("get_recent_trades", loggingTools[1], handleGetRecentTrades);
  register("export_trades", loggingTools[2], handleExportTrades);
  register("get_pnl_curve", loggingTools[3], handleGetPnlCurve);
})();

// ═══════════════════════════════════════
// Public API
// ═══════════════════════════════════════

/** 获取所有已注册的工具定义 */
export function listTools(): ToolDefinition[] {
  return Array.from(toolRegistry.values()).map((v) => v.definition);
}

/** 获取指定分类的工具 */
export function listToolsByCategory(category: "market" | "strategy" | "execution" | "risk" | "logging"): ToolDefinition[] {
  const prefixMap: Record<string, string[]> = {
    market: ["get_index_data", "get_stock_quote", "get_north_flow", "get_sector_flow", "get_daily_bars"],
    strategy: ["list_strategies", "run_strategy", "get_signals", "run_screener"],
    execution: ["place_order", "cancel_order", "get_orders", "get_positions"],
    risk: ["check_position_limit", "check_stop_loss", "calc_position_size", "get_risk_report"],
    logging: ["get_trade_stats", "get_recent_trades", "export_trades", "get_pnl_curve"],
  };

  const names = prefixMap[category] || [];
  return names
    .map((n) => toolRegistry.get(n))
    .filter(Boolean)
    .map((v) => v!.definition);
}

/** 调用工具 */
export async function callTool(name: string, args: any = {}): Promise<string> {
  const entry = toolRegistry.get(name);
  if (!entry) {
    throw new Error(`未知工具: ${name}. 可用: ${Array.from(toolRegistry.keys()).join(", ")}`);
  }
  return entry.handler(args);
}

/** 工具可用性检查 */
export function hasTool(name: string): boolean {
  return toolRegistry.has(name);
}

/** 获取工具定义 */
export function getToolDefinition(name: string): ToolDefinition | undefined {
  return toolRegistry.get(name)?.definition;
}
