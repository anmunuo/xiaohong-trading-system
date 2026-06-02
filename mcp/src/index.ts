#!/usr/bin/env node
/**
 * 小红 MCP Gateway — 主入口
 * 
 * 启动方式:
 *   npm run dev     → 开发模式（tsx）
 *   npm run start   → 生产模式（node dist/）
 * 
 * 用法:
 *   node dist/index.js list                    → 列出全部工具
 *   node dist/index.js call <tool> [json_args] → 调用工具
 */
import { listTools, listToolsByCategory, callTool, getToolDefinition } from "./client.js";

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  switch (command) {
    case "list": {
      const category = args[1] as any;
      const tools = category
        ? listToolsByCategory(category)
        : listTools();

      console.log(`\n🔌 小红 MCP Gateway — ${tools.length} 工具已注册\n`);
      
      const categories = ["market", "strategy", "execution", "risk", "logging"];
      const icons: Record<string, string> = {
        market: "📊", strategy: "🧠", execution: "⚡", risk: "🛡️", logging: "📝",
      };

      if (!category) {
        for (const cat of categories) {
          const catTools = listToolsByCategory(cat as any);
          if (catTools.length > 0) {
            console.log(`${icons[cat]} ${cat.toUpperCase()} (${catTools.length})`);
            for (const t of catTools) {
              console.log(`   ${t.name}: ${t.description}`);
            }
            console.log();
          }
        }
      } else {
        for (const t of tools) {
          console.log(`${t.name}: ${t.description}`);
        }
      }
      break;
    }

    case "call": {
      const toolName = args[1];
      if (!toolName) {
        console.error("用法: call <tool_name> [json_args]");
        process.exit(1);
      }

      const def = getToolDefinition(toolName);
      if (!def) {
        console.error(`❌ 未找到工具: ${toolName}`);
        console.error(`   可用: ${listTools().map(t => t.name).join(", ")}`);
        process.exit(1);
      }

      let toolArgs = {};
      if (args[2]) {
        try {
          toolArgs = JSON.parse(args[2]);
        } catch {
          console.error("❌ JSON 解析失败");
          process.exit(1);
        }
      }

      console.log(`🔧 调用: ${toolName}`);
      console.log(`📋 描述: ${def.description}`);
      console.log(`📥 参数: ${JSON.stringify(toolArgs)}`);
      console.log("---");

      try {
        const result = await callTool(toolName, toolArgs);
        console.log(result);
      } catch (err: any) {
        console.error(`❌ 调用失败: ${err.message}`);
        process.exit(1);
      }
      break;
    }

    case "help":
    default: {
      console.log(`
╔══════════════════════════════════════════════════════╗
║    安幕诺家族 · 小红 🌹 MCP Gateway v2.0              ║
║    TradingSkill 风格 AI 交易工具协议层                 ║
╠══════════════════════════════════════════════════════╣
║                                                      ║
║  用法:                                                ║
║    node dist/index.js list             列出全部工具    ║
║    node dist/index.js list market      列出某类工具    ║
║    node dist/index.js call <tool> []   调用工具        ║
║                                                      ║
║  分类:                                                ║
║    📊 market    行情数据 (5 tools)                    ║
║    🧠 strategy  策略引擎 (4 tools)                    ║
║    ⚡ execution 执行服务 (4 tools)                    ║
║    🛡️ risk      风控服务 (4 tools)                    ║
║    📝 logging   日志服务 (4 tools)                    ║
║                                                      ║
║  示例:                                                ║
║    node dist/index.js call get_index_data             ║
║    node dist/index.js call place_order '{"symbol":"600519","side":"BUY","price":1800,"quantity":100}' ║
║    node dist/index.js call get_trade_stats            ║
║                                                      ║
╚══════════════════════════════════════════════════════╝
      `);
      break;
    }
  }
}

main().catch(console.error);
