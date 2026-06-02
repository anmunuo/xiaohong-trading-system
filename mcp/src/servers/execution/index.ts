/**
 * 执行服务 MCP Server
 * 
 * 工具:
 *   place_order     → 下单（模拟/实盘）
 *   cancel_order    → 撤单
 *   get_orders      → 查询订单状态
 *   get_positions   → 查询当前持仓
 * 
 * 桥接: Python auto_executor.py
 */
import { z } from "zod";

function pyCall(code: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const { exec } = require("child_process");
    exec(
      `python3 -c "${code.replace(/"/g, '\\"')}"`,
      { cwd: "../../scripts", timeout: 30000 },
      (err: any, stdout: string, stderr: string) => {
        if (err) return reject(new Error(stderr || err.message));
        try { resolve(JSON.parse(stdout)); } catch { resolve({ raw: stdout }); }
      }
    );
  });
}

// ═══════════════════════════════════════
// Schemas
// ═══════════════════════════════════════

export const PlaceOrderSchema = z.object({
  symbol: z.string().describe("股票代码"),
  symbol_name: z.string().optional().default("").describe("股票名称"),
  side: z.enum(["BUY", "SELL"]).describe("买卖方向"),
  price: z.number().positive().describe("委托价格"),
  quantity: z.number().int().positive().describe("委托数量（股）"),
  order_type: z.enum(["market", "limit"]).optional().default("market").describe("订单类型"),
  stop_loss: z.number().optional().default(0).describe("止损价"),
  take_profit: z.number().optional().default(0).describe("止盈价"),
  strategy_id: z.string().optional().default("").describe("策略ID"),
  reason: z.string().optional().default("").describe("下单理由"),
});

export const CancelOrderSchema = z.object({
  order_id: z.string().describe("订单ID"),
});

export const GetOrdersSchema = z.object({
  symbol: z.string().optional().describe("按股票代码过滤"),
});

export const GetPositionsSchema = z.object({});

// ═══════════════════════════════════════
// Tools
// ═══════════════════════════════════════

export const executionTools = [
  {
    name: "place_order",
    description: "下单交易（Paper Trading 模式下零风险模拟，实盘需二次确认）",
    inputSchema: PlaceOrderSchema,
  },
  {
    name: "cancel_order",
    description: "撤销未成交的挂单",
    inputSchema: CancelOrderSchema,
  },
  {
    name: "get_orders",
    description: "查询订单历史和状态",
    inputSchema: GetOrdersSchema,
  },
  {
    name: "get_positions",
    description: "查询当前持仓列表（代码/数量/成本/盈亏）",
    inputSchema: GetPositionsSchema,
  },
];

// ═══════════════════════════════════════
// Handlers
// ═══════════════════════════════════════

export async function handlePlaceOrder(
  args: z.infer<typeof PlaceOrderSchema>
): Promise<string> {
  const script = `
import sys, json
sys.path.insert(0, '.')
from auto_executor import AutoExecutor, Signal, SignalStrength

executor = AutoExecutor(mode='paper')
signal = Signal(
    symbol='${args.symbol}',
    symbol_name='${args.symbol_name}',
    side='${args.side}',
    price=${args.price},
    quantity_hint=${args.quantity},
    stop_loss=${args.stop_loss},
    take_profit=${args.take_profit},
    strategy_id='${args.strategy_id}',
    reason='${args.reason}',
    strength=SignalStrength.MODERATE,
)
result = executor.process_signal(signal)
status = executor.generate_status_report()
print(json.dumps({"trade_id": result, "account": {"total_value": executor.account.total_value, "positions": len(executor.account.positions)}}, ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleCancelOrder(
  args: z.infer<typeof CancelOrderSchema>
): Promise<string> {
  return JSON.stringify({
    order_id: args.order_id,
    status: "cancelled",
    message: "Paper Trading 模式下所有订单即时成交，无需撤单",
  });
}

export async function handleGetOrders(
  args: z.infer<typeof GetOrdersSchema>
): Promise<string> {
  const filter = args.symbol ? `symbol='${args.symbol}'` : "";
  const script = `
import sys, json
sys.path.insert(0, '.')
from transaction_logger import TransactionLogger
logger = TransactionLogger()
records = logger.get_transactions(${filter ? filter : ""}, limit=20)
print(json.dumps([{"trade_id": r.trade_id, "symbol": r.symbol, "side": r.side, "price": r.price, "quantity": r.quantity, "status": r.execution_status, "timestamp": r.timestamp} for r in records], ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleGetPositions(): Promise<string> {
  const script = `
import sys, json
sys.path.insert(0, '.')
from auto_executor import AutoExecutor
executor = AutoExecutor(mode='paper')
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
print(json.dumps({"positions": positions, "total_value": executor.account.total_value, "available_cash": executor.account.available_cash}, ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}
