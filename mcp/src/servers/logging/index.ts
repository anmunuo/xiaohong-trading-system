/**
 * 日志服务 MCP Server
 * 
 * 工具:
 *   get_trade_stats     → 交易统计（胜率/盈亏比/PnL）
 *   get_recent_trades   → 最近交易列表
 *   export_trades       → 导出交易记录CSV
 *   get_pnl_curve       → PnL 曲线数据
 * 
 * 桥接: Python transaction_logger.py
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

export const GetTradeStatsSchema = z.object({
  symbol: z.string().optional().describe("按股票过滤"),
});

export const GetRecentTradesSchema = z.object({
  limit: z.number().optional().default(20).describe("返回条数"),
  symbol: z.string().optional().describe("按股票过滤"),
  side: z.enum(["BUY", "SELL"]).optional().describe("按买卖方向过滤"),
});

export const ExportTradesSchema = z.object({
  symbol: z.string().optional().describe("按股票过滤"),
  output_path: z.string().optional().default("workspace/filtered.csv").describe("输出路径"),
});

export const GetPnlCurveSchema = z.object({
  symbol: z.string().optional().describe("按股票过滤"),
});

// ═══════════════════════════════════════
// Tools
// ═══════════════════════════════════════

export const loggingTools = [
  {
    name: "get_trade_stats",
    description: "获取交易统计：总交易数/胜率/盈亏比/总PnL/各标的盈亏",
    inputSchema: GetTradeStatsSchema,
  },
  {
    name: "get_recent_trades",
    description: "获取最近交易记录列表（CSV格式，对标TradingSkill）",
    inputSchema: GetRecentTradesSchema,
  },
  {
    name: "export_trades",
    description: "导出过滤后的交易记录为CSV文件",
    inputSchema: ExportTradesSchema,
  },
  {
    name: "get_pnl_curve",
    description: "获取累计PnL曲线数据（用于图表展示）",
    inputSchema: GetPnlCurveSchema,
  },
];

// ═══════════════════════════════════════
// Handlers
// ═══════════════════════════════════════

export async function handleGetTradeStats(
  args: z.infer<typeof GetTradeStatsSchema>
): Promise<string> {
  const sym_filter = args.symbol ? `symbol='${args.symbol}'` : "";
  const script = `
import sys, json
sys.path.insert(0, '.')
from transaction_logger import TransactionLogger
logger = TransactionLogger()
stats = logger.get_statistics(${args.symbol ? f"symbol='{args.symbol}'" : ""})
print(json.dumps(stats, ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleGetRecentTrades(
  args: z.infer<typeof GetRecentTradesSchema>
): Promise<string> {
  const parts: string[] = [];
  if (args.symbol) parts.push(`symbol='${args.symbol}'`);
  if (args.side) parts.push(`side='${args.side}'`);
  const kwargs = parts.join(", ");
  
  const script = `
import sys, json
sys.path.insert(0, '.')
from transaction_logger import TransactionLogger
logger = TransactionLogger()
records = logger.get_transactions(${kwargs}, limit=${args.limit})
result = []
for r in records:
    result.append({
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
    })
print(json.dumps(result, ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleExportTrades(
  args: z.infer<typeof ExportTradesSchema>
): Promise<string> {
  const sym_filter = args.symbol ? `--symbol ${args.symbol}` : "";
  const script = `
import sys, subprocess
sys.path.insert(0, '.')
r = subprocess.run(['python3', 'transaction_logger.py', 'export', '--output', '${args.output_path}'${args.symbol ? `, '--symbol', '${args.symbol}'` : ''}], capture_output=True, text=True, timeout=30)
print(json.dumps({"result": r.stdout.strip(), "path": "${args.output_path}"}, ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleGetPnlCurve(
  args: z.infer<typeof GetPnlCurveSchema>
): Promise<string> {
  const filter = args.symbol ? f"AND symbol = '{args.symbol}'" : "";
  const script = `
import sys, json, sqlite3
sys.path.insert(0, '.')
conn = sqlite3.connect('data/transactions.db')
rows = conn.execute(
    "SELECT timestamp, pnl, portfolio_value FROM transactions "
    "WHERE execution_status='filled' AND side='SELL' ${filter} "
    "ORDER BY timestamp ASC"
).fetchall()
conn.close()

cumulative = 0
points = []
for r in rows:
    cumulative += (r[1] or 0)
    points.append({"timestamp": r[0], "pnl": r[1] or 0, "cumulative_pnl": round(cumulative, 2), "portfolio_value": r[2] or 0})

print(json.dumps(points, ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}
