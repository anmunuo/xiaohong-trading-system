import React, { useEffect, useState } from 'react';
import { Card, Table, Tag, Spin, Statistic, Row, Col } from 'antd';

const API_BASE = '/api';
interface Pos { symbol: string; name: string; quantity: number; avg_cost: number; current_price: number; market_value: number; unrealized_pnl: number; pnl_pct: number; }

const Positions: React.FC = () => {
  const [account, setAccount] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => { fetch(`${API_BASE}/trade/positions`).then(r => r.json()).then(d => { setAccount(d); setLoading(false); }); }, []);
  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  const totalPnl = (account?.positions || []).reduce((s: number, p: Pos) => s + (p.unrealized_pnl || 0), 0);

  return (
    <div>
      <h2 style={{ color: '#e2e8f0', marginBottom: 24 }}>📋 持仓监控</h2>
      <Row gutter={[16,16]} style={{marginBottom:24}}>
        <Col span={8}><Card><Statistic title="总净值" value={account?.total_value || 0} prefix="¥" precision={0} /></Card></Col>
        <Col span={8}><Card><Statistic title="可用资金" value={account?.available_cash || 0} prefix="¥" precision={0} /></Card></Col>
        <Col span={8}><Card><Statistic title="浮动盈亏" value={totalPnl} prefix="¥" precision={0} valueStyle={{color: totalPnl>=0?'#22c55e':'#ef4444'}} /></Card></Col>
      </Row>
      <Table dataSource={account?.positions || []} rowKey="symbol" columns={[
        {title:'代码',dataIndex:'symbol',width:80},{title:'名称',dataIndex:'name'},
        {title:'数量',dataIndex:'quantity',render:(v:number)=>`${v}股`},
        {title:'成本',dataIndex:'avg_cost',render:(v:number)=>`¥${v.toFixed(2)}`},
        {title:'现价',dataIndex:'current_price',render:(v:number)=>`¥${v.toFixed(2)}`},
        {title:'市值',dataIndex:'market_value',render:(v:number)=>`¥${v.toLocaleString()}`},
        {title:'盈亏',dataIndex:'unrealized_pnl',render:(v:number)=><Tag color={v>=0?'green':'red'}>{v>=0?'+':''}¥{v.toLocaleString()}</Tag>},
        {title:'盈亏%',dataIndex:'pnl_pct',render:(v:number)=><span style={{color:v>=0?'#22c55e':'#ef4444'}}>{v>=0?'+':''}{v.toFixed(2)}%</span>},
      ]} />
    </div>
  );
};
export default Positions;
