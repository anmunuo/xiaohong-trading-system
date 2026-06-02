/**
 * 行情数据 MCP Server — TradingSkill 风格
 * 
 * 工具:
 *   get_index_data     → 全球指数
 *   get_stock_quote    → 个股行情
 *   get_north_flow     → 北向资金
 *   get_sector_flow    → 板块资金排名
 *   get_daily_bars     → 个股日线
 * 
 * 数据源: Python data_pipeline.py (Tushare/AKShare/东方财富/Sina)
 */
import { z } from "zod";

// ═══════════════════════════════════════
// Python Bridge
// ═══════════════════════════════════════
const PY_BRIDGE = "python3 -c";

function pyCall(code: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const { exec } = require("child_process");
    exec(
      `${PY_BRIDGE} "${code.replace(/"/g, '\\"')}"`,
      { cwd: "../../scripts", timeout: 30000 },
      (err: any, stdout: string, stderr: string) => {
        if (err) return reject(new Error(stderr || err.message));
        try {
          resolve(JSON.parse(stdout));
        } catch {
          resolve({ raw: stdout });
        }
      }
    );
  });
}

// ═══════════════════════════════════════
// Tool Schemas (Zod)
// ═══════════════════════════════════════

export const GetIndexDataSchema = z.object({});

export const GetStockQuoteSchema = z.object({
  symbol: z.string().describe("股票代码，如 600519"),
});

export const GetNorthFlowSchema = z.object({});

export const GetSectorFlowSchema = z.object({
  top_n: z.number().optional().default(10).describe("返回前N个板块"),
});

export const GetDailyBarsSchema = z.object({
  symbol: z.string().describe("股票代码"),
  days: z.number().optional().default(60).describe("日线天数"),
});

// ═══════════════════════════════════════
// Tool Definitions
// ═══════════════════════════════════════

export const marketDataTools = [
  {
    name: "get_index_data",
    description: "获取全球主要指数实时数据（上证/深证/恒生/纳指/标普/道指/DAX）",
    inputSchema: GetIndexDataSchema,
  },
  {
    name: "get_stock_quote",
    description: "获取单只个股实时行情（价格/涨跌幅/成交量）",
    inputSchema: GetStockQuoteSchema,
  },
  {
    name: "get_north_flow",
    description: "获取北向资金流向（沪股通+深股通净流入）",
    inputSchema: GetNorthFlowSchema,
  },
  {
    name: "get_sector_flow",
    description: "获取行业板块资金流向排名",
    inputSchema: GetSectorFlowSchema,
  },
  {
    name: "get_daily_bars",
    description: "获取个股历史日线（OHLCV + MA）",
    inputSchema: GetDailyBarsSchema,
  },
];

// ═══════════════════════════════════════
// Tool Handlers
// ═══════════════════════════════════════

export async function handleGetIndexData(): Promise<string> {
  const script = `
import sys, json
sys.path.insert(0, '.')
from data_pipeline import get_index_data
print(json.dumps(get_index_data(), ensure_ascii=False, default=str))
  `;
  const result = await pyCall(script);
  return formatJson(result);
}

export async function handleGetStockQuote(args: z.infer<typeof GetStockQuoteSchema>): Promise<string> {
  const script = `
import sys, json
sys.path.insert(0, '.')
from data_pipeline import get_stock_realtime
result = get_stock_realtime(['${args.symbol}'])
print(json.dumps(result, ensure_ascii=False, default=str))
  `;
  const result = await pyCall(script);
  return formatJson(result);
}

export async function handleGetNorthFlow(): Promise<string> {
  const script = `
import sys, json
sys.path.insert(0, '.')
from data_pipeline import get_north_flow
print(json.dumps(get_north_flow(), ensure_ascii=False, default=str))
  `;
  const result = await pyCall(script);
  return formatJson(result);
}

export async function handleGetSectorFlow(args: z.infer<typeof GetSectorFlowSchema>): Promise<string> {
  const script = `
import sys, json
sys.path.insert(0, '.')
from data_pipeline import get_sector_flow_rank
result = get_sector_flow_rank()
if result:
    result = result[:${args.top_n}]
print(json.dumps(result if result else [], ensure_ascii=False, default=str))
  `;
  const result = await pyCall(script);
  return formatJson(result);
}

export async function handleGetDailyBars(args: z.infer<typeof GetDailyBarsSchema>): Promise<string> {
  const script = `
import sys, json, subprocess
result = subprocess.run(
    ['data', 'fetch', 'stock', '--symbol', '${args.symbol}', '--category', 'daily', '--days', '${args.days}'],
    capture_output=True, text=True, timeout=30
)
print(result.stdout)
  `;
  const result = await pyCall(script);
  return formatJson(result);
}

function formatJson(data: any): string {
  if (typeof data === "string") return data;
  return JSON.stringify(data, null, 2);
}
