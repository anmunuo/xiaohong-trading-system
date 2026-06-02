import React, { useEffect, useState } from 'react';
import { Card, Table, Tag, Spin } from 'antd';

const API_BASE = '/api';

const Strategies: React.FC = () => {
  const [data, setData] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/strategy/list`).then(r => r.json()).then(d => {
      setData(d.strategies || []);
      setLoading(false);
    });
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div>
      <h2 style={{ color: '#e2e8f0', marginBottom: 24 }}>🧠 策略管理</h2>
      <Table
        dataSource={data}
        rowKey="id"
        columns={[
          { title: 'ID', dataIndex: 'id', width: 120 },
          { title: '名称', dataIndex: 'name', width: 200 },
          { title: '描述', dataIndex: 'desc' },
          {
            title: '状态', dataIndex: 'status', width: 100,
            render: (v: string) => (
              <Tag color={v === 'planned' ? 'orange' : 'green'}>
                {v === 'planned' ? '🔜 待上线' : '✅ 可用'}
              </Tag>
            ),
          },
        ]}
      />
    </div>
  );
};
export default Strategies;
