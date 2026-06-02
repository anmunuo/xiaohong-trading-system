/**
 * 仪表盘页面 — 核心指标总览
 */
import React, { useEffect, useState } from 'react';
import { Card, Col, Row, Statistic, Table, Spin, Tag, Space } from 'antd';
import {
  ArrowUpOutlined, ArrowDownOutlined,
  DollarOutlined, TrophyOutlined,
  RiseOutlined, FallOutlined,
} from '@ant-design/icons';

const API_BASE = '/api';

interface Stats {
  total_trades: number; wins: number; losses: number;
  win_rate: number; total_pnl: number; avg_win: number;
  avg_loss: number; profit_factor: number; portfolio_value: number;
}

interface Position {
  symbol: string; name: string; quantity: number;
  avg_cost: number; current_price: number; market_value: number;
  unrealized_pnl: number; pnl_pct: number;
}

const Dashboard: React.FC = () => {
  const [stats, setStats] = useState<Stats | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      const [s, p] = await Promise.all([
        fetch(`${API_BASE}/log/stats`).then(r => r.json()),
        fetch(`${API_BASE}/trade/positions`).then(r => r.json()),
      ]);
      setStats(s);
      setPositions(p.positions || []);
      setLoading(false);
    })();
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div>
      <h2 style={{ color: '#e2e8f0', marginBottom: 24 }}>📊 交易仪表盘</h2>

      {/* Key Metrics */}
      <Row gutter={[16, 16]}>
        <Col span={6}>
          <Card><Statistic title="总净值" value={stats?.portfolio_value || 0} prefix="¥" precision={0} /></Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic
              title="总盈亏" value={stats?.total_pnl || 0} prefix="¥" precision={0}
              valueStyle={{ color: (stats?.total_pnl || 0) >= 0 ? '#22c55e' : '#ef4444' }}
              prefix={stats?.total_pnl && stats.total_pnl >= 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
            />
          </Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="胜率" value={stats?.win_rate || 0} suffix="%" precision={1} prefix={<TrophyOutlined />} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="盈亏比" value={stats?.profit_factor || 0} precision={2} /></Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col span={6}>
          <Card><Statistic title="总交易" value={stats?.total_trades || 0} suffix="笔" /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="平均盈利" value={stats?.avg_win || 0} prefix="¥" precision={0} valueStyle={{ color: '#22c55e' }} /></Card>
        </Col>
        <Col span={6}>
          <Card><Statistic title="平均亏损" value={stats?.avg_loss || 0} prefix="¥" precision={0} valueStyle={{ color: '#ef4444' }} /></Card>
        </Col>
        <Col span={6}>
          <Card>
            <Statistic title="赢/输" value={`${stats?.wins || 0} / ${stats?.losses || 0}`}
              prefix={stats && stats.wins > stats.losses ? <RiseOutlined /> : <FallOutlined />}
            />
          </Card>
        </Col>
      </Row>

      {/* Positions Table */}
      <Card title="📋 当前持仓" style={{ marginTop: 24 }}>
        <Table
          dataSource={positions}
          rowKey="symbol"
          pagination={false}
          columns={[
            { title: '代码', dataIndex: 'symbol', width: 80 },
            { title: '名称', dataIndex: 'name', width: 100 },
            { title: '数量', dataIndex: 'quantity', render: (v: number) => `${v} 股` },
            { title: '成本', dataIndex: 'avg_cost', render: (v: number) => `¥${v.toFixed(2)}` },
            { title: '现价', dataIndex: 'current_price', render: (v: number) => `¥${v.toFixed(2)}` },
            { title: '市值', dataIndex: 'market_value', render: (v: number) => `¥${v.toLocaleString()}` },
            {
              title: '盈亏', dataIndex: 'unrealized_pnl',
              render: (v: number) => (
                <Tag color={v >= 0 ? 'green' : 'red'}>
                  {v >= 0 ? '+' : ''}¥{v.toLocaleString()}
                </Tag>
              ),
            },
            {
              title: '盈亏%', dataIndex: 'pnl_pct',
              render: (v: number) => (
                <span style={{ color: v >= 0 ? '#22c55e' : '#ef4444' }}>
                  {v >= 0 ? '+' : ''}{v.toFixed(2)}%
                </span>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
};

export default Dashboard;
