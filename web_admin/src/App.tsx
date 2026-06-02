/**
 * 小红 Web 管理后台 — 主入口
 * React + Ant Design + React Router
 */
import React from 'react';
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { ConfigProvider, Layout, Menu, theme } from 'antd';
import {
  DashboardOutlined,
  LineChartOutlined,
  WalletOutlined,
  BarChartOutlined,
  SettingOutlined,
  ApiOutlined,
} from '@ant-design/icons';
import zhCN from 'antd/locale/zh_CN';
import Dashboard from './pages/Dashboard';
import Strategies from './pages/Strategies';
import Positions from './pages/Positions';
import TradeLog from './pages/TradeLog';
import Tenants from './pages/Tenants';

const { Header, Sider, Content } = Layout;

const menuItems = [
  { key: '/', icon: <DashboardOutlined />, label: <Link to="/">仪表盘</Link> },
  { key: '/strategies', icon: <LineChartOutlined />, label: <Link to="/strategies">策略管理</Link> },
  { key: '/positions', icon: <WalletOutlined />, label: <Link to="/positions">持仓监控</Link> },
  { key: '/trades', icon: <BarChartOutlined />, label: <Link to="/trades">交易日志</Link> },
  { key: '/tenants', icon: <ApiOutlined />, label: <Link to="/tenants">多租户</Link> },
  { key: '/settings', icon: <SettingOutlined />, label: <Link to="/settings">系统设置</Link> },
];

const AppLayout: React.FC = () => {
  const location = useLocation();

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        theme="dark"
        style={{ background: '#0f172a' }}
        width={220}
      >
        <div style={{ padding: '20px 16px', borderBottom: '1px solid #1e293b' }}>
          <h1 style={{ color: '#fff', fontSize: 18, margin: 0 }}>
            🏰 安幕诺家族
          </h1>
          <p style={{ color: '#f43f5e', fontSize: 13, margin: '4px 0 0' }}>
            小红 🌹 管理后台
          </p>
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          style={{ background: 'transparent', marginTop: 8 }}
        />
      </Sider>
      <Layout>
        <Header style={{ background: '#111827', padding: '0 24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #1e293b' }}>
          <span style={{ color: '#64748b', fontSize: 13 }}>v2.0 — TradingSkill 风格</span>
          <span style={{ color: '#22c55e', fontSize: 13 }}>● 系统正常</span>
        </Header>
        <Content style={{ padding: 24, background: '#0a0e1a', minHeight: 280 }}>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/strategies" element={<Strategies />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/trades" element={<TradeLog />} />
            <Route path="/tenants" element={<Tenants />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
};

const App: React.FC = () => (
  <ConfigProvider
    locale={zhCN}
    theme={{
      algorithm: theme.darkAlgorithm,
      token: {
        colorPrimary: '#f43f5e',
        colorBgContainer: '#111827',
        colorBorder: '#1e293b',
        borderRadius: 8,
      },
    }}
  >
    <BrowserRouter>
      <AppLayout />
    </BrowserRouter>
  </ConfigProvider>
);

export default App;
