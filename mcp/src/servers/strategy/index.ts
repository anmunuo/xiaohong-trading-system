/**
 * 策略引擎 MCP Server
 * 
 * 工具:
 *   list_strategies    → 列出可用策略
 *   run_strategy       → 运行指定策略
 *   get_signals        → 获取综合交易信号
 *   run_screener       → 全市场多因子选股
 * 
 * 桥接: Python strategy_bridge.py + stock_screener.py
 */
import { z } from "zod";

function pyCall(code: string): Promise<any> {
  return new Promise((resolve, reject) => {
    const { exec } = require("child_process");
    exec(
      `python3 -c "${code.replace(/"/g, '\\"')}"`,
      { cwd: "../../scripts", timeout: 60000 },
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

export const ListStrategiesSchema = z.object({});

export const RunStrategySchema = z.object({
  strategy_id: z.enum(["CMP-001", "SEL-001", "POS-002", "STP-001"]).describe("策略ID"),
  symbol: z.string().optional().describe("股票代码（部分策略需要）"),
});

export const GetSignalsSchema = z.object({});

export const RunScreenerSchema = z.object({
  top_n: z.number().optional().default(20).describe("返回前N只"),
  min_roe: z.number().optional().default(10).describe("最低ROE(%)"),
  max_pe: z.number().optional().default(50).describe("最高PE"),
});

// ═══════════════════════════════════════
// Tools
// ═══════════════════════════════════════

export const strategyTools = [
  {
    name: "list_strategies",
    description: "列出所有可用交易策略（CMP/SEL/POS/STP）",
    inputSchema: ListStrategiesSchema,
  },
  {
    name: "run_strategy",
    description: "运行指定策略并获取结果",
    inputSchema: RunStrategySchema,
  },
  {
    name: "get_signals",
    description: "获取当前持仓的综合交易信号（买入/卖出/持有+仓位建议）",
    inputSchema: GetSignalsSchema,
  },
  {
    name: "run_screener",
    description: "全市场多因子选股筛选（PE/PB/ROE/市值/动量）",
    inputSchema: RunScreenerSchema,
  },
];

// ═══════════════════════════════════════
// Handlers
// ═══════════════════════════════════════

export async function handleListStrategies(): Promise<string> {
  const script = `
import sys, json, subprocess
sys.path.insert(0, '.')
r = subprocess.run(['python3', 'strategy_bridge.py', 'list'], capture_output=True, text=True, timeout=30)
print(r.stdout)
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleRunStrategy(
  args: z.infer<typeof RunStrategySchema>
): Promise<string> {
  const sym = args.symbol ? ` ${args.symbol}` : "";
  const script = `
import sys, json, subprocess
sys.path.insert(0, '.')
r = subprocess.run(['python3', 'strategy_bridge.py', 'run', '${args.strategy_id}'${sym ? `, '${args.symbol}'` : ''}], capture_output=True, text=True, timeout=30)
print(r.stdout)
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleGetSignals(): Promise<string> {
  const script = `
import sys, json, subprocess
sys.path.insert(0, '.')
r = subprocess.run(['python3', 'strategy_bridge.py', 'signal'], capture_output=True, text=True, timeout=30)
print(r.stdout)
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleRunScreener(
  args: z.infer<typeof RunScreenerSchema>
): Promise<string> {
  const script = `
import sys, json, subprocess
sys.path.insert(0, '.')
r = subprocess.run(['python3', 'stock_screener.py', '${args.top_n}'], capture_output=True, text=True, timeout=120)
print(r.stdout)
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}
