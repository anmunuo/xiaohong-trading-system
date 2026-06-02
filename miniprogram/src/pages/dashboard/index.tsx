/**
 * 安幕诺家族 · 小红 🌹 仪表盘页面
 * 小程序首页 — 实时净值 / 盈亏 / 指数 / 快捷操作
 */
import { useState, useEffect, useCallback } from "react";
import { View, Text, ScrollView } from "@tarojs/components";
import Taro from "@tarojs/taro";
import XiaohongAPI from "../../services/xiaohong-api";
import type { TradeStats, IndexData, AccountResponse } from "../../services/xiaohong-api";

// 配置（生产环境替换为实际地址）
const API_BASE = "https://api.xiaohong.family";
const API_KEY = "xh-internal-dev";

const api = new XiaohongAPI({ baseUrl: API_BASE, apiKey: API_KEY });

export default function Dashboard() {
  const [stats, setStats] = useState<TradeStats | null>(null);
  const [index, setIndex] = useState<IndexData | null>(null);
  const [account, setAccount] = useState<AccountResponse | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchData = useCallback(async () => {
    setRefreshing(true);
    try {
      const [s, i, a] = await Promise.all([
        api.getStats(),
        api.getIndex(),
        api.getPositions(),
      ]);
      setStats(s);
      setIndex(i);
      setAccount(a);
    } catch (e) {
      Taro.showToast({ title: "加载失败", icon: "error" });
    }
    setRefreshing(false);
  }, []);

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 30000);
    return () => clearInterval(timer);
  }, [fetchData]);

  const totalPnl = account?.positions?.reduce((sum, p) => sum + (p.unrealized_pnl || 0), 0) ?? 0;
  const nav = account?.total_value ?? 0;

  return (
    <ScrollView className="page" refresherEnabled onRefresherRefresh={fetchData}>
      {/* Header */}
      <View className="header">
        <Text className="title">🏰 安幕诺家族</Text>
        <Text className="subtitle">小红 🌹 交易助手</Text>
      </View>

      {/* NAV Card */}
      <View className="card hero">
        <Text className="label">总净值</Text>
        <Text className="value">¥{(nav || 0).toLocaleString()}</Text>
        <Text className={`change ${totalPnl >= 0 ? "up" : "down"}`}>
          {totalPnl >= 0 ? "+" : ""}¥{totalPnl.toLocaleString()}
        </Text>
      </View>

      {/* Stats Row */}
      <View className="row">
        <View className="card mini">
          <Text className="label">胜率</Text>
          <Text className="value">{stats?.win_rate ?? "--"}%</Text>
          <Text className="sub">{stats ? `赢${stats.wins}/输${stats.losses}` : ""}</Text>
        </View>
        <View className="card mini">
          <Text className="label">盈亏比</Text>
          <Text className="value">{stats?.profit_factor ?? "--"}</Text>
          <Text className="sub">总盈亏 ¥{(stats?.total_pnl ?? 0).toLocaleString()}</Text>
        </View>
      </View>

      {/* Index Ticker */}
      {index && (
        <View className="card">
          <Text className="card-title">📊 市场指数</Text>
          <View className="ticker-row">
            {[
              ["上证", index.asia?.shanghai],
              ["深证", index.asia?.shenzhen],
              ["恒生", index.asia?.hang_seng],
            ].map(([name, data]) => (
              <View key={name as string} className="ticker-item">
                <Text className="ticker-name">{name}</Text>
                <Text className="ticker-val">{data?.[0]?.toLocaleString() ?? "--"}</Text>
                <Text className={`ticker-chg ${(data?.[1] ?? 0) >= 0 ? "up" : "down"}`}>
                  {(data?.[1] ?? 0).toFixed(2)}%
                </Text>
              </View>
            ))}
          </View>
        </View>
      )}

      {/* Quick Actions */}
      <View className="card">
        <Text className="card-title">⚡ 快捷操作</Text>
        <View className="actions">
          <View className="btn" onClick={() => Taro.switchTab({ url: "/pages/signals/index" })}>
            🧠 交易信号
          </View>
          <View className="btn" onClick={() => Taro.switchTab({ url: "/pages/positions/index" })}>
            📋 持仓列表
          </View>
          <View className="btn" onClick={() => Taro.switchTab({ url: "/pages/stats/index" })}>
            📈 交易统计
          </View>
        </View>
      </View>

      <View className="footer">
        <Text>数据刷新: 30秒 · API v2.0</Text>
      </View>
    </ScrollView>
  );
}
