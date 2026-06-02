/**
 * 风控服务 MCP Server
 * 
 * 工具:
 *   check_position_limit → 仓位上限检查
 *   check_stop_loss     → 止损检查
 *   calc_position_size  → R值仓位计算
 *   get_risk_report     → 综合风控报告
 * 
 * 桥接: Python ammo_risk.py + auto_executor.RiskManager
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

export const CheckPositionLimitSchema = z.object({
  symbol: z.string().describe("要检查的股票代码"),
  price: z.number().positive().describe("拟买入价格"),
  quantity: z.number().int().positive().optional().default(0).describe("拟买入数量（0=自动计算）"),
});

export const CheckStopLossSchema = z.object({
  symbol: z.string().optional().describe("股票代码（不填=检查全部持仓）"),
});

export const CalcPositionSizeSchema = z.object({
  symbol: z.string().optional().default("").describe("股票代码"),
  price: z.number().positive().describe("当前价格"),
  stop_loss: z.number().positive().describe("止损价"),
});

export const GetRiskReportSchema = z.object({});

// ═══════════════════════════════════════
// Tools
// ═══════════════════════════════════════

export const riskTools = [
  {
    name: "check_position_limit",
    description: "检查拟买入是否符合仓位上限（单股≤33.3%，总持仓≤9只）",
    inputSchema: CheckPositionLimitSchema,
  },
  {
    name: "check_stop_loss",
    description: "检查持仓是否触发止损线",
    inputSchema: CheckStopLossSchema,
  },
  {
    name: "calc_position_size",
    description: "基于R值和凯利公式计算建议仓位（股数+金额）",
    inputSchema: CalcPositionSizeSchema,
  },
  {
    name: "get_risk_report",
    description: "获取综合风控报告（仓位/止损/净值/凯利）",
    inputSchema: GetRiskReportSchema,
  },
];

// ═══════════════════════════════════════
// Handlers
// ═══════════════════════════════════════

export async function handleCheckPositionLimit(
  args: z.infer<typeof CheckPositionLimitSchema>
): Promise<string> {
  const qty = args.quantity > 0 ? args.quantity : "0";
  const script = `
import sys, json
sys.path.insert(0, '.')
from auto_executor import AutoExecutor, Signal, SignalStrength, RiskManager, Account

executor = AutoExecutor(mode='paper')
acct = executor.account
rm = RiskManager(acct)

signal = Signal(symbol='${args.symbol}', side='BUY', price=${args.price}, stop_loss=${args.price * 0.95})

ok, reason = rm.check_buy(signal)
shares = rm._calc_shares(signal)
target_value = ${args.price} * shares
position_pct = (target_value / acct.total_value) * 100

print(json.dumps({
    "passed": ok,
    "reason": reason,
    "suggested_shares": shares,
    "suggested_value": round(target_value, 2),
    "position_pct": round(position_pct, 1),
    "max_position_pct": acct.max_position_pct,
    "current_positions": len(acct.positions),
    "max_positions": acct.max_positions,
    "available_cash": acct.available_cash,
    "total_value": acct.total_value,
}, ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleCheckStopLoss(
  args: z.infer<typeof CheckStopLossSchema>
): Promise<string> {
  const filter = args.symbol ? `codes=['${args.symbol}']` : "";
  const script = `
import sys, json, subprocess
sys.path.insert(0, '.')
r = subprocess.run(['python3', 'strategy_bridge.py', 'risk'${args.symbol ? `, '${args.symbol}'` : ''}], capture_output=True, text=True, timeout=30)
print(r.stdout)
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleCalcPositionSize(
  args: z.infer<typeof CalcPositionSizeSchema>
): Promise<string> {
  const risk_per_share = args.price - args.stop_loss;
  const script = `
import sys, json
sys.path.insert(0, '.')
from auto_executor import AutoExecutor, RiskManager, Account

acct = Account()
rm = RiskManager(acct)

# R 值计算
r_value = acct.total_value * acct.kelly_fraction
shares = int(r_value / (${args.price} * 100)) * 100
shares = max(100, shares)

risk_total = ${risk_per_share} * shares
risk_pct = (risk_total / acct.total_value) * 100

print(json.dumps({
    "price": ${args.price},
    "stop_loss": ${args.stop_loss},
    "risk_per_share": ${risk_per_share},
    "r_value": round(r_value, 2),
    "suggested_shares": shares,
    "suggested_value": round(${args.price} * shares, 2),
    "max_risk": round(risk_total, 2),
    "max_risk_pct": round(risk_pct, 2),
    "kelly_fraction": acct.kelly_fraction,
}, ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}

export async function handleGetRiskReport(): Promise<string> {
  const script = `
import sys, json, subprocess
sys.path.insert(0, '.')
r = subprocess.run(['python3', 'ammo_risk.py'], capture_output=True, text=True, timeout=30)
print(json.dumps({"report": r.stdout[:2000]}, ensure_ascii=False))
  `;
  return JSON.stringify(await pyCall(script), null, 2);
}
