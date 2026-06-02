import React, { useEffect, useState } from 'react';
import { Card, Table, Tag, Spin } from 'antd';

const API_BASE = '/api';

const TradeLog: React.FC = () => {
  const [trades, setTrades] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { fetch(`${API_BASE}/log/trades?limit=100`).then(r => r.json()).then(d => { setTrades(d); setLoading(false); }); }, []);
  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div>
      <h2 style={{ color: '#e2e8f0', marginBottom: 24 }}>📜 交易日志</h2>
      <Table dataSource={trades} rowKey="trade_id" size="small"
        columns={[
          {title:'时间',dataIndex:'timestamp',width:180,render:(v:string)=>v?.slice(0,19)},
          {title:'代码',dataIndex:'symbol',width:80},
          {title:'名称',dataIndex:'name',width:80},
          {title:'方向',dataIndex:'side',width:60,render:(v:string)=><Tag color={v==='BUY'?'green':'red'}>{v==='BUY'?'买入':'卖出'}</Tag>},
          {title:'价格',dataIndex:'price',width:80,render:(v:number)=>`¥${v}`},
          {title:'数量',dataIndex:'quantity',width:60},
          {title:'金额',dataIndex:'value',width:100,render:(v:number)=>`¥${v.toLocaleString()}`},
          {title:'策略',dataIndex:'strategy',width:80},
          {title:'盈亏',dataIndex:'pnl',width:100,render:(v:number,r:any)=>r.side==='SELL'?<span style={{color:v>=0?'#22c55e':'#ef4444'}}>¥{v.toLocaleString()}</span>:'—'},
          {title:'理由',dataIndex:'reason',ellipsis:true},
        ]}
      />
    </div>
  );
};
export default TradeLog;
