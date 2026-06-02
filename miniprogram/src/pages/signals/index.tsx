/**
 * 交易信号页 — 策略推荐 / 星级评级 / 一键下单预览
 */
import { useState, useEffect } from "react";
import { View, Text, ScrollView } from "@tarojs/components";
import Taro from "@tarojs/taro";
import XiaohongAPI from "../../services/xiaohong-api";
import type { StrategySignal, StrategyListItem } from "../../services/xiaohong-api";

const API_BASE = "https://api.xiaohong.family";
const api = new XiaohongAPI({ baseUrl: API_BASE, apiKey: "xh-internal-dev" });

export default function Signals() {
  const [signals, setSignals] = useState<StrategySignal[]>([]);
  const [strategies, setStrategies] = useState<StrategyListItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [sigData, stratData] = await Promise.all([
          api.getSignals(),
          api.listStrategies(),
        ]);
        setSignals(sigData);
        setStrategies(stratData.strategies);
      } catch (e) {
        Taro.showToast({ title: "加载失败", icon: "error" });
      }
      setLoading(false);
    })();
  }, []);

  const severityColor = (s: string) => {
    switch (s) {
      case "critical": return "#ef4444";
      case "warning": return "#f59e0b";
      case "info": return "#3b82f6";
      default: return "#22c55e";
    }
  };

  const severityLabel = (s: string) => {
    switch (s) {
      case "critical": return "🔴 紧急";
      case "warning": return "🟡 警告";
      case "info": return "🔵 信息";
      default: return "🟢 正常";
    }
  };

  return (
    <ScrollView className="page">
      <View className="header">
        <Text className="title">🧠 策略信号</Text>
        <Text className="subtitle">
          {loading ? "加载中..." : `${signals.length} 个信号 · ${strategies.length} 策略可用`}
        </Text>
      </View>

      {/* Signals List */}
      {signals.length > 0 ? (
        signals.map((sig, i) => (
          <View key={i} className="card signal-card" style={{ borderLeftColor: severityColor(sig.severity) }}>
            <View className="signal-header">
              <Text className="signal-symbol">{sig.symbol}</Text>
              <Text className="signal-severity" style={{ color: severityColor(sig.severity) }}>
                {severityLabel(sig.severity)}
              </Text>
            </View>
            <Text className="signal-action">{sig.action}</Text>
            <Text className="signal-reason">{sig.reason}</Text>
          </View>
        ))
      ) : (
        <View className="card empty">
          <Text>📭 暂无交易信号</Text>
          <Text className="sub">策略引擎未检测到符合条件的买卖点</Text>
        </View>
      )}

      {/* Strategy Catalog */}
      <View className="card">
        <Text className="card-title">📚 可用策略</Text>
        {strategies.map((s, i) => (
          <View key={i} className="strategy-item">
            <View className="strategy-left">
              <Text className="strategy-id">{s.id}</Text>
              <Text className="strategy-name">{s.name}</Text>
            </View>
            <Text className={`strategy-status ${s.status === "planned" ? "planned" : "active"}`}>
              {s.status === "planned" ? "🔜 待上线" : "✅"}
            </Text>
          </View>
        ))}
      </View>
    </ScrollView>
  );
}
