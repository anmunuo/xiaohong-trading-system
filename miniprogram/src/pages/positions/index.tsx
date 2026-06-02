/**
 * 持仓页面 — 当前持仓列表 / 盈亏明细 / 止损监控
 */
import { useState, useEffect } from "react";
import { View, Text, ScrollView } from "@tarojs/components";
import Taro from "@tarojs/taro";
import XiaohongAPI from "../../services/xiaohong-api";
import type { AccountResponse, PositionItem } from "../../services/xiaohong-api";

const API_BASE = "https://api.xiaohong.family";
const api = new XiaohongAPI({ baseUrl: API_BASE, apiKey: "xh-internal-dev" });

export default function Positions() {
  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const a = await api.getPositions();
      setAccount(a);
    } catch (e) {
      Taro.showToast({ title: "加载失败", icon: "error" });
    }
    setLoading(false);
  };

  useEffect(() => { fetchData(); }, []);

  const totalPnl = account?.positions?.reduce((s, p) => s + (p.unrealized_pnl || 0), 0) ?? 0;
  const totalReturn = account ? ((account.total_value - 850000) / 850000 * 100) : 0;

  return (
    <ScrollView className="page" refresherEnabled onRefresherRefresh={fetchData}>
      <View className="header">
        <Text className="title">📋 持仓管理</Text>
        <Text className="subtitle">总净值 ¥{account?.total_value?.toLocaleString() ?? "--"}</Text>
      </View>

      {/* Summary */}
      <View className="row">
        <View className="card mini">
          <Text className="label">可用资金</Text>
          <Text className="value">¥{account?.available_cash?.toLocaleString() ?? "--"}</Text>
        </View>
        <View className="card mini">
          <Text className="label">持仓盈亏</Text>
          <Text className={`value ${totalPnl >= 0 ? "up" : "down"}`}>
            {totalPnl >= 0 ? "+" : ""}¥{totalPnl.toLocaleString()}
          </Text>
        </View>
      </View>

      {/* Position List */}
      {account?.positions && account.positions.length > 0 ? (
        account.positions.map((p, i) => (
          <View key={i} className="card position-card">
            <View className="position-header">
              <View>
                <Text className="position-symbol">{p.symbol}</Text>
                <Text className="position-name">{p.name}</Text>
              </View>
              <Text className={`position-pnl ${p.unrealized_pnl >= 0 ? "up" : "down"}`}>
                ¥{p.unrealized_pnl.toLocaleString()}
              </Text>
            </View>
            <View className="position-detail">
              <View className="detail-item">
                <Text className="detail-label">数量</Text>
                <Text className="detail-value">{p.quantity} 股</Text>
              </View>
              <View className="detail-item">
                <Text className="detail-label">成本</Text>
                <Text className="detail-value">¥{p.avg_cost.toFixed(2)}</Text>
              </View>
              <View className="detail-item">
                <Text className="detail-label">现价</Text>
                <Text className="detail-value">¥{p.current_price.toFixed(2)}</Text>
              </View>
              <View className="detail-item">
                <Text className="detail-label">市值</Text>
                <Text className="detail-value">¥{p.market_value.toLocaleString()}</Text>
              </View>
            </View>
            {/* PnL Bar */}
            <View className="pnl-bar">
              <View className="pnl-bar-bg">
                <View
                  className={`pnl-bar-fill ${p.pnl_pct >= 0 ? "up" : "down"}`}
                  style={{ width: `${Math.min(Math.abs(p.pnl_pct) * 3, 100)}%` }}
                />
              </View>
              <Text className={`pnl-pct ${p.pnl_pct >= 0 ? "up" : "down"}`}>
                {p.pnl_pct >= 0 ? "+" : ""}{p.pnl_pct.toFixed(2)}%
              </Text>
            </View>
          </View>
        ))
      ) : (
        <View className="card empty">
          <Text>📭 暂无持仓</Text>
          <Text className="sub">资金 ¥{account?.available_cash?.toLocaleString() ?? "0"} 可用</Text>
        </View>
      )}
    </ScrollView>
  );
}
