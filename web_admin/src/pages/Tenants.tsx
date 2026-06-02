import React from 'react';
import { Card, Table, Tag, Button, Space, message } from 'antd';
import { PlusOutlined, ReloadOutlined } from '@ant-design/icons';

const Tenants: React.FC = () => {
  const tiers = [
    { id: 'default', name: '安幕诺家族', tier: 'internal', active: true, created: '2026-01-01', expires: '2099-12-31' },
    { id: 'demo-free', name: '体验用户', tier: 'free', active: true, created: '2026-05-01', expires: '2027-05-01' },
  ];

  return (
    <div>
      <h2 style={{ color: '#e2e8f0', marginBottom: 24 }}>🏢 多租户管理</h2>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" icon={<PlusOutlined />}>创建租户</Button>
        <Button icon={<ReloadOutlined />}>刷新</Button>
      </Space>
      <Table dataSource={tiers} rowKey="id"
        columns={[
          { title: '租户ID', dataIndex: 'id', width: 120 },
          { title: '名称', dataIndex: 'name' },
          { title: '等级', dataIndex: 'tier', render: (v: string) => {
            const colors: Record<string,string> = {free:'blue',pro:'purple',family:'gold',internal:'red'};
            return <Tag color={colors[v]||'default'}>{v.toUpperCase()}</Tag>;
          }},
          { title: '状态', dataIndex: 'active', render: (v: boolean) => <Tag color={v?'green':'red'}>{v?'✅ 启用':'❌ 停用'}</Tag> },
          { title: '创建', dataIndex: 'created' },
          { title: '过期', dataIndex: 'expires' },
          { title: '操作', render: () => <Space><Button size="small">管理</Button><Button size="small" danger>停用</Button></Space> },
        ]}
      />
    </div>
  );
};
export default Tenants;
