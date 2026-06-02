/**
 * 设置页面 — API配置 / 策略选择 / 通知偏好 / 关于
 */
import { useState, useEffect } from "react";
import { View, Text, Switch, Button } from "@tarojs/components";
import Taro from "@tarojs/taro";

export default function Settings() {
  const [apiKey, setApiKey] = useState("xh-internal-dev");
  const [apiUrl, setApiUrl] = useState("https://api.xiaohong.family");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [notifySignal, setNotifySignal] = useState(true);
  const [notifyAlert, setNotifyAlert] = useState(true);
  const [paperMode, setPaperMode] = useState(true);

  useEffect(() => {
    // 从本地存储加载
    const stored = Taro.getStorageSync("settings");
    if (stored) {
      if (stored.apiKey) setApiKey(stored.apiKey);
      if (stored.apiUrl) setApiUrl(stored.apiUrl);
      if (stored.autoRefresh !== undefined) setAutoRefresh(stored.autoRefresh);
    }
  }, []);

  const saveSettings = () => {
    Taro.setStorageSync("settings", {
      apiKey, apiUrl, autoRefresh,
      notifySignal, notifyAlert, paperMode,
    });
    Taro.showToast({ title: "已保存", icon: "success" });
  };

  return (
    <ScrollView className="page">
      <View className="header">
        <Text className="title">⚙️ 设置</Text>
      </View>

      {/* API Config */}
      <View className="card">
        <Text className="card-title">🔌 API 连接</Text>
        
        <View className="setting-row">
          <Text className="setting-label">API 地址</Text>
          <View className="setting-input-wrap">
            <Text className="setting-value">{apiUrl}</Text>
          </View>
        </View>

        <View className="setting-row">
          <Text className="setting-label">API Key</Text>
          <View className="setting-input-wrap">
            <Text className="setting-value">{apiKey.slice(0, 12)}***</Text>
          </View>
        </View>
      </View>

      {/* Preferences */}
      <View className="card">
        <Text className="card-title">🎛️ 偏好设置</Text>
        
        <View className="setting-row">
          <Text className="setting-label">自动刷新</Text>
          <Switch checked={autoRefresh} onChange={e => setAutoRefresh(e.detail.value)} color="#f43f5e" />
        </View>

        <View className="setting-row">
          <Text className="setting-label">信号通知</Text>
          <Switch checked={notifySignal} onChange={e => setNotifySignal(e.detail.value)} color="#f43f5e" />
        </View>

        <View className="setting-row">
          <Text className="setting-label">告警通知</Text>
          <Switch checked={notifyAlert} onChange={e => setNotifyAlert(e.detail.value)} color="#f43f5e" />
        </View>

        <View className="setting-row">
          <Text className="setting-label">模拟交易</Text>
          <Switch checked={paperMode} onChange={e => setPaperMode(e.detail.value)} color="#f43f5e" />
        </View>
      </View>

      {/* About */}
      <View className="card">
        <Text className="card-title">ℹ️ 关于</Text>
        <View className="about-info">
          <Text className="about-line">安幕诺家族 · 小红 🌹</Text>
          <Text className="about-line">AI 股票交易辅助系统 v2.0</Text>
          <Text className="about-line">TradingSkill 风格</Text>
          <Text className="about-line">MCP Gateway + REST API + 多策略</Text>
        </View>
      </View>

      <View className="save-btn-wrap">
        <Button className="save-btn" onClick={saveSettings}>
          💾 保存设置
        </Button>
      </View>
    </ScrollView>
  );
}
