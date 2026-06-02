/**
 * 统计页面 — 交易统计 / 盈亏曲线 / 各标的业绩
 */
import { useState, useEffect } from "react";
import { View, Text, ScrollView, Canvas } from "@tarojs/components";
import XiaohongAPI from "../../services/xiaohong-api";
import type { TradeStats, TradeItem } from "../../services/xiaohong-api";

const API_BASE = "https://api.xiaohong.family";
const api = new XiaohongAPI({ baseUrl: API_BASE, apiKey: "xh-internal-dev" });

export default function Stats() {
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [trades, setTrades] = useState<TradeItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [s, t] = await Promise.all([
          api.getStats(),
          api.getTrades(undefined, undefined, 50),
        ]);
        setStats(s);
        setTrades(t);
      } catch (e) {
        console.error(e);
      }
      setLoading(false);
    })();
  }, []);

  if (loading) {
    return (
      <View className="page">
        <View className="header"><Text className="title">📈 交易统计</Text></View>
        <View className="card empty"><Text>加载中...</Text></View>
      </View>
    );
  }

  return (
    <ScrollView className="page">
      <View className="header">
        <Text className="title">📈 交易统计</Text>
        <Text className="subtitle">
          {stats ? `${stats.total_trades} 笔交易 · 胜率 ${stats.win_rate}%` : "暂无数据"}
        </Text>
      </View>

      {/* Key Metrics */}
      {stats && (
        <>
          <View className="metrics-grid">
            {[
              ["总盈亏", `¥${stats.total_pnl.toLocaleString()}`, stats.total_pnl >= 0 ? "up" : "down"],
              ["胜率", `${stats.win_rate}%`, stats.win_rate >= 50 ? "up" : "down"],
              ["盈亏比", String(stats.profit_factor), stats.profit_factor >= 1.5 ? "up" : "down"],
              ["平均盈利", `¥${stats.avg_win.toLocaleString()}`, "up"],
              ["平均亏损", `¥${stats.avg_loss.toLocaleString()}`, "down"],
              ["组合净值", `¥${stats.portfolio_value.toLocaleString()}`, "neutral"],
            ].map(([label, value, cls], i) => (
              <View key={i} className={`metric-item ${cls}`}>
                <Text className="metric-label">{label}</Text>
                <Text className="metric-value">{value}</Text>
              </View>
            ))}
          </View>

          {/* Symbol Performance */}
          {stats.symbol_stats.length > 0 && (
            <View className="card">
              <Text className="card-title">🏷️ 各标的业绩</Text>
              {stats.symbol_stats.map((s, i) => (
                <View key={i} className="symbol-row">
                  <Text className="symbol-code">{s.symbol}</Text>
                  <Text className="symbol-trades">{s.trades}笔</Text>
                  <Text className={`symbol-pnl ${s.total_pnl >= 0 ? "up" : "down"}`}>
                    ¥{s.total_pnl.toLocaleString()}
                  </Text>
                </View>
              ))}
            </View>
          )}
        </>
      )}

      {/* Recent Trades */}
      <View className="card">
        <Text className="card-title">📝 最近交易</Text>
        {trades.slice(0, 10).map((t, i) => (
          <View key={i} className="trade-row">
            <View className="trade-left">
              <Text className={`trade-side ${t.side === "BUY" ? "buy" : "sell"}`}>
                {t.side === "BUY" ? "买入" : "卖出"}
              </Text>
              <Text className="trade-symbol">{t.symbol} {t.name}</Text>
            </View>
            <View className="trade-right">
              <Text className="trade-detail">{t.quantity}股 @ ¥{t.price}</Text>
              {t.side === "SELL" && (
                <Text className={`trade-pnl ${t.pnl >= 0 ? "up" : "down"}`}>
                  ¥{t.pnl.toLocaleString()}
                </Text>
              )}
            </View>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}
